from pr_review.context.filter import (
    MAX_REPLIES, ContextFilter, _add_evidence, answers_by_id, apply_verdicts, build_filter_prompt,
)
from pr_review.context.render import UNTRUSTED_RULE
from pr_review.context.model import Entry, PullRequestContext, StackEntry, Thread
from pr_review.payload import Comment, Payload, Source

SRC = Source("claude", "m", "infracode")


def ctx():
    root = Entry(10, "thread", "https://x/r10", "bot", False, "t", "Unused parameter.", "a.py", 4)
    author_reply = Entry(11, "thread", "https://x/r11", "ada", True, "t", "Used later in the stack.", "a.py", 4, 10,
                         association="CONTRIBUTOR")
    other_reply = Entry(12, "thread", "https://x/r12", "bob", False, "t", "Agreed.", "a.py", 4, 10)
    return PullRequestContext(
        number=7, title="T", body="B", author="ada", issues=[],
        comments=[Entry(1, "comment", "https://x/c1", "ada", True, "t", "Deliberate, see the ADR.")],
        threads=[Thread(root, [author_reply, other_reply])],
        stack=[StackEntry(6, "Earlier", "", "merged", "s6", False),
               StackEntry(8, "Later", "", "open", "s8", True),
               StackEntry(9, "Abandoned", "", "closed", "s9", True)],
        stack_position=None, failed=[],
    )


def payload(n=3):
    return Payload(body="Verdict.", comments=[
        Comment(f"f{i}.py", i + 1, f"**Finding {i}.**\n\n**Impact:** x\n\n**Fix:** y", sources=[SRC])
        for i in range(n)
    ])


def test_keep_and_missing_verdicts_keep_the_finding():
    out = apply_verdicts(payload(2), {"verdicts": [{"index": 0, "verdict": "keep"}]}, ctx())
    assert len(out.payload.comments) == 2 and out.dropped == []


def test_fixed_later_drops_and_records_the_pull_request():
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "drop", "reason": "fixed-later", "pull_request": 8, "evidence": "refs/stack/8:a.py sets it"}]}, ctx())
    assert out.payload.comments == []
    assert out.dropped[0].finding == "**Finding 0.**"
    assert (out.dropped[0].reason, out.dropped[0].link, out.dropped[0].evidence) == ("fixed-later", "#8", "refs/stack/8:a.py sets it")


def test_fixed_later_by_an_earlier_or_closed_pull_request_is_kept():
    for pr in (6, 9, 99):
        out = apply_verdicts(payload(1), {"verdicts": [
            {"index": 0, "verdict": "drop", "reason": "fixed-later", "pull_request": pr}]}, ctx())
        assert len(out.payload.comments) == 1, pr
        assert out.warnings, pr


def test_already_raised_and_answered_drop_with_their_link():
    out = apply_verdicts(payload(2), {"verdicts": [
        {"index": 0, "verdict": "drop", "reason": "already-raised", "link": "https://x/r10"},
        {"index": 1, "verdict": "drop", "reason": "answered", "link": "https://x/c1"}]}, ctx())
    assert out.payload.comments == []
    assert [(d.reason, d.link) for d in out.dropped] == [("already-raised", "https://x/r10"), ("answered", "https://x/c1")]


def test_already_raised_or_answered_with_an_unknown_link_is_kept():
    for reason in ("already-raised", "answered"):
        for verdict in ({"link": "https://elsewhere/1"}, {}):
            out = apply_verdicts(payload(1), {"verdicts": [
                {"index": 0, "verdict": "drop", "reason": reason, **verdict}]}, ctx())
            assert len(out.payload.comments) == 1 and out.dropped == [], (reason, verdict)
            assert out.warnings == ["f0.py:1: kept; the verdict linked to no known comment"], (reason, verdict)


def test_answered_with_a_link_to_someone_elses_entry_is_kept():
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "drop", "reason": "answered", "link": "https://x/r12"}]}, ctx())
    assert len(out.payload.comments) == 1 and out.dropped == []
    assert out.warnings == ["f0.py:1: kept; the linked answer is not the author's"]


def test_already_raised_may_link_to_anyone_including_a_thread_reply():
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "drop", "reason": "already-raised", "link": "https://x/r12"}]}, ctx())
    assert out.payload.comments == [] and out.dropped[0].link == "https://x/r12"


def test_an_unknown_reason_or_bad_index_is_ignored():
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "drop", "reason": "vibes"}, {"index": 5, "verdict": "drop", "reason": "answered"}]}, ctx())
    assert len(out.payload.comments) == 1


def test_a_reply_to_an_author_thread_reply_posts_to_the_thread_root():
    # GitHub accepts replies only to a thread's top-level comment: entry 11 replies to 10.
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "reply", "in_reply_to": 11, "body": "**No later pull request calls it.**"}]}, ctx())
    assert out.payload.comments == []
    assert [(r.in_reply_to, r.answer_id, r.body, r.sources) for r in out.payload.replies] == [
        (10, 11, "**No later pull request calls it.**", [SRC])]


