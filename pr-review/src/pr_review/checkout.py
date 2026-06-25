"""Clone a PR into an isolated temp dir (blobless), worktree-free."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass
class Checkout:
    workdir: str
    base: str


def _run(cmd: Sequence[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=True, text=True, **kw)


def clone_pr(
    owner: str,
    repo: str,
    number: int,
    *,
    runner: Runner = _run,
    mkdtemp: Callable[[], str] | None = None,
) -> Checkout:
    make = mkdtemp or (lambda: tempfile.mkdtemp(prefix="pr-review."))
    workdir = make()
    url = f"https://github.com/{owner}/{repo}"
    runner(["git", "clone", "--filter=blob:none", url, workdir])
    runner(["gh", "pr", "checkout", str(number)], cwd=workdir)
    res = runner(
        ["gh", "pr", "view", str(number), "--repo", f"{owner}/{repo}",
         "--json", "baseRefName", "-q", ".baseRefName"],
        cwd=workdir,
        capture_output=True,
    )
    base = (res.stdout or "").strip()
    return Checkout(workdir=workdir, base=base)


def cleanup(checkout: Checkout) -> None:
    shutil.rmtree(checkout.workdir, ignore_errors=True)
