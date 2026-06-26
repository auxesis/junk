# pr-review — cross-model synthesis collation (design)

**Date:** 2026-06-27
**Status:** Approved, ready for implementation planning
**Builds on:** the multi-LLM rewrite and the Codex/model-matrix work.

## Problem

A multi-model / multi-type run currently collates with `DeterministicMergeCollator`,
which **concatenates** every job's inline comments and re-applies the 8-comment
cap. When two models flag the same issue, both comments post — so a run with
several models produces repetitive, duplicated feedback on the PR, which annoys
human reviewers. Text/location dedup can't fix this: the same issue is often
worded differently or anchored to nearby-but-not-identical lines, and naive
merging can't tell a real finding from a hallucinated one.

## Goal

When a run produces more than one job, consolidate all findings into **one**
deduplicated, verified review: merge semantic duplicates, verify findings against
the actual code, weight by cross-model agreement, drop unverifiable lone findings,
and include summary stats. Post exactly one review per PR.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Mechanism | **LLM synthesis pass** — one extra judge LLM run after the reviewers | Only an LLM can semantically de-dupe and verify legitimacy; text/location dedup cannot. |
| Judge | **`--synthesis-model agent[=model]`**, default `claude=claude-opus-4-8` | A strong, predictable judge by default; overridable (e.g. `--synthesis-model codex=gpt-5`). |
| Lone findings | **Keep iff the judge verifies them against the code; label single-source** | 2+ models agree → high confidence; 1 model + verified → single-source; 1 model + unverifiable → dropped. Nothing real is silently lost. |
| Stats | **In the posted review body** (and therefore the terminal, via `render()`) | Reviewers see the consensus; no separate plumbing. |
| When | **Auto for >1 job; `--no-synthesis` falls back to the raw merge** | A single job still passes through unchanged. |
| Failure | **Fall back to the deterministic merge if the judge run fails** | The run always produces *a* review; the synthesis pass can never crash it. |

## CLI

- `--synthesis-model agent[=model]` — the judge agent + model. Default
  `claude=claude-opus-4-8`. A bare `agent` uses that reviewer's `default_model`.
  The agent key is validated against the reviewer registry (fail-fast, like
  `--model`).
- `--no-synthesis` — use `DeterministicMergeCollator` even for >1 job.
- Synthesis is otherwise automatic and needs no flag. `--help` documents both.

## The synthesis pass

After the parallel reviewer jobs finish (and only if ≥1 succeeded **and** there
is more than one successful job), the judge LLM runs once in the clone. It is
given, in its prompt:

- The run context (repo, PR number, base ref, payload-file path to write) — the
  same context block reviewers get, plus "HEAD is checked out; read the diff to
  verify findings."
- **The findings**, grouped per source: for each successful job, its source label
  (`<agent> (<model>) [<review-type>]`), a raw count, and each inline comment as
  `path:line — body` (plus the job's summary body).

It is instructed to:

1. **De-duplicate** — merge findings that describe the same issue, even when
   worded differently or anchored to nearby lines.
2. **Verify** — check each finding against the diff/code (it can run `git diff`,
   read files); **drop** findings it cannot substantiate.
3. **Confidence** — a finding raised by 2+ models is high-confidence; a single
   model's finding that verifies is single-source; a single model's finding that
   doesn't verify is dropped. Label each kept inline comment (e.g.
   `[2 models: claude, codex]`, `[single-source: codex]`).
4. **Cap** — at most 8 inline comments; list any overflow in the body under
   `## Additional findings not posted inline`.
5. **Stats** — include a `## Review stats` section in the body: per-source
   raw/kept counts and cross-model overlap.

Output is the same payload JSON contract (`event`/`body`/`comments`), written to
the payload file and also printed to stdout. It does not post.

## Architecture

### New: `synthesis.py`

`LLMSynthesisCollator(Collator)` — keeps `collate.py` focused (the `Collator` ABC
and `DeterministicMergeCollator` stay there).

- Constructed with: the judge `command` (argv prefix, model already baked in),
  the clone `workdir`, the run context (`owner`, `repo`, `number`, `base`), and a
  `runner` (defaults to `run_cli_payload`) for testability.
