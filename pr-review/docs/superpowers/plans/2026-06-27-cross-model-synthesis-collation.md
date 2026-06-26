# Cross-Model Synthesis Collation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a run has more than one job, run a single judge-LLM synthesis pass that de-dupes findings across models, verifies them against the diff, weights by cross-model agreement, drops unverifiable lone findings, and emits one review + stats — instead of the naive concatenation.

**Architecture:** A new `LLMSynthesisCollator` (in `synthesis.py`) runs a configurable judge agent in the clone, handed every finding tagged by source plus the diff. To reuse the agent/subprocess machinery, `Reviewer` gains `command(model, extra_flags)` and `_run.py` exposes `run_cli_payload(cmd, build_prompt, *, workdir)`. `cli.main` builds the collator (synthesis or the existing deterministic merge) after cloning and passes it to `run_reviews`, which already accepts a collator. On any judge failure the collator falls back to the deterministic merge, so the run never crashes.

**Tech Stack:** Python 3.14, uv, pytest, stdlib-only runtime, `claude`/`codex` CLIs.

## Global Constraints

- Runtime dependencies: none (stdlib only). pytest is dev-only.
- Synthesis judge default: `claude=claude-opus-4-8`. Configured by `--synthesis-model AGENT[=MODEL]` (bare `AGENT` → that reviewer's `default_model`); the agent key is validated against the reviewer registry (fail-fast).
- `--no-synthesis` uses `DeterministicMergeCollator` even for >1 job.
- Synthesis runs automatically for a run with **more than one** successful job; a single job passes through unchanged.
- A judge failure (non-zero exit, empty/invalid payload) → the collator **falls back to `DeterministicMergeCollator`** and prints a warning naming the judge to stderr. The synthesis pass never crashes the run.
- The judge keeps the existing payload JSON contract (`event`/`body`/`comments`), the 8-comment cap (`MAX_INLINE_COMMENTS = 8`), and writes the payload file + prints to stdout. Confidence labels and a `## Review stats` section live in the payload **body** (so they post to the PR and print via `render()`).
- `Collator.collate(jobs)` keeps its signature; `Job = (label, type_name, payload)` where `label` is the orchestrator's `"<agent> (<model>)"` string (empty model → just `<agent>`).

---

### Task 1: Reviewer.command() + run_cli_payload refactor

**Files:**
- Modify: `src/pr_review/reviewers/base.py` (add abstract `command`; make `review` concrete)
- Modify: `src/pr_review/reviewers/claude.py` (replace `review` with `command`)
- Modify: `src/pr_review/reviewers/codex.py` (replace `review` with `command`)
- Modify: `src/pr_review/reviewers/_run.py` (extract `run_cli_payload`; `run_cli_reviewer` wraps it)
- Test: `tests/test_reviewers.py`

**Interfaces:**
- Consumes: `pr_review.payload`, `pr_review.review_types.base.ReviewType`, existing `build_review_prompt`/`_review_env`.
- Produces:
  - `Reviewer.command(model: str, extra_flags: list[str]) -> list[str]` (abstract); `Reviewer.review(...)` now concrete, delegating to `run_cli_reviewer(self.command(model, extra_flags), ...)`.
  - `pr_review.reviewers._run.run_cli_payload(cmd_prefix, build_prompt, *, workdir) -> Payload` where `build_prompt(payload_path: str) -> str`.
  - `ClaudeReviewer.command` / `CodexReviewer.command` argv (codex omits `--model` for an empty model).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reviewers.py`:

```python
def test_claude_command_includes_model_and_flags():
    cmd = get_reviewer("claude").command("claude-opus-4-8", ["--foo"])
    assert cmd[:4] == ["claude", "--print", "--model", "claude-opus-4-8"]
    assert "--dangerously-skip-permissions" in cmd
    assert cmd[-1] == "--foo"


def test_codex_command_omits_model_when_empty():
    cmd = get_reviewer("codex").command("", [])
    assert cmd == ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]


