import os
import subprocess
import tempfile

from pr_review.checkout import Checkout, cleanup, clone_pr

BASE_SHA = "17393b97af6589011dbf566e284025891a80da9f"


class FakeRunner:
    def __init__(self, meta_out=f"remove-v2\t{BASE_SHA}\n"):
        self.calls = []
        self.meta_out = meta_out

    def __call__(self, cmd, **kw):
        self.calls.append((list(cmd), kw))
        stdout = self.meta_out if cmd[:2] == ["gh", "api"] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")


def test_clone_pr_builds_expected_commands(tmp_path):
    runner = FakeRunner()
    workdir = str(tmp_path / "repo")
    result = clone_pr("org", "repo", 42, runner=runner, mkdtemp=lambda: workdir)

    assert result == Checkout(workdir=workdir, base=BASE_SHA, base_ref="remove-v2")
    cmds = [c[0] for c in runner.calls]
    # PR metadata is read before the clone, so a bad PR fails fast.
    assert cmds[0] == ["gh", "api", "repos/org/repo/pulls/42",
                       "--jq", "[.base.ref, .base.sha] | @tsv"]
    assert cmds[1] == ["git", "clone", "--filter=blob:none",
                       "https://github.com/org/repo", workdir]
    # refs/pull/N/head survives head-branch deletion; `gh pr checkout` does not.
    assert cmds[2] == ["git", "fetch", "--filter=blob:none", "origin",
                       "+refs/pull/42/head:refs/remotes/origin/pr/42"]
    # the base commit may be unreachable from any surviving branch
    assert cmds[3] == ["git", "fetch", "--filter=blob:none", "origin", BASE_SHA]
    assert cmds[4] == ["git", "checkout", "--detach", "refs/remotes/origin/pr/42"]
    assert len(cmds) == 5
    # every git command after the clone runs inside it
    for call in runner.calls[2:]:
        assert call[1].get("cwd") == workdir


def test_clone_pr_pins_base_to_a_commit_not_a_branch(tmp_path):
    """A merged PR's base branch already contains the head, so `origin/<branch>...HEAD`
    is empty. Pinning to the base commit keeps the three-dot diff correct."""
    runner = FakeRunner()
    result = clone_pr("org", "repo", 42, runner=runner, mkdtemp=lambda: str(tmp_path))

    assert result.base == BASE_SHA
    assert "origin/" not in result.base


def test_clone_pr_rejects_unresolvable_pr_metadata(tmp_path):
    runner = FakeRunner(meta_out="\n")
    try:
        clone_pr("org", "repo", 42, runner=runner, mkdtemp=lambda: str(tmp_path))
    except ValueError as e:
        assert "org/repo#42" in str(e)
    else:
        raise AssertionError("expected ValueError for empty PR metadata")


def test_cleanup_removes_workdir():
    d = tempfile.mkdtemp(prefix="pr-review-test.")
    assert os.path.isdir(d)
    cleanup(Checkout(workdir=d, base=BASE_SHA, base_ref="main"))
    assert not os.path.isdir(d)
