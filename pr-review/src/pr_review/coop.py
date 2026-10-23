"""Run reviews inside an isolated coop microVM."""

import re
import secrets
import subprocess
from collections.abc import Callable

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
    """Destroy the VM `name`; never raises, so it is safe in a `finally` block."""
    try:
        runner(["coop", "destroy", name], capture_output=True, text=True)
    except Exception:
        pass