def test_codex_command_includes_model_when_given():
    cmd = get_reviewer("codex").command("gpt-5", ["--oss"])
    assert cmd[:4] == ["codex", "exec", "--model", "gpt-5"]
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert cmd[-1] == "--oss"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_reviewers.py -k command -v`
Expected: FAIL — `AttributeError: 'ClaudeReviewer' object has no attribute 'command'`.

- [ ] **Step 3: Add `run_cli_payload` and wrap `run_cli_reviewer`**

In `src/pr_review/reviewers/_run.py`, add `Callable` to the imports line and replace the `run_cli_reviewer` function with:

```python
def run_cli_payload(
    cmd_prefix: Sequence[str],
    build_prompt: Callable[[str], str],
    *,
    workdir: str,
) -> Payload:
    fd, payload_path = tempfile.mkstemp(prefix="pr-review-payload.", suffix=".json")
    os.close(fd)
    try:
        prompt = build_prompt(payload_path)
        subprocess.run(
            list(cmd_prefix), cwd=workdir, input=prompt, text=True, check=True,
            env=_review_env(workdir),
        )
        with open(payload_path, encoding="utf-8") as f:
            raw = f.read()
        if not raw.strip():
            raise RuntimeError(f"{cmd_prefix[0]} produced an empty payload")
        return parse_payload(raw)
    finally:
        try:
            os.unlink(payload_path)
        except FileNotFoundError:
            pass


def run_cli_reviewer(
    cmd_prefix: Sequence[str],
    *,
    workdir: str,
    owner: str,
    repo: str,
    number: int,
    base: str,
    review_type: ReviewType,
) -> Payload:
    def build(payload_path: str) -> str:
        return build_review_prompt(
            owner=owner, repo=repo, number=number, base=base,
            payload_path=payload_path, review_type=review_type,
        )

    return run_cli_payload(cmd_prefix, build, workdir=workdir)
```

The imports line at the top becomes:
```python
from collections.abc import Callable, Sequence
```

- [ ] **Step 4: Make `review` concrete and add abstract `command` in base.py**

Replace `src/pr_review/reviewers/base.py` with:

```python
"""Reviewer seam: an LLM backend that turns a checkout into a Payload."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pr_review.payload import Payload
from pr_review.reviewers._run import run_cli_reviewer
from pr_review.review_types.base import ReviewType

_REGISTRY: dict[str, "Reviewer"] = {}


class Reviewer(ABC):
    name: str
    default_model: str

    @abstractmethod
    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        """The CLI argv (with the model baked in) that runs this agent headless."""

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
        return run_cli_reviewer(
            self.command(model, extra_flags),
            workdir=workdir, owner=owner, repo=repo, number=number,
            base=base, review_type=review_type,
        )


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

- [ ] **Step 5: Replace `review` with `command` in claude.py**

Replace `src/pr_review/reviewers/claude.py` with:

```python
"""Claude headless reviewer (wraps `claude --print`)."""
from __future__ import annotations

from pr_review.reviewers.base import Reviewer, register


class ClaudeReviewer(Reviewer):
    name = "claude"
    default_model = "claude-opus-4-8"

    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        return [
            "claude", "--print", "--model", model,
            "--permission-mode", "acceptEdits", "--dangerously-skip-permissions",
            "--allowedTools", "Bash", "Read", "Grep", "Glob", "Write",
            *extra_flags,
        ]


register(ClaudeReviewer())
```

- [ ] **Step 6: Replace `review` with `command` in codex.py**

Replace `src/pr_review/reviewers/codex.py` with:

```python
"""Codex headless reviewer (wraps `codex exec`)."""
from __future__ import annotations

from pr_review.reviewers.base import Reviewer, register


class CodexReviewer(Reviewer):
    name = "codex"
    # Empty = let codex use its own configured default model (see codex auth).
    default_model = ""

    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        cmd = ["codex", "exec"]
        if model:
            cmd += ["--model", model]
        cmd += ["--dangerously-bypass-approvals-and-sandbox", *extra_flags]
        return cmd


register(CodexReviewer())
```

- [ ] **Step 7: Run the reviewer tests, then the full suite**

Run: `uv run pytest tests/test_reviewers.py -v`
Expected: PASS (registry, default_model, build_review_prompt, _review_env, and the new command tests).

Run: `uv run pytest -q`
Expected: PASS (no regressions — `review()` still works via the base class).

- [ ] **Step 8: Commit**

```bash
git add src/pr_review/reviewers/base.py src/pr_review/reviewers/claude.py src/pr_review/reviewers/codex.py src/pr_review/reviewers/_run.py tests/test_reviewers.py
git commit -m "refactor(pr-review): add Reviewer.command() and run_cli_payload"
```

---

### Task 2: Synthesis prompt + findings serialization

**Files:**
- Create: `src/pr_review/synthesis.py`
- Test: `tests/test_synthesis.py`

**Interfaces:**
- Consumes: `pr_review.collate.Job`, `pr_review.payload.{Payload, Comment}`.
- Produces:
  - `serialize_findings(jobs: list[Job]) -> str`
  - `build_synthesis_prompt(*, owner, repo, number, base, payload_path, findings) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_synthesis.py`:

```python
from pr_review.payload import Comment, Payload
from pr_review.synthesis import build_synthesis_prompt, serialize_findings


def test_serialize_findings_labels_sources_with_counts():
    jobs = [
        ("claude (opus)", "test-gap",
         Payload(body="b1", comments=[Comment("a.py", 3, "gap one"), Comment("a.py", 9, "gap two")])),
        ("codex", "infracode",
         Payload(body="b2", comments=[Comment("infra.tf", 5, "iam bloat")])),
    ]
    text = serialize_findings(jobs)
    assert "claude (opus) [test-gap] — 2 finding(s)" in text
    assert "codex [infracode] — 1 finding(s)" in text
    assert "a.py:3 — gap one" in text
    assert "infra.tf:5 — iam bloat" in text


def test_build_synthesis_prompt_has_context_findings_and_instructions():
    prompt = build_synthesis_prompt(
        owner="o", repo="r", number=7, base="main",
        payload_path="/tmp/p.json", findings="FINDINGS_HERE",
    )
    assert "Repository: o/r" in prompt
    assert "/tmp/p.json" in prompt
    assert "# Synthesis Review" in prompt
    assert "## Review stats" in prompt
    assert "HARD CAP: 8 inline comments" in prompt
    assert "FINDINGS_HERE" in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_synthesis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.synthesis'`.

- [ ] **Step 3: Create `synthesis.py` (pure helpers)**

`src/pr_review/synthesis.py`:

```python
"""LLM synthesis collation: one judge pass de-dupes and verifies findings."""
from __future__ import annotations

from pr_review.collate import Job

_INSTRUCTIONS = r"""# Synthesis Review

