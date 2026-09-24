from pr_review.plain_language.check import (
    BLOCKING, MINOR, check_body, check_comment, sentences,
)

GOOD = """**Fix before merge: `DEPLOY_REGION` is not set in any environment file, so the deploy task cannot run.**

**Impact:** Every `deploy` run stops at its first check, with the error `DEPLOY_REGION is not set`.

**Evidence:** `load_settings()` requires the variable (`src/deploy/settings.py:42`). The variable is set only in `tests/fixtures/`.

**Fix:** Set the variable in each environment's `mise.toml`:

```toml
[env]
DEPLOY_REGION = "ap-southeast-2"
```
"""

BAD = """**The loader is inert on the happy path.**

This doesn't fail loudly: the retry wrapper silently swallows the timeout, so the cache is never refreshed and every request after the first one in the window reads a stale value that nobody notices until a customer reports it days later in a ticket.
"""


def details(problems, level=None):
    return [p.detail for p in problems if level is None or p.level == level]


def test_a_plain_comment_has_no_problems():
    assert check_comment(GOOD) == []


def test_a_jargon_comment_has_every_kind_of_blocking_problem():
    found = " | ".join(details(check_comment(BAD), BLOCKING))
    assert 'contraction "doesn\'t"' in found
    assert '"inert"' in found and '"happy path"' in found
    assert '"silently"' in found and '"swallows"' in found
    assert "sentence of" in found
    assert "no **Impact:** section" in found
    assert "no **Fix:** section" in found


def test_the_first_line_must_be_a_bold_finding_line():
    body = GOOD.replace("**Fix before merge: `DEPLOY_REGION`", "Fix before merge: `DEPLOY_REGION`", 1)
    body = body.replace("cannot run.**", "cannot run.", 1)
    assert "the first line is not a bold finding line" in details(check_comment(body))


def test_evidence_is_optional():
    body = GOOD.split("**Evidence:**")[0] + "**Fix:**" + GOOD.split("**Fix:**")[1]
    assert check_comment(body) == []


def test_a_sentence_of_26_to_35_words_is_minor():
    long = " ".join(["word"] * 30) + "."
    problems = check_body(long)
    assert [p.level for p in problems] == [MINOR]
    assert "sentence of 30 words" in problems[0].detail


def test_a_sentence_over_35_words_is_blocking():
    problems = check_body(" ".join(["word"] * 36) + ".")
    assert [p.level for p in problems] == [BLOCKING]


def test_code_is_never_checked():
    body = "Run it:\n\n```sh\n# this doesn't matter and is silently ignored\n```\n\nThe flag `--dont-silently-fail` is fine."
    assert check_body(body) == []


def test_repo_terms_pass():
    assert check_body("The drift alert reads the root's state lock.") == []


def test_list_items_and_headings_are_separate_sentences():
    text = "## Verdict\n\n- First item without a full stop\n- Second item\n\nOne. Two."
    assert sentences(text) == ["## Verdict", "First item without a full stop", "Second item", "One.", "Two."]


def test_table_rows_are_not_sentences():
    assert sentences("| a | b |\n|---|---|\n| " + "x " * 40 + "|") == []
