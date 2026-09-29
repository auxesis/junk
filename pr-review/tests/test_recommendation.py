from pr_review.payload import Comment, Payload, Reply
from pr_review.plain_language.recommendation import recommend


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


def test_overflow_bullets_count():
    body = ("Verdict.\n\n---\n\n## Other findings not posted as comments\n\n"
            "- Fix before merge: the lock is never released. `a.py:3`")
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
        "## Recommendation: 🟢 merge as it is (1 of 2 review jobs failed)")
