import pytest

from pr_review.context.gather import gather_context

PR = {"number": 7, "title": "Add widgets", "body": "Fixes #3.", "user": {"login": "ada"},
      "head": {"ref": "w", "sha": "s7"},
      "base": {"ref": "main", "repo": {"default_branch": "main", "owner": {"login": "acme"}}}}


class FakeGitHub:
    owner, repo = "acme", "widgets"

    def __init__(self, broken=()):
        self.broken = set(broken)

    def get(self, path):
        if path in self.broken:
            raise RuntimeError(f"{path} failed")
        if path == "pulls/7":
            return PR
        return {"number": 3, "title": "Widgets are missing", "state": "open", "body": "Please add."}

    def get_all(self, path):
        if path.split("?")[0] in self.broken or path in self.broken:
            raise RuntimeError(f"{path} failed")
        return []

    def graphql(self, query, **v):
        raise AssertionError("no native stack here")


def test_gathers_description_issues_and_empty_discussion():
    ctx = gather_context(FakeGitHub(), 7)
    assert (ctx.number, ctx.title, ctx.author) == (7, "Add widgets", "ada")
    assert [i.number for i in ctx.issues] == [3]
    assert ctx.stack == [] and ctx.stack_position is None
    assert ctx.failed == [] and ctx.errors == []


def test_a_failed_part_is_left_out_and_named():
    ctx = gather_context(FakeGitHub(broken={"issues/7/comments", "issues/3"}), 7)
    assert ctx.comments == [] and ctx.threads == []
    assert ctx.issues == []
    assert ctx.failed == ["discussion", "issue #3"]
    assert ctx.errors == ["discussion (issues/7/comments failed)", "issue #3"]


def test_a_failed_stack_is_named_without_its_reason_in_failed():
    ctx = gather_context(FakeGitHub(broken={"pulls"}), 7)
    assert ctx.stack == [] and ctx.failed == ["stack"]
    assert ctx.errors == ["stack (pulls?base=w&state=all failed)"]


def test_a_failed_pull_request_read_raises():
    with pytest.raises(RuntimeError):
        gather_context(FakeGitHub(broken={"pulls/7"}), 7)