You are consolidating several independent reviews of the SAME pull request,
produced by different models and/or review types. Your job: produce ONE
de-duplicated, verified review. DO NOT POST ANYTHING. Your only side effect is
writing the payload file named in the context above.

## What you are given

Below, under "Findings to consolidate", are the findings from each source,
labelled `<agent> (<model>) [<review-type>]` with a raw count. The same real
issue may appear from multiple sources, worded differently or anchored to
nearby lines.

## What to do

1. Read the diff to ground yourself: `git diff origin/<base>...HEAD` (three-dot =
   exactly the changes on this branch).
2. De-duplicate: merge findings that describe the SAME issue, even when worded
   differently or anchored to slightly different lines. Treat them as one finding.
3. Verify each merged finding against the actual diff/code. DROP any finding you
   cannot substantiate from the code — these are likely hallucinations.
4. Confidence:
   - raised by 2+ models AND verified -> keep; label `[N models: a, b]`.
   - raised by 1 model AND verified -> keep; label `[single-source: <model>]`.
   - raised by 1 model AND not verifiable -> drop.
5. HARD CAP: 8 inline comments (highest-confidence first). List any overflow as a
   bullet list in the body under "## Additional findings not posted inline".

## Stats (REQUIRED)

Include a "## Review stats" section in the body with:
- one row per source: its raw finding count and how many of its findings survived.
- cross-model overlap: how many kept findings were corroborated by 2+ models.

## Output (REQUIRED)