- `collate(jobs)`:
  - `len(jobs) <= 1` → passthrough (delegate to `DeterministicMergeCollator`).
  - otherwise: build the synthesis prompt from the jobs, run the judge via the
    runner, parse its payload, return it.
  - **On any failure** (judge exits non-zero, empty/invalid payload): log a
    warning to stderr and **fall back** to `DeterministicMergeCollator().collate(jobs)`.

Pure helpers (unit-tested): `serialize_findings(jobs) -> str` (jobs → tagged,
counted findings text) and `build_synthesis_prompt(context, findings, payload_path)`.

### Refactor: reuse the agent machinery

So the judge can run any agent without duplicating the subprocess/payload dance:

- `Reviewer` gains `command(model: str, extra_flags: list[str]) -> list[str]`.
  `ClaudeReviewer` and `CodexReviewer` build their argv there (codex still omits
  `--model` for an empty model); each `review()` calls `self.command(...)`.
- `_run.py` exposes `run_cli_payload(cmd_prefix, build_prompt, *, workdir) -> Payload`
  — the mkstemp → `subprocess.run(..., cwd=workdir, env=_review_env(workdir))` →
  read (utf-8) → empty-check → `parse_payload` → unlink-in-`finally` core, where
  `build_prompt(payload_path) -> str` lets the caller supply its own prompt.
  `run_cli_reviewer` becomes a thin wrapper that passes a `build_review_prompt`
  closure. The synthesis collator passes a `build_synthesis_prompt` closure.

### Wiring

- `cli.py`: parse `--synthesis-model` (→ `(agent, model)`, default
  `("claude", "claude-opus-4-8")`) and `--no-synthesis` into `RunConfig`.
- `cli.main`, after cloning, builds the collator: when synthesis is enabled,
  `LLMSynthesisCollator(command=get_reviewer(j_agent).command(j_model,
  flags_by_agent.get(j_agent, [])), workdir=checkout.workdir, owner=…, repo=…,
  number=…, base=checkout.base)`; otherwise `DeterministicMergeCollator()`. It
  passes the collator into `run_reviews` (which already accepts one).
- `run_reviews` is unchanged except that the injected collator now may run the
  judge. Total-failure short-circuit (all jobs failed → `payload=None`) still
  happens before `collate`, so the judge never runs with zero findings.

## Output

The judge's stats section and per-comment confidence labels live in the payload
**body**. `cli.main` already posts that body (one review) and prints it via
`output.render()`, so the stats reach both the PR and the terminal with no extra
code. Posting behaviour, the not-posted payload-file hint, and the 8-comment cap
are unchanged.

## Error handling

- Synthesis judge run fails → fall back to deterministic merge (never crashes the
  run); a warning naming the judge is printed to stderr.
- Unknown `--synthesis-model` agent → `ValueError` before any clone (fail-fast).
- A single successful job → passthrough; zero successful jobs → existing
  `RunResult(payload=None)` path (exit 1), synthesis not invoked.

## Testing

Unit tests cover the pure logic:

- `serialize_findings` — sources are labelled `<agent> (<model>) [<type>]` with
  raw counts and each `path:line — body`.
- `build_synthesis_prompt` — contains the context (payload path), the findings,
  and the dedupe/verify/confidence/cap/stats instructions.
- `LLMSynthesisCollator.collate` with an **injected fake runner**: a judge result
  is returned for >1 job; a single job passes through; a runner that raises →
  deterministic-merge fallback output.
- `--synthesis-model` / `--no-synthesis` parsing into `RunConfig`; the judge
  `command` chosen for the configured agent/model.
- `Reviewer.command()` argv for claude and codex (incl. codex omitting `--model`
  when empty).

The judge's real LLM run (and synthesis quality) is a thin shell verified by a
manual end-to-end run, like the reviewers.

## Out of scope (future)

- Tuning confidence thresholds or making "drop unverifiable" configurable.
- Persisting stats across runs / trend reporting.
- A non-LLM deterministic dedup mode beyond the existing `--no-synthesis` merge.
