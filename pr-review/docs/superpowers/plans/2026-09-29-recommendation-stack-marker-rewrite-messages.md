# Recommendation Heading, Stack Marker and Rewrite Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every posted review starts with a code-written Recommendation heading; the stack line marks the reviewed pull request; the plain-language messages say plainly when nothing needed a rewrite, and the reader test counts three more cases as blocking.

**Architecture:** A pure `recommend()` reads the urgency phrase of every posted finding and returns the heading, which `finalize` puts first in the body. `describe_stack` marks the current pull request. `StageResult` and `RunRecord` gain `needed_rewrite` so stderr and the posted record can tell "nothing needed a rewrite" from "a rewrite was needed and did not happen".

**Tech Stack:** Python 3.14, stdlib only, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-09-24-plain-language-design.md` (section "Recommendation"). Items #2 and #3 were approved in chat as bounded designs; their exact text is in this plan. Glossary: `CONTEXT.md` ("Recommendation").

## Global Constraints

- Python `>=3.14`; stdlib only. No test runs a model, git, gh or the network.
- Run tests with `uv run pytest` from `pr-review/`.
- Recommendation headings, exactly: `## Recommendation: 🔴 fix before merging`, `## Recommendation: 🟡 merge after changes`, `## Recommendation: 🟢 merge as it is`; with failed jobs, append ` (N of M review jobs failed)`.
- State rule: red if any posted finding starts with "Fix before merge:"; else yellow if any starts with "Change before merge:" or has no recognised urgency phrase; else green (including no findings).
- The state names and emoji live only in `src/pr_review/plain_language/rules.json`.
- Stack marker: `:asterisk:` before the reviewed pull request's number, and the key ` :asterisk: marks this pull request.` after the list.
- Text pr-review shows a reader writes negatives in full.
- `CLAUDE.md`'s Test suite walkthrough and test count are updated in every task that changes tests.

---

### Task 1: Recommendation heading

**Files:**
- Modify: `src/pr_review/plain_language/rules.json`, `src/pr_review/plain_language/rules.py`, `src/pr_review/attribution.py`, `README.md`, `CLAUDE.md`
- Create: `src/pr_review/plain_language/recommendation.py`, `tests/test_recommendation.py`
- Test: `tests/test_plain_language_rules.py`, `tests/test_attribution.py`

**Interfaces:**
- Produces: `Rules.recommendation: dict[str, tuple[str, str]]` (state → (emoji, text)); `recommend(payload: Payload, *, failed_jobs: int = 0, total_jobs: int = 0) -> str`.
- `finalize(payload, record)` puts `recommend(...)` as the first line of the body, computing `failed_jobs`/`total_jobs` from `record.jobs`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_recommendation.py`:

```python
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
```

Append to `tests/test_plain_language_rules.py`:

```python
def test_rules_carry_the_recommendation_states():
    assert load_rules().recommendation == {
        "red": ("🔴", "fix before merging"),
        "yellow": ("🟡", "merge after changes"),
        "green": ("🟢", "merge as it is"),
    }


def test_the_block_tells_the_model_not_to_write_a_heading():
    block = writing_rules_block()
    assert "Do not write your own recommendation heading." in block
    for text in ("fix before merging", "merge after changes", "merge as it is"):
        assert text in block
```

In `tests/test_attribution.py`, change the assertion in `test_finalize_appends_footers_and_details_without_changing_the_input` from `out.body.startswith("Verdict.\n\n<details>")` to:

```python
    assert out.body.startswith("## Recommendation: 🟡 merge after changes\n\nVerdict.\n\n<details>")
```

(its comment `**X.**` has no urgency phrase, so it is yellow), and append:

```python
def test_finalize_names_failed_jobs_in_the_heading():
    p = Payload(body="Verdict.")
    out = finalize(p, RunRecord(jobs=[JobRecord(OPUS, raw=0), JobRecord(CODEX, error="boom")]))
    assert out.body.startswith("## Recommendation: 🟢 merge as it is (1 of 2 review jobs failed)\n\n")
