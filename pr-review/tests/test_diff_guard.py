import subprocess

from pr_review.diff_guard import changed_paths, guard_off_diff
from pr_review.payload import Comment, Payload, Reply, Source


def _runner(stdout):
    def run(cmd, **kw):
        _runner.cmd = cmd
        _runner.kw = kw
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
    return run


def test_changed_paths_runs_name_only_three_dot_diff_in_the_workdir():
    run = _runner("packages/a/src/x.rs\npackages/b/tests/y.rs\n")
    paths = changed_paths("/clone", "abc123", runner=run)
    assert paths == {"packages/a/src/x.rs", "packages/b/tests/y.rs"}
    assert _runner.cmd == ["git", "diff", "--name-only", "abc123...HEAD"]
    assert _runner.kw["cwd"] == "/clone"


def test_changed_paths_ignores_blank_lines():
    paths = changed_paths("/clone", "abc123", runner=_runner("a.py\n\n"))
    assert paths == {"a.py"}


def test_guard_keeps_comments_whose_path_is_in_the_diff():
    payload = Payload(body="verdict", comments=[Comment("in.rs", 3, "**X**\n\ndetail")])
    kept, dropped = guard_off_diff(payload, {"in.rs"})
    assert [c.path for c in kept.comments] == ["in.rs"]
    assert dropped == []
    assert kept.body == "verdict"


def test_guard_moves_an_off_diff_comment_to_a_body_overflow_bullet():
    off = Comment("nope.rs", 9, "**Finding line**\n\nrest")
    payload = Payload(body="verdict", comments=[Comment("in.rs", 3, "keep"), off])
    kept, dropped = guard_off_diff(payload, {"in.rs"})
    assert [c.path for c in kept.comments] == ["in.rs"]
    assert dropped == [off]
    assert "## Other findings not posted as comments" in kept.body
    assert "- `nope.rs:9` — **Finding line**" in kept.body


def test_guard_appends_to_an_existing_overflow_section():
    body = "verdict\n\n---\n\n## Other findings not posted as comments\n\n- `old.rs:1` — old"
    off = Comment("nope.rs", 9, "**New**")
    payload = Payload(body=body, comments=[off])
    kept, _ = guard_off_diff(payload, {"in.rs"})
    assert kept.body.count("## Other findings not posted as comments") == 1
    assert "- `old.rs:1` — old" in kept.body
    assert "- `nope.rs:9` — **New**" in kept.body


def test_guard_preserves_event_replies_and_comment_sources():
    src = [Source("claude", "opus", "rust")]
    keep = Comment("in.rs", 3, "keep", sources=src)
    reply = Reply(in_reply_to=5, body="r")
    payload = Payload(body="b", comments=[keep], event="REQUEST_CHANGES", replies=[reply])
    kept, _ = guard_off_diff(payload, {"in.rs"})
    assert kept.event == "REQUEST_CHANGES"
    assert kept.replies == [reply]
    assert kept.comments[0].sources == src