def test_a_reply_to_an_author_thread_root_posts_to_that_root():
    c = ctx()
    c.threads.append(Thread(Entry(20, "thread", "https://x/r20", "ada", True, "t", "On purpose.", "b.py", 2), []))
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "reply", "in_reply_to": 20, "body": "**No.**"}]}, c)
    assert [(r.in_reply_to, r.answer_id) for r in out.payload.replies] == [(20, 20)]


def test_a_reply_to_someone_else_or_to_an_issue_comment_stays_a_comment_with_a_link():
    out = apply_verdicts(payload(2), {"verdicts": [
        {"index": 0, "verdict": "reply", "in_reply_to": 12, "body": "x"},
        {"index": 1, "verdict": "reply", "in_reply_to": 1, "body": "x"}]}, ctx())
    assert out.payload.replies == []
    assert len(out.payload.comments) == 2
    assert "**Evidence:** The author answered in [this comment](https://x/c1)." in out.payload.comments[1].body
    assert "**Fix:** y" in out.payload.comments[1].body
    # Check that Evidence appears before Fix
    evidence_pos = out.payload.comments[1].body.index("**Evidence:**")
    fix_pos = out.payload.comments[1].body.index("**Fix:**")
    assert evidence_pos < fix_pos


def test_replies_beyond_the_cap_go_to_the_overflow_list():
    n = MAX_REPLIES + 1
    out = apply_verdicts(payload(n), {"verdicts": [
        {"index": i, "verdict": "reply", "in_reply_to": 11, "body": f"**Reply {i}.**"} for i in range(n)]}, ctx())
    assert len(out.payload.replies) == MAX_REPLIES
    assert f"- [**Reply {n - 1}.**](https://x/r11)" in out.payload.body


def test_the_prompt_names_refs_states_findings_and_the_context_file():
    prompt = build_filter_prompt(payload_path="/o.json", context_path="/c.md", ctx=ctx(), payload=payload(1))
    for expected in ("/o.json", "/c.md", "refs/stack/8", "(closed, later", "### Finding 0: f0.py:1",
                     '"fixed-later"', '"already-raised"', '"answered"', '"reply"', "(author)",
                     "- 11: thread by ada [CONTRIBUTOR] (author)", UNTRUSTED_RULE):
        assert expected in prompt, expected


def test_a_failed_filter_call_keeps_every_finding():
    def boom(*a, **k):
        raise RuntimeError("down")

    out = ContextFilter(command=["j"], workdir="/wd", context_path="/c.md", runner=boom).apply(payload(2), ctx())
    assert len(out.payload.comments) == 2
    assert "context filter failed" in out.warnings[0]


def test_answers_by_id_covers_comments_and_every_thread_entry():
    assert answers_by_id(ctx()) == {1: "Deliberate, see the ADR.", 10: "Unused parameter.",
                                    11: "Used later in the stack.", 12: "Agreed."}


def test_add_evidence_inserts_before_fix_when_no_evidence():
    body = "**Finding.**\n\n**Impact:** x\n\n**Fix:** y"
    result = _add_evidence(body, "The author answered in [this comment](url).")
    assert "**Evidence:** The author answered in [this comment](url)." in result
    assert result.index("**Evidence:**") < result.index("**Fix:**")


def test_add_evidence_appends_to_existing_evidence():
    body = "**Finding.**\n\n**Evidence:** Something\n\n**Fix:** y"
    result = _add_evidence(body, "plus this.")
    assert "**Evidence:** Something plus this." in result
    assert result.index("**Evidence:**") < result.index("**Fix:**")


def test_add_evidence_appends_at_end_when_no_fix():
    body = "**Finding.**\n\n**Impact:** x"
    result = _add_evidence(body, "The author answered in [this comment](url).")
    assert result.endswith("**Evidence:** The author answered in [this comment](url).")


def test_verdicts_missing_or_not_a_list_keeps_every_finding():
    for data in ({}, {"verdicts": None}):
        out = apply_verdicts(payload(2), data, ctx())
        assert len(out.payload.comments) == 2
        assert "context filter returned no verdicts list; every finding is kept" in out.warnings


def test_data_not_a_dict_keeps_every_finding():
    out = apply_verdicts(payload(2), [], ctx())
    assert len(out.payload.comments) == 2
    assert "context filter returned no verdicts list; every finding is kept" in out.warnings


def test_missing_pull_request_in_fixed_later_verdict():
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "drop", "reason": "fixed-later"}]}, ctx())
    assert len(out.payload.comments) == 1
    assert "the verdict named no later pull request" in out.warnings[0]