```

- [ ] **Step 2: Run them to verify they fail.** `uv run pytest tests/test_recommendation.py tests/test_plain_language_rules.py tests/test_attribution.py -v` — expected: import error and assertion failures.

- [ ] **Step 3: Implement.**

`rules.json` — add after `"urgency"`:

```json
  "recommendation": {
    "red": {"emoji": "🔴", "text": "fix before merging"},
    "yellow": {"emoji": "🟡", "text": "merge after changes"},
    "green": {"emoji": "🟢", "text": "merge as it is"}
  },
```

`rules.py` — `Rules` gains `recommendation: dict[str, tuple[str, str]]`, loaded as `{k: (v["emoji"], v["text"]) for k, v in data["recommendation"].items()}`. In `writing_rules_block`, replace the final paragraph ("The review body starts with a verdict: …") with:

```python
    red, yellow, green = (r.recommendation[k][1] for k in ("red", "yellow", "green"))
    block_phrase, change_phrase = r.urgency["block"], r.urgency["request-changes"]
```

and the text:

```
pr-review adds a Recommendation heading above the review body. It is
"{red}" if any finding starts with "{block_phrase}:"; otherwise "{yellow}" if
any finding starts with "{change_phrase}:" or has no urgency phrase; otherwise
"{green}". Do not write your own recommendation heading. Start the body with
one or two sentences that say what must change before merging, if anything,
and what can wait.
```

Create `src/pr_review/plain_language/recommendation.py`:

```python
"""The Recommendation heading, worked out from the findings that were posted."""
from __future__ import annotations

from pr_review.payload import Payload
from pr_review.plain_language.rules import load_rules

_OVERFLOW_HEADINGS = ("## Other findings not posted as comments", "## Other replies not posted")


def _finding_lines(payload: Payload) -> list[str]:
    lines = [u.body.strip().splitlines()[0] for u in [*payload.comments, *payload.replies] if u.body.strip()]
    in_overflow = False
    for line in payload.body.splitlines():
        if line.startswith("## "):
            in_overflow = line.strip() in _OVERFLOW_HEADINGS
        elif in_overflow and line.startswith("- "):
            lines.append(line[2:])
    return lines


def _level(line: str, urgency: dict[str, str]) -> str:
    text = line.strip().lstrip("[*").strip()
    for level, phrase in urgency.items():
        if text.startswith(f"{phrase}:"):
            return level
    # A finding with no phrase can raise the recommendation, never lower it.
    return "request-changes"


def recommend(payload: Payload, *, failed_jobs: int = 0, total_jobs: int = 0) -> str:
    rules = load_rules()
    levels = {_level(line, rules.urgency) for line in _finding_lines(payload)}
    state = "red" if "block" in levels else "yellow" if "request-changes" in levels else "green"
    emoji, text = rules.recommendation[state]
    note = f" ({failed_jobs} of {total_jobs} review jobs failed)" if failed_jobs else ""
    return f"## Recommendation: {emoji} {text}{note}"
```

`attribution.py` `finalize` — build the body as:

```python
    failed = sum(1 for j in record.jobs if j.error is not None)
    heading = recommend(payload, failed_jobs=failed, total_jobs=len(record.jobs))
    details = render_details(record, [*payload.comments, *payload.replies])
    body = f"{heading}\n\n{payload.body.rstrip()}\n\n{details}"
