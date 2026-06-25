import subprocess

from pr_review.output import PostMode, decide_mode, post_review, render
from pr_review.payload import Comment, Payload
from pr_review.target import Target


def test_no_post_always_review_only():
    assert decide_mode(yes=False, no_post=True, has_tty=True) is PostMode.REVIEW_ONLY
    assert decide_mode(yes=True, no_post=True, has_tty=True) is PostMode.REVIEW_ONLY


def test_yes_posts():
    assert decide_mode(yes=True, no_post=False, has_tty=False) is PostMode.POST


def test_no_tty_without_yes_is_review_only():
    assert decide_mode(yes=False, no_post=False, has_tty=False) is PostMode.REVIEW_ONLY


def test_tty_without_yes_prompts():
    assert decide_mode(yes=False, no_post=False, has_tty=True) is PostMode.PROMPT


def test_render_includes_body_and_comment_anchors():
    p = Payload(body="summary", comments=[Comment("a.py", 12, "**Gap:** x")])
    out = render(p)
    assert "summary" in out
    assert "a.py:12" in out
    assert "**Gap:** x" in out


def test_post_review_builds_gh_api_command(tmp_path):
    calls = []

    def runner(cmd, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    post_review(Target("org", "repo", 5), Payload(body="b"), runner=runner)
    cmd = calls[0]
    assert cmd[:2] == ["gh", "api"]
    assert cmd[2] == "repos/org/repo/pulls/5/reviews"
    assert "--method" in cmd and "POST" in cmd and "--input" in cmd
