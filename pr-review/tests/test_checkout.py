import os
import subprocess
import tempfile

from pr_review.checkout import Checkout, cleanup, clone_pr


class FakeRunner:
    def __init__(self, base_out="main\n"):
        self.calls = []
        self.base_out = base_out

    def __call__(self, cmd, **kw):
        self.calls.append((list(cmd), kw))
        stdout = self.base_out if cmd[:3] == ["gh", "pr", "view"] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")


def test_clone_pr_builds_expected_commands(tmp_path):
    runner = FakeRunner()
    workdir = str(tmp_path / "repo")
    result = clone_pr("org", "repo", 42, runner=runner, mkdtemp=lambda: workdir)

    assert result == Checkout(workdir=workdir, base="main")
    cmds = [c[0] for c in runner.calls]
    assert cmds[0] == ["git", "clone", "--filter=blob:none",
                       "https://github.com/org/repo", workdir]
    assert cmds[1] == ["gh", "pr", "checkout", "42"]
    assert cmds[2] == ["gh", "pr", "view", "42", "--repo", "org/repo",
                       "--json", "baseRefName", "-q", ".baseRefName"]
    # gh commands run inside the clone
    assert runner.calls[1][1].get("cwd") == workdir
    assert runner.calls[2][1].get("cwd") == workdir


def test_cleanup_removes_workdir():
    d = tempfile.mkdtemp(prefix="pr-review-test.")
    assert os.path.isdir(d)
    cleanup(Checkout(workdir=d, base="main"))
    assert not os.path.isdir(d)