```

(import `recommend` from `pr_review.plain_language.recommendation`; check for an import cycle — `recommendation.py` imports only `payload` and `rules`).

`README.md` — in the "Plain language" section add: "Every review starts with a **Recommendation** heading that pr-review works out from the posted findings: 🔴 fix before merging (any finding marked "Fix before merge"), 🟡 merge after changes (any "Change before merge", or a finding with no urgency), or 🟢 merge as it is. A failed review job is named in the heading."

`CLAUDE.md` — add a `test_recommendation.py` entry and update the rules and attribution entries and the counts.

- [ ] **Step 4: Run the full suite.** `uv run pytest` — all pass.

- [ ] **Step 5: Commit** `feat(pr-review): start every review with a recommendation heading`.

---

### Task 2: Mark the reviewed pull request in the stack line

**Files:**
- Modify: `src/pr_review/context/render.py`, `CLAUDE.md`
- Test: `tests/test_context_render.py` (and any `tests/test_cli.py` assertion on `stack_line` text)

**Interfaces:**
- Produces: `CURRENT_MARK = ":asterisk:"` in `render.py`; `describe_stack(ctx, missing=0)` output as below.

- [ ] **Step 1: Update the tests.** In `tests/test_context_render.py`, the `describe_stack` expectations become:

```python
    assert describe_stack(ctx([EARLIER, LATER], (2, 3))) == (
        "Stack: position 2 of 3 (#6, :asterisk: #7, #8). :asterisk: marks this pull request.")
    assert describe_stack(ctx([LATER])) == (
        "Stack: 0 earlier and 1 later pull request(s) (:asterisk: #7, #8). :asterisk: marks this pull request.")
    assert describe_stack(ctx()) == "Stack: not part of a stack."
```

and any `missing=` expectation keeps " Some pull requests in the stack could not be fetched." after the key. Search `tests/` for other `Stack: position` / `later pull request(s)` literals and update them the same way.

- [ ] **Step 2: Run them to verify they fail.** `uv run pytest tests/test_context_render.py tests/test_cli.py -v`.

- [ ] **Step 3: Implement** in `render.py`:

```python
CURRENT_MARK = ":asterisk:"
_CURRENT_KEY = f" {CURRENT_MARK} marks this pull request."


def _describe_fetched_stack(ctx: PullRequestContext) -> str:
    if not ctx.stack:
        return "Stack: not part of a stack."
    mark = lambda n: f"{CURRENT_MARK} #{n}" if n == ctx.number else f"#{n}"
    if ctx.stack_position:
        numbers = sorted([e.number for e in ctx.stack] + [ctx.number])
        pos, size = ctx.stack_position
        return f"Stack: position {pos} of {size} ({', '.join(mark(n) for n in numbers)}).{_CURRENT_KEY}"
    earlier = [e.number for e in ctx.stack if not e.later]
    later = [e.number for e in ctx.stack if e.later]
    numbers = [*earlier, ctx.number, *later]
    return (f"Stack: {len(earlier)} earlier and {len(later)} later pull request(s) "
            f"({', '.join(mark(n) for n in numbers)}).{_CURRENT_KEY}")
```

(use a small `def` instead of the lambda if the file avoids lambdas.) Update `CLAUDE.md`'s test_context_render entry.

- [ ] **Step 4: Run the full suite.** `uv run pytest`.

- [ ] **Step 5: Commit** `feat(pr-review): mark the reviewed pull request in the stack line`.

---

### Task 3: Rewrite messages and a stricter reader test

**Files:**
- Modify: `src/pr_review/plain_language/stage.py`, `src/pr_review/plain_language/reader.py`, `src/pr_review/attribution.py`, `src/pr_review/cli.py`, `CLAUDE.md`
- Test: `tests/test_plain_language_stage.py`, `tests/test_plain_language_reader.py`, `tests/test_attribution.py`

**Interfaces:**
- Produces: `StageResult.needed_rewrite: int = 0` — the number of units (comments and replies) that had a blocking problem before the rewrite; set on every return of `apply` after the blocking items are known (0 on the early return with nothing to rewrite; `len(items)` on the rewrite-failure return and the final return). `RunRecord.needed_rewrite: int = 0`, passed from `staged.needed_rewrite` in `cli.main`.

- [ ] **Step 1: Write/update the tests.**

`tests/test_plain_language_stage.py`:
- In `test_the_report_lists_problems_left_and_warnings`, replace the header assertion with `assert "rewrote 0 of the 1 comment(s) that needed it; 1 comment(s) still have problems (" in report`.
- In `test_the_report_when_rewrite_succeeds_with_nothing_left`, assert `"rewrote 1 of the 1 comment(s) that needed it; no problems left." in report`.
- In the reply-count report test, change the header assertion to the new wording with the same counts.
- Add:

```python
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
```

`tests/test_plain_language_reader.py` — add:

```python
def test_the_reader_is_told_three_cases_are_always_blocking():
    prompt = build_reader_prompt(payload_path="/p", comments=[], body="")
    assert "These are always blocking:" in prompt
    assert "open a link or another file" in prompt
    assert "covers only part of what the comment says must change" in prompt
    assert "uses a name that neither the diff lines nor the comment defines" in prompt
