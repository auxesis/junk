import json
import os
import subprocess

from pr_review import output
from pr_review.output import PostMode, decide_mode, dispatch, post_review, render
from pr_review.payload import Comment, Payload, Reply
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

    path = post_review(Target("org", "repo", 5), Payload(body="b"), runner=runner)
    try:
        cmd = calls[0]
        assert cmd[:2] == ["gh", "api"]
        assert cmd[2] == "repos/org/repo/pulls/5/reviews"
        assert "--method" in cmd and "POST" in cmd and "--input" in cmd
    finally:
        os.unlink(path)


def test_post_review_leaves_payload_file_on_disk():
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    path = post_review(Target("org", "repo", 5), Payload(body="b"), runner=runner)
    try:
        assert os.path.exists(path)
        assert json.load(open(path))["body"] == "b"
    finally:
        os.unlink(path)


def test_dispatch_keeps_payload_and_exits_nonzero_when_post_fails(capsys):
    def runner(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd)

    code = dispatch(PostMode.POST, Target("org", "repo", 5), Payload(body="b"), runner=runner)
    err = capsys.readouterr().err
    assert code == 1
    # the failure hint must name a real file holding the payload, so an
    # expensive review isn't lost to a tail-end auth/permission error
    path = err.split("--input ", 1)[1].strip()
    try:
        assert os.path.exists(path)
        assert json.load(open(path))["body"] == "b"
    finally:
        os.unlink(path)


def test_dispatch_reports_payload_path_after_a_successful_post(capsys):
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    code = dispatch(PostMode.POST, Target("org", "repo", 5), Payload(body="b"), runner=runner)
    err = capsys.readouterr().err
    assert code == 0
    assert "posted review to org/repo#5" in err
    path = err.split("payload kept at ", 1)[1].strip()
    try:
        assert os.path.exists(path)
    finally:
        os.unlink(path)


def test_dispatch_review_only_keeps_payload_and_exits_zero(capsys):
    code = dispatch(PostMode.REVIEW_ONLY, Target("org", "repo", 5), Payload(body="b"))
    err = capsys.readouterr().err
    assert code == 0
    path = err.split("--input ", 1)[1].strip()
    try:
        assert os.path.exists(path)
    finally:
        os.unlink(path)


def test_write_payload_file_creates_valid_json():
    path = output._write_payload_file(Payload(body="b", comments=[Comment("a.py", 1, "g")]))
    try:
        with open(path) as f:
            data = json.load(f)
        assert data["body"] == "b"
        assert data["comments"][0]["path"] == "a.py"
    finally:
        os.unlink(path)


def test_not_posted_hint_writes_payload_and_includes_path():
    hint = output._not_posted_hint(Target("org", "repo", 5), Payload(body="b"))
    # the hint must name a real file (not a placeholder) that holds the payload
    input_path = hint.split("--input ", 1)[1].strip()
    try:
        assert os.path.exists(input_path)
        assert json.load(open(input_path))["body"] == "b"
    finally:
        os.unlink(input_path)


def test_show_review_renders_with_glow_when_present(capsys):
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        with open(cmd[-1], encoding="utf-8") as f:
            captured["content"] = f.read()
        return subprocess.CompletedProcess(cmd, 0)

    output.show_review(
        Payload(body="hello", comments=[Comment("a.py", 1, "gap")]),
        which=lambda name: "/usr/bin/glow", run=fake_run,
    )
    assert captured["cmd"][:4] == ["glow", "-p", "-w", "100"]
    assert "hello" in captured["content"]
    assert "a.py:1" in captured["content"]
    assert capsys.readouterr().out == ""  # glow rendered it; nothing printed


def test_show_review_prints_plain_when_glow_absent(capsys):
    output.show_review(Payload(body="hello", comments=[]), which=lambda name: None)
    assert "hello" in capsys.readouterr().out


def test_show_review_falls_back_to_print_when_glow_fails(capsys):
    def failing(cmd):
        return subprocess.CompletedProcess(cmd, 1)

    output.show_review(
        Payload(body="hello", comments=[]),
        which=lambda name: "/usr/bin/glow", run=failing,
    )
    assert "hello" in capsys.readouterr().out


def _ok(cmd, **kw):
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _paths(err):
    return [line.split("--input ", 1)[1].strip() for line in err.splitlines() if "--input " in line]


def test_replies_post_after_the_review_and_their_files_are_removed(capsys):
    calls = []

    def runner(cmd, **kw):
        calls.append(list(cmd))
        return _ok(cmd)

    p = Payload(body="b", replies=[Reply(11, "r1"), Reply(12, "r2")])
    code = dispatch(PostMode.POST, Target("org", "repo", 5), p, runner=runner)
    assert code == 0
    assert calls[0][2] == "repos/org/repo/pulls/5/reviews"
    assert calls[1][2] == "repos/org/repo/pulls/5/comments/11/replies"
    assert calls[2][2] == "repos/org/repo/pulls/5/comments/12/replies"
    reply_file = calls[1][calls[1].index("--input") + 1]
    assert not os.path.exists(reply_file)
    os.unlink(capsys.readouterr().err.split("payload kept at ", 1)[1].strip())


def test_a_failed_reply_does_not_stop_the_others_and_keeps_its_file(capsys):
    def runner(cmd, **kw):
        if "comments/11/replies" in cmd[2]:
            raise subprocess.CalledProcessError(1, cmd)
        return _ok(cmd)

    p = Payload(body="b", replies=[Reply(11, "r1"), Reply(12, "r2")])
    code = dispatch(PostMode.POST, Target("org", "repo", 5), p, runner=runner)
    err = capsys.readouterr().err
    assert code == 1
    assert "review posted; 1 of 2 replies failed" in err
    [kept] = _paths(err)
    try:
        assert "comments/11/replies" in err
        assert json.load(open(kept)) == {"body": "r1"}
    finally:
        os.unlink(kept)


def test_a_failed_review_posts_no_replies_and_keeps_everything(capsys):
    calls = []

    def runner(cmd, **kw):
        calls.append(list(cmd))
        raise subprocess.CalledProcessError(1, cmd)

    p = Payload(body="b", replies=[Reply(11, "r1")])
    code = dispatch(PostMode.POST, Target("org", "repo", 5), p, runner=runner)
    err = capsys.readouterr().err
    assert code == 1
    assert len(calls) == 1
    paths = _paths(err)
    assert len(paths) == 2
    for path in paths:
        assert os.path.exists(path)
        os.unlink(path)


def test_review_only_writes_reply_files_with_a_command_each(capsys):
    code = dispatch(PostMode.REVIEW_ONLY, Target("org", "repo", 5), Payload(body="b", replies=[Reply(11, "r1")]))
    err = capsys.readouterr().err
    assert code == 0
    paths = _paths(err)
    assert len(paths) == 2 and "comments/11/replies" in err
    for path in paths:
        os.unlink(path)


def test_the_confirm_prompt_counts_replies(monkeypatch):
    written = []
    monkeypatch.setattr(output.terminal, "open_interactive",
                        lambda: (lambda: "n", written.append, lambda: None))
    assert output._confirm(Target("org", "repo", 5), 2, 1) is False
    assert "with 2 inline comment(s) and 1 reply(ies)?" in written[0]