Write the consolidated review to the payload file named in the context above, as
JSON:

  {
    "event": "COMMENT",
    "body": "<verdict + the ## Review stats section + any overflow list>",
    "comments": [
      {"path": "relative/path", "line": N, "side": "RIGHT",
       "body": "[2 models: claude, codex] **<finding>** ..."}
    ]
  }

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number. Then ALSO print the same review to stdout
in readable markdown. Writing the payload file is mandatory even when there are
zero kept findings.
"""


def serialize_findings(jobs: list[Job]) -> str:
    """Render every job's findings as text, grouped and counted per source."""
    blocks: list[str] = []
    for label, rtype, payload in jobs:
        lines = [f"### Source: {label} [{rtype}] — {len(payload.comments)} finding(s)"]
        if payload.body.strip():
            lines.append(f"Summary: {payload.body.strip()}")
        for c in payload.comments:
            lines.append(f"- {c.path}:{c.line} — {c.body}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_synthesis_prompt(
    *, owner: str, repo: str, number: int, base: str, payload_path: str, findings: str,
) -> str:
    context = (
        "You are consolidating GitHub pull request reviews. Context for this run:\n"
        f"- Repository: {owner}/{repo}\n"
        f"- PR number: {number}\n"
        f"- Base ref:  origin/{base}\n"
        "- HEAD is ALREADY checked out at the exact code to review. Do not switch branches.\n"
        f"- Payload file to write: {payload_path}\n"
    )
    return f"{context}\n{_INSTRUCTIONS}\n## Findings to consolidate\n\n{findings}\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_synthesis.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/synthesis.py tests/test_synthesis.py
git commit -m "feat(pr-review): add synthesis prompt and findings serialization"
```

---

### Task 3: LLMSynthesisCollator

**Files:**
- Modify: `src/pr_review/synthesis.py` (add the collator)
- Test: `tests/test_synthesis.py`

**Interfaces:**
- Consumes: `serialize_findings`/`build_synthesis_prompt` (Task 2); `pr_review.collate.{Collator, DeterministicMergeCollator, Job}`; `pr_review.reviewers._run.run_cli_payload` (Task 1); `pr_review.payload.Payload`.
- Produces:
  - `LLMSynthesisCollator(*, command: list[str], workdir: str, owner: str, repo: str, number: int, base: str, runner=run_cli_payload)` — a `Collator`. Its `collate(jobs)`: passthrough (delegate to `DeterministicMergeCollator`) for ≤1 job; otherwise run the judge via `runner(command, build, workdir=workdir)`; on any exception, warn to stderr and fall back to `DeterministicMergeCollator().collate(jobs)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_synthesis.py`:

```python
import pytest

from pr_review.synthesis import LLMSynthesisCollator


def _job(label, rtype, n):
    return (label, rtype, Payload(body=f"{label} body",
                                  comments=[Comment("f.py", i, f"c{i}") for i in range(n)]))


def _collator(runner):
    return LLMSynthesisCollator(
        command=["judge", "--print"], workdir="/wd",
        owner="o", repo="r", number=9, base="main", runner=runner,
    )


def test_synthesis_passthrough_for_single_job():
    p = Payload(body="solo", comments=[Comment("a", 1, "x")])

    def runner(*a, **k):
        raise AssertionError("runner must not be called for a single job")

    out = _collator(runner).collate([("claude (opus)", "test-gap", p)])
    assert out is p


def test_synthesis_runs_judge_for_multiple_jobs():
    captured = {}

    def runner(command, build_prompt, *, workdir):
        captured["command"] = command
        captured["workdir"] = workdir
        captured["prompt"] = build_prompt("/tmp/x.json")
        return Payload(body="SYNTH", comments=[Comment("a", 1, "merged")])

    jobs = [_job("claude (opus)", "test-gap", 2), _job("codex", "test-gap", 2)]
    out = _collator(runner).collate(jobs)
    assert out.body == "SYNTH"
    assert captured["command"] == ["judge", "--print"]
    assert captured["workdir"] == "/wd"
    assert "claude (opus) [test-gap]" in captured["prompt"]
    assert "/tmp/x.json" in captured["prompt"]


