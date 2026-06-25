# pr-review Multi-LLM Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `test-gap-review` bash script with `pr-review`, a uv-managed Python package that reviews a named GitHub PR in an isolated clone, fans out to `(reviewer × review-type)` jobs in parallel, and collates them into one review.

**Architecture:** Pure-logic core (target parsing, payload model, collation, posting-mode decision) wrapped by thin side-effecting shells (git/gh/claude subprocesses). A `Reviewer` registry and a `ReviewType` registry make new LLM backends and review types additive. An orchestrator fans jobs out over a `ThreadPoolExecutor` against one shared read-only checkout, then a `Collator` merges the payloads.

**Tech Stack:** Python 3.14, uv (project + venv + lockfile), pytest, hatchling build backend, stdlib-only runtime (no third-party runtime deps), `git`/`gh`/`claude` CLIs invoked as subprocesses, mise for tasks.

## Global Constraints

- Python floor: `requires-python = ">=3.14"`.
- Runtime dependencies: **none** (stdlib only). pytest is a dev-only dependency.
- Package name: `pr_review` (importable). Command name: `pr-review`. Alias command: `test-gap-review` (injects `--type test-gap`).
- Build backend: `hatchling`; wheel package path `src/pr_review`.
- Default model id: `claude-opus-4-8` (env `MODEL` overrides).
- Inline comment cap: `MAX_INLINE_COMMENTS = 8`, re-applied across the merged set.
- Review payload schema (unchanged from the bash tool):
  `{"event": "COMMENT", "body": <str>, "comments": [{"path": <str>, "line": <int>, "side": "RIGHT", "body": <str>}]}`.
- Env knobs: `MODEL`, `YES=1` (post), `NO_POST=1` (review-only), `CLAUDE_FLAGS` (extra claude flags), `KEEP=1` (keep temp clone).
- Clone strategy: `git clone --filter=blob:none` into a unique temp dir; delete on exit unless `KEEP=1`.
- Input: explicit target only — a PR URL or `owner/repo#N`. No cwd/branch inference, no non-PR branch mode.
- Registration is import-side-effect: importing `pr_review.reviewers` / `pr_review.review_types` registers the built-ins.

---

### Task 1: Project scaffold + target parsing

**Files:**
- Create: `pyproject.toml`
- Create: `mise.toml`
- Create: `src/pr_review/__init__.py`
- Create: `src/pr_review/target.py`
- Test: `tests/test_target.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `pr_review.target.Target(owner: str, repo: str, number: int)` with property `slug -> str` (`"owner/repo"`); `pr_review.target.parse_target(text: str) -> Target` (raises `ValueError` on unrecognised input).

- [ ] **Step 1: Create the project scaffold**

`pyproject.toml`:

```toml
[project]
name = "pr-review"
version = "0.1.0"
description = "Multi-LLM, multi-type GitHub PR reviewer"
requires-python = ">=3.14"
dependencies = []

[project.scripts]
pr-review = "pr_review.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pr_review"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`mise.toml` (install task is added in Task 10):

```toml
[tools]
python = "3.14"
uv = "latest"

[tasks.test]
description = "Run the test suite"
run = "uv run pytest"
```

`src/pr_review/__init__.py`:

```python
"""pr-review: multi-LLM, multi-type GitHub PR reviewer."""
```

- [ ] **Step 2: Write the failing test**

`tests/test_target.py`:

```python
import pytest

from pr_review.target import Target, parse_target


def test_parse_pr_url():
    t = parse_target("https://github.com/org/repo/pull/214")
    assert t == Target("org", "repo", 214)


def test_parse_pr_url_trailing_slash():
    t = parse_target("https://github.com/org/repo/pull/214/")
    assert t.number == 214


def test_parse_short_form():
    t = parse_target("org/repo#9")
    assert t == Target("org", "repo", 9)
    assert t.slug == "org/repo"


def test_parse_strips_whitespace():
    assert parse_target("  org/repo#1  ").number == 1


@pytest.mark.parametrize("bad", ["org/repo", "214", "https://example.com/x", "org/repo#"])
def test_parse_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_target(bad)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_target.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.target'`.

- [ ] **Step 4: Write minimal implementation**

`src/pr_review/target.py`:

```python
"""Parse a PR target string into (owner, repo, number)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)/?$"
)
_SHORT_RE = re.compile(r"^(?P<owner>[^/\s]+)/(?P<repo>[^/#\s]+)#(?P<number>\d+)$")


@dataclass(frozen=True)
class Target:
    owner: str
    repo: str
    number: int

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_target(text: str) -> Target:
    text = text.strip()
    for rx in (_URL_RE, _SHORT_RE):
        m = rx.match(text)
        if m:
            return Target(m["owner"], m["repo"], int(m["number"]))
    raise ValueError(
        f"unrecognised PR target: {text!r}\n"
        "expected a PR URL (https://github.com/owner/repo/pull/N) or owner/repo#N"
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_target.py -v`
Expected: PASS (5 tests / parametrized cases green).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml mise.toml src/pr_review/__init__.py src/pr_review/target.py tests/test_target.py
git commit -m "feat(pr-review): scaffold uv project and PR target parsing"
```

---

### Task 2: Payload model, validation, and comment cap

**Files:**
- Create: `src/pr_review/payload.py`
- Test: `tests/test_payload.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `MAX_INLINE_COMMENTS = 8`
  - `Comment(path: str, line: int, body: str, side: str = "RIGHT")` with `.to_dict() -> dict`
  - `Payload(body: str, comments: list[Comment] = [], event: str = "COMMENT")` with `.to_dict() -> dict` and `.to_json() -> str`
  - `parse_payload(text: str) -> Payload` (raises `ValueError` on malformed input)
  - `cap_comments(comments: list[Comment], limit: int = MAX_INLINE_COMMENTS) -> tuple[list[Comment], list[Comment]]` returning `(kept, overflow)`

