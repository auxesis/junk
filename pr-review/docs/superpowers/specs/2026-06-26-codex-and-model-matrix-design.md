# pr-review — Codex agent + per-agent model matrix (design)

**Date:** 2026-06-26
**Status:** Approved, ready for implementation planning
**Builds on:** the multi-LLM rewrite (`2026-06-26-pr-review-multi-llm-rewrite-design.md`)

## Summary

Add a second agent (**Codex**, via the `codex` CLI) and a **model dimension** to
the review fan-out. A run becomes the product of **review_types × (agent, model)
pairs**, where models are assigned to agents explicitly. The existing `Reviewer`
abstraction, orchestrator fan-out, and collator carry the new dimension with
small, additive changes.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Agent × model validity | **Per-agent model lists** | A model is run by one agent (claude runs `claude-*`; codex runs `gpt-*`). Assigning models to agents explicitly means no invalid pairs to skip. |
| CLI surface | **One repeatable `--model agent[=models]` flag; `--agent` removed** | The participating agents are the keys of `--model`. One flag couples the now-coupled agent+model dimensions; no redundancy. |
| Codex output | **Payload file, mirroring Claude** | `codex exec` reads the prompt on stdin and can write files; reusing the write-payload-file contract keeps the `Reviewer` abstraction uniform. |
| Codex invocation | `codex exec --model <m> --dangerously-bypass-approvals-and-sandbox`, cwd=clone, prompt on stdin | Mirrors `claude --print … --dangerously-skip-permissions`; bypass lets it write the payload temp file outside the clone. |
| Codex default model | `gpt-5-codex` | Used only for a bare `--model codex`; overridable. |
| Per-reviewer default | Each `Reviewer` gains a `default_model` attribute | claude → `claude-opus-4-8`, codex → `gpt-5-codex`. |
| Extra flags | **`--claude-flags` is claude-only** | Codex jobs receive no extra flags for now; a `--codex-flags` can be added later. |
| Provenance | Collated sections labelled **agent + model** | `## test-gap — claude (claude-opus-4-8)` keeps multi-model runs legible. |

## CLI surface

```
pr-review <target> --review-type test-gap,infracode \
  --model claude=claude-opus-4-8,claude-fable-5 \
  --model codex=gpt-5,gpt-5.5
```

- `--model` is **repeatable** (argparse `action="append"`). Each value is
  `agent` or `agent=model[,model…]`.
  - `agent` with no `=` → that agent's `default_model`.
  - `agent=m1,m2` → those models for that agent.
- The `agent` key is validated against the reviewer registry (`claude`, `codex`);
  an unknown agent fails fast, before any clone, listing what is available.
- Model strings are passed **verbatim** to the agent's CLI — no alias layer. The
  user supplies the real model id (`claude-opus-4-8`, not `opus-4.8`).