def test_synthesis_falls_back_to_merge_on_failure(capsys):
    def runner(*a, **k):
        raise RuntimeError("judge died")

    jobs = [_job("claude (opus)", "test-gap", 1), _job("codex", "test-gap", 1)]
    out = _collator(runner).collate(jobs)
    assert "## test-gap — claude (opus)" in out.body
    assert "## test-gap — codex" in out.body
    assert len(out.comments) == 2
    assert "synthesis failed" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_synthesis.py -k synthesis -v`
Expected: FAIL — `ImportError: cannot import name 'LLMSynthesisCollator'`.

- [ ] **Step 3: Add the collator**

In `src/pr_review/synthesis.py`, update the imports at the top to:

```python
import sys
from collections.abc import Callable

from pr_review.collate import Collator, DeterministicMergeCollator, Job
from pr_review.payload import Payload
from pr_review.reviewers._run import run_cli_payload
```

and append the class at the end of the file:

```python
class LLMSynthesisCollator(Collator):
    def __init__(
        self,
        *,
        command: list[str],
        workdir: str,
        owner: str,
        repo: str,
        number: int,
        base: str,
        runner: Callable[..., Payload] = run_cli_payload,
    ):
        self._command = command
        self._workdir = workdir
        self._owner = owner
        self._repo = repo
        self._number = number
        self._base = base
        self._runner = runner

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
            return self._runner(self._command, build, workdir=self._workdir)
        except Exception as e:
            print(
                f"pr-review: synthesis failed ({self._command[0]}: {e}); "
                "falling back to the raw merge.",
                file=sys.stderr,
            )
            return DeterministicMergeCollator().collate(jobs)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_synthesis.py -v`
Expected: PASS (Task 2 + Task 3 tests).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pr_review/synthesis.py tests/test_synthesis.py
git commit -m "feat(pr-review): add LLMSynthesisCollator with deterministic fallback"
```

---

### Task 4: CLI wiring (--synthesis-model, --no-synthesis)

**Files:**
- Modify: `src/pr_review/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `LLMSynthesisCollator` (Task 3); `DeterministicMergeCollator`; `get_reviewer(...).command(...)` (Task 1); existing `RunConfig`, `_parse_agent_models`, `build_jobs`, `run_reviews`.
- Produces:
  - `RunConfig` gains `synthesis_model: tuple[str, str]` and `no_synthesis: bool`.
  - `config_from_args` parses `--synthesis-model AGENT[=MODEL]` (default `("claude", "claude-opus-4-8")`) and `--no-synthesis`.
  - `build_collator(cfg, *, workdir: str, base: str) -> Collator` — `DeterministicMergeCollator()` when `no_synthesis`, else `LLMSynthesisCollator(...)` with the judge command.
  - `main` builds the collator after cloning and passes it to `run_reviews`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_config_synthesis_defaults():
    cfg = config_from_args(["org/repo#1"])
    assert cfg.synthesis_model == ("claude", "claude-opus-4-8")
    assert cfg.no_synthesis is False


def test_config_synthesis_model_override():
    cfg = config_from_args(["--synthesis-model", "codex=gpt-5", "org/repo#1"])
    assert cfg.synthesis_model == ("codex", "gpt-5")


def test_config_synthesis_bare_agent_uses_default():
    cfg = config_from_args(["--synthesis-model", "claude", "org/repo#1"])
    assert cfg.synthesis_model == ("claude", "claude-opus-4-8")


def test_config_no_synthesis_flag():
    cfg = config_from_args(["--no-synthesis", "org/repo#1"])
    assert cfg.no_synthesis is True


def test_build_collator_returns_synthesis_by_default():
    from pr_review.cli import build_collator
    from pr_review.synthesis import LLMSynthesisCollator

    cfg = config_from_args(["org/repo#1"])
    assert isinstance(build_collator(cfg, workdir="/wd", base="main"), LLMSynthesisCollator)


def test_build_collator_no_synthesis_returns_merge():
    from pr_review.cli import build_collator
    from pr_review.collate import DeterministicMergeCollator

    cfg = config_from_args(["--no-synthesis", "org/repo#1"])
    assert isinstance(build_collator(cfg, workdir="/wd", base="main"), DeterministicMergeCollator)


def test_build_collator_uses_the_judge_command():
    from pr_review.cli import build_collator

    cfg = config_from_args(["--synthesis-model", "codex=gpt-5", "org/repo#1"])
    collator = build_collator(cfg, workdir="/wd", base="main")
    assert collator._command[:4] == ["codex", "exec", "--model", "gpt-5"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "synthesis or build_collator" -v`
