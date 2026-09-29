import os

from pr_review.payload import Comment, Payload, Reply, Source
from pr_review.plain_language.stage import PlainLanguageStage, check_payload, format_report

CLEAN = "**`f()` returns the wrong value.**\n\n**Impact:** Callers get zero.\n\n**Fix:** Return `x`."
JARGON = "**`g()` is inert.**\n\n**Impact:** Callers get zero.\n\n**Fix:** Return `y`."
FIXED = "**`g()` does nothing.**\n\n**Impact:** Callers get zero.\n\n**Fix:** Return `y`."
SRC = Source("claude", "m", "test-gap")


def payload(*bodies):
    return Payload(
        body="This pull request can merge.",
        comments=[Comment(f"f{i}.py", i + 1, b, side="RIGHT", sources=[SRC]) for i, b in enumerate(bodies)],
    )


class FakeRunner:
    """Answers the reader call, then the rewrite call, and records both prompts."""

    def __init__(self, reader=None, rewrite=None, fail=()):
        self.answers = [reader or {"comments": [], "body": {}}, rewrite or {"comments": [], "body": None}]
        self.fail = set(fail)
        self.prompts = []

    def __call__(self, command, build_prompt, *, workdir):
        call = len(self.prompts)
        self.prompts.append(build_prompt("/tmp/out.json"))
        if call in self.fail:
            raise RuntimeError(f"call {call} failed")
        return self.answers[call]


def stage(runner):
    return PlainLanguageStage(command=["judge"], workdir="/wd", base="b", runner=runner,
                              diff=lambda workdir, base: "")


def test_check_payload_runs_the_check_only():
    result = check_payload(payload(CLEAN, JARGON))
    assert result.remaining[0] == []
    assert any('"inert"' in p.detail for p in result.remaining[1])


def test_no_blocking_problem_means_no_rewrite_call():
    runner = FakeRunner()
    result = stage(runner).apply(payload(CLEAN))
    assert len(runner.prompts) == 1
    assert result.rewritten == 0
    assert result.payload.comments[0].body == CLEAN


def test_only_comments_with_blocking_problems_are_rewritten():
    runner = FakeRunner(rewrite={"comments": [{"index": 1, "body": FIXED}], "body": None})
    result = stage(runner).apply(payload(CLEAN, JARGON))
    assert "### Comment 1: f1.py:2" in runner.prompts[1]
    assert "### Comment 0:" not in runner.prompts[1]
    assert result.payload.comments[1].body == FIXED
    assert result.remaining[1] == []
    assert result.rewritten == 1


def test_a_reader_blocking_problem_triggers_a_rewrite():
    runner = FakeRunner(
        reader={"comments": [{"index": 0, "blocking": ["zero: which zero?"]}], "body": {}},
        rewrite={"comments": [{"index": 0, "body": CLEAN.replace("zero", "the number 0")}]},
    )
    result = stage(runner).apply(payload(CLEAN))
    assert "reader: zero: which zero?" in runner.prompts[1]
    assert result.rewritten == 1


def test_path_line_side_and_sources_never_change():
    runner = FakeRunner(rewrite={"comments": [{"index": 0, "body": FIXED}]})
    before = payload(JARGON).comments[0]
    after = stage(runner).apply(payload(JARGON)).payload.comments[0]
    assert (after.path, after.line, after.side, after.sources) == (before.path, before.line, before.side, before.sources)


def test_a_rewrite_that_drops_inline_code_keeps_the_original():
    runner = FakeRunner(rewrite={"comments": [{"index": 0, "body": FIXED.replace("`y`", "y")}]})
    result = stage(runner).apply(payload(JARGON))
    assert result.payload.comments[0].body == JARGON
    assert result.rewritten == 0
    assert any("f0.py:1: the rewrite dropped `y`; kept the original" in w for w in result.warnings)