- [ ] **Step 1: Write the failing test**

`tests/test_payload.py`:

```python
import pytest

from pr_review.payload import (
    MAX_INLINE_COMMENTS,
    Comment,
    Payload,
    cap_comments,
    parse_payload,
)


def test_payload_to_dict_roundtrip_shape():
    p = Payload(body="hi", comments=[Comment("a.py", 3, "gap")])
    d = p.to_dict()
    assert d["event"] == "COMMENT"
    assert d["body"] == "hi"
    assert d["comments"] == [{"path": "a.py", "line": 3, "side": "RIGHT", "body": "gap"}]


def test_parse_valid_payload():
    raw = '{"event":"COMMENT","body":"b","comments":[{"path":"x.py","line":2,"side":"RIGHT","body":"g"}]}'
    p = parse_payload(raw)
    assert p.body == "b"
    assert p.comments[0].path == "x.py"
    assert p.comments[0].line == 2


def test_parse_missing_comments_defaults_empty():
    assert parse_payload('{"body":"only body"}').comments == []


def test_parse_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_payload("not json")


def test_parse_rejects_missing_body():
    with pytest.raises(ValueError):
        parse_payload('{"comments":[]}')


def test_parse_rejects_comment_missing_path():
    with pytest.raises(ValueError):
        parse_payload('{"body":"b","comments":[{"line":1,"body":"g"}]}')


def test_cap_splits_at_limit():
    comments = [Comment("f", i, "g") for i in range(10)]
    kept, overflow = cap_comments(comments)
    assert len(kept) == MAX_INLINE_COMMENTS
    assert len(overflow) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_payload.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.payload'`.

- [ ] **Step 3: Write minimal implementation**

`src/pr_review/payload.py`:

```python
"""PR review payload: model, JSON validation, and the inline-comment cap."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

MAX_INLINE_COMMENTS = 8


@dataclass
class Comment:
    path: str
    line: int
    body: str
    side: str = "RIGHT"

    def to_dict(self) -> dict:
        return {"path": self.path, "line": self.line, "side": self.side, "body": self.body}


@dataclass
class Payload:
    body: str
    comments: list[Comment] = field(default_factory=list)
    event: str = "COMMENT"

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "body": self.body,
            "comments": [c.to_dict() for c in self.comments],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def parse_payload(text: str) -> Payload:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"payload is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    if not isinstance(data.get("body"), str):
        raise ValueError("payload must have a string 'body'")
    raw_comments = data.get("comments", [])
    if not isinstance(raw_comments, list):
        raise ValueError("payload 'comments' must be a list")
    comments: list[Comment] = []
    for i, c in enumerate(raw_comments):
        if not isinstance(c, dict):
            raise ValueError(f"comment {i} must be an object")
        try:
            comments.append(
                Comment(path=c["path"], line=int(c["line"]), body=c["body"],
                        side=c.get("side", "RIGHT"))
            )
        except KeyError as e:
            raise ValueError(f"comment {i} missing field {e}") from e
    return Payload(body=data["body"], comments=comments, event=data.get("event", "COMMENT"))


def cap_comments(
    comments: list[Comment], limit: int = MAX_INLINE_COMMENTS
) -> tuple[list[Comment], list[Comment]]:
    return comments[:limit], comments[limit:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_payload.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/payload.py tests/test_payload.py
git commit -m "feat(pr-review): add review payload model, validation, and comment cap"
```

---

### Task 3: ReviewType seam + TestGapType

**Files:**
- Create: `src/pr_review/review_types/__init__.py`
- Create: `src/pr_review/review_types/base.py`
- Create: `src/pr_review/review_types/test_gap.py`
- Test: `tests/test_review_types.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `pr_review.review_types.base.ReviewType` (ABC: attribute `name: str`, method `instructions() -> str`)
  - `register(rt: ReviewType) -> ReviewType`, `get_review_type(name: str) -> ReviewType` (raises `ValueError`), `available() -> list[str]`
  - `TestGapType` registered under name `"test-gap"`
  - Re-exports from `pr_review.review_types`: `ReviewType`, `register`, `get_review_type`, `available`

- [ ] **Step 1: Write the failing test**

`tests/test_review_types.py`:

```python
import pytest

from pr_review.review_types import available, get_review_type


def test_test_gap_is_registered():
    assert "test-gap" in available()


def test_get_returns_instance_with_name():
    rt = get_review_type("test-gap")
    assert rt.name == "test-gap"


