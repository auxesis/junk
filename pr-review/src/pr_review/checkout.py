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
    """Commit to diff against — `git diff <base>...HEAD` is the PR's changes.

    Always a commit, never a branch name: once a PR is merged its base branch
    contains the head, so `origin/<base-branch>...HEAD` diffs to nothing.
    """
    base_ref: str = ""
    """Name of the base branch, for display only."""


def _run(cmd: Sequence[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=True, text=True, **kw)


def _pr_metadata(owner: str, repo: str, number: int, runner: Runner) -> tuple[str, str]:
    res = runner(
        ["gh", "api", f"repos/{owner}/{repo}/pulls/{number}",
         "--jq", "[.base.ref, .base.sha] | @tsv"],
        capture_output=True,
    )
    parts = (res.stdout or "").strip().split("\t")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"could not resolve base ref/sha for {owner}/{repo}#{number}")
    return parts[0], parts[1]


def clone_pr(
    owner: str,
    repo: str,
    number: int,
    *,
    runner: Runner = _run,
    mkdtemp: Callable[[], str] | None = None,
) -> Checkout:
    # Read metadata first so an unresolvable PR fails before we pay for a clone.
    base_ref, base_sha = _pr_metadata(owner, repo, number, runner)

    make = mkdtemp or (lambda: tempfile.mkdtemp(prefix="pr-review."))
    workdir = make()
    url = f"https://github.com/{owner}/{repo}"
    runner(["git", "clone", "--filter=blob:none", url, workdir])

    # `gh pr checkout` fetches the head *branch*, which GitHub deletes on merge.
    # refs/pull/<n>/head is permanent, and also covers fork PRs.
    pr_ref = f"refs/remotes/origin/pr/{number}"
    runner(
        ["git", "fetch", "--filter=blob:none", "origin",
         f"+refs/pull/{number}/head:{pr_ref}"],
        cwd=workdir,
    )
    # The base commit is not always reachable from a surviving branch (deleted or
    # rewritten base branch), so ask for it by sha instead of assuming the clone
    # already has it.
    runner(["git", "fetch", "--filter=blob:none", "origin", base_sha], cwd=workdir)
    runner(["git", "checkout", "--detach", pr_ref], cwd=workdir)

    return Checkout(workdir=workdir, base=base_sha, base_ref=base_ref)


def cleanup(checkout: Checkout) -> None:
    shutil.rmtree(checkout.workdir, ignore_errors=True)
