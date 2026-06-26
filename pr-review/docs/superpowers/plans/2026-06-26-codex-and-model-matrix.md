# Codex Agent + Per-Agent Model Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Codex agent and a per-agent model dimension so a run is the product of review_types × (agent, model) pairs, selected via a repeatable `--model agent[=models]` flag (with `--agent` removed and interactive prompting when omitted).

**Architecture:** Extract the shared payload-file/prompt runner so Claude and Codex reviewers differ only by their CLI command. Move `model` (and per-agent `extra_flags`) out of `run_reviews` into each `ReviewJob`. Replace the `--agent` + single `--model` CLI with one repeatable `--model agent[=models]` flag parsed into `(agent, model)` pairs, plus per-agent `--claude-flags`/`--codex-flags`. Both `--model` and `--review-type`, when omitted, resolve via an interactive `/dev/tty` menu (shared `select_from_menu` helper) or exit 2 with no terminal.

**Tech Stack:** Python 3.14, uv, pytest, stdlib-only runtime, `claude` and `codex` CLIs invoked as subprocesses.

## Global Constraints

- Runtime dependencies: none (stdlib only). pytest is dev-only.
- Reviewer default models: `claude` → `claude-opus-4-8`; `codex` → `gpt-5-codex`.
- `--model` is **repeatable** (`action="append"`); each value is `agent` or `agent=model[,model…]`. Bare `agent` → that agent's `default_model`. Model strings pass **verbatim** to the agent's CLI (no aliases).
- The `agent` key in `--model` is validated against the reviewer registry; unknown → `ValueError` listing registered agents, before any clone.
- `--agent` is **removed**.
- Extra flags are **per-agent**: `--claude-flags` for claude jobs, `--codex-flags` for codex jobs; stored as `flags_by_agent: dict[str, list[str]]`; an agent with neither gets `[]`.
- Omitted `--model` or `--review-type` → interactive prompt on `/dev/tty`; with no terminal, exit 2 with a `pass --<flag> …` hint. Prompt defaults (claude, `claude-opus-4-8`) reproduce the old default in two keystrokes.
- Claude command (unchanged): `claude --print --model <m> --permission-mode acceptEdits --dangerously-skip-permissions --allowedTools Bash Read Grep Glob Write <extra_flags>`, prompt on stdin, cwd=clone.
- Codex command: `codex exec --model <m> --dangerously-bypass-approvals-and-sandbox <extra_flags>`, prompt on stdin, cwd=clone.
- Collated section labels include the model: `## <type> — <agent> (<model>)`. `collate.py` is unchanged (label is an opaque string).
- Inline comment cap stays 8; payload schema unchanged.

---

### Task 1: Shared CLI-reviewer runner + reviewer default_model

**Files:**
- Create: `src/pr_review/reviewers/_run.py`
- Modify: `src/pr_review/reviewers/base.py` (add `default_model` to the ABC)
- Modify: `src/pr_review/reviewers/claude.py` (use the shared runner; add `default_model`)
- Test: `tests/test_reviewers.py`

**Interfaces:**
- Consumes: `pr_review.payload.Payload`/`parse_payload`; `pr_review.review_types.base.ReviewType`.
- Produces:
  - `pr_review.reviewers._run.build_review_prompt(*, owner, repo, number, base, payload_path, review_type) -> str`
  - `pr_review.reviewers._run.run_cli_reviewer(cmd_prefix: Sequence[str], *, workdir, owner, repo, number, base, review_type) -> Payload`
  - `Reviewer.default_model: str` (class attribute on the ABC); `ClaudeReviewer.default_model == "claude-opus-4-8"`.

- [ ] **Step 1: Update the test to target the shared prompt builder**

Replace `tests/test_reviewers.py` with:

```python
import pytest

from pr_review.reviewers import available, get_reviewer
from pr_review.reviewers._run import build_review_prompt
from pr_review.review_types import get_review_type


def test_claude_is_registered():
    assert "claude" in available()
    assert get_reviewer("claude").name == "claude"


def test_claude_default_model():
    assert get_reviewer("claude").default_model == "claude-opus-4-8"


def test_unknown_reviewer_raises():
    with pytest.raises(ValueError):
        get_reviewer("nope")


def test_build_review_prompt_includes_context_and_instructions():
    prompt = build_review_prompt(
        owner="org", repo="repo", number=7, base="main",
        payload_path="/tmp/p.json", review_type=get_review_type("test-gap"),
    )
    assert "Repository: org/repo" in prompt
    assert "PR number: 7" in prompt
    assert "origin/main" in prompt
    assert "/tmp/p.json" in prompt
    assert "# Test Coverage Review" in prompt
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_reviewers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_review.reviewers._run'`.

- [ ] **Step 3: Create the shared runner**

`src/pr_review/reviewers/_run.py`:

```python
"""Shared payload-file runner used by CLI-backed reviewers."""
from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Sequence

from pr_review.payload import Payload, parse_payload
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


def build_review_prompt(
    *, owner: str, repo: str, number: int, base: str,
    payload_path: str, review_type: ReviewType,
) -> str:
    context = _build_context(
        owner=owner, repo=repo, number=number, base=base, payload_path=payload_path
    )
    return context + "\n" + review_type.instructions()


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
    fd, payload_path = tempfile.mkstemp(prefix="pr-review-payload.", suffix=".json")
    os.close(fd)
    try:
        prompt = build_review_prompt(
            owner=owner, repo=repo, number=number, base=base,
            payload_path=payload_path, review_type=review_type,
        )
        subprocess.run(list(cmd_prefix), cwd=workdir, input=prompt, text=True, check=True)
        with open(payload_path, encoding="utf-8") as f:
            raw = f.read()
        if not raw.strip():
            raise RuntimeError("reviewer produced an empty payload")
        return parse_payload(raw)
    finally:
        try:
            os.unlink(payload_path)
        except FileNotFoundError:
            pass
```

- [ ] **Step 4: Add `default_model` to the Reviewer ABC**

In `src/pr_review/reviewers/base.py`, add the attribute annotation right after `name: str`:

```python
class Reviewer(ABC):
    name: str
    default_model: str
```

(Leave the rest of `base.py` unchanged.)

- [ ] **Step 5: Refactor ClaudeReviewer onto the shared runner**

Replace `src/pr_review/reviewers/claude.py` with:

```python
"""Claude headless reviewer (wraps `claude --print`)."""
from __future__ import annotations

from pr_review.payload import Payload
from pr_review.reviewers._run import run_cli_reviewer
from pr_review.reviewers.base import Reviewer, register
from pr_review.review_types.base import ReviewType


class ClaudeReviewer(Reviewer):
    name = "claude"
    default_model = "claude-opus-4-8"

    def review(
        self, *, workdir: str, base: str, owner: str, repo: str, number: int,
        review_type: ReviewType, model: str, extra_flags: list[str],
    ) -> Payload:
        cmd = [
            "claude", "--print", "--model", model,
            "--permission-mode", "acceptEdits", "--dangerously-skip-permissions",
            "--allowedTools", "Bash", "Read", "Grep", "Glob", "Write",
            *extra_flags,
        ]
        return run_cli_reviewer(
            cmd, workdir=workdir, owner=owner, repo=repo, number=number,
            base=base, review_type=review_type,
        )


register(ClaudeReviewer())
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_reviewers.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (no regressions).

- [ ] **Step 8: Commit**

```bash
git add src/pr_review/reviewers/_run.py src/pr_review/reviewers/base.py src/pr_review/reviewers/claude.py tests/test_reviewers.py
git commit -m "refactor(pr-review): extract shared reviewer runner; add default_model"
```

---

### Task 2: CodexReviewer

**Files:**
- Create: `src/pr_review/reviewers/codex.py`
- Modify: `src/pr_review/reviewers/__init__.py` (register codex)
- Test: `tests/test_reviewers.py`

**Interfaces:**
- Consumes: `pr_review.reviewers._run.run_cli_reviewer`; `Reviewer`/`register`.
- Produces: `CodexReviewer` registered under `"codex"`, `default_model == "gpt-5-codex"`.

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_reviewers.py`:

```python
def test_codex_is_registered():
    assert "codex" in available()
    assert get_reviewer("codex").name == "codex"


def test_codex_default_model():
    assert get_reviewer("codex").default_model == "gpt-5-codex"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_reviewers.py -k codex -v`
Expected: FAIL — `ValueError: unknown reviewer: 'codex'`.

- [ ] **Step 3: Create CodexReviewer**

`src/pr_review/reviewers/codex.py`:

```python
"""Codex headless reviewer (wraps `codex exec`)."""
from __future__ import annotations

from pr_review.payload import Payload
from pr_review.reviewers._run import run_cli_reviewer
from pr_review.reviewers.base import Reviewer, register
from pr_review.review_types.base import ReviewType


class CodexReviewer(Reviewer):
    name = "codex"
    default_model = "gpt-5-codex"

    def review(
        self, *, workdir: str, base: str, owner: str, repo: str, number: int,
        review_type: ReviewType, model: str, extra_flags: list[str],
    ) -> Payload:
        cmd = [
            "codex", "exec", "--model", model,
            "--dangerously-bypass-approvals-and-sandbox",
            *extra_flags,
        ]
        return run_cli_reviewer(
            cmd, workdir=workdir, owner=owner, repo=repo, number=number,
            base=base, review_type=review_type,
        )


register(CodexReviewer())
```

- [ ] **Step 4: Register codex for its import side-effect**

In `src/pr_review/reviewers/__init__.py`, add the import next to the existing `claude` import:

```python
from pr_review.reviewers import claude  # noqa: F401  (registers ClaudeReviewer)
from pr_review.reviewers import codex  # noqa: F401  (registers CodexReviewer)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_reviewers.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add src/pr_review/reviewers/codex.py src/pr_review/reviewers/__init__.py tests/test_reviewers.py
git commit -m "feat(pr-review): add Codex reviewer (codex exec)"
```

---

### Task 3: Per-job model & flags in the orchestrator

