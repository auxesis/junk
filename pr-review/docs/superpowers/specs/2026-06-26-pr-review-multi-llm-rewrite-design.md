# pr-review — multi-LLM, multi-type PR reviewer (design)

**Date:** 2026-06-26
**Status:** Approved, ready for implementation planning
**Supersedes:** the `test-gap-review` bash script (`pr-review/test-gap-review`)

## Summary

Rewrite the single-purpose `test-gap-review` bash script as `pr-review`, a Python
package that reviews a named GitHub PR in an **isolated throwaway clone**, fans out
to one-or-more **(reviewer × review-type)** jobs **in parallel**, collates their
payloads into one, then prints and optionally posts it.

The rewrite has two goals:

1. **Isolation + parallelism now.** Replace today's in-place HEAD switch with a
   fresh clone per run, so reviews run concurrently and never touch the user's
   working tree.
2. **Seams for the known future.** The tool will grow more LLM backends (Codex,
   …), parallel multi-LLM runs, an analyse/summarise collation stage, and more
   review types (e.g. `~/.claude/skills/reviewing-infracode`). The architecture
   introduces clean interfaces and registries so each of those is an *additive*
   change, not a rewrite.

Scope for this pass: build the fan-out + collation **plumbing** end-to-end, but
implement only `ClaudeReviewer`, the `test-gap` type, and a deterministic merge
collator. A default run is therefore N=1 (claude × test-gap); the multi-job paths
are real code, exercised by tests with N=2 fixtures.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Isolation | Fresh **blobless** clone to a unique temp dir, deleted on exit | Truly isolated, runs from anywhere, parallel-safe by construction. Blobless (`--filter=blob:none`) keeps the full history graph so `git diff base...HEAD` has its merge-base, while staying fast and light. |
| Input | **Explicit target only**: PR URL or `owner/repo#N` | Clean-clone model removes any dependence on cwd; no inference, no surprises. |
| Branch (non-PR) mode | **Dropped** | The old branch-diff/review-only path is gone — the tool is PR-focused. |
| Language / project | **uv-managed** Python project, `src/` layout, pytest | Maintainability; uv keeps the (soon-churning, multi-provider) dependency set locked and reproducible. |
| Install | **`uv run` shim symlinked into `~/bin`** (option A) | Always runs current code *and* current deps — no "did I forget to re-install?" trap. The new multi-LLM direction (frequent dependency churn) makes this clearly better than `uv tool install --editable`, whose only edge — leaner runtime — is irrelevant against a multi-clone, multi-LLM workload. |
| Scope now | **Seams + parallel/collate plumbing**, single reviewer/type implemented | Proves the multi-review flow before a second backend exists; future backends/types/collators slot in additively. |
| Command name | **Generalize to `pr-review`** (`--type`, default `test-gap`); keep a `test-gap-review` alias | Matches the directory name and the multi-type future; alias preserves muscle memory. |

## CLI & interface

```
pr-review [--reviewer claude] [--type test-gap] <pr-url | owner/repo#N>
```

- `--reviewer` and `--type` accept **comma-separated lists**; the run is their
  **cross-product**. Both default to a single value today → N=1. An unknown name
  errors with the list of registered reviewers/types.
- `test-gap-review` is an alias that bakes in `--type test-gap`.

### Environment knobs

Carried over from the bash tool, plus one new:

- `MODEL` — Claude model id (default `claude-opus-4-8`).
- `YES=1` — post without prompting (non-interactive / CI).
- `NO_POST=1` — review and print only; never post, never prompt.
- `CLAUDE_FLAGS` — extra flags appended to the `claude` invocation.
- `KEEP=1` — **new**: keep the temp clone on exit (debugging).

Posting/TTY fallback is preserved: with no TTY and `YES` unset, the tool falls
back to review-only and prints how to post manually.

## Data flow

```
target → resolve(owner, repo, N, base)
       → checkout ONCE: blobless clone + gh pr checkout      → <tmp>/repo
       → orchestrator fans out [(reviewer, type)] in parallel (ThreadPoolExecutor)
            each job: reviewer runs its LLM headless with the type's instructions
                      → writes/parses its own payload temp file → Payload
       → collator merges [Payload...] → one Payload
       → output: print, then post / prompt / review-only per env + TTY
       → cleanup temp clone (unless KEEP=1)
```

**One shared read-only checkout** for all jobs. Reviewers only read (`git diff`,
file reads) and write payloads to temp files *outside* the repo, so concurrent
jobs over the same working tree don't collide — this avoids N redundant clones.

**Parallelism** uses a `ThreadPoolExecutor`: each job is dominated by waiting on
an external LLM subprocess, so threads over blocking subprocess calls are the
simplest correct model. Results are collected in a deterministic order
(reviewer, then type) for stable collation output.

**Collation now** is a `DeterministicMergeCollator`: it concatenates inline
comments (re-applying the 8-comment cap across the merged set) and merges review
bodies under per-job headers noting provenance (which reviewer × type produced
what). This is the plumbing that proves fan-out → collate → post with multiple
payloads. The future **LLM-synthesis collator** (analyse and summarise N reviews
into one coherent feedback) is an additive `Collator` subclass and is **not**
built in this pass.

## Project layout

