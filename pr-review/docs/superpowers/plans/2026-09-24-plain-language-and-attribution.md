# Plain-Language Review Text and Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every comment and review body pr-review posts can be read and acted on by an engineer who does not know this part of the system, and model attribution moves from the start of each comment to a small footer.

**Architecture:** A shared writing-rules block, rendered from one `rules.json`, goes into every review-type prompt and the synthesis prompt. After collation, a new plain-language stage runs a deterministic word-and-shape check and one batched model "reader test", then one batched rewrite of comments with blocking problems. Code, not a model, then appends a `<sub>` attribution footer to each comment and a collapsed "How this review was made" block to the body.

**Tech Stack:** Python 3.14, stdlib only, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-09-24-plain-language-design.md` (read it before starting). Glossary: `CONTEXT.md`. Decision record: `docs/adr/0001-plain-language-rewrites-only-blocking-problems.md`.

## Global Constraints

- Python `>=3.14`; no new runtime dependencies (`pyproject.toml` `dependencies = []` stays empty).
- No test runs a model, `git`, `gh` or the network. Side effects go through injected fake runners (`CLAUDE.md`, "Testing principle").
- Run tests with `uv run pytest` (same as `mise run test`) from `pr-review/`.
- Sentence thresholds: minor over **25** words, blocking over **35** words.
- Required comment labels: `**Impact:**` and `**Fix:**`. Optional: `**Evidence:**`. No `Problem:` label.
- Urgency phrases: block → `Fix before merge:`, request-changes → `Change before merge:`, follow-up → `Fix in a follow-up:`, minor → `Optional:`.
- Footer strings: `<sub>Found by N model(s): a, b</sub>`; `<sub>Found by pr-review</sub>` when no source is known.
- Details block summary text: `How this review was made`.
- Every word list, threshold and label lives only in `src/pr_review/plain_language/rules.json`.
- Text pr-review itself shows a reader (footers, details block, stderr report) writes negatives in full ("does not", never "doesn't").
- Code comments: only what a reader cannot infer from the code (see the repo's comment style).
- Test fixtures use invented code and paths. Never copy text from reviewed repositories.
- `CLAUDE.md`'s **Test suite** walkthrough is updated in the last task.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `src/pr_review/payload.py` | modify | `Source`; `Comment.sources`; `payload_from_dict` |
| `src/pr_review/reviewers/_run.py` | modify | `run_cli_json` (file-is-the-contract runner for any JSON); `run_cli_payload` built on it |
| `src/pr_review/plain_language/__init__.py` | create | package marker |
| `src/pr_review/plain_language/rules.json` | create | the only word list, thresholds, labels, urgency phrases |
| `src/pr_review/plain_language/rules.py` | create | load `rules.json`; render the writing-rules prompt block |
| `src/pr_review/plain_language/check.py` | create | deterministic check (`Problem`, `check_comment`, `check_body`) |
| `src/pr_review/plain_language/hunks.py` | create | `git diff` text → the hunk around one line |
| `src/pr_review/plain_language/reader.py` | create | reader-test prompt and result parsing |
| `src/pr_review/plain_language/rewrite.py` | create | rewrite prompt, result parsing, guards |
| `src/pr_review/plain_language/stage.py` | create | `PlainLanguageStage`, `check_payload`, `format_report` |
| `src/pr_review/attribution.py` | create | `JobRecord`, `RunRecord`, `attribution`, `render_details`, `finalize` |
| `src/pr_review/review_types/*.py` | modify | new comment shape; append the writing-rules block |
| `src/pr_review/orchestrator.py` | modify | stamp sources; `RunResult.jobs`; drop the failed-jobs body line |
| `src/pr_review/collate.py` | modify | overflow heading |
| `src/pr_review/synthesis.py` | modify | new prompt; `sources` mapping; `ran` flag; `run_cli_json` |
| `src/pr_review/cli.py` | modify | new flags; run the stage; finalize; stderr report |
| `tests/test_*.py` | create/modify | one test file per new module |
| `CLAUDE.md`, `README.md` | modify | test walkthrough; options and behaviour |

---

### Task 1: `Source`, `Comment.sources` and `payload_from_dict`

**Files:**
- Modify: `src/pr_review/payload.py`
- Test: `tests/test_payload.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `Source(agent: str, model: str, review_type: str)` — frozen dataclass, hashable.
  - `Comment(path, line, body, side="RIGHT", sources: list[Source] = [])` — `to_dict()` never includes `sources`.
  - `payload_from_dict(data: object) -> Payload` — raises `ValueError` on a bad shape.
  - `parse_payload(text: str) -> Payload` — unchanged behaviour, now `json.loads` then `payload_from_dict`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_payload.py`:

```python
from pr_review.payload import Source, payload_from_dict


def test_sources_never_reach_the_github_payload():
    c = Comment("a.py", 3, "gap", sources=[Source("claude", "opus", "test-gap")])
    assert "sources" not in c.to_dict()
    assert "sources" not in Payload(body="b", comments=[c]).to_json()


def test_comment_sources_default_to_empty_and_are_not_shared():
    a, b = Comment("a.py", 1, "x"), Comment("b.py", 2, "y")
    a.sources.append(Source("claude", "m", "t"))
    assert b.sources == []


def test_source_is_hashable_and_compares_by_value():
    assert Source("claude", "m", "t") == Source("claude", "m", "t")
    assert len({Source("claude", "m", "t"), Source("claude", "m", "t")}) == 1


def test_payload_from_dict_matches_parse_payload():
    data = {"body": "b", "comments": [{"path": "x.py", "line": 2, "body": "g"}]}
    p = payload_from_dict(data)
    assert p.body == "b"
    assert p.comments[0].path == "x.py"


def test_payload_from_dict_rejects_a_non_object():
    with pytest.raises(ValueError, match="JSON object"):
        payload_from_dict(["not", "an", "object"])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_payload.py -v`
Expected: FAIL with `ImportError: cannot import name 'Source'`.

- [ ] **Step 3: Implement** — in `src/pr_review/payload.py`, add `Source` above `Comment`, add the `sources` field, and split `parse_payload`:

```python
@dataclass(frozen=True)
class Source:
    """The job that raised a finding. Internal to pr-review; never posted."""

    agent: str
    model: str
    review_type: str


@dataclass
class Comment:
    path: str
    line: int
    body: str
    side: str = "RIGHT"
    sources: list[Source] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"path": self.path, "line": self.line, "side": self.side, "body": self.body}
```

Replace the start of `parse_payload` so the validation lives in `payload_from_dict`:

```python
def parse_payload(text: str) -> Payload:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"payload is not valid JSON: {e}") from e
    return payload_from_dict(data)


def payload_from_dict(data: object) -> Payload:
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    # ... the rest of the old parse_payload body, unchanged, from
    # `if not isinstance(data.get("body"), str):` to the final `return Payload(...)`
```

(Move the existing lines — do not retype them — so every existing validation message stays identical.)

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_payload.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/payload.py tests/test_payload.py
git commit -m "feat(pr-review): record each comment's sources inside pr-review"
```

---

### Task 2: `run_cli_json`

**Files:**
- Modify: `src/pr_review/reviewers/_run.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: `payload.parse_payload` (Task 1).
- Produces: `run_cli_json(cmd_prefix: Sequence[str], build_prompt: Callable[[str], str], *, workdir: str, parse: Callable[[str], T] = json.loads, runner: Callable[..., int] = run_agent) -> T`. Same contract as `run_cli_payload`: the file the agent was told to write is the result; an empty/missing file raises `RuntimeError` naming the exit status; a parse failure raises `ValueError` naming the exit status; the temp file is always removed. `run_cli_payload(...)` becomes `run_cli_json(..., parse=parse_payload)`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_run.py`:

```python
from pr_review.reviewers._run import run_cli_json


def test_run_cli_json_returns_the_parsed_file():
    data = run_cli_json(["agent"], build, workdir="/tmp",
                        runner=fake_runner(writes='{"verdicts": [1, 2]}'))
    assert data == {"verdicts": [1, 2]}


def test_run_cli_json_survives_a_nonzero_exit_status():
    data = run_cli_json(["agent"], build, workdir="/tmp",
                        runner=fake_runner(writes='{"ok": true}', status=101))
    assert data == {"ok": True}


def test_run_cli_json_reports_the_exit_status_for_bad_json():
    with pytest.raises(ValueError, match="exit status 7"):
        run_cli_json(["agent"], build, workdir="/tmp",
                     runner=fake_runner(writes="{nope", status=7))


def test_run_cli_json_reports_the_exit_status_for_an_empty_file():
    with pytest.raises(RuntimeError, match="empty payload.*exit status 3"):
        run_cli_json(["agent"], build, workdir="/tmp",
                     runner=fake_runner(writes="", status=3))


def test_run_cli_json_cleans_up_its_file():
    seen = {}
    run_cli_json(["agent"], build, workdir="/w", runner=fake_runner(writes="{}", seen=seen))
    assert not os.path.exists(seen["path"])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_run.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_cli_json'`.

- [ ] **Step 3: Implement** — in `src/pr_review/reviewers/_run.py`, add `import json` and `from typing import IO, TypeVar`, define `T = TypeVar("T")`, then replace `run_cli_payload` with:

```python
def run_cli_json(
    cmd_prefix: Sequence[str],
    build_prompt: Callable[[str], str],
    *,
    workdir: str,
    parse: Callable[[str], T] = json.loads,
    runner: Callable[..., int] = run_agent,
) -> T:
    """Run an agent and parse the file it was told to write.

    The file, not the exit status, is the contract: agents have been seen
    finishing their work, writing a valid file, and only then dying on the way
    out (see `run_agent`). A non-zero status is only reported when the file is
    missing or unusable.
    """
    fd, payload_path = tempfile.mkstemp(prefix="pr-review-payload.", suffix=".json")
    os.close(fd)
    try:
        prompt = build_prompt(payload_path)
        status = runner(cmd_prefix, prompt, workdir=workdir)
        try:
            with open(payload_path, encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            raw = ""
        if not raw.strip():
            raise RuntimeError(
                f"{cmd_prefix[0]} produced an empty payload (exit status {status})"
            )
        try:
            return parse(raw)
        except ValueError as e:
            raise ValueError(f"{e} (exit status {status})") from None
    finally:
        try:
            os.unlink(payload_path)
        except FileNotFoundError:
            pass


def run_cli_payload(
    cmd_prefix: Sequence[str],
    build_prompt: Callable[[str], str],
    *,
    workdir: str,
    runner: Callable[..., int] = run_agent,
) -> Payload:
    return run_cli_json(cmd_prefix, build_prompt, workdir=workdir,
                        parse=parse_payload, runner=runner)
```

(`json.JSONDecodeError` is a `ValueError`, so bad JSON gets the exit status too.)

- [ ] **Step 4: Run the whole run-test file** (the existing `run_cli_payload` tests must still pass)

Run: `uv run pytest tests/test_run.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/reviewers/_run.py tests/test_run.py
git commit -m "refactor(pr-review): add run_cli_json and build run_cli_payload on it"
```

---

### Task 3: `rules.json` and the writing-rules block

**Files:**
- Create: `src/pr_review/plain_language/__init__.py`, `src/pr_review/plain_language/rules.json`, `src/pr_review/plain_language/rules.py`
- Test: `tests/test_plain_language_rules.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `BlockingWord(word: str, pattern: re.Pattern[str], instead: str)`
  - `Rules(sentence_minor_words: int, sentence_blocking_words: int, labels: dict[str, str], required_labels: tuple[str, ...], urgency: dict[str, str], blocking_words: tuple[BlockingWord, ...])`
  - `load_rules() -> Rules` (cached)
  - `writing_rules_block() -> str` (cached) — the Markdown section every prompt gets; starts with `## How to write each comment (REQUIRED)`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_plain_language_rules.py`:

```python
from pr_review.plain_language.rules import load_rules, writing_rules_block


def test_rules_load_with_the_spec_thresholds_and_labels():
    rules = load_rules()
    assert rules.sentence_minor_words == 25
    assert rules.sentence_blocking_words == 35
    assert rules.labels == {"impact": "Impact", "evidence": "Evidence", "fix": "Fix"}
    assert rules.required_labels == ("impact", "fix")
    assert rules.urgency["block"] == "Fix before merge"


def test_every_blocking_word_matches_its_own_display_word():
    for w in load_rules().blocking_words:
        assert w.pattern.search(w.word), w.word
        assert w.instead


def test_repo_terms_are_not_on_the_list():
    rules = load_rules()
    for term in ("drift", "root", "state lock"):
        assert not any(w.pattern.search(term) for w in rules.blocking_words), term


def test_the_block_names_every_label_threshold_word_and_urgency_phrase():
    rules, block = load_rules(), writing_rules_block()
    assert block.startswith("## How to write each comment (REQUIRED)")
    for label in rules.labels.values():
        assert f"**{label}:**" in block
    assert "25 words" in block and "35 words" in block
    for w in rules.blocking_words:
        assert f'"{w.word}"' in block
    for phrase in rules.urgency.values():
        assert f'"{phrase}:"' in block


def test_the_block_itself_writes_negatives_in_full():
    import re
    # The quoted examples of what not to write are the only contractions allowed.
    text = re.sub(r'"[^"]*"', "", writing_rules_block())
    assert not re.search(r"\b\w+n['’]t\b", text)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_plain_language_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pr_review.plain_language'`.

- [ ] **Step 3: Create the package marker** — `src/pr_review/plain_language/__init__.py`:

```python
"""Plain-language rules, check, reader test and rewrite for posted reviews."""
```

- [ ] **Step 4: Create `src/pr_review/plain_language/rules.json`**:

```json
{
  "_comment": [
    "The only list of plain-language words, thresholds and labels in pr-review.",
    "rules.py renders the prompt block from it and check.py checks against it,",
    "so a word added here is both taught and enforced. Every pattern is a regular",
    "expression, matched case-insensitively. Repo terms (drift, root, state lock)",
    "are deliberately absent: a repository's own words are not jargon."
  ],
  "sentence_minor_words": 25,
  "sentence_blocking_words": 35,
  "labels": {"impact": "Impact", "evidence": "Evidence", "fix": "Fix"},
  "required_labels": ["impact", "fix"],
  "urgency": {
    "block": "Fix before merge",
    "request-changes": "Change before merge",
    "follow-up": "Fix in a follow-up",
    "minor": "Optional"
  },
  "blocking_words": [
    {"word": "silently", "pattern": "\\bsilently\\b", "instead": "say \"with no error or log message\""},
    {"word": "swallow", "pattern": "\\bswallow(s|ed|ing)?\\b", "instead": "say \"catches and ignores\""},
    {"word": "load-bearing", "pattern": "\\bload[- ]bearing\\b", "instead": "say what breaks if it is removed"},
    {"word": "inert", "pattern": "\\binert\\b", "instead": "say \"does nothing\" or \"never runs\""},
    {"word": "dead end", "pattern": "\\bdead[- ]ends?\\b", "instead": "say \"stops with no next step\""},
    {"word": "interleave", "pattern": "\\binterleav(e|es|ed|ing)\\b", "instead": "say \"run at the same time and mix their writes\""},
    {"word": "footgun", "pattern": "\\bfoot-?guns?\\b", "instead": "say what mistake is easy to make and what it causes"},
    {"word": "blast radius", "pattern": "\\bblast radius\\b", "instead": "say what else breaks"},
    {"word": "plumb", "pattern": "\\bplumb(s|ed|ing)?\\b", "instead": "say \"pass\" or \"connect\""},
    {"word": "leverage", "pattern": "\\bleverag(e|es|ed|ing)\\b", "instead": "say \"use\""},
    {"word": "orthogonal", "pattern": "\\borthogonal\\b", "instead": "say \"unrelated\""},
    {"word": "first-class", "pattern": "\\bfirst[- ]class\\b", "instead": "say \"fully supported\""},
    {"word": "belt and braces", "pattern": "\\bbelt[- ]and[- ]braces\\b", "instead": "say \"a second check\""},
    {"word": "smell", "pattern": "\\bsmells?\\b", "instead": "say what is wrong"},
    {"word": "landmine", "pattern": "\\blandmines?\\b", "instead": "say what fails and when"},
    {"word": "bite", "pattern": "\\bbites?\\b", "instead": "say what fails and when"},
    {"word": "punt", "pattern": "\\bpunt(s|ed|ing)?\\b", "instead": "say \"leave for later\""},
    {"word": "paper over", "pattern": "\\bpaper(s|ed|ing)? over\\b", "instead": "say \"hides\""},
    {"word": "tripwire", "pattern": "\\btripwires?\\b", "instead": "say \"check\""},
    {"word": "clobber", "pattern": "\\bclobber(s|ed|ing)?\\b", "instead": "say \"overwrites\""},
    {"word": "stomp", "pattern": "\\bstomp(s|ed|ing)?\\b", "instead": "say \"overwrites\""},
    {"word": "escape hatch", "pattern": "\\bescape hatch(es)?\\b", "instead": "say \"a way to turn it off\""},
    {"word": "sharp edge", "pattern": "\\bsharp edges?\\b", "instead": "say what goes wrong"},
    {"word": "hot path", "pattern": "\\bhot path\\b", "instead": "say \"code that runs on every request\""},
    {"word": "bubble up", "pattern": "\\bbubbles? up\\b", "instead": "say \"is passed to the caller\""},
    {"word": "happy path", "pattern": "\\bhappy path\\b", "instead": "say \"the case where nothing fails\""},
    {"word": "gated", "pattern": "\\bgat(ed|ing)\\b", "instead": "say \"only runs when\""},
    {"word": "surfaces", "pattern": "\\bsurfac(es|ed|ing)\\b", "instead": "say \"shows\" or \"reports\""},
    {"word": "wedge", "pattern": "\\bwedg(e|es|ed|ing)\\b", "instead": "say \"hangs\""},
    {"word": "hermetic", "pattern": "\\bhermetic\\b", "instead": "say \"isolated\""},
    {"word": "baked in", "pattern": "\\bbake[sd]?[- ]in\\b", "instead": "say \"hard-coded\""},
    {"word": "vacuous", "pattern": "\\bvacuous(ly)?\\b", "instead": "say \"always passes\" or \"checks nothing\""},
    {"word": "key off", "pattern": "\\bkey(s|ed|ing)? off\\b", "instead": "say \"uses X to decide\""},
    {"word": "cutover", "pattern": "\\bcut-?over\\b", "instead": "say \"switch from X to Y\""},
    {"word": "repoint", "pattern": "\\brepoint(s|ed|ing)?\\b", "instead": "say \"change X to use Y\""},
    {"word": "backstop", "pattern": "\\bbackstops?\\b", "instead": "say \"fallback check\""},
    {"word": "alert storm", "pattern": "\\balert storms?\\b", "instead": "say \"many alerts at once\""},
    {"word": "non-starter", "pattern": "\\bnon-?starters?\\b", "instead": "say why it cannot work"}
  ]
}
```

- [ ] **Step 5: Implement `src/pr_review/plain_language/rules.py`**:

```python
"""Load rules.json and render the writing rules every prompt receives."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files


@dataclass(frozen=True)
class BlockingWord:
    word: str
    pattern: re.Pattern[str]
    instead: str


@dataclass(frozen=True)
class Rules:
    sentence_minor_words: int
    sentence_blocking_words: int
    labels: dict[str, str]
    required_labels: tuple[str, ...]
    urgency: dict[str, str]
    blocking_words: tuple[BlockingWord, ...]


@cache
def load_rules() -> Rules:
    data = json.loads(files(__package__).joinpath("rules.json").read_text(encoding="utf-8"))
    return Rules(
        sentence_minor_words=data["sentence_minor_words"],
        sentence_blocking_words=data["sentence_blocking_words"],
        labels=dict(data["labels"]),
        required_labels=tuple(data["required_labels"]),
        urgency=dict(data["urgency"]),
        blocking_words=tuple(
            BlockingWord(w["word"], re.compile(w["pattern"], re.IGNORECASE), w["instead"])
            for w in data["blocking_words"]
        ),
    )


@cache
def writing_rules_block() -> str:
    r = load_rules()
    impact, evidence, fix = r.labels["impact"], r.labels["evidence"], r.labels["fix"]
    urgency = "\n".join(f'  - {level}: "{phrase}:"' for level, phrase in r.urgency.items())
    words = "\n".join(f'- "{w.word}": {w.instead}' for w in r.blocking_words)
    return f"""## How to write each comment (REQUIRED)

Write every comment, and the review body, for this reader: an engineer on the
team who did not write this code, does not know this part of the system, and may
not have English as a first language. They must be able to act on each comment
without asking anyone.

Every inline comment has this shape, in this order:

    **<finding line: one sentence that says what is wrong>**

    **{impact}:** <what breaks, and when>

    **{evidence}:** <optional: how you know, such as a file and line or a command and its output>

    **{fix}:** <what to change; any code goes here, and only here>

- The finding line is bold and comes first. Do not add a "Problem:" label.
- If your instructions have a severity ladder, start the finding line with the
  plain phrase for the level, never with the ladder's own name:
{urgency}
- {impact} and {fix} are required. Leave out {evidence} only when the finding
  line already shows how you know.

Writing rules (from ISO 24495-1 plain language and ASD-STE100 Simplified
Technical English):

1. Put the most important information first.
2. Keep one idea in each sentence.
3. Keep most sentences under 20 words. Split a sentence over
   {r.sentence_minor_words} words unless it is a list of paths or a quoted
   message. Never write a sentence over {r.sentence_blocking_words} words.
4. Use the active voice. Say who or what does the action.
5. Write negatives in full: "does not" and "cannot", never "doesn't" or "can't".
6. Use literal words, with no metaphor and no programmer slang. Say what
   happens: "the alert does not fire", not "the guard is inert".
7. Use one term for one thing. Keep the repository's own words. If the diff shows
   what a repository term means, define it once, in a few words. Never replace a
   term with a similar general word.
8. Keep exact technical names: identifiers, commands, file paths, product names
   and real engineering terms. Put code names in backticks.
9. Use code fences only for code, commands and command output. Never put an
   explanation inside a fence.
10. Each comment must make sense alone. Do not refer to "the above" or to another
    comment.

Never use these words and phrases; write the plain words instead:
{words}

The review body starts with a verdict: one or two sentences that say whether the
pull request can merge as it is, and what must change first.
"""
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_plain_language_rules.py -v`
Expected: all PASS.

- [ ] **Step 7: Confirm `rules.json` ships in the wheel**

Run: `uv build --wheel -o /tmp/prr-wheel && python3 -m zipfile -l /tmp/prr-wheel/*.whl | grep rules.json`
Expected: one line ending in `pr_review/plain_language/rules.json`.

- [ ] **Step 8: Commit**

```bash
git add src/pr_review/plain_language tests/test_plain_language_rules.py
git commit -m "feat(pr-review): add the plain-language rules and the prompt block"
```

---

### Task 4: The deterministic check

**Files:**
- Create: `src/pr_review/plain_language/check.py`
- Test: `tests/test_plain_language_check.py`

**Interfaces:**
- Consumes: `load_rules()`, `Rules` (Task 3).
- Produces:
  - `BLOCKING = "blocking"`, `MINOR = "minor"`
  - `Problem(level: str, detail: str)` — frozen dataclass
  - `FENCE: re.Pattern` (a fenced code block), `INLINE_CODE: re.Pattern` (an inline code span)
  - `sentences(text: str) -> list[str]`
  - `check_text(text: str, rules: Rules | None = None) -> list[Problem]`
  - `check_comment(body: str, rules: Rules | None = None) -> list[Problem]` — shape + `check_text`
  - `check_body(body: str, rules: Rules | None = None) -> list[Problem]` — `check_text` only

- [ ] **Step 1: Write the failing tests** — create `tests/test_plain_language_check.py`:

~~~python
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
~~~

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_plain_language_check.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/plain_language/check.py`**:

```python
"""The plain-language problems code can find without a model."""
from __future__ import annotations

import re
from dataclasses import dataclass

from pr_review.plain_language.rules import Rules, load_rules

BLOCKING = "blocking"
MINOR = "minor"


@dataclass(frozen=True)
class Problem:
    level: str
    detail: str


FENCE = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n.*?^[ \t]*\1[ \t]*$", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]+`")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_CONTRACTION = re.compile(r"\b[A-Za-z]+n['’]t\b")
_NEW_BLOCK = re.compile(r"^\s*([-*+]\s|\d+[.)]\s|#|>)")
_LIST_MARKER = re.compile(r"^([-*+]|\d+[.)])\s+")
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[*_`])")
_FINDING_LINE = re.compile(r"^\*\*[^*\s].*\*\*$")


def _prose(text: str) -> str:
    text = FENCE.sub("\n\n", text)
    text = INLINE_CODE.sub("CODE", text)
    text = _LINK.sub(r"\1", text)
    return text.replace("**", "")


def sentences(text: str) -> list[str]:
    """Split prose into sentences; list items, headings and quotes stand alone."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in _prose(text).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|"):
            if current:
                blocks.append(current)
                current = []
            continue
        if _NEW_BLOCK.match(line) and current:
            blocks.append(current)
            current = []
        current.append(_LIST_MARKER.sub("", stripped))
    if current:
        blocks.append(current)
    out: list[str] = []
    for block in blocks:
        out.extend(s.strip() for s in _SPLIT.split(" ".join(block)) if s.strip())
    return out


def _preview(sentence: str) -> str:
    words = sentence.split()
    return " ".join(words[:8]) + (" ..." if len(words) > 8 else "")


def check_text(text: str, rules: Rules | None = None) -> list[Problem]:
    rules = rules or load_rules()
    plain = _prose(text)
    problems = [
        Problem(BLOCKING, f'contraction "{m.group(0)}": write the negative in full')
        for m in _CONTRACTION.finditer(plain)
    ]
    for word in rules.blocking_words:
        problems.extend(
            Problem(BLOCKING, f'"{m.group(0)}": {word.instead}')
            for m in word.pattern.finditer(plain)
        )
    for s in sentences(text):
        n = len(s.split())
        if n > rules.sentence_blocking_words:
            problems.append(Problem(BLOCKING, f'sentence of {n} words ("{_preview(s)}")'))
        elif n > rules.sentence_minor_words:
            problems.append(Problem(MINOR, f'sentence of {n} words ("{_preview(s)}")'))
    return problems


def check_comment(body: str, rules: Rules | None = None) -> list[Problem]:
    rules = rules or load_rules()
    problems: list[Problem] = []
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if not _FINDING_LINE.match(first):
        problems.append(Problem(BLOCKING, "the first line is not a bold finding line"))
    for key in rules.required_labels:
        label = rules.labels[key]
        if not re.search(rf"^\*\*{re.escape(label)}:\*\*", body, re.M):
            problems.append(Problem(BLOCKING, f"no **{label}:** section"))
    return problems + check_text(body, rules)


def check_body(body: str, rules: Rules | None = None) -> list[Problem]:
    return check_text(body, rules)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_plain_language_check.py -v`
Expected: all PASS. If `test_list_items_and_headings_are_separate_sentences` fails on the heading, check that `_NEW_BLOCK` matches `#` at line start.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/plain_language/check.py tests/test_plain_language_check.py
git commit -m "feat(pr-review): add the deterministic plain-language check"
```

---

### Task 5: Diff hunks

**Files:**
- Create: `src/pr_review/plain_language/hunks.py`
- Test: `tests/test_plain_language_hunks.py`

**Interfaces:**
- Produces:
  - `hunk_for(diff: str, path: str, line: int, context: int = 20) -> str` — the `@@` header plus up to `context` rows either side of new-file line `line`; `""` when the path or line is not in the diff.
  - `git_diff(workdir: str, base: str, runner=subprocess.run) -> str` — `git diff <base>...HEAD` in `workdir`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_plain_language_hunks.py`:

```python
from pr_review.plain_language.hunks import git_diff, hunk_for

DIFF = """diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+import sys
 
 def main():
@@ -10,4 +11,5 @@ def main():
     a = 1
-    b = 2
+    b = 3
+    c = 4
     return a
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old
+new
"""


def test_finds_the_hunk_containing_the_line():
    out = hunk_for(DIFF, "src/app.py", 13)
    assert out.startswith("@@ -10,4 +11,5 @@")
    assert "+    c = 4" in out
    assert "import sys" not in out


def test_removed_lines_do_not_count_as_new_lines():
    out = hunk_for(DIFF, "src/app.py", 12)
    assert "+    b = 3" in out
    assert "-    b = 2" in out


def test_another_file_in_the_same_diff():
    assert hunk_for(DIFF, "README.md", 1).splitlines() == ["@@ -1 +1 @@", "-old", "+new"]


def test_a_line_or_path_outside_the_diff_gives_nothing():
    assert hunk_for(DIFF, "src/app.py", 99) == ""
    assert hunk_for(DIFF, "missing.py", 1) == ""


def test_context_limits_the_rows_around_the_line():
    body = "\n".join(f"+line {i}" for i in range(1, 101))
    diff = f"diff --git a/f b/f\n--- /dev/null\n+++ b/f\n@@ -0,0 +1,100 @@\n{body}\n"
    out = hunk_for(diff, "f", 50, context=2).splitlines()
    assert out == ["@@ -0,0 +1,100 @@", "+line 48", "+line 49", "+line 50", "+line 51", "+line 52"]


def test_git_diff_runs_a_three_dot_diff_in_the_workdir():
    calls = []

    class Done:
        stdout = "DIFF"

    def runner(cmd, **kw):
        calls.append((cmd, kw))
        return Done()

    assert git_diff("/wd", "abc123", runner=runner) == "DIFF"
    cmd, kw = calls[0]
    assert cmd == ["git", "diff", "abc123...HEAD"]
    assert kw["cwd"] == "/wd"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_plain_language_hunks.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/plain_language/hunks.py`**:

```python
"""Find the diff lines a comment is attached to, as a reader on GitHub sees them."""
from __future__ import annotations

import re
import subprocess

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _file_sections(diff: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    in_header = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_header, current = True, None
        elif in_header:
            # An added line can itself start with "+++ ", so only the header's
            # "+++ " names the file.
            if line.startswith("+++ "):
                in_header = False
                name = line[4:]
                if name.startswith("b/"):
                    current = sections.setdefault(name[2:], [])
        elif current is not None:
            current.append(line)
    return sections


def hunk_for(diff: str, path: str, line: int, context: int = 20) -> str:
    hunks: list[tuple[str, list[tuple[int | None, str]]]] = []
    new = 0
    for text in _file_sections(diff).get(path, []):
        m = _HUNK.match(text)
        if m:
            new = int(m.group(1))
            hunks.append((text, []))
        elif not hunks or text.startswith("\\"):
            continue
        elif text.startswith("-"):
            hunks[-1][1].append((None, text))
        else:
            hunks[-1][1].append((new, text))
            new += 1
    for header, rows in hunks:
        idx = next((i for i, (n, _) in enumerate(rows) if n == line), None)
        if idx is not None:
            window = rows[max(0, idx - context): idx + context + 1]
            return "\n".join([header, *(t for _, t in window)])
    return ""


def git_diff(workdir: str, base: str, runner=subprocess.run) -> str:
    res = runner(
        ["git", "diff", f"{base}...HEAD"],
        cwd=workdir, capture_output=True, text=True, check=True,
    )
    return res.stdout
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_plain_language_hunks.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/plain_language/hunks.py tests/test_plain_language_hunks.py
git commit -m "feat(pr-review): find the diff hunk a comment is attached to"
```

---

### Task 6: The reader test (prompt and parsing)

**Files:**
- Create: `src/pr_review/plain_language/reader.py`
- Test: `tests/test_plain_language_reader.py`

**Interfaces:**
- Consumes: `Comment` (Task 1).
- Produces:
  - `Verdict(blocking: list[str] = [], minor: list[str] = [])`
  - `ReaderResult(comments: dict[int, Verdict], body: Verdict)`
  - `build_reader_prompt(*, payload_path: str, comments: list[tuple[int, Comment, str]], body: str) -> str` — each tuple is `(index, comment, hunk)`.
  - `parse_reader_result(data: object) -> ReaderResult` — raises `ValueError` if `data` is not a JSON object; ignores malformed entries.

- [ ] **Step 1: Write the failing tests** — create `tests/test_plain_language_reader.py`:

```python
import pytest

from pr_review.payload import Comment
from pr_review.plain_language.reader import build_reader_prompt, parse_reader_result


def test_prompt_shows_each_comment_beside_its_diff_lines():
    prompt = build_reader_prompt(
        payload_path="/tmp/out.json",
        comments=[(0, Comment("a.py", 3, "**Finding.**"), "@@ -1 +1 @@\n+x = 1")],
        body="Verdict: fine.",
    )
    assert "/tmp/out.json" in prompt
    assert "### Comment 0: a.py:3" in prompt
    assert "+x = 1" in prompt
    assert "**Finding.**" in prompt
    assert "Verdict: fine." in prompt
    assert "What should I change?" in prompt
    assert '"blocking"' in prompt and '"minor"' in prompt


def test_prompt_says_when_no_diff_lines_were_found():
    prompt = build_reader_prompt(payload_path="/p", comments=[(0, Comment("a", 1, "x"), "")], body="")
    assert "(no diff lines found)" in prompt


def test_parse_reads_blocking_and_minor_per_comment_and_for_the_body():
    result = parse_reader_result({
        "comments": [{"index": 1, "blocking": ["inert: had to guess"], "minor": ["long"]}],
        "body": {"blocking": [], "minor": ["verdict is vague"]},
    })
    assert result.comments[1].blocking == ["inert: had to guess"]
    assert result.comments[1].minor == ["long"]
    assert result.body.minor == ["verdict is vague"]


def test_parse_ignores_malformed_entries():
    result = parse_reader_result({
        "comments": [{"index": "zero"}, "junk", {"index": 2, "blocking": [3, "real"]}],
    })
    assert list(result.comments) == [2]
    assert result.comments[2].blocking == ["real"]
    assert result.body.blocking == []


def test_parse_rejects_a_non_object():
    with pytest.raises(ValueError):
        parse_reader_result([])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_plain_language_reader.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/plain_language/reader.py`**:

~~~python
"""The reader test: a model reads each comment as the target reader would."""
from __future__ import annotations

from dataclasses import dataclass, field

from pr_review.payload import Comment

_INSTRUCTIONS = """# Reader test

You are the reader of a pull request review: an engineer on the team who did not
write this code, does not know this part of the system, and may not have English
as a first language. You see each comment beside the diff lines it is attached
to, as you would on GitHub. Do not read any other file and do not run any
command other than writing the output file.

For each comment, answer from the comment and its diff lines alone:
1. What is wrong?
2. What breaks, and when?
3. What should I change?

Then list its problems:
- "blocking": you could not answer one of the three questions, or you had to
  guess what a word or phrase means to answer it. Name the phrase and say why.
- "minor": the comment was harder to read than it needed to be, but you could
  still act on it.
Exact technical names (identifiers, commands, file paths, product names and real
engineering terms) are not problems.

For the review body, answer one question: what must I do before this pull
request merges? List its blocking and minor problems the same way.

Write ONLY this JSON to the output file:
{"comments": [{"index": 0, "what_wrong": "...", "what_breaks": "...",
   "what_to_change": "...", "blocking": ["phrase: why"], "minor": ["phrase: why"]}],
 "body": {"what_to_do_before_merge": "...", "blocking": [], "minor": []}}
"""


@dataclass
class Verdict:
    blocking: list[str] = field(default_factory=list)
    minor: list[str] = field(default_factory=list)


@dataclass
class ReaderResult:
    comments: dict[int, Verdict]
    body: Verdict


def build_reader_prompt(
    *, payload_path: str, comments: list[tuple[int, Comment, str]], body: str
) -> str:
    parts = [f"Output file to write: {payload_path}\n", _INSTRUCTIONS, "## Comments\n"]
    for index, comment, hunk in comments:
        parts.append(
            f"### Comment {index}: {comment.path}:{comment.line}\n\n"
            f"Diff lines:\n```diff\n{hunk or '(no diff lines found)'}\n```\n\n"
            f"Comment:\n<<<\n{comment.body}\n>>>\n"
        )
    parts.append(f"## Review body\n\n<<<\n{body}\n>>>\n")
    return "\n".join(parts)


def _strings(value: object) -> list[str]:
    return [s for s in value if isinstance(s, str)] if isinstance(value, list) else []


def parse_reader_result(data: object) -> ReaderResult:
    if not isinstance(data, dict):
        raise ValueError("reader result must be a JSON object")
    comments: dict[int, Verdict] = {}
    raw = data.get("comments")
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and isinstance(item.get("index"), int):
            comments[item["index"]] = Verdict(_strings(item.get("blocking")), _strings(item.get("minor")))
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    return ReaderResult(comments, Verdict(_strings(body.get("blocking")), _strings(body.get("minor"))))
~~~

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_plain_language_reader.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/plain_language/reader.py tests/test_plain_language_reader.py
git commit -m "feat(pr-review): add the plain-language reader test prompt and parser"
```

---

### Task 7: The rewrite (prompt, parsing, guards)

**Files:**
- Create: `src/pr_review/plain_language/rewrite.py`
- Test: `tests/test_plain_language_rewrite.py`

**Interfaces:**
- Consumes: `Comment` (Task 1), `writing_rules_block()` (Task 3), `FENCE`, `INLINE_CODE` (Task 4).
- Produces:
  - `RewriteItem(index: int, comment: Comment, hunk: str, problems: list[str])`
  - `build_rewrite_prompt(*, payload_path: str, items: list[RewriteItem], body: str, body_problems: list[str]) -> str`
  - `parse_rewrite_result(data: object) -> tuple[dict[int, str], str | None]` — raises `ValueError` if `data` is not an object.
  - `guard(original: str, rewritten: str) -> str | None` — `None` when the rewrite is safe, otherwise the reason (`"changed a code block"` / ``"dropped `x`"`` / `"is empty"`).

- [ ] **Step 1: Write the failing tests** — create `tests/test_plain_language_rewrite.py`:

~~~python
import pytest

from pr_review.payload import Comment
from pr_review.plain_language.rewrite import (
    RewriteItem, build_rewrite_prompt, guard, parse_rewrite_result,
)

ORIGINAL = "**The loader is inert.**\n\nSee `load()`.\n\n```py\nload(retry=True)\n```"


def test_prompt_lists_items_with_problems_and_the_writing_rules():
    prompt = build_rewrite_prompt(
        payload_path="/tmp/o.json",
        items=[RewriteItem(2, Comment("a.py", 7, ORIGINAL), "@@ +7 @@\n+load()", ['"inert": say "does nothing"'])],
        body="Verdict.", body_problems=[],
    )
    assert "/tmp/o.json" in prompt
    assert "### Comment 2: a.py:7" in prompt
    assert '"inert": say "does nothing"' in prompt
    assert "## How to write each comment (REQUIRED)" in prompt
    assert "write null" in prompt


def test_prompt_includes_the_body_when_it_has_problems():
    prompt = build_rewrite_prompt(payload_path="/p", items=[], body="LGTM, ship it.",
                                  body_problems=["verdict is vague"])
    assert "LGTM, ship it." in prompt
    assert "verdict is vague" in prompt


def test_parse_reads_bodies_by_index_and_the_review_body():
    bodies, body = parse_rewrite_result(
        {"comments": [{"index": 2, "body": "new"}, {"index": "x", "body": "bad"}], "body": "B"}
    )
    assert bodies == {2: "new"}
    assert body == "B"


def test_parse_treats_a_missing_or_null_body_as_none():
    assert parse_rewrite_result({"comments": []}) == ({}, None)
    assert parse_rewrite_result({"comments": [], "body": None}) == ({}, None)


def test_parse_rejects_a_non_object():
    with pytest.raises(ValueError):
        parse_rewrite_result("nope")


def test_guard_accepts_a_rewrite_that_keeps_code():
    new = "**The loader does nothing.**\n\n**Impact:** x\n\n**Fix:** Call `load()`:\n\n```py\nload(retry=True)\n```"
    assert guard(ORIGINAL, new) is None


def test_guard_rejects_a_changed_code_block():
    new = ORIGINAL.replace("retry=True", "retry=False")
    assert guard(ORIGINAL, new) == "changed a code block"


def test_guard_rejects_a_dropped_inline_code_span():
    new = ORIGINAL.replace("See `load()`.", "See the loader.")
    assert guard(ORIGINAL, new) == "dropped `load()`"


def test_guard_rejects_an_empty_rewrite():
    assert guard(ORIGINAL, "   ") == "is empty"
~~~

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_plain_language_rewrite.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/plain_language/rewrite.py`**:

~~~python
"""One batched rewrite of the comments a reader could not act on."""
from __future__ import annotations

from dataclasses import dataclass

from pr_review.payload import Comment
from pr_review.plain_language.check import FENCE, INLINE_CODE
from pr_review.plain_language.rules import writing_rules_block

_INSTRUCTIONS = """# Plain-language rewrite

Rewrite each comment below, and the review body if it is included, so the reader
described in the writing rules can act on it. Fix every listed problem.

- Keep the meaning. Do not add facts that are not in the original or its diff lines.
- Keep every fenced code block exactly as it is, in the same order.
- Keep every `inline code` span.
- Keep the repository's own terms. You may define a term once, in a few words, if
  the diff lines show what it means. Never replace it with a different term.
- Keep the shape: the bold finding line first, then **Impact:**, an optional
  **Evidence:**, then **Fix:**.

Write ONLY this JSON to the output file:
{"comments": [{"index": 0, "body": "<the rewritten comment>"}], "body": "<the rewritten review body, or null>"}
"""


@dataclass
class RewriteItem:
    index: int
    comment: Comment
    hunk: str
    problems: list[str]


def build_rewrite_prompt(
    *, payload_path: str, items: list[RewriteItem], body: str, body_problems: list[str]
) -> str:
    parts = [f"Output file to write: {payload_path}\n", _INSTRUCTIONS, writing_rules_block(),
             "## Comments to rewrite\n"]
    for item in items:
        problems = "\n".join(f"- {p}" for p in item.problems)
        parts.append(
            f"### Comment {item.index}: {item.comment.path}:{item.comment.line}\n\n"
            f"Problems:\n{problems}\n\n"
            f"Diff lines:\n```diff\n{item.hunk or '(no diff lines found)'}\n```\n\n"
            f"Comment:\n<<<\n{item.comment.body}\n>>>\n"
        )
    if body_problems:
        problems = "\n".join(f"- {p}" for p in body_problems)
        parts.append(f"## Review body to rewrite\n\nProblems:\n{problems}\n\n<<<\n{body}\n>>>\n")
    else:
        parts.append("## Review body\n\nThe review body does not need rewriting; write null for it.\n")
    return "\n".join(parts)


def parse_rewrite_result(data: object) -> tuple[dict[int, str], str | None]:
    if not isinstance(data, dict):
        raise ValueError("rewrite result must be a JSON object")
    bodies: dict[int, str] = {}
    raw = data.get("comments")
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and isinstance(item.get("index"), int) and isinstance(item.get("body"), str):
            bodies[item["index"]] = item["body"]
    body = data.get("body")
    return bodies, body if isinstance(body, str) else None


def guard(original: str, rewritten: str) -> str | None:
    if not rewritten.strip():
        return "is empty"
    if [m.group(0) for m in FENCE.finditer(original)] != [m.group(0) for m in FENCE.finditer(rewritten)]:
        return "changed a code block"
    outside = FENCE.sub("", rewritten)
    for span in INLINE_CODE.findall(FENCE.sub("", original)):
        if span not in outside:
            return f"dropped {span}"
    return None
~~~

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_plain_language_rewrite.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/plain_language/rewrite.py tests/test_plain_language_rewrite.py
git commit -m "feat(pr-review): add the plain-language rewrite prompt, parser and guards"
```

---

### Task 8: The plain-language stage

**Files:**
- Create: `src/pr_review/plain_language/stage.py`
- Test: `tests/test_plain_language_stage.py`

**Interfaces:**
- Consumes: Tasks 1–7 (`Payload`, `Comment`, `run_cli_json`, `check_comment`, `check_body`, `Problem`, `BLOCKING`, `MINOR`, `hunk_for`, `git_diff`, `build_reader_prompt`, `parse_reader_result`, `RewriteItem`, `build_rewrite_prompt`, `parse_rewrite_result`, `guard`).
- Produces:
  - `StageResult(payload: Payload, remaining: dict[int, list[Problem]], body_remaining: list[Problem], rewritten: int = 0, warnings: list[str] = [])`
  - `check_payload(payload: Payload) -> StageResult` — the check only, no model.
  - `PlainLanguageStage(*, command: list[str], workdir: str, base: str, runner=run_cli_json, diff=git_diff)` with `.apply(payload: Payload) -> StageResult`. The runner is called as `runner(command, build_prompt, workdir=workdir)` and returns parsed JSON.
  - `format_report(result: StageResult) -> str` — `""` when there is nothing to say.

- [ ] **Step 1: Write the failing tests** — create `tests/test_plain_language_stage.py`:

~~~python
from pr_review.payload import Comment, Payload, Source
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


def test_a_failed_reader_call_still_rewrites_on_the_check():
    runner = FakeRunner(rewrite={"comments": [{"index": 0, "body": FIXED}]}, fail={0})
    result = stage(runner).apply(payload(JARGON))
    assert result.payload.comments[0].body == FIXED
    assert any("reader test failed" in w for w in result.warnings)


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


def test_the_body_is_rewritten_when_it_has_a_blocking_problem():
    p = payload(CLEAN)
    p.body = "It doesn't merge."
    runner = FakeRunner(rewrite={"comments": [], "body": "It does not merge yet."})
    result = stage(runner).apply(p)
    assert result.payload.body == "It does not merge yet."
    assert result.body_remaining == []


def test_the_report_lists_problems_left_and_warnings():
    runner = FakeRunner(fail={1})
    report = format_report(stage(runner).apply(payload(JARGON)))
    assert "pr-review: plain language: rewrite failed" in report
    assert "f0.py:1  blocking:" in report


def test_the_report_is_empty_when_there_is_nothing_to_say():
    assert format_report(check_payload(payload(CLEAN))) == ""
~~~

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_plain_language_stage.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/plain_language/stage.py`**:

```python
"""The plain-language stage: check, reader test, one rewrite, check again."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from pr_review.payload import Payload
from pr_review.plain_language.check import BLOCKING, MINOR, Problem, check_body, check_comment
from pr_review.plain_language.hunks import git_diff, hunk_for
from pr_review.plain_language.reader import Verdict, build_reader_prompt, parse_reader_result
from pr_review.plain_language.rewrite import (
    RewriteItem, build_rewrite_prompt, guard, parse_rewrite_result,
)
from pr_review.reviewers._run import run_cli_json


@dataclass
class StageResult:
    payload: Payload
    remaining: dict[int, list[Problem]]
    body_remaining: list[Problem]
    rewritten: int = 0
    warnings: list[str] = field(default_factory=list)


def check_payload(payload: Payload) -> StageResult:
    return StageResult(
        payload=payload,
        remaining={i: check_comment(c.body) for i, c in enumerate(payload.comments)},
        body_remaining=check_body(payload.body),
    )


def _reader_problems(verdict: Verdict | None) -> list[Problem]:
    if verdict is None:
        return []
    return ([Problem(BLOCKING, f"reader: {t}") for t in verdict.blocking]
            + [Problem(MINOR, f"reader: {t}") for t in verdict.minor])


def _blocking(problems: list[Problem]) -> list[str]:
    return [p.detail for p in problems if p.level == BLOCKING]


class PlainLanguageStage:
    def __init__(
        self,
        *,
        command: list[str],
        workdir: str,
        base: str,
        runner: Callable[..., object] = run_cli_json,
        diff: Callable[[str, str], str] = git_diff,
    ):
        self._command = command
        self._workdir = workdir
        self._base = base
        self._runner = runner
        self._diff = diff

    def apply(self, payload: Payload) -> StageResult:
        checked = check_payload(payload)
        warnings: list[str] = []
        try:
            diff = self._diff(self._workdir, self._base)
        except Exception as e:
            warnings.append(f"could not read the diff ({e}); the reader test sees no diff lines")
            diff = ""
        hunks = {i: hunk_for(diff, c.path, c.line) for i, c in enumerate(payload.comments)}

        reader = None
        try:
            reader = parse_reader_result(self._runner(
                self._command,
                lambda path: build_reader_prompt(
                    payload_path=path,
                    comments=[(i, c, hunks[i]) for i, c in enumerate(payload.comments)],
                    body=payload.body,
                ),
                workdir=self._workdir,
            ))
        except Exception as e:
            warnings.append(f"reader test failed ({e}); rewriting on the word-and-shape check only")

        problems = {
            i: checked.remaining[i] + _reader_problems(reader.comments.get(i) if reader else None)
            for i in range(len(payload.comments))
        }
        body_problems = checked.body_remaining + _reader_problems(reader.body if reader else None)
        items = [
            RewriteItem(i, c, hunks[i], _blocking(problems[i]))
            for i, c in enumerate(payload.comments) if _blocking(problems[i])
        ]
        body_blocking = _blocking(body_problems)
        if not items and not body_blocking:
            return StageResult(payload, problems, body_problems, 0, warnings)

        try:
            new_bodies, new_body = parse_rewrite_result(self._runner(
                self._command,
                lambda path: build_rewrite_prompt(
                    payload_path=path, items=items, body=payload.body, body_problems=body_blocking,
                ),
                workdir=self._workdir,
            ))
        except Exception as e:
            warnings.append(f"rewrite failed ({e}); posting the review as written")
            return StageResult(payload, problems, body_problems, 0, warnings)

        comments = list(payload.comments)
        rewritten = 0
        for item in items:
            text = new_bodies.get(item.index)
            if text is None:
                continue
            original = comments[item.index]
            reason = guard(original.body, text)
            if reason:
                warnings.append(f"{original.path}:{original.line}: the rewrite {reason}; kept the original")
                continue
            comments[item.index] = replace(original, body=text)
            problems[item.index] = check_comment(text)
            rewritten += 1

        body = payload.body
        if body_blocking and new_body is not None:
            reason = guard(payload.body, new_body)
            if reason:
                warnings.append(f"review body: the rewrite {reason}; kept the original")
            else:
                body, body_problems = new_body, check_body(new_body)

        return StageResult(Payload(body=body, comments=comments, event=payload.event),
                           problems, body_problems, rewritten, warnings)


def format_report(result: StageResult) -> str:
    lines = [f"pr-review: plain language: {w}" for w in result.warnings]
    left = [
        f"  {c.path}:{c.line}  {p.level}: {p.detail}"
        for i, c in enumerate(result.payload.comments) for p in result.remaining.get(i, [])
    ] + [f"  review body  {p.level}: {p.detail}" for p in result.body_remaining]
    if left:
        lines.append(f"pr-review: plain language: {result.rewritten} comment(s) rewritten; problems left:")
        lines.extend(left)
    elif result.rewritten:
        lines.append(f"pr-review: plain language: {result.rewritten} comment(s) rewritten; no problems left.")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_plain_language_stage.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full suite** (nothing else should have changed)

Run: `uv run pytest`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pr_review/plain_language/stage.py tests/test_plain_language_stage.py
git commit -m "feat(pr-review): add the plain-language stage"
```

---

### Task 9: Review types use the new comment shape and the writing rules

**Files:**
- Modify: `src/pr_review/review_types/test_gap.py`, `infracode.py`, `golang.py`, `typescript.py`, `rust.py`, `python.py`
- Test: `tests/test_plain_language_rules.py`

**Interfaces:**
- Consumes: `writing_rules_block()` (Task 3).
- Produces: every registered type's `instructions()` ends with `writing_rules_block()`; no type contains `## Each inline comment must be self-contained` or a `**block:**` / `**Gap:**` example prefix.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_plain_language_rules.py`:

```python
import pytest

from pr_review.review_types import available, get_review_type


@pytest.mark.parametrize("name", available())
def test_every_review_type_includes_the_writing_rules(name):
    assert get_review_type(name).instructions().endswith(writing_rules_block())


@pytest.mark.parametrize("name", available())
def test_no_review_type_keeps_the_old_comment_shape(name):
    text = get_review_type(name).instructions()
    assert "## Each inline comment must be self-contained" not in text
    assert "**block:**" not in text
    assert "**Gap:**" not in text
    assert "**Impact:**" in text and "**Fix:**" in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_plain_language_rules.py -v`
Expected: the two new parametrised tests FAIL for all six types.

- [ ] **Step 3: Edit each type.** In each file, (a) replace the whole `## Each inline comment must be self-contained` section — from that heading up to, but not including, the next `##` heading — with the text given for that file, (b) replace the single `"body": "**block:** ...` (or `"body": "**Gap:** ...`) line in the `## Output (REQUIRED)` JSON example with the line given, and (c) change `instructions()` to `return _INSTRUCTIONS + "\n" + writing_rules_block()`, adding `from pr_review.plain_language.rules import writing_rules_block` to the imports.

**`test_gap.py`** — section:

~~~
## What goes in each comment

- Finding line: the gap, for example **`seal()` has no test for an empty key.**
- Impact: what could break without any test noticing.
- Evidence: optional; for example, the test file you checked and what it covers.
- Fix: a concrete test sketch (about 5-20 lines) in the repo's language and
  framework that the author can paste in, then one sentence that says what the
  test expects.

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

~~~

Example line:

~~~
       "body": "**<the gap>**\n\n**Impact:** ...\n\n**Fix:** ...\n\n```<lang>\n<sketch>\n```\n\n<what the test expects>"}
~~~

**`infracode.py`** — section:

~~~
## What goes in each comment

- Finding line: the urgency phrase for its severity (see the ladder below), then
  the risk: downtime, what else breaks, drift, or scope creep.
- Impact: what breaks, for whom, and when.
- Evidence: optional; the resource, plan output or command output that shows it.
- Fix: a concrete fix, ideally a one-line sketch (a `moved {}` block, a narrowed
  ARN + `Condition`, a YAML anchor, `templatefile()`).

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

~~~

Example line:

~~~
       "body": "**Fix before merge: <the risk>**\n\n**Impact:** ...\n\n**Evidence:** ...\n\n**Fix:** ...\n\n```hcl\n<sketch>\n```"}
~~~

**`golang.py`** — section:

~~~
## What goes in each comment

- Finding line: the urgency phrase for its severity (see the ladder below), then
  what actually goes wrong at runtime (a goroutine that never exits, a request
  that hangs, a matcher that stops matching), not the rule it violates.
- Impact: what breaks, for whom, and when.
- Evidence: optional; the line, call path or command output that shows it.
- Fix: a concrete fix, ideally a short Go sketch.

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

~~~

Example line:

~~~
       "body": "**Fix before merge: <what goes wrong>**\n\n**Impact:** ...\n\n**Evidence:** ...\n\n**Fix:** ...\n\n```go\n<sketch>\n```"}
~~~

**`typescript.py`** — section:

~~~
## What goes in each comment

- Finding line: the urgency phrase for its severity (see the ladder below), then
  what actually goes wrong at runtime (a crash on undefined, a payload that is
  never validated, a new union variant that no code handles), not the rule it
  violates.
- Impact: what breaks, for whom, and when.
- Evidence: optional; the line, call path or command output that shows it.
- Fix: a concrete fix, ideally a short TypeScript sketch.

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

~~~

Example line:

~~~
       "body": "**Fix before merge: <what goes wrong>**\n\n**Impact:** ...\n\n**Evidence:** ...\n\n**Fix:** ...\n\n```ts\n<sketch>\n```"}
~~~

**`rust.py`** — section:

~~~
## What goes in each comment

- Finding line: the urgency phrase for its severity (see the ladder below), then
  what actually goes wrong at runtime (a panic on hostile input, an executor that
  stops making progress, a use-after-free, a task whose error nobody sees), not
  the rule it violates.
- Impact: what breaks, for whom, and when.
- Evidence: optional; the line, call path or command output that shows it.
- Fix: a concrete fix, ideally a short Rust sketch.

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

~~~

Example line:

~~~
       "body": "**Fix before merge: <what goes wrong>**\n\n**Impact:** ...\n\n**Evidence:** ...\n\n**Fix:** ...\n\n```rust\n<sketch>\n```"}
~~~

**`python.py`** — section:

~~~
## What goes in each comment

- Finding line: the urgency phrase for its severity (see the ladder below), then
  what actually goes wrong at runtime (state shared between calls, an error that
  is caught and ignored, an event loop that stops, a patch that patches nothing),
  not the rule it violates.
- Impact: what breaks, for whom, and when.
- Evidence: optional; the line, call path or command output that shows it.
- Fix: a concrete fix, ideally a short Python sketch.

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

~~~

Example line:

~~~
       "body": "**Fix before merge: <what goes wrong>**\n\n**Impact:** ...\n\n**Evidence:** ...\n\n**Fix:** ...\n\n```python\n<sketch>\n```"}
~~~

- [ ] **Step 4: Run the review-type and rules tests**

Run: `uv run pytest tests/test_plain_language_rules.py tests/test_review_types.py -v`
Expected: all PASS. (`test_review_types.py` still finds `## Output (REQUIRED)`, `HARD CAP: 8 inline comments`, `## Severity ladder`, each axis and each toolchain command.)

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/review_types tests/test_plain_language_rules.py
git commit -m "feat(pr-review): teach every review type the plain-language comment shape"
```

---

### Task 10: Attribution footer and "How this review was made"

**Files:**
- Create: `src/pr_review/attribution.py`
- Test: `tests/test_attribution.py`

**Interfaces:**
- Consumes: `Source`, `Comment`, `Payload` (Task 1).
- Produces:
  - `JobRecord(source: Source, raw: int = 0, error: str | None = None)`
  - `RunRecord(jobs: list[JobRecord] = [], synthesis_model: str | None = None, plain_language_model: str | None = None, rewritten: int = 0)`
  - `attribution(sources: list[Source]) -> str`
  - `render_details(record: RunRecord, comments: list[Comment]) -> str`
  - `finalize(payload: Payload, record: RunRecord) -> Payload` — returns a new payload; the input is not changed.

- [ ] **Step 1: Write the failing tests** — create `tests/test_attribution.py`:

```python
from pr_review.attribution import JobRecord, RunRecord, attribution, finalize, render_details
from pr_review.payload import Comment, Payload, Source

OPUS = Source("claude", "claude-opus-5", "test-gap")
OPUS_INFRA = Source("claude", "claude-opus-5", "infracode")
SONNET = Source("claude", "claude-sonnet-5", "test-gap")
CODEX = Source("codex", "gpt-5.6-terra", "test-gap")


def test_one_source():
    assert attribution([OPUS]) == "<sub>Found by 1 model: claude</sub>"


def test_two_agents_list_agent_names_only():
    assert attribution([OPUS, CODEX]) == "<sub>Found by 2 models: claude, codex</sub>"


def test_one_agent_with_two_models_names_the_models():
    assert attribution([OPUS, SONNET]) == (
        "<sub>Found by 2 models: claude (claude-opus-5), claude (claude-sonnet-5)</sub>"
    )


def test_two_review_types_on_one_model_count_as_one_model():
    assert attribution([OPUS, OPUS_INFRA]) == "<sub>Found by 1 model: claude</sub>"


def test_no_known_source():
    assert attribution([]) == "<sub>Found by pr-review</sub>"


def test_details_list_every_job_with_found_and_posted_counts():
    record = RunRecord(jobs=[JobRecord(OPUS, raw=3), JobRecord(CODEX, error="boom\ntrace")])
    comments = [Comment("a", 1, "x", sources=[OPUS]), Comment("b", 2, "y", sources=[OPUS, CODEX])]
    text = render_details(record, comments)
    assert text.startswith("<details>\n<summary>How this review was made</summary>")
    assert "| claude | claude-opus-5 | test-gap | 3 found, 2 posted |" in text
    assert "| codex | gpt-5.6-terra | test-gap | failed: boom |" in text
    assert text.rstrip().endswith("</details>")
    assert "Synthesis" not in text and "Plain language" not in text


def test_details_mention_synthesis_and_plain_language_when_they_ran():
    record = RunRecord(jobs=[JobRecord(OPUS, raw=1), JobRecord(CODEX, raw=1)],
                       synthesis_model="claude-opus-5", plain_language_model="claude-opus-5", rewritten=2)
    comments = [Comment("b", 2, "y", sources=[OPUS, CODEX])]
    text = render_details(record, comments)
    assert "Synthesis: `claude-opus-5`" in text
    assert "1 posted finding(s) were raised by two or more models." in text
    assert "Plain language: `claude-opus-5`" in text and "rewrote 2" in text


def test_a_pipe_in_an_error_does_not_break_the_table():
    text = render_details(RunRecord(jobs=[JobRecord(CODEX, error="a | b")]), [])
    assert "failed: a \\| b" in text


def test_finalize_appends_footers_and_details_without_changing_the_input():
    p = Payload(body="Verdict.", comments=[Comment("a", 1, "**X.**", sources=[OPUS, CODEX])])
    out = finalize(p, RunRecord(jobs=[JobRecord(OPUS, raw=1), JobRecord(CODEX, raw=1)]))
    assert out.comments[0].body == "**X.**\n\n<sub>Found by 2 models: claude, codex</sub>"
    assert out.body.startswith("Verdict.\n\n<details>")
    assert p.comments[0].body == "**X.**"
    assert (out.comments[0].path, out.comments[0].line) == ("a", 1)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_attribution.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/attribution.py`**:

```python
"""Model attribution: a footer on each comment and a collapsed record of the run."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

from pr_review.payload import Comment, Payload, Source


@dataclass
class JobRecord:
    source: Source
    raw: int = 0
    error: str | None = None


@dataclass
class RunRecord:
    jobs: list[JobRecord] = field(default_factory=list)
    synthesis_model: str | None = None
    plain_language_model: str | None = None
    rewritten: int = 0


def _models(sources: list[Source]) -> list[tuple[str, str]]:
    return list(dict.fromkeys((s.agent, s.model) for s in sources))


def attribution(sources: list[Source]) -> str:
    models = _models(sources)
    if not models:
        return "<sub>Found by pr-review</sub>"
    per_agent = Counter(agent for agent, _ in models)
    names = [f"{a} ({m})" if per_agent[a] > 1 and m else a for a, m in models]
    noun = "model" if len(models) == 1 else "models"
    return f"<sub>Found by {len(models)} {noun}: {', '.join(names)}</sub>"


def _cell(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first[:120].replace("|", "\\|")


def render_details(record: RunRecord, comments: list[Comment]) -> str:
    lines = [
        "<details>", "<summary>How this review was made</summary>", "",
        "| Agent | Model | Review type | Result |", "|---|---|---|---|",
    ]
    for job in record.jobs:
        s = job.source
        if job.error is not None:
            result = f"failed: {_cell(job.error)}"
        else:
            posted = sum(1 for c in comments if s in c.sources)
            result = f"{job.raw} found, {posted} posted"
        lines.append(f"| {s.agent} | {s.model or '(default)'} | {s.review_type} | {result} |")
    if record.synthesis_model:
        shared = sum(1 for c in comments if len(_models(c.sources)) > 1)
        lines += ["", (
            f"Synthesis: `{record.synthesis_model}` merged the findings, removed duplicates "
            f"and dropped findings it could not confirm in the code. {shared} posted "
            "finding(s) were raised by two or more models."
        )]
    if record.plain_language_model:
        lines += ["", (
            f"Plain language: `{record.plain_language_model}` read every comment as a new "
            f"reader would, and rewrote {record.rewritten} of them."
        )]
    lines += ["", "</details>"]
    return "\n".join(lines)


def finalize(payload: Payload, record: RunRecord) -> Payload:
    comments = [
        replace(c, body=f"{c.body.rstrip()}\n\n{attribution(c.sources)}")
        for c in payload.comments
    ]
    body = f"{payload.body.rstrip()}\n\n{render_details(record, payload.comments)}"
    return Payload(body=body, comments=comments, event=payload.event)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_attribution.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/attribution.py tests/test_attribution.py
git commit -m "feat(pr-review): add the attribution footer and the run record block"
```

---

### Task 11: The orchestrator stamps sources; collation headings

**Files:**
- Modify: `src/pr_review/orchestrator.py`, `src/pr_review/collate.py`
- Test: `tests/test_orchestrator.py`, `tests/test_collate.py`

**Interfaces:**
- Consumes: `Source` (Task 1), `JobRecord` (Task 10).
- Produces:
  - Every comment in a successful job's payload has `sources == [Source(reviewer.name, model, review_type.name)]` before collation.
  - `RunResult(payload, failures, jobs: list[JobRecord])` — `jobs` in job order, `raw` = the job's comment count, `error` set for a failed job.
  - The body no longer gets the "⚠️ N review job(s) failed" line.
  - Overflow heading in both collators: `## Other findings not posted as comments`.

- [ ] **Step 1: Update and add tests.** In `tests/test_orchestrator.py`, replace `test_partial_failure_keeps_successes_and_notes_failure` with:

```python
def test_partial_failure_keeps_successes_and_records_the_failure():
    jobs = [
        ReviewJob(FakeReviewer("claude"), FakeType("test-gap"), "m1", []),
        ReviewJob(BoomReviewer(), FakeType("infracode"), "m2", []),
    ]
    result = _run(jobs)
    assert result.payload is not None
    assert "claude/test-gap" in result.payload.body
    assert "excluded" not in result.payload.body
    assert len(result.failures) == 1
    assert result.failures[0][0] == "boom (m2)"
    assert [j.error is None for j in result.jobs] == [True, False]
    assert "kaboom" in result.jobs[1].error


def test_each_comment_carries_its_job_source():
    from pr_review.payload import Source

    result = _run([ReviewJob(FakeReviewer("claude"), FakeType("test-gap"), "m1", [])])
    assert result.payload.comments[0].sources == [Source("claude", "m1", "test-gap")]
    assert result.jobs[0].raw == 1
```

In `tests/test_collate.py`, change the last assertion of `test_merge_reapplies_cap_and_lists_overflow` to:

```python
    assert "## Other findings not posted as comments" in out.body
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_orchestrator.py tests/test_collate.py -v`
Expected: the new/changed tests FAIL.

- [ ] **Step 3: Implement.** In `src/pr_review/orchestrator.py`:

```python
from dataclasses import dataclass, field

from pr_review.attribution import JobRecord
from pr_review.payload import Payload, Source
```

```python
@dataclass
class RunResult:
    payload: Payload | None  # collated successes; None when every job failed
    failures: list[tuple[str, str, str]]  # (label, review_type_name, error)
    jobs: list[JobRecord] = field(default_factory=list)
```

Replace `_one` and everything after the `with ThreadPoolExecutor(...)` block with:

```python
    def _one(job: ReviewJob):
        label = _label(job.reviewer.name, job.model)
        source = Source(job.reviewer.name, job.model, job.review_type.name)
        try:
            payload = job.reviewer.review(
                workdir=workdir, base=base, owner=owner, repo=repo, number=number,
                review_type=job.review_type, model=job.model, extra_flags=job.extra_flags,
            )
            for comment in payload.comments:
                comment.sources = [source]
            return ("ok", label, job.review_type.name, payload, source)
        except Exception as e:  # a failed job must not abort the whole run
            return ("err", label, job.review_type.name, str(e), source)

    with ThreadPoolExecutor(max_workers=max_workers or len(jobs) or 1) as ex:
        outcomes = list(ex.map(_one, jobs))

    successes: list[Job] = [
        (label, rt, result) for kind, label, rt, result, _ in outcomes if kind == "ok"
    ]
    failures: list[tuple[str, str, str]] = [
        (label, rt, result) for kind, label, rt, result, _ in outcomes if kind == "err"
    ]
    records = [
        JobRecord(source, raw=len(result.comments)) if kind == "ok"
        else JobRecord(source, error=result)
        for kind, _, _, result, source in outcomes
    ]

    if not successes:
        return RunResult(payload=None, failures=failures, jobs=records)
    return RunResult(payload=collator.collate(successes), failures=failures, jobs=records)
```

Update the module docstring's last sentence to: "A failing job never aborts the run: its error is recorded in `RunResult.jobs`, the surviving jobs still produce a review, and only when every job fails is there no payload."

In `src/pr_review/collate.py`, change the overflow heading string to `"\n\n---\n\n## Other findings not posted as comments\n\n"`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_orchestrator.py tests/test_collate.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/orchestrator.py src/pr_review/collate.py tests/test_orchestrator.py tests/test_collate.py
git commit -m "feat(pr-review): stamp each finding with its source and record every job"
```

---

### Task 12: Synthesis returns sources, not a prefix

**Files:**
- Modify: `src/pr_review/synthesis.py`
- Test: `tests/test_synthesis.py`

**Interfaces:**
- Consumes: `run_cli_json` (Task 2), `payload_from_dict`, `Source` (Task 1), `writing_rules_block()` (Task 3), stamped sources (Task 11).
- Produces:
  - `LLMSynthesisCollator(..., runner=run_cli_json)`; the runner returns parsed JSON (a dict), not a `Payload`.
  - `LLMSynthesisCollator.ran: bool` — `True` only when the judge's output was used.
  - Each synthesised comment's `sources` is mapped from the judge's `"sources"` labels (`"<label> [<review-type>]"`); unknown labels are dropped; a comment with none left gets `[]` and a stderr warning.
  - The prompt contains `writing_rules_block()`, asks for `"sources"`, and no longer asks for `[N models: …]` labels or a `## Review stats` section.

- [ ] **Step 1: Update the tests.** In `tests/test_synthesis.py`:

Change `_job` so its comments carry a source, matching what the orchestrator now does:

```python
from pr_review.payload import Source


def _job(label, rtype, n):
    agent = label.split(" ")[0]
    src = Source(agent, "m", rtype)
    return (label, rtype, Payload(body=f"{label} body",
                                  comments=[Comment("f.py", i, f"c{i}", sources=[src]) for i in range(n)]))
```

In `test_build_synthesis_prompt_has_context_findings_and_instructions`, replace `assert "## Review stats" in prompt` with:

```python
    assert "## Review stats" not in prompt
    assert "[2 models:" not in prompt
    assert '"sources"' in prompt
    assert "## How to write each comment (REQUIRED)" in prompt
```

In `test_synthesis_runs_judge_for_multiple_jobs`, make the runner return a dict:

```python
        return {"body": "SYNTH", "comments": [{"path": "a", "line": 1, "body": "merged"}]}
```

In `test_synthesis_caps_judge_output_to_eight`, return a dict and change the heading:

```python
    def runner(command, build_prompt, *, workdir):
        return {"body": "SYNTH",
                "comments": [{"path": "f.py", "line": i, "body": f"c{i}"} for i in range(11)]}
    ...
    assert "## Other findings not posted as comments" in out.body
```

Append:

```python
def test_synthesis_maps_judge_sources_back_to_jobs(capsys):
    def runner(command, build_prompt, *, workdir):
        return {"body": "SYNTH", "comments": [
            {"path": "a", "line": 1, "body": "both",
             "sources": ["claude (opus) [test-gap]", "codex [test-gap]", "ghost [x]"]},
            {"path": "b", "line": 2, "body": "nobody", "sources": ["ghost [x]"]},
        ]}

    jobs = [_job("claude (opus)", "test-gap", 1), _job("codex", "test-gap", 1)]
    collator = _collator(runner)
    out = collator.collate(jobs)
    assert out.comments[0].sources == [Source("claude", "m", "test-gap"), Source("codex", "m", "test-gap")]
    assert out.comments[1].sources == []
    assert "no known source for b:2" in capsys.readouterr().err
    assert collator.ran is True


def test_ran_is_false_for_a_single_job_and_after_a_fallback():
    single = _collator(lambda *a, **k: None)
    single.collate([_job("claude (opus)", "test-gap", 1)])
    assert single.ran is False

    def boom(*a, **k):
        raise RuntimeError("judge died")

    failed = _collator(boom)
    failed.collate([_job("claude (opus)", "test-gap", 1), _job("codex", "test-gap", 1)])
    assert failed.ran is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_synthesis.py -v`
Expected: FAIL (`ran` missing, prompt still asks for stats, dict runner result not handled).

- [ ] **Step 3: Implement.** In `src/pr_review/synthesis.py`:

Imports:

```python
from pr_review.payload import Payload, Source, cap_comments, payload_from_dict
from pr_review.plain_language.rules import writing_rules_block
from pr_review.reviewers._run import run_cli_json
```

In `_INSTRUCTIONS`, replace step 4 ("Confidence: …" and its three bullets) with:

```
4. Keep a finding only if you verified it against the code. A finding raised by
   two or more models is more likely to be real, but verify it too.
```

Delete the whole `## Stats (REQUIRED)` section. Replace the `## Output (REQUIRED)` JSON example with:

```
  {
    "event": "COMMENT",
    "body": "<verdict + any overflow list>",
    "comments": [
      {"path": "relative/path", "line": N, "side": "RIGHT",
       "sources": ["<label> [<review-type>]", "..."],
       "body": "**<finding line>**\n\n**Impact:** ...\n\n**Evidence:** ...\n\n**Fix:** ..."}
    ]
  }

"sources" lists every source whose findings this comment merges, each written
exactly as it appears after "### Source: " below, up to but not including " — ".
Do not name models in the comment body; pr-review adds that itself.
```

Also change the overflow heading in step 5 of `_INSTRUCTIONS` to `"## Other findings not posted as comments"`, and make `_cap_payload` give each overflow bullet its finding line, not a bare `path:line` (import `_first_line` from `pr_review.collate`):

```python
def _cap_payload(payload: Payload) -> Payload:
    """Enforce the inline-comment cap on a synthesised payload (defensive)."""
    kept, overflow = cap_comments(payload.comments)
    if overflow:
        payload.comments = kept
        payload.body += (
            "\n\n---\n\n## Other findings not posted as comments\n\n"
            + "\n".join(f"- `{c.path}:{c.line}` — {_first_line(c.body)}" for c in overflow)
        )
    return payload
```

Add to the test file:

```python
def test_overflow_bullets_carry_the_finding_line():
    def runner(command, build_prompt, *, workdir):
        return {"body": "SYNTH",
                "comments": [{"path": "f.py", "line": i, "body": f"**Finding {i}.**\n\nmore"} for i in range(9)]}

    out = _collator(runner).collate([_job("claude (opus)", "test-gap", 1), _job("codex", "test-gap", 1)])
    assert "- `f.py:8` — **Finding 8.**" in out.body
```

In `build_synthesis_prompt`, return:

```python
    return f"{context}\n{_INSTRUCTIONS}\n{writing_rules_block()}\n## Findings to consolidate\n\n{findings}\n"
```

Add a helper and rewrite `LLMSynthesisCollator` (constructor default runner, `ran`, and `collate`):

```python
def _sources_by_key(jobs: list[Job]) -> dict[str, Source]:
    by_key: dict[str, Source] = {}
    for label, rtype, payload in jobs:
        for c in payload.comments:
            if c.sources:
                by_key[f"{label} [{rtype}]"] = c.sources[0]
                break
    return by_key


def _map_sources(labels: object, by_key: dict[str, Source]) -> list[Source]:
    found: list[Source] = []
    for label in labels if isinstance(labels, list) else []:
        source = by_key.get(label) if isinstance(label, str) else None
        if source is not None and source not in found:
            found.append(source)
    return found
```

```python
    def __init__(self, *, command, workdir, owner, repo, number, base,
                 runner: Callable[..., object] = run_cli_json):
        # ... existing assignments ...
        self.ran = False

    def collate(self, jobs: list[Job]) -> Payload:
        if len(jobs) <= 1:
            return DeterministicMergeCollator().collate(jobs)

        findings = serialize_findings(jobs)

        def build(payload_path: str) -> str:
            return build_synthesis_prompt(
                owner=self._owner, repo=self._repo, number=self._number,
                base=self._base, payload_path=payload_path, findings=findings,
            )

        try:
            data = self._runner(self._command, build, workdir=self._workdir)
            payload = payload_from_dict(data)
        except Exception as e:
            print(
                f"pr-review: synthesis failed ({self._command[0]}: {e}); "
                "falling back to the raw merge.",
                file=sys.stderr,
            )
            return DeterministicMergeCollator().collate(jobs)

        by_key = _sources_by_key(jobs)
        raw = data.get("comments")
        raw = raw if isinstance(raw, list) else []
        for i, comment in enumerate(payload.comments):
            entry = raw[i] if i < len(raw) and isinstance(raw[i], dict) else {}
            comment.sources = _map_sources(entry.get("sources"), by_key)
            if not comment.sources:
                print(
                    f"pr-review: synthesis gave no known source for "
                    f"{comment.path}:{comment.line}; its footer will say pr-review.",
                    file=sys.stderr,
                )
        self.ran = True
        return _cap_payload(payload)
```

Remove the now-unused `run_cli_payload` import.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_synthesis.py tests/test_cli.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/synthesis.py tests/test_synthesis.py
git commit -m "feat(pr-review): have the judge return sources instead of a label prefix"
```

---

### Task 13: Wire the stage, attribution and flags into the CLI

**Files:**
- Modify: `src/pr_review/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `PlainLanguageStage`, `check_payload`, `format_report` (Task 8), `RunRecord`, `finalize` (Task 10), `RunResult.jobs` (Task 11), `LLMSynthesisCollator.ran` (Task 12).
- Produces:
  - `RunConfig.plain_language_model: tuple[str, str] | None` (None = follow `synthesis_model`), `RunConfig.no_plain_language: bool`.
  - Flags `--plain-language-model AGENT[=MODEL]` and `--no-plain-language`.
  - `build_plain_language_stage(cfg, *, workdir, base) -> PlainLanguageStage | None`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_cli.py`:

```python
def test_config_plain_language_defaults():
    cfg = config_from_args(["org/repo#1"])
    assert cfg.plain_language_model is None
    assert cfg.no_plain_language is False


def test_config_plain_language_model_and_off_switch():
    cfg = config_from_args(["--plain-language-model", "codex=gpt-5", "--no-plain-language", "org/repo#1"])
    assert cfg.plain_language_model == ("codex", "gpt-5")
    assert cfg.no_plain_language is True


def test_plain_language_stage_follows_the_synthesis_model_by_default():
    from pr_review.cli import build_plain_language_stage

    cfg = config_from_args(["--synthesis-model", "codex=gpt-5", "org/repo#1"])
    stage = build_plain_language_stage(cfg, workdir="/wd", base="b")
    assert stage._command[:4] == ["codex", "exec", "--model", "gpt-5"]


def test_plain_language_model_overrides_the_synthesis_model():
    from pr_review.cli import build_plain_language_stage

    cfg = config_from_args(["--synthesis-model", "codex=gpt-5",
                            "--plain-language-model", "claude=claude-sonnet-5", "org/repo#1"])
    stage = build_plain_language_stage(cfg, workdir="/wd", base="b")
    assert stage._command[:4] == ["claude", "--print", "--model", "claude-sonnet-5"]


def test_no_plain_language_builds_no_stage():
    from pr_review.cli import build_plain_language_stage

    cfg = config_from_args(["--no-plain-language", "org/repo#1"])
    assert build_plain_language_stage(cfg, workdir="/wd", base="b") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** In `src/pr_review/cli.py`:

Imports:

```python
from pr_review.attribution import RunRecord, finalize
from pr_review.plain_language.stage import PlainLanguageStage, check_payload, format_report
```

`RunConfig` gains:

```python
    plain_language_model: tuple[str, str] | None
    no_plain_language: bool
```

In `build_parser`, after `--no-synthesis`:

```python
    p.add_argument(
        "--plain-language-model", metavar="AGENT[=MODEL]", default=None,
        help=(
            "agent/model for the plain-language reader test and rewrite "
            "(default: the synthesis model)"
        ),
    )
    p.add_argument(
        "--no-plain-language", action="store_true",
        help=(
            "skip the plain-language reader test and rewrite; the word-and-shape "
            "check still reports (default: false)"
        ),
    )
```

In `config_from_args`'s `RunConfig(...)`:

```python
        plain_language_model=(
            _parse_synthesis_model(args.plain_language_model)
            if args.plain_language_model else None
        ),
        no_plain_language=args.no_plain_language,
```

Add after `build_collator`:

```python
def _plain_language_pair(cfg: RunConfig) -> tuple[str, str]:
    return cfg.plain_language_model or cfg.synthesis_model


def build_plain_language_stage(cfg: RunConfig, *, workdir: str, base: str) -> PlainLanguageStage | None:
    if cfg.no_plain_language:
        return None
    agent, model = _plain_language_pair(cfg)
    command = get_reviewer(agent).command(model, cfg.flags_by_agent.get(agent, []))
    return PlainLanguageStage(command=command, workdir=workdir, base=base)
```

In `main`, replace everything from `collator = build_collator(...)` to the end with:

```python
    collator = build_collator(cfg, workdir=checkout.workdir, base=checkout.base)
    stage = build_plain_language_stage(cfg, workdir=checkout.workdir, base=checkout.base)
    staged = None
    try:
        result = run_reviews(
            jobs=jobs, workdir=checkout.workdir, base=checkout.base,
            owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number,
            collator=collator,
        )
        # The stage reads diff hunks from the clone, so it runs before cleanup.
        if result.payload is not None:
            staged = stage.apply(result.payload) if stage else check_payload(result.payload)
    finally:
        if cfg.keep:
            print(f"pr-review: kept checkout at {checkout.workdir}", file=sys.stderr)
        else:
            cleanup(checkout)

    for label, rtype, err in result.failures:
        print(f"pr-review: {label} / {rtype} failed: {err}", file=sys.stderr)

    if staged is None:
        print(
            f"pr-review: all {len(jobs)} review job(s) failed; no review produced.",
            file=sys.stderr,
        )
        return 1

    report = format_report(staged)
    if report:
        print(report, file=sys.stderr)

    agent, model = _plain_language_pair(cfg)
    record = RunRecord(
        jobs=result.jobs,
        synthesis_model=(cfg.synthesis_model[1] or cfg.synthesis_model[0])
        if getattr(collator, "ran", False) else None,
        plain_language_model=(model or agent) if stage else None,
        rewritten=staged.rewritten,
    )
    payload = finalize(staged.payload, record)

    output.show_review(payload)
    mode = output.decide_mode(
        yes=cfg.yes, no_post=cfg.no_post, has_tty=output.tty_available()
    )
    return output.dispatch(mode, cfg.target, payload)
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest`
Expected: all PASS. `test_help_shows_default_values` must still pass: both new flags' help text contains `(default:`.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/cli.py tests/test_cli.py
git commit -m "feat(pr-review): run the plain-language stage and add attribution before posting"
```

---

### Task 14: Documentation

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Count the tests**

Run: `uv run pytest -q | tail -1` and `ls tests/test_*.py | wc -l`
Note both numbers.

- [ ] **Step 2: Update `CLAUDE.md`'s Test suite walkthrough.** Change the header line to the new file and test counts. Update the existing entries:

- **test_payload.py** — add: "`Source`, `Comment.sources` (never in `to_dict`), and `payload_from_dict`."
- **test_run.py** — add: "`run_cli_json` follows the same file-is-the-contract rules for any JSON."
- **test_collate.py** — overflow heading is now "Other findings not posted as comments".
- **test_orchestrator.py** — replace "partial failures keep the successes and note them in the body" with "partial failures keep the successes and are recorded in `RunResult.jobs`; every comment carries its job's `Source`".
- **test_synthesis.py** — replace the collate description with "the judge's `sources` labels map back to jobs (unknown labels dropped, none left warns), `ran` is true only when the judge's output was used, and the prompt carries the writing rules instead of label prefixes and a stats section".
- **test_cli.py** — add "`--plain-language-model` (defaults to the synthesis model) / `--no-plain-language` and `build_plain_language_stage`".

Add new entries:

- **test_plain_language_rules.py** — `rules.json` loads with the spec's thresholds, labels and urgency phrases; every blocking word matches its display word; repo terms (drift, root, state lock) are not listed; the rendered block names every label, threshold, word and phrase and writes its own negatives in full; every registered review type ends with the block and no longer has the old comment shape.
- **test_plain_language_check.py** — the deterministic check: a plain comment passes; contractions, listed words, sentences over 35 words, a missing bold finding line and missing Impact/Fix are blocking; 26–35 words is minor; Evidence is optional; code is never checked; repo terms pass; list items, headings and tables split correctly.
- **test_plain_language_hunks.py** — `hunk_for` finds the hunk around a new-file line across files, ignores removed lines when counting, limits context, and returns nothing outside the diff; `git_diff` builds a three-dot diff in the workdir through a fake runner.
- **test_plain_language_reader.py** — the reader prompt shows each comment beside its diff lines and asks the three questions; parsing keeps blocking/minor per comment and for the body and ignores malformed entries.
- **test_plain_language_rewrite.py** — the rewrite prompt lists problems and the writing rules and asks for null when the body needs no rewrite; parsing; guards reject a changed code block, a dropped inline code span or an empty rewrite.
- **test_plain_language_stage.py** — with a fake runner: no blocking problem means no rewrite call; only blocking comments are sent; a reader blocking problem triggers a rewrite; path, line, side and sources never change; a guard failure keeps the original; a failed reader call still rewrites on the check; a failed rewrite posts as written; the check runs again after the rewrite; the body is rewritten; the stderr report.
- **test_attribution.py** — the footer for one source, two agents, one agent with two models, two review types on one model, and no source; the "How this review was made" block lists every job with found/posted counts or its failure, and mentions synthesis and plain language only when they ran; a pipe in an error is escaped; `finalize` appends both without changing its input.

- [ ] **Step 3: Update `README.md`.** In **Collating multiple models**, replace the sentence about confidence labels and `## Review stats` with:

```markdown
each comment ends with a small footer naming the models that found it
(`Found by 2 models: claude, codex`), and the body ends with a collapsed
**How this review was made** block listing every job, its review type, how many
findings it raised and how many were posted.
```

Add a new section after it:

```markdown
### Plain language

Every comment is written for an engineer who did not write the code and does not
know this part of the system. Each one has a bold finding line, then **Impact**,
an optional **Evidence**, and **Fix**. After collation pr-review checks every
comment for listed jargon, contractions and long sentences, has a model read each
comment beside its diff lines as a new reader would, and rewrites only the
comments that reader could not act on. Anything left is listed on stderr before
you confirm the post. The rules and word list are in
`src/pr_review/plain_language/rules.json`.

- `--plain-language-model AGENT[=MODEL]` — the reader and rewriter (default: the synthesis model).
- `--no-plain-language` — skip the reader test and rewrite; the word-and-shape check still reports.
```

Add two rows to the **Options** table:

```markdown
| `--plain-language-model agent[=model]` | Reader test and rewrite model | the synthesis model |
| `--no-plain-language` | Skip the reader test and rewrite | off |
```

- [ ] **Step 4: Run the full suite one last time**

Run: `uv run pytest`
Expected: all PASS, count matches `CLAUDE.md`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs(pr-review): document plain language and attribution"
```

- [ ] **Step 6: Manual check (not automated).** Run `pr-review --print-only --review-type infracode --model claude,codex <a PR you own>` and confirm: every comment starts with a bold finding line, has Impact and Fix, ends with a `Found by …` footer, and the body ends with a collapsed "How this review was made" block; stderr lists any problems left.