def test_instructions_contain_schema_and_cap():
    text = get_review_type("test-gap").instructions()
    assert "## Output (REQUIRED)" in text
    assert "HARD CAP: 8 inline comments" in text


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        get_review_type("does-not-exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_review_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.review_types'`.

- [ ] **Step 3: Write minimal implementation**

`src/pr_review/review_types/base.py`:

```python
"""ReviewType seam: a named, reviewer-agnostic review prompt."""
from __future__ import annotations

from abc import ABC, abstractmethod

_REGISTRY: dict[str, "ReviewType"] = {}


class ReviewType(ABC):
    name: str

    @abstractmethod
    def instructions(self) -> str:
        """The full instruction block handed to a reviewer."""


def register(rt: ReviewType) -> ReviewType:
    _REGISTRY[rt.name] = rt
    return rt


def get_review_type(name: str) -> ReviewType:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown review type: {name!r}; available: {', '.join(sorted(_REGISTRY))}"
        ) from None


def available() -> list[str]:
    return sorted(_REGISTRY)
```

`src/pr_review/review_types/test_gap.py` (the `_INSTRUCTIONS` string is the verbatim instruction block from the old bash tool; a raw string keeps the example `\n` literal):

```python
"""Test-coverage gap review type (carried over verbatim from test-gap-review)."""
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
```

`src/pr_review/review_types/__init__.py`:

```python
"""Review types package — importing it registers the built-in types."""
from pr_review.review_types.base import (
    ReviewType,
    available,
    get_review_type,
    register,
)
from pr_review.review_types import test_gap  # noqa: F401  (registers TestGapType)

__all__ = ["ReviewType", "available", "get_review_type", "register"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_review_types.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/review_types tests/test_review_types.py
git commit -m "feat(pr-review): add ReviewType seam and test-gap type"
```

---

### Task 4: Reviewer seam + ClaudeReviewer

**Files:**
- Create: `src/pr_review/reviewers/__init__.py`
- Create: `src/pr_review/reviewers/base.py`
- Create: `src/pr_review/reviewers/claude.py`
- Test: `tests/test_reviewers.py`

**Interfaces:**
- Consumes: `pr_review.payload.Payload`, `pr_review.payload.parse_payload`, `pr_review.review_types.base.ReviewType`.
- Produces:
  - `pr_review.reviewers.base.Reviewer` (ABC: attribute `name: str`; method
    `review(*, workdir: str, base: str, owner: str, repo: str, number: int, review_type: ReviewType, model: str, extra_flags: list[str]) -> Payload`)
  - `register(rev: Reviewer) -> Reviewer`, `get_reviewer(name: str) -> Reviewer` (raises `ValueError`), `available() -> list[str]`
  - `ClaudeReviewer` registered under `"claude"`, with pure helper `build_prompt(*, owner, repo, number, base, payload_path, review_type) -> str`
  - Re-exports from `pr_review.reviewers`: `Reviewer`, `register`, `get_reviewer`, `available`

- [ ] **Step 1: Write the failing test**

`tests/test_reviewers.py` (only the pure pieces — the `claude` subprocess is verified manually in Task 10):

```python
import pytest

from pr_review.reviewers import available, get_reviewer
from pr_review.reviewers.claude import ClaudeReviewer
from pr_review.review_types import get_review_type


def test_claude_is_registered():
    assert "claude" in available()
    assert get_reviewer("claude").name == "claude"


def test_unknown_reviewer_raises():
    with pytest.raises(ValueError):
        get_reviewer("nope")


def test_build_prompt_includes_context_and_instructions():
    prompt = ClaudeReviewer().build_prompt(
        owner="org", repo="repo", number=7, base="main",
        payload_path="/tmp/p.json", review_type=get_review_type("test-gap"),
    )
    assert "Repository: org/repo" in prompt
    assert "PR number: 7" in prompt
    assert "origin/main" in prompt
    assert "/tmp/p.json" in prompt
    assert "# Test Coverage Review" in prompt  # instructions appended
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reviewers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.reviewers'`.

- [ ] **Step 3: Write minimal implementation**

`src/pr_review/reviewers/base.py`:

```python
"""Reviewer seam: an LLM backend that turns a checkout into a Payload."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pr_review.payload import Payload
from pr_review.review_types.base import ReviewType

_REGISTRY: dict[str, "Reviewer"] = {}


class Reviewer(ABC):
    name: str

    @abstractmethod
    def review(
        self,
        *,
        workdir: str,
        base: str,
        owner: str,
        repo: str,
        number: int,
        review_type: ReviewType,
        model: str,
        extra_flags: list[str],
    ) -> Payload:
        """Run the backend over the checkout and return a parsed Payload."""


def register(rev: Reviewer) -> Reviewer:
    _REGISTRY[rev.name] = rev
    return rev


def get_reviewer(name: str) -> Reviewer:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown reviewer: {name!r}; available: {', '.join(sorted(_REGISTRY))}"
        ) from None


def available() -> list[str]:
    return sorted(_REGISTRY)
```

`src/pr_review/reviewers/claude.py`:

```python
"""Claude headless reviewer (wraps `claude --print`)."""
from __future__ import annotations

import os
import subprocess
import tempfile

from pr_review.payload import Payload, parse_payload
from pr_review.reviewers.base import Reviewer, register
from pr_review.review_types.base import ReviewType


def _build_context(*, owner: str, repo: str, number: int, base: str, payload_path: str) -> str:
    return (
        "You are reviewing a GitHub pull request. Context for this run:\n"
        f"- Repository: {owner}/{repo}\n"
        f"- PR number: {number}\n"
        f"- Base ref:  origin/{base}\n"
        "- HEAD is ALREADY checked out at the exact code to review. Do not switch branches.\n"
        f"- Payload file to write: {payload_path}\n"
    )


class ClaudeReviewer(Reviewer):
    name = "claude"

    def build_prompt(
        self, *, owner: str, repo: str, number: int, base: str,
        payload_path: str, review_type: ReviewType,
    ) -> str:
        context = _build_context(
            owner=owner, repo=repo, number=number, base=base, payload_path=payload_path
        )
        return context + "\n" + review_type.instructions()

    def review(
        self, *, workdir: str, base: str, owner: str, repo: str, number: int,
        review_type: ReviewType, model: str, extra_flags: list[str],
    ) -> Payload:
        fd, payload_path = tempfile.mkstemp(prefix="pr-review-payload.", suffix=".json")
        os.close(fd)
        try:
            prompt = self.build_prompt(
                owner=owner, repo=repo, number=number, base=base,
                payload_path=payload_path, review_type=review_type,
            )
            cmd = [
                "claude", "--print", "--model", model,
                "--permission-mode", "acceptEdits",
                "--dangerously-skip-permissions",
                "--allowedTools", "Bash", "Read", "Grep", "Glob", "Write",
                *extra_flags,
            ]
            subprocess.run(cmd, cwd=workdir, input=prompt, text=True, check=True)
            with open(payload_path) as f:
                raw = f.read()
            if not raw.strip():
                raise RuntimeError("claude produced an empty payload")
            return parse_payload(raw)
        finally:
            try:
                os.unlink(payload_path)
            except FileNotFoundError:
                pass


register(ClaudeReviewer())
```

`src/pr_review/reviewers/__init__.py`:

```python
"""Reviewers package — importing it registers the built-in reviewers."""
from pr_review.reviewers.base import Reviewer, available, get_reviewer, register
from pr_review.reviewers import claude  # noqa: F401  (registers ClaudeReviewer)

__all__ = ["Reviewer", "available", "get_reviewer", "register"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reviewers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/reviewers tests/test_reviewers.py
git commit -m "feat(pr-review): add Reviewer seam and Claude headless reviewer"
```

---

### Task 5: Collator + DeterministicMergeCollator

**Files:**
- Create: `src/pr_review/collate.py`
- Test: `tests/test_collate.py`

**Interfaces:**
- Consumes: `pr_review.payload.Payload`, `Comment`, `cap_comments`, `MAX_INLINE_COMMENTS`.
- Produces:
  - `Job = tuple[str, str, Payload]` — `(reviewer_name, type_name, payload)`
  - `Collator` (ABC: `collate(jobs: list[Job]) -> Payload`)
  - `DeterministicMergeCollator` — passthrough for a single job; for multiple, merges bodies under `## {type} — {reviewer}` headers in `(reviewer, type)` order, concatenates comments, re-applies the 8-comment cap, and lists overflow under `## Additional coverage gaps not posted inline`.

- [ ] **Step 1: Write the failing test**

`tests/test_collate.py`:

```python
from pr_review.collate import DeterministicMergeCollator
from pr_review.payload import Comment, Payload


def _job(reviewer, rtype, n_comments):
    comments = [Comment(f"{reviewer}.py", i, f"{reviewer}-gap-{i}") for i in range(n_comments)]
    return (reviewer, rtype, Payload(body=f"{reviewer} body", comments=comments))


def test_single_job_is_passthrough():
    p = Payload(body="solo", comments=[Comment("a", 1, "g")])
    out = DeterministicMergeCollator().collate([("claude", "test-gap", p)])
    assert out is p


def test_empty_jobs_returns_placeholder():
    out = DeterministicMergeCollator().collate([])
    assert out.comments == []
    assert out.body


def test_merge_two_jobs_combines_bodies_and_comments():
    jobs = [_job("codex", "test-gap", 2), _job("claude", "test-gap", 2)]
    out = DeterministicMergeCollator().collate(jobs)
    # ordered by reviewer name: claude before codex
    assert out.body.index("## test-gap — claude") < out.body.index("## test-gap — codex")
    assert len(out.comments) == 4


def test_merge_reapplies_cap_and_lists_overflow():
    jobs = [_job("claude", "test-gap", 5), _job("codex", "test-gap", 5)]
    out = DeterministicMergeCollator().collate(jobs)
    assert len(out.comments) == 8
    assert "## Additional coverage gaps not posted inline" in out.body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_collate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.collate'`.

- [ ] **Step 3: Write minimal implementation**

`src/pr_review/collate.py`:

```python
"""Collate one-or-more review payloads into a single payload."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pr_review.payload import MAX_INLINE_COMMENTS, Comment, Payload, cap_comments

Job = tuple[str, str, Payload]  # (reviewer_name, type_name, payload)


def _first_line(text: str) -> str:
    stripped = text.strip()
    return stripped.splitlines()[0] if stripped else ""


class Collator(ABC):
    @abstractmethod
    def collate(self, jobs: list[Job]) -> Payload:
        """Merge review jobs into a single payload."""


class DeterministicMergeCollator(Collator):
    def collate(self, jobs: list[Job]) -> Payload:
        if not jobs:
            return Payload(body="_No reviews were produced._", comments=[])
        if len(jobs) == 1:
            return jobs[0][2]

        ordered = sorted(jobs, key=lambda j: (j[0], j[1]))
        body_parts: list[str] = []
        all_comments: list[Comment] = []
        for reviewer, rtype, payload in ordered:
            body_parts.append(f"## {rtype} — {reviewer}\n\n{payload.body}")
            all_comments.extend(payload.comments)

        kept, overflow = cap_comments(all_comments, MAX_INLINE_COMMENTS)
        body = "\n\n---\n\n".join(body_parts)
        if overflow:
            extra = "\n".join(
                f"- `{c.path}:{c.line}` — {_first_line(c.body)}" for c in overflow
            )
            body += "\n\n---\n\n## Additional coverage gaps not posted inline\n\n" + extra
        return Payload(body=body, comments=kept)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_collate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/collate.py tests/test_collate.py
git commit -m "feat(pr-review): add deterministic merge collator"
```

---

### Task 6: Checkout (blobless clone + gh pr checkout)

**Files:**
- Create: `src/pr_review/checkout.py`
- Test: `tests/test_checkout.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Checkout(workdir: str, base: str)` dataclass
  - `Runner = Callable[..., subprocess.CompletedProcess]`
  - `clone_pr(owner: str, repo: str, number: int, *, runner: Runner = ..., mkdtemp: Callable[[], str] | None = None) -> Checkout` — runs `git clone --filter=blob:none <url> <workdir>`, `gh pr checkout <number>` in `workdir`, and reads `baseRefName` via `gh pr view`.
  - `cleanup(checkout: Checkout) -> None` — `shutil.rmtree(..., ignore_errors=True)`

- [ ] **Step 1: Write the failing test**

`tests/test_checkout.py`:

```python
import os
import subprocess
import tempfile

from pr_review.checkout import Checkout, cleanup, clone_pr


class FakeRunner:
    def __init__(self, base_out="main\n"):
        self.calls = []
        self.base_out = base_out

    def __call__(self, cmd, **kw):
        self.calls.append((list(cmd), kw))
        stdout = self.base_out if cmd[:3] == ["gh", "pr", "view"] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")


def test_clone_pr_builds_expected_commands(tmp_path):
    runner = FakeRunner()
    workdir = str(tmp_path / "repo")
    result = clone_pr("org", "repo", 42, runner=runner, mkdtemp=lambda: workdir)

    assert result == Checkout(workdir=workdir, base="main")
    cmds = [c[0] for c in runner.calls]
    assert cmds[0] == ["git", "clone", "--filter=blob:none",
                       "https://github.com/org/repo", workdir]
    assert cmds[1] == ["gh", "pr", "checkout", "42"]
    assert cmds[2][:3] == ["gh", "pr", "view"]
    # gh commands run inside the clone
    assert runner.calls[1][1].get("cwd") == workdir


def test_cleanup_removes_workdir():
    d = tempfile.mkdtemp(prefix="pr-review-test.")
    assert os.path.isdir(d)
    cleanup(Checkout(workdir=d, base="main"))
    assert not os.path.isdir(d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_checkout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.checkout'`.

- [ ] **Step 3: Write minimal implementation**

`src/pr_review/checkout.py`:

```python
"""Clone a PR into an isolated temp dir (blobless), worktree-free."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass
class Checkout:
    workdir: str
    base: str


def _run(cmd: Sequence[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=True, text=True, **kw)


def clone_pr(
    owner: str,
    repo: str,
    number: int,
    *,
    runner: Runner = _run,
    mkdtemp: Callable[[], str] | None = None,
) -> Checkout:
    make = mkdtemp or (lambda: tempfile.mkdtemp(prefix="pr-review."))
    workdir = make()
    url = f"https://github.com/{owner}/{repo}"
    runner(["git", "clone", "--filter=blob:none", url, workdir])
    runner(["gh", "pr", "checkout", str(number)], cwd=workdir)
    res = runner(
        ["gh", "pr", "view", str(number), "--repo", f"{owner}/{repo}",
         "--json", "baseRefName", "-q", ".baseRefName"],
        cwd=workdir,
        capture_output=True,
    )
    base = (res.stdout or "").strip()
    return Checkout(workdir=workdir, base=base)


def cleanup(checkout: Checkout) -> None:
    shutil.rmtree(checkout.workdir, ignore_errors=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_checkout.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/checkout.py tests/test_checkout.py
git commit -m "feat(pr-review): add isolated blobless PR checkout"
```

---

### Task 7: Output (posting-mode decision, render, post)

**Files:**
- Create: `src/pr_review/output.py`
- Test: `tests/test_output.py`

**Interfaces:**
- Consumes: `pr_review.payload.Payload`, `pr_review.target.Target`.
- Produces:
  - `PostMode` enum: `POST`, `PROMPT`, `REVIEW_ONLY`
  - `decide_mode(*, yes: bool, no_post: bool, has_tty: bool) -> PostMode`
  - `render(payload: Payload) -> str`
  - `post_review(target: Target, payload: Payload, *, runner=_run) -> None` — `gh api repos/<slug>/pulls/<n>/reviews --method POST --input <file>`
  - `tty_available() -> bool`
  - `dispatch(mode: PostMode, target: Target, payload: Payload, *, runner=_run) -> None`

- [ ] **Step 1: Write the failing test**

`tests/test_output.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_output.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.output'`.

- [ ] **Step 3: Write minimal implementation**

`src/pr_review/output.py`:

```python
"""Decide whether to post, render the review, and post via gh."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from enum import Enum

from pr_review.payload import Payload
from pr_review.target import Target


class PostMode(Enum):
    POST = "post"
    PROMPT = "prompt"
    REVIEW_ONLY = "review_only"


def decide_mode(*, yes: bool, no_post: bool, has_tty: bool) -> PostMode:
    if no_post:
        return PostMode.REVIEW_ONLY
    if yes:
        return PostMode.POST
    if not has_tty:
        return PostMode.REVIEW_ONLY
    return PostMode.PROMPT


def tty_available() -> bool:
    return sys.stdin.isatty() or os.path.exists("/dev/tty")


def render(payload: Payload) -> str:
    lines = [payload.body, ""]
    for c in payload.comments:
        lines.append(f"### {c.path}:{c.line}")
        lines.append(c.body)
        lines.append("")
    return "\n".join(lines)


def _run(cmd: Sequence[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=True, text=True, **kw)


def post_review(target: Target, payload: Payload, *, runner=_run) -> None:
    fd, path = tempfile.mkstemp(prefix="pr-review-post.", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(payload.to_json())
        runner(
            ["gh", "api", f"repos/{target.slug}/pulls/{target.number}/reviews",
             "--method", "POST", "--input", path]
        )
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _manual_hint(target: Target) -> str:
    return (
        f"pr-review: not posted. To post manually:\n"
        f"  gh api repos/{target.slug}/pulls/{target.number}/reviews "
        f"--method POST --input <payload.json>"
    )


def _confirm(target: Target, n_comments: int) -> bool:
    try:
        with open("/dev/tty", "r+") as tty:
            tty.write(
                f"\nPost this review to {target.slug}#{target.number} "
                f"with {n_comments} inline comment(s)? [y/N] "
            )
            tty.flush()
            reply = tty.readline().strip().lower()
    except OSError:
        return False
    return reply in ("y", "yes")


def dispatch(mode: PostMode, target: Target, payload: Payload, *, runner=_run) -> None:
    if mode is PostMode.POST:
        post_review(target, payload, runner=runner)
        print(f"pr-review: posted review to {target.slug}#{target.number}.", file=sys.stderr)
    elif mode is PostMode.PROMPT and _confirm(target, len(payload.comments)):
        post_review(target, payload, runner=runner)
        print(f"pr-review: posted review to {target.slug}#{target.number}.", file=sys.stderr)
    else:
        print(_manual_hint(target), file=sys.stderr)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_output.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/output.py tests/test_output.py
git commit -m "feat(pr-review): add posting-mode decision, render, and gh post"
```

---

### Task 8: Orchestrator (parallel fan-out + collate)

**Files:**
- Create: `src/pr_review/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `pr_review.collate.Collator`, `DeterministicMergeCollator`, `Job`; `pr_review.reviewers.base.Reviewer`; `pr_review.review_types.base.ReviewType`; `pr_review.payload.Payload`.
- Produces:
  - `ReviewJob(reviewer: Reviewer, review_type: ReviewType)` dataclass
  - `run_reviews(*, jobs: list[ReviewJob], workdir: str, base: str, owner: str, repo: str, number: int, model: str, extra_flags: list[str], collator: Collator | None = None, max_workers: int | None = None) -> Payload` — runs each job's `reviewer.review(...)` concurrently over a `ThreadPoolExecutor`, builds `(reviewer.name, review_type.name, payload)` triples, and returns `collator.collate(...)`.

- [ ] **Step 1: Write the failing test**

`tests/test_orchestrator.py`:

```python
from pr_review.orchestrator import ReviewJob, run_reviews
from pr_review.payload import Comment, Payload


class FakeType:
    def __init__(self, name):
        self.name = name

    def instructions(self):
        return "x"


class FakeReviewer:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def review(self, *, workdir, base, owner, repo, number, review_type, model, extra_flags):
        self.calls.append((review_type.name, workdir))
        return Payload(body=f"{self.name}/{review_type.name}",
                       comments=[Comment("f.py", 1, "g")])


def test_run_reviews_single_job_passthrough():
    r = FakeReviewer("claude")
    out = run_reviews(
        jobs=[ReviewJob(r, FakeType("test-gap"))],
        workdir="/wd", base="main", owner="o", repo="r", number=1,
        model="m", extra_flags=[],
    )
    assert out.body == "claude/test-gap"
    assert r.calls == [("test-gap", "/wd")]


def test_run_reviews_two_jobs_merge():
    jobs = [
        ReviewJob(FakeReviewer("claude"), FakeType("test-gap")),
        ReviewJob(FakeReviewer("codex"), FakeType("test-gap")),
    ]
    out = run_reviews(
        jobs=jobs, workdir="/wd", base="main", owner="o", repo="r", number=1,
        model="m", extra_flags=[],
    )
    assert "## test-gap — claude" in out.body
    assert "## test-gap — codex" in out.body
    assert len(out.comments) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.orchestrator'`.

- [ ] **Step 3: Write minimal implementation**

`src/pr_review/orchestrator.py`:

```python
"""Fan out (reviewer x review-type) jobs in parallel, then collate."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pr_review.collate import Collator, DeterministicMergeCollator, Job
from pr_review.payload import Payload
from pr_review.reviewers.base import Reviewer
from pr_review.review_types.base import ReviewType


@dataclass
class ReviewJob:
    reviewer: Reviewer
    review_type: ReviewType


def run_reviews(
    *,
    jobs: list[ReviewJob],
    workdir: str,
    base: str,
    owner: str,
    repo: str,
    number: int,
    model: str,
    extra_flags: list[str],
    collator: Collator | None = None,
    max_workers: int | None = None,
) -> Payload:
    collator = collator or DeterministicMergeCollator()

    def _one(job: ReviewJob) -> Job:
        payload = job.reviewer.review(
            workdir=workdir, base=base, owner=owner, repo=repo, number=number,
            review_type=job.review_type, model=model, extra_flags=extra_flags,
        )
        return (job.reviewer.name, job.review_type.name, payload)

    with ThreadPoolExecutor(max_workers=max_workers or len(jobs)) as ex:
        results = list(ex.map(_one, jobs))
    return collator.collate(results)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(pr-review): add parallel review orchestrator"
```

---

### Task 9: CLI wiring

**Files:**
- Create: `src/pr_review/cli.py`
- Create: `src/pr_review/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `parse_target`/`Target`; `get_reviewer`; `get_review_type`; `ReviewJob`/`run_reviews`; `clone_pr`/`cleanup`; `output` module.
- Produces:
  - `RunConfig` dataclass (`target: Target`, `reviewer_names: list[str]`, `type_names: list[str]`, `model: str`, `extra_flags: list[str]`, `yes: bool`, `no_post: bool`, `keep: bool`)
  - `config_from_args(argv: list[str], env: Mapping[str, str]) -> RunConfig`
  - `build_jobs(cfg: RunConfig) -> list[ReviewJob]` (cross-product; validates names)
  - `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:

```python
import pytest

from pr_review.cli import build_jobs, config_from_args
from pr_review.target import Target


def test_config_defaults():
    cfg = config_from_args(["org/repo#3"], env={})
    assert cfg.target == Target("org", "repo", 3)
    assert cfg.reviewer_names == ["claude"]
    assert cfg.type_names == ["test-gap"]
    assert cfg.model == "claude-opus-4-8"
    assert cfg.extra_flags == []
    assert cfg.yes is False and cfg.no_post is False and cfg.keep is False


def test_config_reads_env_and_flags():
    cfg = config_from_args(
        ["--reviewer", "claude,codex", "--type", "test-gap", "org/repo#9"],
        env={"MODEL": "m", "YES": "1", "KEEP": "1", "CLAUDE_FLAGS": "--foo --bar"},
    )
    assert cfg.reviewer_names == ["claude", "codex"]
    assert cfg.model == "m"
    assert cfg.yes is True and cfg.keep is True
    assert cfg.extra_flags == ["--foo", "--bar"]


def test_build_jobs_cross_product():
    cfg = config_from_args(["--reviewer", "claude", "--type", "test-gap", "org/repo#1"], env={})
    jobs = build_jobs(cfg)
    assert len(jobs) == 1
    assert jobs[0].reviewer.name == "claude"
    assert jobs[0].review_type.name == "test-gap"


def test_build_jobs_unknown_name_raises():
    cfg = config_from_args(["--reviewer", "ghost", "org/repo#1"], env={})
    with pytest.raises(ValueError):
        build_jobs(cfg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.cli'`.

- [ ] **Step 3: Write minimal implementation**

`src/pr_review/cli.py`:

```python
"""pr-review command-line entry point."""
from __future__ import annotations

import argparse
import os
import shlex
import sys
from collections.abc import Mapping
from dataclasses import dataclass

from pr_review.checkout import cleanup, clone_pr
from pr_review.orchestrator import ReviewJob, run_reviews
from pr_review.reviewers import available as reviewers_available, get_reviewer
from pr_review.review_types import available as types_available, get_review_type
from pr_review.target import Target, parse_target
from pr_review import output

DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class RunConfig:
    target: Target
    reviewer_names: list[str]
    type_names: list[str]
    model: str
    extra_flags: list[str]
    yes: bool
    no_post: bool
    keep: bool


def _split(value: str) -> list[str]:
    return [s for s in (part.strip() for part in value.split(",")) if s]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr-review",
        description="Review a GitHub PR in an isolated clone with one or more LLMs.",
    )
    p.add_argument("target", help="PR URL or owner/repo#N")
    p.add_argument(
        "--reviewer", default="claude",
        help=f"comma-separated reviewers (available: {', '.join(reviewers_available())})",
    )
    p.add_argument(
        "--type", dest="types", default="test-gap",
        help=f"comma-separated review types (available: {', '.join(types_available())})",
    )
    return p


def config_from_args(argv: list[str], env: Mapping[str, str]) -> RunConfig:
    args = build_parser().parse_args(argv)
    return RunConfig(
        target=parse_target(args.target),
        reviewer_names=_split(args.reviewer),
        type_names=_split(args.types),
        model=env.get("MODEL", DEFAULT_MODEL),
        extra_flags=shlex.split(env.get("CLAUDE_FLAGS", "")),
        yes=env.get("YES") == "1",
        no_post=env.get("NO_POST") == "1",
        keep=env.get("KEEP") == "1",
    )


def build_jobs(cfg: RunConfig) -> list[ReviewJob]:
    return [
        ReviewJob(get_reviewer(r), get_review_type(t))
        for r in cfg.reviewer_names
        for t in cfg.type_names
    ]


def main(argv: list[str] | None = None) -> int:
    cfg = config_from_args(sys.argv[1:] if argv is None else argv, os.environ)
    jobs = build_jobs(cfg)  # validates reviewer/type names before any clone

    checkout = clone_pr(cfg.target.owner, cfg.target.repo, cfg.target.number)
    print(
        f"pr-review: {cfg.target.slug}#{cfg.target.number} "
        f"base=origin/{checkout.base} jobs={len(jobs)}",
        file=sys.stderr,
    )
    try:
        payload = run_reviews(
            jobs=jobs, workdir=checkout.workdir, base=checkout.base,
            owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number,
            model=cfg.model, extra_flags=cfg.extra_flags,
        )
    finally:
        if cfg.keep:
            print(f"pr-review: kept checkout at {checkout.workdir}", file=sys.stderr)
        else:
            cleanup(checkout)

    print(output.render(payload))
    mode = output.decide_mode(
        yes=cfg.yes, no_post=cfg.no_post, has_tty=output.tty_available()
    )
    output.dispatch(mode, cfg.target, payload)
    return 0
```

`src/pr_review/__main__.py`:

```python
import sys

from pr_review.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS — every test from Tasks 1–9.

- [ ] **Step 6: Commit**

```bash
git add src/pr_review/cli.py src/pr_review/__main__.py tests/test_cli.py
git commit -m "feat(pr-review): wire CLI (target, reviewers, types, run)"
```

---

### Task 10: Install shims, mise install task, retire bash script

**Files:**
- Create: `bin/pr-review`
- Create: `bin/test-gap-review`
- Modify: `mise.toml` (add `[tasks.install]`)
- Delete: `test-gap-review` (the old bash script, currently untracked)

**Interfaces:**
- Consumes: the `pr-review` console script provided by the installed project (`pyproject.toml` `[project.scripts]`).
- Produces: two executable shims and a `mise run install` task that syncs deps and symlinks both into `~/bin`.

- [ ] **Step 1: Create the launcher shims**

`bin/pr-review`:

```bash
#!/usr/bin/env bash
set -euo pipefail
# Resolve this script's real path (it is symlinked into ~/bin).
source="${BASH_SOURCE[0]}"
while [ -L "$source" ]; do
  dir=$(cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd)
  source=$(readlink "$source")
  [[ $source != /* ]] && source="$dir/$source"
done
repo=$(cd -P "$(dirname "$source")/.." >/dev/null 2>&1 && pwd)
exec uv run --project "$repo" pr-review "$@"
```

`bin/test-gap-review` (alias — injects the type):

```bash
#!/usr/bin/env bash
set -euo pipefail
source="${BASH_SOURCE[0]}"
while [ -L "$source" ]; do
  dir=$(cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd)
  source=$(readlink "$source")
  [[ $source != /* ]] && source="$dir/$source"
done
repo=$(cd -P "$(dirname "$source")/.." >/dev/null 2>&1 && pwd)
exec uv run --project "$repo" pr-review --type test-gap "$@"
```

- [ ] **Step 2: Make the shims executable**

Run:
```bash
chmod +x bin/pr-review bin/test-gap-review
```
Expected: no output; `ls -l bin` shows both as executable.

- [ ] **Step 3: Add the install task to `mise.toml`**

Append to `mise.toml`:

```toml
[tasks.install]
description = "Sync deps and symlink pr-review (+ test-gap-review alias) into ~/bin"
run = """
uv sync
mkdir -p "$HOME/bin"
ln -sf "$MISE_PROJECT_ROOT/bin/pr-review"       "$HOME/bin/pr-review"
ln -sf "$MISE_PROJECT_ROOT/bin/test-gap-review" "$HOME/bin/test-gap-review"
"""
```

- [ ] **Step 4: Verify install + entry point resolve**

Run:
```bash
mise run install
~/bin/pr-review --help
```
Expected: `uv sync` creates the venv; `~/bin/pr-review --help` prints the argparse usage (`usage: pr-review [-h] [--reviewer REVIEWER] [--type TYPES] target`).

- [ ] **Step 5: Retire the old bash script**

Run:
```bash
rm -f test-gap-review
```
Expected: the legacy script is gone; the new `~/bin/test-gap-review` symlink (from Step 4) now points at the alias shim. Confirm: `~/bin/test-gap-review --help` prints the same usage.

- [ ] **Step 6: Manual end-to-end verification (no posting)**

Pick a small PR you can read and run review-only:
```bash
NO_POST=1 ~/bin/pr-review <owner>/<repo>#<N>
```
Expected: a temp clone appears and is removed on exit; Claude runs; a rendered review (body + any `path:line` gaps) prints to stdout; stderr shows the manual `gh api` hint. Re-run with `KEEP=1` to confirm the checkout is retained and its path is printed.

- [ ] **Step 7: Commit**

```bash
git add bin/pr-review bin/test-gap-review mise.toml
git rm --cached --ignore-unmatch test-gap-review 2>/dev/null || true
git commit -m "feat(pr-review): add uv-run shims and mise install task; retire bash script"
```

---

## Self-Review

**Spec coverage:**
- Isolation / blobless clone → Task 6. Cleanup + `KEEP=1` → Tasks 6, 9.
- Explicit target only (URL / `owner/repo#N`) → Task 1.
- Reviewer/ReviewType/Collator seams + registries → Tasks 3, 4, 5.
- Parallel fan-out (ThreadPoolExecutor), shared read-only checkout → Tasks 8, 9.
- Deterministic merge collator (N=2 fixtures, cap, provenance) → Task 5.
- CLI `pr-review` with `--reviewer`/`--type` lists, cross-product, env knobs → Task 9.
- `test-gap-review` alias → Task 10.
- Payload schema + 8-comment cap → Task 2 (cap), Task 3 (schema text), Task 5 (cap re-apply).
- Posting model (`YES`/`NO_POST`/TTY, `gh api`) → Task 7.
- uv project, `src/` layout, pytest, `mise run test`/`install`, `uv run` shim install (option A) → Tasks 1, 10.
- Verbatim test-gap instructions → Task 3.

**Placeholder scan:** none — every code step contains complete content; the only `<...>` tokens are user-supplied values in shell commands (`<owner>/<repo>#<N>`).

**Type consistency:** verified across tasks — `Payload`/`Comment`/`cap_comments`/`MAX_INLINE_COMMENTS` (Task 2) are used identically in Tasks 4, 5, 7; `Job = (reviewer_name, type_name, payload)` (Task 5) is produced by the orchestrator (Task 8); `ReviewJob(reviewer, review_type)` and `run_reviews(...)` signatures match between Tasks 8 and 9; `Reviewer.review(...)` keyword signature is identical in Tasks 4, 8 (fake), and 9; `clone_pr`/`Checkout`/`cleanup` (Task 6) match their use in Task 9; `decide_mode`/`render`/`dispatch`/`tty_available` (Task 7) match Task 9.