```
pr-review/
├── pyproject.toml          # [project.scripts] pr-review = "pr_review.cli:main"; pytest dev dep
├── uv.lock
├── mise.toml
├── bin/
│   ├── pr-review           # uv-run shim: resolves repo via readlink loop, execs
│   │                       #   `uv run --project <repo> pr-review "$@"`
│   └── test-gap-review     # alias shim: `... pr-review --type test-gap "$@"`
├── src/pr_review/
│   ├── __init__.py
│   ├── cli.py              # parse args/env → RunConfig → orchestrator → output
│   ├── target.py           # parse PR URL / owner/repo#N                 (pure)
│   ├── checkout.py         # blobless clone + gh pr checkout; resolve base ref
│   ├── orchestrator.py     # parallel fan-out, collect payloads, collate
│   ├── payload.py          # Payload model + JSON validation + cap helper (pure)
│   ├── collate.py          # Collator ABC + DeterministicMergeCollator
│   ├── output.py           # posting-mode decision + print + `gh api` post
│   ├── reviewers/
│   │   ├── __init__.py      # registry: name → Reviewer
│   │   ├── base.py          # Reviewer ABC
│   │   └── claude.py        # ClaudeReviewer (wraps `claude --print …`)
│   └── review_types/
│       ├── __init__.py      # registry: name → ReviewType
│       ├── base.py          # ReviewType ABC
│       └── test_gap.py      # TestGapType (the INSTRUCTIONS text, verbatim)
└── tests/
    ├── test_target.py       # URL / owner-repo-N parsing
    ├── test_payload.py      # JSON validation, comment cap
    ├── test_collate.py      # merge N=2 payloads, cap enforcement, provenance
    ├── test_output.py       # env → posting-mode decision (YES / NO_POST / TTY)
    └── test_orchestrator.py # fan-out wiring with a fake in-process reviewer
```

- Subpackages `reviewers/` and `review_types/` keep each future backend/type a
  small, focused file plus one registry line. `review_types` (not `types`) avoids
  the stdlib name clash.
- The package is `pr_review`; the command is `pr-review`.

## Component seams

### Reviewer

```
Reviewer.review(workdir, base, context, review_type) -> Payload
```

Owns invoking its LLM CLI headless, and writing/parsing its own payload temp
file. `ClaudeReviewer` reproduces today's call:
`claude --print --model <MODEL> --permission-mode acceptEdits
--dangerously-skip-permissions --allowedTools Bash Read Grep Glob Write`,
prompt fed on stdin. New backends (e.g. `CodexReviewer`) register a name and
implement `review`.

### ReviewType

```
ReviewType.instructions(context) -> str
```

`TestGapType` returns the existing INSTRUCTIONS text **unchanged** (gap
categories, self-contained-comment rules, scope rules, calibration, 8-comment
cap, JSON payload schema). A future `InfracodeType` will source from
`~/.claude/skills/reviewing-infracode` — most likely by instructing Claude to use
that skill, a reviewer-specific binding deferred until it is built.

### Payload

The review payload schema is unchanged from the bash tool:

```json
{
  "event": "COMMENT",
  "body": "<markdown summary>",
  "comments": [
    {"path": "relative/path", "line": 0, "side": "RIGHT", "body": "**Gap:** …"}
  ]
}
```

`payload.py` provides validation (well-formed JSON, required keys) and the
8-comment cap helper, both pure and unit-tested.

### Collator

```
Collator.collate(jobs: list[(reviewer_name, type_name, Payload)]) -> Payload
```

`DeterministicMergeCollator` is the only implementation now (see Data flow).

### Output

`output.py` decides posting mode from env + TTY (preserving the bash logic:
`NO_POST` → review-only; no TTY and `YES` unset → review-only; `YES` → post;
else prompt `[y/N]` on `/dev/tty`), prints the collated review, and posts via
`gh api repos/<owner>/<repo>/pulls/<N>/reviews --method POST --input <payload>`.

## Install & tasks (mise.toml)

```toml
[tools]
python = "3.14"
uv = "latest"

[tasks.test]
description = "Run the test suite"
run = "uv run pytest"

[tasks.install]
description = "Sync deps and symlink pr-review (+ test-gap-review alias) into ~/bin"
run = """
uv sync
ln -sf "$MISE_PROJECT_ROOT/bin/pr-review"       "$HOME/bin/pr-review"
ln -sf "$MISE_PROJECT_ROOT/bin/test-gap-review" "$HOME/bin/test-gap-review"
"""
```

Two **separate** shims (rather than one symlinked twice) so the alias injects
`--type test-gap` without argv[0] sniffing. Each shim resolves its own real path
through a `readlink` loop — so the `~/bin` symlink finds the repo and runs
`uv run --project <repo>` against current code and current (auto-synced) deps.

## Testing approach

`mise run test` runs pytest over the **pure / high-value** logic:

- target parsing (URL and `owner/repo#N`);
- payload validation and the comment cap;
- deterministic collation with N=2 fixtures (merge order, cap re-application,
  provenance headers);
- posting-mode decision across `YES` / `NO_POST` / TTY combinations;
- orchestrator fan-out wiring, using a **fake in-process reviewer** so no
  `claude` / `gh` / `git` subprocess runs.

The clone, LLM invocation, and post are thin shells over external tools; they are
verified by a manual end-to-end run, not by `mise run test`.

## Out of scope (future, additive)

- `CodexReviewer` and any other LLM backends.
- LLM-synthesis collation (analyse / summarise N reviews into one).
- `InfracodeType` and other review types beyond test-gap.
- Caching clones across runs (today every run clones fresh).
