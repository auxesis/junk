"""Shared payload-file runner used by CLI-backed reviewers."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Sequence
from typing import IO

from pr_review.payload import Payload, parse_payload
from pr_review.review_types.base import ReviewType


def _build_context(*, owner: str, repo: str, number: int, base: str, payload_path: str) -> str:
    return (
        "You are reviewing a GitHub pull request. Context for this run:\n"
        f"- Repository: {owner}/{repo}\n"
        f"- PR number: {number}\n"
        f"- Base commit: {base}\n"
        "- HEAD is ALREADY checked out at the exact code to review. Do not switch branches.\n"
        f"- Payload file to write: {payload_path}\n"
    )


def build_review_prompt(
    *, owner: str, repo: str, number: int, base: str,
    payload_path: str, review_type: ReviewType,
) -> str:
    context = _build_context(
        owner=owner, repo=repo, number=number, base=base, payload_path=payload_path
    )
    return context + "\n" + review_type.instructions()


def _review_env(workdir: str) -> dict[str, str]:
    """Environment for the reviewer subprocess.

    Trust any `mise.toml` in the fresh clone so the agent's `mise` commands run.
    A freshly cloned repo's config is never in mise's trust store, so without this
    every `mise exec` the agent runs fails with "not trusted". We grant trust only
    for this clone (no global trust-store mutation); the agent already runs with
    full access to the clone, so this is no extra exposure.
    """
    env = dict(os.environ)
    existing = env.get("MISE_TRUSTED_CONFIG_PATHS")
    env["MISE_TRUSTED_CONFIG_PATHS"] = f"{workdir}:{existing}" if existing else workdir
    return env


def _feed_stdin(stdin: IO[str], prompt: str) -> None:
    try:
        stdin.write(prompt)
    except (BrokenPipeError, ValueError):
        pass  # the agent exited before reading its prompt; `status` will say so
    finally:
        try:
            stdin.close()
        except (BrokenPipeError, ValueError):
            pass


def run_agent(
    cmd: Sequence[str], prompt: str, *, workdir: str, sink: IO[str] | None = None
) -> int:
    """Run an agent CLI on pipes of our own, relaying its output; return its status.

    The agent must NOT inherit our stdout/stderr. Those file descriptors are shared
    with every other job in the run, and `O_NONBLOCK` lives on the open file
    description, not the descriptor: the `claude` CLI sets that flag on the stdio it
    inherits, so a sibling agent's next big write returns EAGAIN. Rust's `std` does
    not retry EAGAIN — `codex` panics with "failed printing to stderr: Resource
    temporarily unavailable (os error 35)" and exits 101, mid-review. Private pipes
    give each agent its own file description, so no job can flip flags under another.
    """
    sink = sink if sink is not None else sys.stderr
    proc = subprocess.Popen(
        list(cmd), cwd=workdir, text=True, env=_review_env(workdir),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    assert proc.stdin is not None and proc.stdout is not None
    feeder = threading.Thread(target=_feed_stdin, args=(proc.stdin, prompt), daemon=True)
    feeder.start()
    try:
        for line in proc.stdout:  # relay live, so a long review still shows progress
            sink.write(line)
            sink.flush()
    finally:
        proc.stdout.close()
        feeder.join()
    return proc.wait()


def run_cli_payload(
    cmd_prefix: Sequence[str],
    build_prompt: Callable[[str], str],
    *,
    workdir: str,
    runner: Callable[..., int] = run_agent,
) -> Payload:
    """Run an agent and read the payload it was told to write.

    The payload file, not the exit status, is the contract: agents have been seen
    finishing a review, writing a valid payload, and only then dying on the way out
    (see `run_agent`). Discarding a complete review over a tail-end crash costs the
    whole job, so a non-zero status is only reported when the payload is missing or
    unusable.
    """
    fd, payload_path = tempfile.mkstemp(prefix="pr-review-payload.", suffix=".json")
    os.close(fd)
    try:
        prompt = build_prompt(payload_path)
        status = runner(cmd_prefix, prompt, workdir=workdir)
        try:
            with open(payload_path, encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            raw = ""
        if not raw.strip():
            raise RuntimeError(
                f"{cmd_prefix[0]} produced an empty payload (exit status {status})"
            )
        try:
            return parse_payload(raw)
        except ValueError as e:
            raise ValueError(f"{e} (exit status {status})") from None
    finally:
        try:
            os.unlink(payload_path)
        except FileNotFoundError:
            pass


def run_cli_reviewer(
    cmd_prefix: Sequence[str],
    *,
    workdir: str,
    owner: str,
    repo: str,
    number: int,
    base: str,
    review_type: ReviewType,
) -> Payload:
    def build(payload_path: str) -> str:
        return build_review_prompt(
            owner=owner, repo=repo, number=number, base=base,
            payload_path=payload_path, review_type=review_type,
        )

    return run_cli_payload(cmd_prefix, build, workdir=workdir)