def test_a_nonempty_diff_that_matches_no_comment_warns():
    runner = FakeRunner()
    other_file_diff = (
        "diff --git a/other.py b/other.py\n--- a/other.py\n+++ b/other.py\n"
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    s = PlainLanguageStage(command=["judge"], workdir="/wd", base="b", runner=runner,
                           diff=lambda workdir, base: other_file_diff)
    result = s.apply(payload(CLEAN))
    assert any(
        "no comment matched a line in the diff" in w for w in result.warnings
    )


def test_a_failed_reader_call_still_rewrites_on_the_check():
    runner = FakeRunner(rewrite={"comments": [{"index": 0, "body": FIXED}]}, fail={0})
    result = stage(runner).apply(payload(JARGON))
    assert result.payload.comments[0].body == FIXED
    assert any("reader test failed" in w for w in result.warnings)
    assert result.reader_ran is False


def test_reader_ran_is_true_when_the_reader_call_succeeds():
    runner = FakeRunner(rewrite={"comments": [{"index": 0, "body": FIXED}]})
    result = stage(runner).apply(payload(JARGON))
    assert result.reader_ran is True


def test_reader_ran_is_false_when_no_rewrite_is_needed_and_the_reader_failed():
    runner = FakeRunner(fail={0})
    result = stage(runner).apply(payload(CLEAN))
    assert result.reader_ran is False


def test_a_failed_rewrite_call_posts_the_review_as_written():
    runner = FakeRunner(fail={1})
    result = stage(runner).apply(payload(JARGON))
    assert result.payload.comments[0].body == JARGON
    assert any("rewrite failed" in w for w in result.warnings)


def test_the_check_runs_again_after_the_rewrite():
    still_bad = FIXED.replace("does nothing", "does nothing on the happy path")
    runner = FakeRunner(rewrite={"comments": [{"index": 0, "body": still_bad}]})
    result = stage(runner).apply(payload(JARGON))
    assert any('"happy path"' in p.detail for p in result.remaining[0])


def test_reader_and_rewrite_run_in_a_fresh_empty_tempdir_not_the_clone():
    seen = []

    def runner(command, build_prompt, *, workdir):
        seen.append((workdir, os.path.isdir(workdir), os.listdir(workdir)))
        build_prompt("/tmp/out.json")
        answers = [{"comments": [], "body": {}}, {"comments": [{"index": 0, "body": FIXED}], "body": None}]
        return answers[len(seen) - 1]

    stage = PlainLanguageStage(command=["judge"], workdir="/wd", base="b", runner=runner,
                               diff=lambda workdir, base: "")
    stage.apply(payload(JARGON))
    assert len(seen) == 2
    for workdir, isdir, contents in seen:
        assert workdir != "/wd"
        assert isdir
        assert contents == []


def test_the_body_is_rewritten_when_it_has_a_blocking_problem():
    p = payload(CLEAN)
    p.body = "It doesn't merge."
    runner = FakeRunner(rewrite={"comments": [], "body": "It does not merge yet."})
    result = stage(runner).apply(p)
    assert result.payload.body == "It does not merge yet."
    assert result.body_remaining == []
    assert result.body_rewritten is True


def test_body_rewritten_is_false_when_the_body_needs_no_rewrite():
    runner = FakeRunner()
    result = stage(runner).apply(payload(CLEAN))
    assert result.body_rewritten is False


def test_body_rewritten_is_false_when_the_body_rewrite_is_guarded_off():
    p = payload(CLEAN)
    p.body = "It doesn't merge."
    runner = FakeRunner(rewrite={"comments": [], "body": ""})
    result = stage(runner).apply(p)
    assert result.payload.body == "It doesn't merge."
    assert result.body_rewritten is False


def test_the_report_lists_problems_left_and_warnings():
    runner = FakeRunner(fail={1})
    report = format_report(stage(runner).apply(payload(JARGON)))
    assert "pr-review: plain language: rewrite failed" in report
    assert "rewrote 0 of the 1 comment(s) that needed it; 1 comment(s) still have problems (" in report
    assert "f0.py:1  blocking:" in report


def test_the_report_when_rewrite_succeeds_with_nothing_left():
    runner = FakeRunner(rewrite={"comments": [{"index": 0, "body": FIXED}]})
    report = format_report(stage(runner).apply(payload(JARGON)))
    assert "rewrote 1 of the 1 comment(s) that needed it; no problems left." in report


def test_the_report_is_empty_when_there_is_nothing_to_say():
    assert format_report(check_payload(payload(CLEAN))) == ""


def test_the_report_names_unattempted_blocking_problems_without_a_rewrite_count():
    report = format_report(check_payload(payload(JARGON)))
    assert "1 comment(s) have problems (" in report
    assert "0 of the 0" not in report


def test_replies_are_checked_and_rewritten_with_the_answer_as_context():
    p = payload(CLEAN)
    p.replies = [Reply(10, JARGON, sources=[SRC])]
    runner = FakeRunner(rewrite={"comments": [{"index": 1, "body": FIXED}]})
    result = stage(runner).apply(p, answers={10: "Used in the next pull request."})
    assert "Used in the next pull request." in runner.prompts[0]
    assert "### Comment 1: reply to comment 10" in runner.prompts[1]
    assert result.payload.replies[0].body == FIXED
    assert result.payload.replies[0].in_reply_to == 10
    assert result.payload.replies[0].sources == [SRC]


def test_the_reader_sees_the_answer_named_by_answer_id():
    p = payload(CLEAN)
    p.replies = [Reply(10, JARGON, sources=[SRC], answer_id=11)]
    runner = FakeRunner()
    stage(runner).apply(p, answers={10: "The thread root.", 11: "The author's answer."})
    assert "The author's answer." in runner.prompts[0]
    assert "The thread root." not in runner.prompts[0]


def test_check_payload_covers_replies():
    p = payload(CLEAN)
    p.replies = [Reply(10, JARGON)]
    assert any('"inert"' in x.detail for x in check_payload(p).remaining[1])


def test_the_report_lists_a_reply_problem_and_counts_it():
    p = payload(CLEAN)
    p.replies = [Reply(10, JARGON)]
    runner = FakeRunner(fail={1})
    report = format_report(stage(runner).apply(p, answers={10: "context"}))
    assert "reply to comment 10  blocking:" in report
    assert "rewrote 0 of the 1 comment(s) that needed it; 1 comment(s) still have problems (" in report


def test_only_minor_problems_say_no_rewrite_was_needed():
    runner = FakeRunner(reader={"comments": [{"index": 0, "minor": ["a little long"]}], "body": {}})
    result = stage(runner).apply(payload(CLEAN))
    assert result.needed_rewrite == 0
    report = format_report(result)
    assert ("no comment needed a rewrite. 1 comment(s) have minor problems, "
            "which are reported, not rewritten:") in report


def test_needed_rewrite_counts_blocking_units():
    runner = FakeRunner(rewrite={"comments": [{"index": 1, "body": FIXED}]})
    assert stage(runner).apply(payload(CLEAN, JARGON)).needed_rewrite == 1