- No `--model` at all → default `[("claude", "claude-opus-4-8")]` (today's run).
- `--review-type` is unchanged: comma-separated, prompts interactively when
  omitted, errors (exit 2) with no terminal.
- `--model`'s `--help` advertises its default (`claude=claude-opus-4-8`).

## Matrix & job model

The run is **review_types × (agent, model) pairs**. Each `--model` entry expands
to one-or-more `(agent, model)` pairs; the flat, de-duplicated list of pairs
crosses with the review types.

- `RunConfig` replaces `agent_names: list[str]` + `model: str` with
  `agent_models: list[tuple[str, str]]` (validated `(agent, model)` pairs). It
  keeps `type_names: list[str] | None`, the parsed claude flags, `yes`,
  `no_post`, `keep`, and `target`.
- `ReviewJob` gains `model: str` and `extra_flags: list[str]` (per job).
- `build_jobs(cfg)` →
  `ReviewJob(get_reviewer(agent), get_review_type(t), model, flags_for(agent))`
  for every `(agent, model)` pair × every review type. `flags_for(agent)` returns
  the parsed `--claude-flags` for `claude` and `[]` otherwise.
- `orchestrator.run_reviews` **drops** its top-level `model` and `extra_flags`
  params; each job carries its own. The per-job call becomes
  `job.reviewer.review(workdir=…, …, review_type=job.review_type,
  model=job.model, extra_flags=job.extra_flags)`.
- The orchestrator's result triple's label includes the model:
  `(f"{job.reviewer.name} ({job.model})", job.review_type.name, payload)`. The
  collator treats the first element as an opaque label, so `collate.py` is
  unchanged — the model just appears in the `## {type} — {label}` header.

Example: `claude=opus,fable + codex=gpt-5` × `{test-gap, infracode}` = 3 pairs ×
2 types = **6 jobs**, fanned out in parallel as today.

## Reviewers

### Shared runner (refactor)

The payload-file lifecycle and prompt assembly are identical between agents.
Extract them so each reviewer supplies only its command:

- A shared `build_review_prompt(owner, repo, number, base, payload_path,
  review_type) -> str` (today's `ClaudeReviewer._build_context` + `build_prompt`).
- A shared `run_cli_reviewer(cmd_prefix, *, workdir, owner, repo, number, base,
  review_type) -> Payload` that: creates the payload temp file, builds the
  prompt, runs `cmd_prefix` with the prompt on stdin and `cwd=workdir`
  (`check=True`), reads the file (utf-8), raises on empty, `parse_payload`s it,
  and unlinks the temp file in a `finally`.

Both live in a new `reviewers/_run.py`.

### ClaudeReviewer (refactored)

```python
class ClaudeReviewer(Reviewer):
    name = "claude"
    default_model = "claude-opus-4-8"

    def review(self, *, model, extra_flags, **ctx) -> Payload:
        cmd = ["claude", "--print", "--model", model,
               "--permission-mode", "acceptEdits", "--dangerously-skip-permissions",
               "--allowedTools", "Bash", "Read", "Grep", "Glob", "Write",
               *extra_flags]
        return run_cli_reviewer(cmd, **ctx)
```

### CodexReviewer (new)

```python
class CodexReviewer(Reviewer):
    name = "codex"
    default_model = "gpt-5-codex"

    def review(self, *, model, extra_flags, **ctx) -> Payload:
        cmd = ["codex", "exec", "--model", model,
               "--dangerously-bypass-approvals-and-sandbox", *extra_flags]
        return run_cli_reviewer(cmd, **ctx)
```

Registered in `reviewers/__init__.py` for its import side-effect. The same shared
prompt instructs the agent to write the JSON payload to the file named in the
context; codex writes it under bypass mode; the framework reads it back.

## Error handling

- Unknown agent in `--model` → `ValueError` listing registered agents, before any
  clone (same fail-fast path as today's `build_jobs`).
- A model string invalid for its agent (e.g. `--model claude=gpt-5`) is not
  validated up front — it fails at agent-CLI run time. The orchestrator already
  attributes a failing job as `RuntimeError("<agent> (<model>)/<type> … failed")`.
- Codex not installed / not authenticated → the `codex exec` subprocess fails;
  surfaced as an attributed job failure.

## Testing

Unit tests cover the new **pure** logic:

- `--model` parsing: `agent=models`, bare `agent` → default model, multiple
  `--model` entries, de-duplication, unknown-agent rejection, and the
  no-`--model` default `[("claude", "claude-opus-4-8")]`.
- `build_jobs`: `(agent, model) × review_type` expansion (count and contents),
  and that claude jobs carry the parsed `--claude-flags` while codex jobs carry
  `[]`.
- Orchestrator: a fake reviewer asserts it receives the **per-job** `model` and
  `extra_flags`, and that the collated label includes the model.
- Reviewer registry: `codex` registered; `default_model` on both reviewers.
- The shared `build_review_prompt` (context + instructions) is unit-tested.

The `codex exec` / `claude --print` subprocess calls remain thin shells verified
by a manual end-to-end run, not the unit suite.

## Out of scope (future, additive)

- `--codex-flags` (per-agent extra flags beyond claude).
- Model-id validation / aliases (friendly names → real ids).
- LLM-synthesis collation across the now-larger job set.
- Interactive prompting for `--model` when omitted (only `--review-type` prompts).
