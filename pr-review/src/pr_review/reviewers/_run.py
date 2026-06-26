"""Shared payload-file runner used by CLI-backed reviewers."""
from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Sequence

from pr_review.payload import Payload, parse_payload
from pr_review.review_types.base import ReviewType


def _build_context(*, owner: str, repo: str, number: int, base: str, payload_path: str) -> str:
    return (
        "You are reviewing a GitHub pull request. Context for this run:\n"
        f"- Repository: {owner}/{repo}\n"
        f"- PR number: {number}\n"
        f"- Base ref:  origin/{base}\n"
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
    fd, payload_path = tempfile.mkstemp(prefix="pr-review-payload.", suffix=".json")
    os.close(fd)
    try:
        prompt = build_review_prompt(
            owner=owner, repo=repo, number=number, base=base,
            payload_path=payload_path, review_type=review_type,
        )
        subprocess.run(
            list(cmd_prefix), cwd=workdir, input=prompt, text=True, check=True,
            env=_review_env(workdir),
        )
        with open(payload_path, encoding="utf-8") as f:
            raw = f.read()
        if not raw.strip():
            raise RuntimeError(f"{cmd_prefix[0]} produced an empty payload")
        return parse_payload(raw)
    finally:
        try:
            os.unlink(payload_path)
        except FileNotFoundError:
            pass
