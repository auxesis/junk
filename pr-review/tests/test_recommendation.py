from pr_review.collate import DeterministicMergeCollator
from pr_review.payload import Comment, Payload, Reply
from pr_review.plain_language.recommendation import recommend
from pr_review.synthesis import _cap_payload


def c(first_line):
    return Comment("a.py", 1, f"**{first_line}**\n\n**Impact:** x\n\n**Fix:** y")


def test_no_findings_is_green():
    assert recommend(Payload(body="Fine.")) == "## Recommendation: 🟢 merge as it is"


def test_only_follow_ups_and_optional_is_green():
    p = Payload(body="b", comments=[c("Fix in a follow-up: a."), c("Optional: b.")])
    assert recommend(p) == "## Recommendation: 🟢 merge as it is"


def test_change_before_merge_is_yellow():
    p = Payload(body="b", comments=[c("Fix in a follow-up: a."), c("Change before merge: b.")])
    assert recommend(p) == "## Recommendation: 🟡 merge after changes"


def test_fix_before_merge_wins():
    p = Payload(body="b", comments=[c("Change before merge: a."), c("Fix before merge: b.")])
    assert recommend(p) == "## Recommendation: 🔴 fix before merging"


def test_a_finding_with_no_phrase_is_yellow():
    p = Payload(body="b", comments=[c("`seal()` has no test for an empty key.")])
    assert recommend(p) == "## Recommendation: 🟡 merge after changes"


def test_collate_overflow_bullet_can_be_red():
    kept = [Comment("k.py", i, f"Some finding {i}.") for i in range(8)]
    overflow = [Comment("a.py", 3, "**Fix before merge: the lock is never released.**")]
    jobs = [("claude", "test-gap", Payload(body="b", comments=kept)),
            ("codex", "test-gap", Payload(body="b", comments=overflow))]
    out = DeterministicMergeCollator().collate(jobs)
    assert "## Other findings not posted as comments" in out.body
    assert recommend(out) == "## Recommendation: 🔴 fix before merging"


def test_synthesis_cap_payload_overflow_bullet_can_be_red():
    comments = [Comment("k.py", i, f"Some finding {i}.") for i in range(8)] + [
        Comment("a.py", 3, "**Fix before merge: the lock is never released.**")
    ]
    out = _cap_payload(Payload(body="b", comments=comments))
    assert "## Other findings not posted as comments" in out.body
    assert recommend(out) == "## Recommendation: 🔴 fix before merging"


def test_overflow_heading_matches_level_3_and_trailing_text():
    body = ("Verdict.\n\n---\n\n### Other findings not posted as comments (1)\n\n"
            "- `a.py:3` — **Fix before merge: the lock is never released.**")
    assert recommend(Payload(body=body)) == "## Recommendation: 🔴 fix before merging"


def test_bullets_outside_the_overflow_list_do_not_count():
    body = "Verdict.\n\n- Fix before merge: this is only an example in the prose."
    assert recommend(Payload(body=body)) == "## Recommendation: 🟢 merge as it is"


def test_replies_and_overflow_replies_count():
    p = Payload(body="b", replies=[Reply(10, "**Change before merge: no later PR calls it.**")])
    assert recommend(p) == "## Recommendation: 🟡 merge after changes"
    body = "b\n\n---\n\n## Other replies not posted\n\n- [**Fix before merge: x.**](https://x/r1)"
    assert recommend(Payload(body=body)) == "## Recommendation: 🔴 fix before merging"


def test_failed_jobs_are_named():
    assert recommend(Payload(body="b"), failed_jobs=1, total_jobs=2) == (
        "## Recommendation: 🟢 merge as it is (1 of 2 review job(s) failed)")
