"""Run reviews inside an isolated coop microVM."""

import json
import re
import secrets
import shlex
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from typing import TypeVar

from pr_review.reviewers._run import _feed_stdin, run_cli_json

T = TypeVar("T")

MIN_VCPUS, MAX_VCPUS = 2, 8
MIN_MEM_MIB, MAX_MEM_MIB = 4096, 12288
MEM_PER_JOB_MIB = 1536


def vm_size(job_count: int) -> tuple[int, int]:
    """Return (vcpus, mem_mib) for a VM that runs `job_count` jobs."""
    vcpus = min(max(job_count, MIN_VCPUS), MAX_VCPUS)
    mem_mib = min(max(job_count * MEM_PER_JOB_MIB, MIN_MEM_MIB), MAX_MEM_MIB)
    return vcpus, mem_mib


class CoopUnavailable(Exception):
    """Coop is not ready to run a review; the message names the fix."""


def preflight(*, runner: Callable[..., object] = subprocess.run) -> None:
    """Raise CoopUnavailable unless the coop binary, a template and the proxy are ready."""

    def run(cmd: list[str]):
        return runner(cmd, capture_output=True, text=True)

    try:
        version = run(["coop", "--version"])
    except OSError:
        version = None
    if version is None or version.returncode != 0:
        raise CoopUnavailable("coop is not installed or not working. Run: coop setup")

    images = run(["coop", "images"])
    if images.returncode != 0 or not (images.stdout or "").strip():
        raise CoopUnavailable("coop has no template image. Run: coop setup")

    status = run(["coop", "proxy", "status"])
    proxy = status.stdout or ""
    if status.returncode != 0 or any(
        "anthropic" in line and "off" in line for line in proxy.lower().splitlines()
    ):
        raise CoopUnavailable(
            "the coop Anthropic proxy is off. Run: claude setup-token, "
            "then: coop proxy setup"
        )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def vm_name(owner: str, repo: str, number: int, *, suffix: str | None = None) -> str:
    """Return a VM name safe for coop: `pr-review-<owner>-<repo>-<n>-<suffix>`."""
    suffix = suffix if suffix is not None else secrets.token_hex(2)
    return "-".join(["pr-review", _slug(owner), _slug(repo), str(number), suffix])


def _run_checked(
    cmd: list[str], runner: Callable[..., object], what: str
) -> None:
    """Run a coop command; raise CoopUnavailable with coop's own error text on failure."""
    try:
        result = runner(cmd, capture_output=True, text=True)
    except OSError as e:
        raise CoopUnavailable(
            f"{what} could not run coop ({e}). Run: coop setup"
        ) from e
    if result.returncode != 0:
        detail = (getattr(result, "stderr", "") or "").strip()
        message = f"{what} failed with exit status {result.returncode}"
        raise CoopUnavailable(f"{message}: {detail}" if detail else message)


def create_vm(
    workdir: str,
    name: str,
    *,
    vcpus: int,
    mem: int,
    runner: Callable[..., object] = subprocess.run,
) -> None:
    """Boot a fresh VM named `name` with `workdir` mounted; raise if coop fails."""
    _run_checked(
        [
            "coop", "up", workdir,
            "--name", name,
            "--new-instance",
            "--no-prompt",
            "--vcpus", str(vcpus),
            "--mem", str(mem),
        ],
        runner,
        "coop up",
    )


def install_ssh_alias(
    name: str, *, runner: Callable[..., object] = subprocess.run
) -> None:
    """Install the ssh alias for the VM `name`; raise if coop fails."""
    _run_checked(["coop", "ssh-config", name], runner, "coop ssh-config")


def destroy_vm(name: str, *, runner: Callable[..., object] = subprocess.run) -> None:
    """Destroy the VM `name`; never raises, so it is safe in a `finally` block.

    A failure prints a warning to stderr, because the VM holds credentials.
    """
    try:
        result = runner(["coop", "destroy", name], capture_output=True, text=True)
        if result.returncode == 0:
            return
        detail = (getattr(result, "stderr", "") or "").strip()
        reason = f": {detail}" if detail else ""
    except Exception as e:
        reason = f": {e}"
    print(
        f"pr-review: could not destroy VM {name}; "
        f"remove it manually with: coop destroy {name}{reason}",
        file=sys.stderr,
    )