**Files:**
- Modify: `src/pr_review/orchestrator.py`
- Modify: `src/pr_review/cli.py` (`build_jobs` constructs the new `ReviewJob`; `main` drops `model`/`extra_flags` from the `run_reviews` call)
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `pr_review.collate.{Collator,DeterministicMergeCollator,Job}`; `Reviewer`; `ReviewType`; `Payload`.
- Produces:
  - `ReviewJob(reviewer: Reviewer, review_type: ReviewType, model: str, extra_flags: list[str])`
  - `run_reviews(*, jobs: list[ReviewJob], workdir, base, owner, repo, number, collator=None, max_workers=None) -> Payload` (no `model`/`extra_flags` params). Each result label is `f"{reviewer.name} ({model})"`.

- [ ] **Step 1: Rewrite the orchestrator test for per-job model/flags**

Replace `tests/test_orchestrator.py` with:

```python
import pytest

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
        self.calls.append({"type": review_type.name, "model": model, "flags": extra_flags})
        return Payload(body=f"{self.name}/{review_type.name}", comments=[Comment("f.py", 1, "g")])


def _run(jobs):
    return run_reviews(jobs=jobs, workdir="/wd", base="main", owner="o", repo="r", number=1)


def test_single_job_passthrough_and_per_job_args():
    r = FakeReviewer("claude")
    out = _run([ReviewJob(r, FakeType("test-gap"), "m1", ["--x"])])
    assert out.body == "claude/test-gap"
    assert r.calls == [{"type": "test-gap", "model": "m1", "flags": ["--x"]}]


def test_two_jobs_merge_label_includes_model():
    jobs = [
        ReviewJob(FakeReviewer("claude"), FakeType("test-gap"), "m1", []),
        ReviewJob(FakeReviewer("codex"), FakeType("test-gap"), "m2", []),
    ]
    out = _run(jobs)
    assert "## test-gap — claude (m1)" in out.body
    assert "## test-gap — codex (m2)" in out.body
    assert len(out.comments) == 2


class BoomReviewer:
    name = "boom"

    def review(self, **kwargs):
        raise RuntimeError("kaboom")


def test_run_reviews_attributes_failing_job():
    jobs = [ReviewJob(BoomReviewer(), FakeType("test-gap"), "m1", [])]
    with pytest.raises(RuntimeError, match=r"boom \(m1\)/test-gap"):
        _run(jobs)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: FAIL — `TypeError: ReviewJob.__init__() takes 3 positional arguments but 5 were given` (or `run_reviews` missing `model`).

- [ ] **Step 3: Update the orchestrator**

Replace `src/pr_review/orchestrator.py` with:

```python
"""Fan out (agent, model) x review-type jobs in parallel, then collate."""
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
    model: str
    extra_flags: list[str]


def run_reviews(
    *,
    jobs: list[ReviewJob],
    workdir: str,
    base: str,
    owner: str,
    repo: str,
    number: int,
    collator: Collator | None = None,
    max_workers: int | None = None,
) -> Payload:
    collator = collator or DeterministicMergeCollator()

    def _one(job: ReviewJob) -> Job:
        label = f"{job.reviewer.name} ({job.model})"
        try:
            payload = job.reviewer.review(
                workdir=workdir, base=base, owner=owner, repo=repo, number=number,
                review_type=job.review_type, model=job.model, extra_flags=job.extra_flags,
            )
        except Exception as e:
            raise RuntimeError(
                f"{label}/{job.review_type.name} review failed: {e}"
            ) from e
        return (label, job.review_type.name, payload)

    with ThreadPoolExecutor(max_workers=max_workers or len(jobs) or 1) as ex:
        results = list(ex.map(_one, jobs))
    return collator.collate(results)
```

- [ ] **Step 4: Update `build_jobs` and `main` in `cli.py`**

In `src/pr_review/cli.py`, change `build_jobs` to construct the new `ReviewJob` (still using the current single `cfg.model` and `cfg.extra_flags`):

```python
def build_jobs(cfg: RunConfig) -> list[ReviewJob]:
    return [
        ReviewJob(get_reviewer(a), get_review_type(t), cfg.model, cfg.extra_flags)
        for a in cfg.agent_names
        for t in cfg.type_names or []
    ]