```

`tests/test_attribution.py` — in the test that asserts `"rewrote 2"`, set `needed_rewrite=2` on the `RunRecord` and assert `"2 comment(s) had a problem that stopped the reader acting; it rewrote 2." in text`; add:

```python
def test_details_say_no_rewrite_was_needed():
    record = RunRecord(jobs=[JobRecord(OPUS, raw=1)], plain_language_model="claude-opus-5",
                       reader_ran=True, needed_rewrite=0)
    assert ("No comment had a problem that stopped the reader acting, so none was rewritten."
            in render_details(record, []))
```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement.**

`stage.py` — add `needed_rewrite: int = 0` to `StageResult`; pass `needed_rewrite=len(items)` on the rewrite-failure and final returns (the no-items early return keeps 0). Rewrite `format_report`'s header logic, keeping the per-problem lines and warnings unchanged:

```python
    n_blocking = sum(1 for line in left if "  blocking: " in line)
    n_minor = len(left) - n_blocking
    if left:
        if result.needed_rewrite == 0 and n_blocking == 0:
            head = (f"no comment needed a rewrite. {k} comment(s) have minor problems, "
                    "which are reported, not rewritten:")
        else:
            head = (f"rewrote {result.rewritten} of the {result.needed_rewrite} comment(s) that "
                    f"needed it; {k} comment(s) still have problems ({n_blocking} blocking, {n_minor} minor):")
        lines.append(f"pr-review: plain language: {head}")
        lines.extend(left)
    elif result.rewritten:
        lines.append(f"pr-review: plain language: rewrote {result.rewritten} of the "
                     f"{result.needed_rewrite} comment(s) that needed it; no problems left.")
```

(count blocking/minor from the `Problem.level` values rather than string matching if that is cleaner — the result must be the same.)

`reader.py` — in `_INSTRUCTIONS`, after the `"blocking"` bullet, add:

```
  These are always blocking:
  - you would have to open a link or another file to know whether the point
    still stands;
  - the Fix covers only part of what the comment says must change;
  - suggested code uses a name that neither the diff lines nor the comment
    defines.
```

`attribution.py` — `RunRecord` gains `needed_rewrite: int = 0`; in `render_details`, when `reader_ran`:

```python
            if record.needed_rewrite == 0:
                note = (f"Plain language: `{record.plain_language_model}` read every comment as a new "
                        "reader would. No comment had a problem that stopped the reader acting, "
                        "so none was rewritten.")
            else:
                note = (f"Plain language: `{record.plain_language_model}` read every comment as a new "
                        f"reader would. {record.needed_rewrite} comment(s) had a problem that stopped "
                        f"the reader acting; it rewrote {record.rewritten}.")
```

`cli.py` — pass `needed_rewrite=staged.needed_rewrite` into `RunRecord`.

Update `CLAUDE.md` entries for the stage, reader and attribution tests, and the count.

- [ ] **Step 4: Run the full suite.** `uv run pytest`.

- [ ] **Step 5: Commit** `fix(pr-review): say when no comment needed a rewrite, and tighten the reader test`.