GUEST_WORKDIR = "/workspace"
GUEST_PAYLOAD_DIR = "/workspace/.git/pr-review"


def _ssh_agent_runner(cmd: Sequence[str], prompt: str, *, workdir: str) -> int:
    """Run an ssh command on pipes of our own, relaying its output; return its status.

    Same private-pipe discipline as `run_agent`: the ssh child must not inherit
    our shared stdout/stderr, or a sibling job's O_NONBLOCK flag leaks into it.
    `workdir` is a host path and is ignored: the agent runs in the guest.
    """
    proc = subprocess.Popen(
        list(cmd), text=True,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    assert proc.stdin is not None and proc.stdout is not None
    feeder = threading.Thread(target=_feed_stdin, args=(proc.stdin, prompt), daemon=True)
    feeder.start()
    try:
        for line in proc.stdout:
            sys.stderr.write(line)
            sys.stderr.flush()
    finally:
        proc.stdout.close()
        feeder.join()
    return proc.wait()


def _ssh_cat(name: str, path: str) -> str:
    """Return the contents of guest file `path`; raise if ssh or cat fails."""
    result = subprocess.run(
        ["ssh", f"coop-{name}", "cat", path], capture_output=True, text=True
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        message = f"ssh cat {path} on coop-{name} failed with exit status {result.returncode}"
        raise RuntimeError(f"{message}: {detail}" if detail else message)
    return result.stdout


class HostExecutor:
    """Run agents as host subprocesses (the default, no isolation)."""

    def guest_path(self, host_path: str) -> str:
        return host_path

    def run_json(
        self,
        command: Sequence[str],
        build_prompt: Callable[[str], str],
        *,
        workdir: str,
        parse: Callable[[str], T] = json.loads,
    ) -> T:
        return run_cli_json(command, build_prompt, workdir=workdir, parse=parse)


class CoopExecutor:
    """Run agents inside the coop VM `name` over ssh."""

    def __init__(
        self,
        name: str,
        *,
        host_workdir: str,
        agent_runner: Callable[..., int] = _ssh_agent_runner,
        cat_runner: Callable[[str, str], str] = _ssh_cat,
    ) -> None:
        self.name = name
        self._host_workdir = host_workdir.rstrip("/")
        self._agent_runner = agent_runner
        self._cat_runner = cat_runner

    def guest_path(self, host_path: str) -> str:
        """Translate a path inside the host clone to the same path in the guest."""
        prefix = self._host_workdir
        if host_path and host_path.startswith(prefix + "/"):
            return GUEST_WORKDIR + host_path[len(prefix):]
        return host_path

    def run_json(
        self,
        command: Sequence[str],
        build_prompt: Callable[[str], str],
        *,
        workdir: str,
        parse: Callable[[str], T] = json.loads,
    ) -> T:
        """Mirror `run_cli_json` over ssh; the guest payload file is the contract."""
        guest_payload = f"{GUEST_PAYLOAD_DIR}/payload.{secrets.token_hex(8)}.json"
        prompt = build_prompt(guest_payload)
        remote = (
            f"mkdir -p {GUEST_PAYLOAD_DIR} && cd {GUEST_WORKDIR} && "
            f"MISE_TRUSTED_CONFIG_PATHS={GUEST_WORKDIR} "
            + shlex.join(command)
        )
        argv = ["ssh", f"coop-{self.name}", remote]
        status = self._agent_runner(argv, prompt, workdir=workdir)
        raw = self._cat_runner(self.name, guest_payload)
        if not raw.strip():
            raise RuntimeError(
                f"{command[0]} produced an empty payload (exit status {status})"
            )
        try:
            return parse(raw)
        except ValueError as e:
            raise ValueError(f"{e} (exit status {status})") from None