Expected: FAIL — `AttributeError: 'RunConfig' object has no attribute 'synthesis_model'`.

- [ ] **Step 3: Add the synthesis config, parser, and build_collator**

In `src/pr_review/cli.py`:

1. Add imports near the existing ones:
```python
from pr_review.collate import Collator, DeterministicMergeCollator
from pr_review.synthesis import LLMSynthesisCollator
```

2. Add two fields to the `RunConfig` dataclass (after `flags_by_agent`):
```python
    synthesis_model: tuple[str, str]
    no_synthesis: bool
```

3. Add the single-pair parser next to `_parse_agent_models`:
```python
def _parse_synthesis_model(value: str) -> tuple[str, str]:
    agent, sep, model = value.partition("=")
    agent = agent.strip()
    reviewer = get_reviewer(agent)  # validates the agent; raises ValueError
    model = model.strip() if (sep and model.strip()) else reviewer.default_model
    return (agent, model)
```

4. Add two arguments in `build_parser` (before `return p`):
```python
    p.add_argument(
        "--synthesis-model", metavar="AGENT[=MODEL]", default=None,
        help=(
            "judge agent/model that de-dupes and verifies findings across jobs "
            f"(default: claude={DEFAULT_MODEL})"
        ),
    )
    p.add_argument(
        "--no-synthesis", action="store_true",
        help="skip the synthesis pass; raw-merge multi-job results (default: false)",
    )
```

5. In `config_from_args`, set the two new fields in the returned `RunConfig`:
```python
        synthesis_model=(
            _parse_synthesis_model(args.synthesis_model)
            if args.synthesis_model else ("claude", DEFAULT_MODEL)
        ),
        no_synthesis=args.no_synthesis,
```

6. Add `build_collator` (next to `build_jobs`):
```python
def build_collator(cfg: RunConfig, *, workdir: str, base: str) -> Collator:
    if cfg.no_synthesis:
        return DeterministicMergeCollator()
    agent, model = cfg.synthesis_model
    command = get_reviewer(agent).command(model, cfg.flags_by_agent.get(agent, []))
    return LLMSynthesisCollator(
        command=command, workdir=workdir,
        owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number, base=base,
    )
```

- [ ] **Step 4: Wire the collator into `main`**

In `main`, build the collator after `clone_pr` and pass it to `run_reviews`. Replace the `run_reviews(...)` call so it reads:

```python
    collator = build_collator(cfg, workdir=checkout.workdir, base=checkout.base)
    try:
        result = run_reviews(
            jobs=jobs, workdir=checkout.workdir, base=checkout.base,
            owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number,
            collator=collator,
        )
```

(Leave the surrounding `print`, the `finally` cleanup, and the result handling unchanged.)

- [ ] **Step 5: Run the CLI tests, then the full suite**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Verify `--help`**

Run: `uv run pr-review --help`
Expected: usage lists `[--synthesis-model AGENT[=MODEL]]` and `[--no-synthesis]`; the `--synthesis-model` line shows `default: claude=claude-opus-4-8`.

- [ ] **Step 7: Commit**

```bash
git add src/pr_review/cli.py tests/test_cli.py
git commit -m "feat(pr-review): wire --synthesis-model / --no-synthesis and build_collator"
```

---

### Task 5: Docs (README + CLAUDE)

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the finished behaviour from Tasks 1–4.

- [ ] **Step 1: Document synthesis in the README**

In `README.md`, immediately after the "Selecting agents, models, and review types" section (before "### Posting behaviour"), insert:

```markdown
### Collating multiple models

When a run produces more than one job, pr-review runs a **synthesis pass** before
posting: a judge LLM is handed every finding (tagged by model and review-type)
plus the diff, and it de-dupes findings that overlap across models, verifies each
against the code (dropping ones it can't substantiate), and emits one review —
each comment labelled by confidence (`[2 models: claude, codex]` /
`[single-source: codex]`), with a `## Review stats` section showing per-model
counts and cross-model overlap.

- `--synthesis-model AGENT[=MODEL]` — the judge (default `claude=claude-opus-4-8`;
  e.g. `--synthesis-model codex=gpt-5`).