```

And in `main`, drop `model=` and `extra_flags=` from the `run_reviews(...)` call so it reads:

```python
        payload = run_reviews(
            jobs=jobs, workdir=checkout.workdir, base=checkout.base,
            owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number,
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator.py tests/test_cli.py -v`
Expected: PASS (orchestrator tests green; existing CLI tests still green).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pr_review/orchestrator.py src/pr_review/cli.py tests/test_orchestrator.py
git commit -m "refactor(pr-review): carry model and extra_flags per ReviewJob"
```

---

### Task 4: `--model agent=models` CLI + per-agent flags (drop `--agent`)

**Files:**
- Modify: `src/pr_review/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `get_reviewer`/`reviewers_available`; `get_review_type`/`types_available`; `parse_target`/`Target`; `ReviewJob`.
- Produces:
  - `DEFAULT_MODEL = "claude-opus-4-8"`
  - `RunConfig(target, agent_models: list[tuple[str, str]], type_names: list[str] | None, flags_by_agent: dict[str, list[str]], yes, no_post, keep)`
  - `config_from_args(argv) -> RunConfig` (parses repeatable `--model`, `--claude-flags`, `--codex-flags`; no `--agent`)
  - `build_jobs(cfg) -> list[ReviewJob]` over `(agent, model) × review_type` with `flags_by_agent.get(agent, [])`

- [ ] **Step 1: Rewrite the CLI test for the new surface**

Replace `tests/test_cli.py` with:

```python
import pytest

from pr_review.cli import build_jobs, config_from_args
from pr_review.target import Target


def test_config_defaults():
    cfg = config_from_args(["org/repo#3"])
    assert cfg.target == Target("org", "repo", 3)
    assert cfg.agent_models == [("claude", "claude-opus-4-8")]
    assert cfg.type_names is None
    assert cfg.flags_by_agent == {}
    assert cfg.yes is False and cfg.no_post is False and cfg.keep is False


def test_model_bare_agent_uses_default_model():
    cfg = config_from_args(["--model", "codex", "org/repo#1"])
    assert cfg.agent_models == [("codex", "gpt-5-codex")]


def test_model_explicit_and_repeatable():
    cfg = config_from_args([
        "--model", "claude=claude-opus-4-8,claude-fable-5",
        "--model", "codex=gpt-5,gpt-5.5",
        "--review-type", "test-gap",
        "org/repo#9",
    ])
    assert cfg.agent_models == [
        ("claude", "claude-opus-4-8"), ("claude", "claude-fable-5"),
        ("codex", "gpt-5"), ("codex", "gpt-5.5"),
    ]


def test_model_unknown_agent_raises():
    with pytest.raises(ValueError):
        config_from_args(["--model", "ghost=x", "org/repo#1"])


def test_flags_by_agent_parsing():
    cfg = config_from_args([
        "--claude-flags=--foo --bar", "--codex-flags=--oss", "org/repo#1",
    ])
    assert cfg.flags_by_agent == {"claude": ["--foo", "--bar"], "codex": ["--oss"]}


def test_help_shows_default_values(capsys):
    with pytest.raises(SystemExit):
        config_from_args(["--help"])
    out = capsys.readouterr().out
    assert "claude-opus-4-8" in out
    assert "default:" in out


def test_build_jobs_full_matrix_and_per_agent_flags():
    cfg = config_from_args([
        "--model", "claude=claude-opus-4-8", "--model", "codex=gpt-5",
        "--review-type", "test-gap,infracode",
        "--claude-flags=--foo", "org/repo#1",
    ])
    jobs = build_jobs(cfg)
    # 2 (agent,model) pairs x 2 review types = 4 jobs
    assert len(jobs) == 4
    triples = {(j.reviewer.name, j.review_type.name, j.model) for j in jobs}
    assert triples == {
        ("claude", "test-gap", "claude-opus-4-8"),
        ("claude", "infracode", "claude-opus-4-8"),
        ("codex", "test-gap", "gpt-5"),
        ("codex", "infracode", "gpt-5"),
    }
    claude_job = next(j for j in jobs if j.reviewer.name == "claude")
    codex_job = next(j for j in jobs if j.reviewer.name == "codex")
    assert claude_job.extra_flags == ["--foo"]
    assert codex_job.extra_flags == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `AttributeError: 'RunConfig' object has no attribute 'agent_models'` (and `--model` not repeatable).

- [ ] **Step 3: Rewrite `cli.py`'s parsing, config, and build_jobs**

Replace `src/pr_review/cli.py` with:

```python
"""pr-review command-line entry point."""
from __future__ import annotations

import argparse
import shlex
import sys
from dataclasses import dataclass

from pr_review.checkout import cleanup, clone_pr
from pr_review.orchestrator import ReviewJob, run_reviews
from pr_review.reviewers import available as reviewers_available, get_reviewer
from pr_review.review_types import available as types_available, get_review_type
from pr_review.target import Target, parse_target
from pr_review import output, prompts

DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class RunConfig:
    target: Target
    agent_models: list[tuple[str, str]]
    type_names: list[str] | None
    flags_by_agent: dict[str, list[str]]
    yes: bool
    no_post: bool
    keep: bool


def _split(value: str) -> list[str]:
    return [s for s in (part.strip() for part in value.split(",")) if s]


def _parse_agent_models(values: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for value in values:
        agent, sep, models_str = value.partition("=")
        agent = agent.strip()
        reviewer = get_reviewer(agent)  # validates agent; raises ValueError
        models = _split(models_str) if (sep and models_str.strip()) else [reviewer.default_model]
        for model in models:
            if (agent, model) not in pairs:
                pairs.append((agent, model))
    return pairs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr-review",
        description="Review a GitHub PR in an isolated clone with one or more LLMs.",
    )
    p.add_argument("target", help="PR URL or owner/repo#N (or 'help' for this message)")
    p.add_argument(
        "--model", action="append", metavar="AGENT[=MODELS]", default=None,
        help=(
            "per-agent models, repeatable, e.g. --model claude=claude-opus-4-8,claude-fable-5 "
            f"(agents: {', '.join(reviewers_available())}; default: claude=claude-opus-4-8)"
        ),
    )
    p.add_argument(
        "--review-type", dest="types", default=None,
        help=(
            "comma-separated review types "
            f"(available: {', '.join(types_available())}; omit to choose interactively)"
        ),
    )
    p.add_argument(
        "--post-without-prompting", action="store_true",
        help="Post the review without the confirmation prompt (default: false)",
    )
    p.add_argument(
        "--print-only", action="store_true",
        help="Print the review only; never post and never prompt (default: false)",
    )
    p.add_argument(
        "--claude-flags", default="",
        help='Extra flags for claude jobs, e.g. --claude-flags="--debug" (default: "")',
    )
    p.add_argument(
        "--codex-flags", default="",
        help='Extra flags for codex jobs, e.g. --codex-flags="--oss" (default: "")',
    )
    p.add_argument(
        "--keep-clone", action="store_true",
        help="Keep the temporary clone on exit instead of deleting it (default: false)",
    )
    return p


def config_from_args(argv: list[str]) -> RunConfig:
    # `pr-review help` behaves like `pr-review --help`.
    if argv and argv[0] == "help":
        argv = ["--help", *argv[1:]]
    args = build_parser().parse_args(argv)

    agent_models = (
        _parse_agent_models(args.model) if args.model else [("claude", DEFAULT_MODEL)]
    )
    flags_by_agent: dict[str, list[str]] = {}
    if args.claude_flags:
        flags_by_agent["claude"] = shlex.split(args.claude_flags)
    if args.codex_flags:
        flags_by_agent["codex"] = shlex.split(args.codex_flags)

    return RunConfig(
        target=parse_target(args.target),
        agent_models=agent_models,
        type_names=_split(args.types) if args.types is not None else None,
        flags_by_agent=flags_by_agent,
        yes=args.post_without_prompting,
        no_post=args.print_only,
        keep=args.keep_clone,
    )


def build_jobs(cfg: RunConfig) -> list[ReviewJob]:
    return [
        ReviewJob(get_reviewer(agent), get_review_type(t), model,
                  cfg.flags_by_agent.get(agent, []))
        for agent, model in cfg.agent_models
        for t in cfg.type_names or []
    ]


def resolve_review_types(
    type_names: list[str] | None,
    *,
    has_tty: bool,
    prompt_fn=prompts.prompt_review_types_via_tty,
) -> list[str]:
    if type_names is not None:
        return type_names
    if not has_tty:
        print(
            "pr-review: no terminal to prompt for --review-type.\n"
            f"  pass one, e.g. --review-type {','.join(types_available())}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return prompt_fn(types_available())


def main(argv: list[str] | None = None) -> int:
    cfg = config_from_args(sys.argv[1:] if argv is None else argv)
    cfg.type_names = resolve_review_types(cfg.type_names, has_tty=output.tty_available())
    jobs = build_jobs(cfg)  # validates agent/type names before any clone

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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Verify `--help` and a dry parse**

Run:
```bash
uv run pr-review --help
```
Expected: usage shows `[--model AGENT[=MODELS]]`, no `--agent`, and `--codex-flags`; the `--model` line shows `default: claude=claude-opus-4-8`.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pr_review/cli.py tests/test_cli.py
git commit -m "feat(pr-review): per-agent --model matrix and --codex-flags; drop --agent"
```

---

### Task 5: Shared menu + agent/model prompt helpers

**Files:**
- Modify: `src/pr_review/prompts.py`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `select_from_menu(available: list[str], reader, writer, *, default: str, what: str) -> list[str]`
  - `choose_review_types(available, reader, writer, *, default="test-gap") -> list[str]` (now wraps `select_from_menu`)
  - `choose_agent_models(agents: list[str], default_model: Callable[[str], str], reader, writer) -> list[tuple[str, str]]`
  - `prompt_agent_models_via_tty(agents: list[str], default_model: Callable[[str], str]) -> list[tuple[str, str]]`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_prompts.py`:

```python
from pr_review.prompts import choose_agent_models, select_from_menu


def _scripted(lines):
    it = iter(lines)
    return lambda: next(it)


_DM = {"claude": "claude-opus-4-8", "codex": "gpt-5-codex"}


def test_select_from_menu_by_number_and_name():
    _, w = _sink()
    assert select_from_menu(
        ["claude", "codex"], _reader("1,codex\n"), w, default="claude", what="agent"
    ) == ["claude", "codex"]


def test_select_from_menu_empty_uses_default():
    _, w = _sink()
    assert select_from_menu(
        ["claude", "codex"], _reader("\n"), w, default="claude", what="agent"
    ) == ["claude"]


def test_select_from_menu_rejects_unknown():
    _, w = _sink()
    with pytest.raises(ValueError):
        select_from_menu(["claude"], _reader("nope\n"), w, default="claude", what="agent")


def test_choose_agent_models_defaults():
    _, w = _sink()
    pairs = choose_agent_models(
        ["claude", "codex"], lambda a: _DM[a], _scripted(["\n", "\n"]), w
    )
    assert pairs == [("claude", "claude-opus-4-8")]


def test_choose_agent_models_explicit():
    _, w = _sink()
    pairs = choose_agent_models(
        ["claude", "codex"], lambda a: _DM[a],
        _scripted(["claude,codex\n", "claude-opus-4-8,claude-fable-5\n", "gpt-5\n"]), w,
    )
    assert pairs == [
        ("claude", "claude-opus-4-8"), ("claude", "claude-fable-5"), ("codex", "gpt-5"),
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_prompts.py -k "select_from_menu or agent_models" -v`
Expected: FAIL — `ImportError: cannot import name 'choose_agent_models'`.

- [ ] **Step 3: Refactor `prompts.py`**

Replace `src/pr_review/prompts.py` with:

```python
"""Interactive selection of review types and agent/model pairs."""
from __future__ import annotations

import sys
from collections.abc import Callable


def select_from_menu(
    available: list[str],
    reader: Callable[[], str],
    writer: Callable[[str], None],
    *,
    default: str,
    what: str,
) -> list[str]:
    """Render a numbered menu and parse a comma-separated reply of numbers/names.

    Empty input selects `default`. Unknown names / out-of-range numbers raise
    `ValueError`. Results are de-duplicated, preserving order.
    """
    writer(f"Select {what}(s):\n")
    for i, name in enumerate(available, 1):
        writer(f"  {i}) {name}\n")
    writer(f"Enter numbers or names (comma-separated) [default: {default}]: ")

    reply = reader().strip()
    if not reply:
        return [default]

    selected: list[str] = []
    for tok in (t.strip() for t in reply.split(",")):
        if not tok:
            continue
        if tok.isdigit():
            idx = int(tok) - 1
            if not 0 <= idx < len(available):
                raise ValueError(f"selection out of range: {tok}")
            selected.append(available[idx])
        elif tok in available:
            selected.append(tok)
        else:
            raise ValueError(f"unknown {what}: {tok}")

    seen: set[str] = set()
    result: list[str] = []
    for name in selected:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result or [default]


def choose_review_types(
    available: list[str],
    reader: Callable[[], str],
    writer: Callable[[str], None],
    *,
    default: str = "test-gap",
) -> list[str]:
    return select_from_menu(available, reader, writer, default=default, what="review type")


def choose_agent_models(
    agents: list[str],
    default_model: Callable[[str], str],
    reader: Callable[[], str],
    writer: Callable[[str], None],
) -> list[tuple[str, str]]:
    chosen = select_from_menu(agents, reader, writer, default="claude", what="agent")
    pairs: list[tuple[str, str]] = []
    for agent in chosen:
        dm = default_model(agent)
        writer(f"Models for {agent} (comma-separated) [default: {dm}]: ")
        reply = reader().strip()
        models = [m.strip() for m in reply.split(",") if m.strip()] if reply else [dm]
        for model in models:
            if (agent, model) not in pairs:
                pairs.append((agent, model))
    return pairs


def _tty_io():
    try:
        tty = open("/dev/tty", "r+")
    except OSError:
        return None
    return tty


def prompt_review_types_via_tty(available: list[str]) -> list[str]:
    tty = _tty_io()
    if tty is None:
        print(
            "pr-review: no terminal to prompt for --review-type.\n"
            f"  pass one, e.g. --review-type {','.join(available)}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    with tty:
        def reader() -> str:
            return tty.readline()

        def writer(text: str) -> None:
            tty.write(text)
            tty.flush()

        for _ in range(3):
            try:
                return choose_review_types(available, reader, writer)
            except ValueError as exc:
                writer(f"  {exc}\n")
        raise SystemExit("pr-review: no valid review type selected")


def prompt_agent_models_via_tty(
    agents: list[str], default_model: Callable[[str], str]
) -> list[tuple[str, str]]:
    tty = _tty_io()
    if tty is None:
        print(
            "pr-review: no terminal to prompt for --model.\n"
            "  pass one, e.g. --model claude=claude-opus-4-8",
            file=sys.stderr,
        )
        raise SystemExit(2)
    with tty:
        def reader() -> str:
            return tty.readline()

        def writer(text: str) -> None:
            tty.write(text)
            tty.flush()

        for _ in range(3):
            try:
                return choose_agent_models(agents, default_model, reader, writer)
            except ValueError as exc:
                writer(f"  {exc}\n")
        raise SystemExit("pr-review: no valid agent/model selected")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: PASS (existing review-type tests plus the new select_from_menu / agent_models tests).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pr_review/prompts.py tests/test_prompts.py
git commit -m "feat(pr-review): shared menu helper + agent/model prompt"
```

---

### Task 6: Interactive `--model` prompt when omitted

**Files:**
- Modify: `src/pr_review/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `pr_review.prompts.prompt_agent_models_via_tty`; `reviewers_available`; `get_reviewer`.
- Produces:
  - `RunConfig.agent_models: list[tuple[str, str]] | None` (None = `--model` omitted)
  - `resolve_agent_models(agent_models, *, has_tty, prompt_fn=prompts.prompt_agent_models_via_tty) -> list[tuple[str, str]]`

- [ ] **Step 1: Update the CLI tests for the prompt behaviour**

In `tests/test_cli.py`, change `test_config_defaults` so the omitted-`--model` case is `None`:

```python
def test_config_defaults():
    cfg = config_from_args(["org/repo#3"])
    assert cfg.target == Target("org", "repo", 3)
    assert cfg.agent_models is None
    assert cfg.type_names is None
    assert cfg.flags_by_agent == {}
    assert cfg.yes is False and cfg.no_post is False and cfg.keep is False
```

Add `resolve_agent_models` to the import line and append these tests:

```python
from pr_review.cli import build_jobs, config_from_args, resolve_agent_models


def test_resolve_agent_models_explicit_passthrough():
    pairs = [("claude", "claude-opus-4-8")]
    assert resolve_agent_models(pairs, has_tty=True, prompt_fn=lambda a, d: []) == pairs


def test_resolve_agent_models_prompts_when_tty():
    seen = {}

    def fake_prompt(agents, default_model):
        seen["agents"] = agents
        seen["claude_default"] = default_model("claude")
        return [("codex", "gpt-5")]

    assert resolve_agent_models(None, has_tty=True, prompt_fn=fake_prompt) == [("codex", "gpt-5")]
    assert "claude" in seen["agents"]
    assert seen["claude_default"] == "claude-opus-4-8"


def test_resolve_agent_models_errors_without_tty(capsys):
    with pytest.raises(SystemExit) as exc:
        resolve_agent_models(None, has_tty=False, prompt_fn=lambda a, d: [])
    assert exc.value.code == 2
    assert "--model" in capsys.readouterr().err
```

Also update `test_build_jobs_full_matrix_and_per_agent_flags` (it passes `--model` explicitly, so `cfg.agent_models` is a concrete list — no change needed there).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "resolve_agent_models or config_defaults" -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_agent_models'` and `assert [("claude", ...)] is None`.

- [ ] **Step 3: Make `--model` default to None and add the resolver**

In `src/pr_review/cli.py`:

1. Change `RunConfig.agent_models` annotation to allow None (the
   `from pr_review import output, prompts` import already exists from Task 4):
```python
    agent_models: list[tuple[str, str]] | None
```

2. In `config_from_args`, change the agent-models line so an omitted `--model` is `None`:
```python
    agent_models = _parse_agent_models(args.model) if args.model else None
```

3. Add the resolver (next to `resolve_review_types`):
```python
def resolve_agent_models(
    agent_models: list[tuple[str, str]] | None,
    *,
    has_tty: bool,
    prompt_fn=prompts.prompt_agent_models_via_tty,
) -> list[tuple[str, str]]:
    if agent_models is not None:
        return agent_models
    if not has_tty:
        print(
            "pr-review: no terminal to prompt for --model.\n"
            f"  pass one, e.g. --model claude={DEFAULT_MODEL}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return prompt_fn(reviewers_available(), lambda a: get_reviewer(a).default_model)
```

4. In `main`, resolve agent-models before building jobs (right after `config_from_args`):
```python
    cfg.agent_models = resolve_agent_models(
        cfg.agent_models, has_tty=output.tty_available()
    )
    cfg.type_names = resolve_review_types(
        cfg.type_names, has_tty=output.tty_available()
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Smoke-test the no-TTY error paths**

Run:
```bash
uv run pr-review org/repo#1 --review-type test-gap < /dev/null ; echo "exit $?"
```
Expected: stderr `pr-review: no terminal to prompt for --model.` and `exit 2`.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pr_review/cli.py tests/test_cli.py
git commit -m "feat(pr-review): prompt for --model interactively when omitted"
```

---

### Task 7: Docs (README + CLAUDE)

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the finished CLI/behaviour from Tasks 1–6.
- Produces: docs reflecting the Codex agent, the `--model agent=models` matrix, `--codex-flags`, and the `--model` prompt.

- [ ] **Step 1: Update the README**

In `README.md`:

1. Intro — note two agents:
   - Find: `Today it ships one agent (**Claude**, headless) and two review types`
   - Replace `one agent (**Claude**, headless)` with `two agents (**Claude** and **Codex**, headless)`.

2. Replace the "Selecting agents and review types" section body with the `--model` matrix. Find the section starting `### Selecting agents and review types` through its closing paragraph and replace with:

```markdown
### Selecting agents, models, and review types

A run is the product of **review types × (agent, model) pairs**. Assign models to
agents with the repeatable `--model agent[=models]` flag; `--review-type` is a
comma-separated list.

```bash
pr-review <target> --review-type test-gap,infracode \
  --model claude=claude-opus-4-8,claude-fable-5 \
  --model codex=gpt-5,gpt-5.5
```

- `--model claude` (no `=`) uses claude's default model (`claude-opus-4-8`);
  `codex`'s default is `gpt-5-codex`.
- Model ids are passed **verbatim** to the agent's CLI — give real ids
  (`claude-opus-4-8`, not `opus-4.8`).
- Registered agents: `claude`, `codex`. Registered review types: `test-gap`,
  `infracode`. Unknown names fail fast, before any clone.
- Omit `--model` (or `--review-type`) to choose interactively; with no terminal
  (CI, piped stdin) the tool errors and asks you to pass the flag.
- `--claude-flags="…"` / `--codex-flags="…"` pass extra flags to that agent's CLI.
```

3. In the Options table, replace the `--model` row and add `--codex-flags`:
   - Find the row `| `--model <id>` | Claude model id | `claude-opus-4-8` |` and replace with:
```markdown
| `--model agent[=models]` | Per-agent models (repeatable) | `claude=claude-opus-4-8` |
| `--codex-flags="<flags>"` | Extra flags appended to the `codex` invocation | empty |
```

4. In the parenthetical after the Options table, find `(`--agent` and `--review-type` are described above.` and replace `--agent` with `--model`.

5. In the "Extending: add a review type" / "add a reviewer" examples, no change is needed, but verify the reviewer example still references `--model <name>` rather than `--agent`. If the add-a-reviewer section ends with `--agent codex … just works`, change it to `--model codex … just works`.

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md`, update the affected walkthrough lines:

1. The `test_reviewers.py` line — find it and replace with:
```markdown
- **test_reviewers.py** — the `Reviewer` registry (`claude` and `codex` registered,
  each with a `default_model`, unknown raises) and the shared
  `build_review_prompt` (carries run context + the type's instructions). The
  `review()` methods shell out to `claude`/`codex` and are not unit-tested.
```

2. The `test_cli.py` line — find it and replace with:
```markdown
- **test_cli.py** — `config_from_args` option parsing (`--model agent[=models]`
  repeatable → `(agent, model)` pairs, `--review-type` lists, per-agent
  `--claude-flags`/`--codex-flags`, the booleans), `build_jobs` (the
  `(agent,model) × review_type` matrix with per-agent flags), `resolve_agent_models`
  and `resolve_review_types` (explicit / prompt on TTY / exit-2 without one), and
  the `help` word aliasing to `--help`.
```

3. The `test_prompts.py` line — find it and replace with:
```markdown
- **test_prompts.py** — `select_from_menu` (numbers / names / empty-default /
  dedupe / invalid), `choose_review_types` (wraps it), and `choose_agent_models`
  (pick agents, then per-agent models with defaults). The `/dev/tty` wrappers are
  the thin shells, verified manually.
```

4. Update the test-suite count line — find `holds 10 files, one per `src/pr_review/` module (60 tests total)` and replace the total with the current count from `uv run pytest -q` (it will be higher; read it off the run and write the exact number).

- [ ] **Step 3: Verify the docs match reality**

Run:
```bash
uv run pr-review --help
uv run pytest -q
```
Confirm the README's `--model`/`--codex-flags` text matches `--help`, and write the exact passing-test count into the CLAUDE.md line from Step 2.4.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs(pr-review): document Codex agent, --model matrix, and --codex-flags"
```

---

## Self-Review

**Spec coverage:**
- Codex reviewer (`codex exec` + bypass) → Task 2; shared runner refactor → Task 1.
- `default_model` per reviewer (claude `claude-opus-4-8`, codex `gpt-5-codex`) → Tasks 1, 2.
- Model dimension in jobs (`ReviewJob` gains `model`; `run_reviews` drops it) → Task 3.
- `--model agent[=models]` repeatable, `--agent` removed, verbatim models, unknown-agent fail-fast → Task 4.
- Per-agent flags `--claude-flags`/`--codex-flags` → `flags_by_agent`, applied per job → Task 4.
- `(agent,model) × review_type` matrix in `build_jobs` → Task 4.
- Shared `select_from_menu`; `choose_agent_models` → Task 5.
- Interactive `--model` prompt when omitted; `resolve_agent_models`; no-TTY exit 2 → Task 6.
- Collated label includes model (`## type — agent (model)`); `collate.py` unchanged → Task 3.
- Docs → Task 7.

**Placeholder scan:** None — every code step contains complete, runnable content; the only `<...>`/`<target>` tokens are user-supplied values in shell commands and example invocations.

**Type consistency:** `ReviewJob(reviewer, review_type, model, extra_flags)` is defined in Task 3 and constructed identically in Task 4's `build_jobs`. `run_reviews(*, jobs, workdir, base, owner, repo, number, collator=None, max_workers=None)` (Task 3) matches the `main` call site (Tasks 3, 4). `RunConfig` fields are consistent across Tasks 4 and 6 (`agent_models` goes `list` → `list | None`; `flags_by_agent`, `type_names` stable). `select_from_menu(..., *, default, what)` (Task 5) is consumed by `choose_review_types` and `choose_agent_models` in the same file. `resolve_agent_models(agent_models, *, has_tty, prompt_fn)` (Task 6) mirrors the existing `resolve_review_types` signature. `default_model` is set on both reviewers (Tasks 1, 2) and read by `_parse_agent_models` and `resolve_agent_models` (Tasks 4, 6).
