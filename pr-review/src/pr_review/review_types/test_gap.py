"""Test-coverage gap review type."""
from __future__ import annotations

from pr_review.review_types.base import ReviewType, register

_INSTRUCTIONS = r"""# Test Coverage Review

Your job: identify test-coverage gaps for NEW or CHANGED code in this diff, and
emit a single PR review as a JSON payload file. DO NOT POST ANYTHING. Do not run
`gh api`, `gh pr comment`, or `gh pr review`. The wrapper posts it later
after the human confirms. Your only side effect is writing the payload file.

## Workflow

1. Read the diff: `git diff origin/<base>...HEAD` (three-dot = exactly the
   changes on this branch). Orient with `--stat` first. Focus on `+` lines only.

2. Detect the repo's test conventions before writing any sketch. Find the test
   directory and the sibling test file closest to each changed area; read it and
   mirror its framework, imports, attributes/macros, helpers, assertion style,
   and naming. Your sketches MUST be drop-in for THIS repo's language and
   harness — never impose a framework the repo doesn't use.

3. For each non-trivial added/changed function, type, method, or routine, ask:
   - Is every public entry point covered by at least one test?
   - Is every branch in the added logic exercised? (each arm / if / early return)
   - Are negative cases tested? (wrong input, wrong key, malformed, missing field)
   - For encode/decode or seal/open pairs: is there a roundtrip test?
   - Are boundary inputs tested? (empty, max-size, exactly-at-limit, null)
   - For operations that should be nondeterministic (fresh-nonce AEAD seal): is
     there an assertion that two calls differ?

## Reference gap categories (from prior manual audits)

- Untested branches in new/changed functions.
- Public API added without tests.
- Lopsided negative cases — e.g. wrong-AAD covered but wrong-key missing; one
  tamper axis tested but the other three are not.
- Missing roundtrip property tests for encode/decode pairs.
- Missing boundary tests — empty, max-size, exactly-at-limit, malformed.
- Missing nondeterminism assertions for fresh-nonce / randomised outputs.

When a gap mirrors a known anti-pattern ("AAD mismatch is tested but key
mismatch is not"), say so — it grounds the recommendation.

## Each inline comment must be self-contained

1. One sentence stating the gap.
2. A concrete test sketch (~5-20 lines) in the repo's language/framework that
   the author can paste in.
3. The expected pass/fail behaviour.

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

## Scope rules

- In scope: gaps introduced by NEW or CHANGED code in this diff.
- Out of scope: pre-existing untested code the diff doesn't touch. Do not report it.
- Out of scope: crypto / security vulnerabilities. If you notice one
  incidentally, mention it briefly in the review BODY, not as an inline comment.

## Calibration

- Be conservative: only flag a gap when the missing test is clearly worth adding.
  Trivial getters and one-line wrappers are not gaps.
- Prefer patterns already established in the affected area.
- Don't restate the diff back at the author. Cite path:line and trust them to look.
- HARD CAP: 8 inline comments. List any overflow as a bullet list in the review
  body under "## Additional coverage gaps not posted inline".
- If the diff is doc-only / CI-only / has no test-relevant changes: write a
  payload whose body is a one-line note saying so and whose comments array is
  empty.

## Output (REQUIRED)

Write the PR review to the payload file named in the context above, as JSON:

  {
    "event": "COMMENT",
    "body": "<markdown summary — verdict + any out-of-scope notes + overflow list>",
    "comments": [
      {"path": "relative/path", "line": N, "side": "RIGHT",
       "body": "**Gap:** ...\n\n```<lang>\n<sketch>\n```\n\nExpected: ..."}
    ]
  }

Then ALSO print the same review to stdout in readable markdown so the human can
skim it (the summary body, then each gap with its path:line and sketch). Writing
the payload file is mandatory even when there are zero comments.
"""


class TestGapType(ReviewType):
    name = "test-gap"

    def instructions(self) -> str:
        return _INSTRUCTIONS


register(TestGapType())