- `--no-synthesis` — skip it and raw-merge the jobs (today's behaviour).
- A single job skips synthesis; if the judge run fails, pr-review falls back to
  the raw merge so you always get a review.
```

Then add two rows to the Options table (after the `--codex-flags` row):

```markdown
| `--synthesis-model agent[=model]` | Judge that de-dupes/verifies findings across jobs | `claude=claude-opus-4-8` |
| `--no-synthesis` | Skip synthesis; raw-merge multi-job results | off |
```

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md`:

1. Update the file/test count line — find `holds 11 files, one per `src/pr_review/` module (80 tests total)` and replace with the real numbers from `uv run pytest -q` (it will be 12 files including `test_synthesis.py`; write the exact passing-test count from the run).

2. Update the `test_reviewers.py` walkthrough line to mention `command`:
   find the `test_reviewers.py` bullet and replace with:
```markdown
- **test_reviewers.py** — the `Reviewer` registry (`claude` and `codex` registered,
  each with a `default_model`, unknown raises), `Reviewer.command` argv for both
  agents (codex omits `--model` when empty), the shared `build_review_prompt`, and
  `_review_env` (trusts the clone's `mise.toml`). The `review()` calls shell out to
  `claude`/`codex` and are not unit-tested.
```

3. Add a `test_synthesis.py` bullet at the end of the test-suite list:
```markdown
- **test_synthesis.py** — `serialize_findings` (sources labelled `<agent> (<model>)
  [<type>]` with counts), `build_synthesis_prompt` (context + findings + dedupe/
  verify/stats instructions), and `LLMSynthesisCollator.collate` with an injected
  fake runner (single-job passthrough, judge runs for >1 job, and fall-back to the
  deterministic merge when the judge raises).
```

4. Update the `test_cli.py` bullet to mention synthesis config: find it and append before its closing period: `, plus --synthesis-model / --no-synthesis parsing and build_collator (synthesis vs deterministic, judge command)`.

- [ ] **Step 3: Verify the docs match reality**

Run: `uv run pr-review --help` and confirm the README's `--synthesis-model`/`--no-synthesis` descriptions match. Run `uv run pytest -q` and write the exact passing-test count into the CLAUDE.md line from Step 2.1.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs(pr-review): document cross-model synthesis collation"
```

---

## Self-Review

**Spec coverage:**
- LLM synthesis pass for >1 job; single-job passthrough → Task 3 (`LLMSynthesisCollator.collate`).
- Judge via `--synthesis-model` (default `claude=claude-opus-4-8`, bare-agent default, registry validation) → Task 4.
- `--no-synthesis` raw-merge fallback → Task 4 (`build_collator`).
- Dedupe / verify / confidence labels / 8-cap / stats-in-body → Task 2 (`_INSTRUCTIONS`).
- Fallback to deterministic merge on judge failure → Task 3.
- `Reviewer.command()` + `run_cli_payload` refactor → Task 1.
- Stats reach PR body + terminal via existing `render()` (no new plumbing) → no code needed; covered by the body containing the stats (Task 2 instructions) + unchanged `main`.
- Findings serialized tagged-with-counts → Task 2 (`serialize_findings`).
- Docs → Task 5.

**Placeholder scan:** none — every code step contains complete, runnable content; the only `<...>` tokens are inside the judge instruction text (the JSON schema example) and user-supplied shell values.

**Type consistency:** `run_cli_payload(cmd_prefix, build_prompt, *, workdir) -> Payload` (Task 1) is consumed by `LLMSynthesisCollator` (Task 3) via the injectable `runner` with the same `(command, build, workdir=...)` call shape, and by `run_cli_reviewer` (Task 1). `Reviewer.command(model, extra_flags) -> list[str]` (Task 1) is consumed by `build_collator` (Task 4). `LLMSynthesisCollator(*, command, workdir, owner, repo, number, base, runner=...)` (Task 3) matches its construction in `build_collator` (Task 4). `RunConfig.synthesis_model: tuple[str, str]` / `no_synthesis: bool` (Task 4) are produced by `config_from_args` and consumed by `build_collator` in the same task. `Job = (label, type_name, payload)` is used identically by `serialize_findings` (Task 2) and the collator (Task 3).
