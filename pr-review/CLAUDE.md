# pr-review — agent guide

`pr-review` reviews a GitHub PR with one or more LLMs in an isolated clone. See
`README.md` for install/run/develop, and `docs/superpowers/` for the design spec
and implementation plan.

## Tests

```bash
mise run test        # == uv run pytest, from this directory
```

**Maintaining this file:** when you add, remove, or rename tests in `tests/`,
update the **Test suite** walkthrough below in the same change so it stays an
accurate map of what is covered.

## Testing principle

Pure logic is unit-tested directly. The four real side effects — `git clone`,
the `claude` CLI review, the `codex` CLI review, and the `gh api` post — are never executed in the suite:
the shells around them are tested through injected fake runners, and the true
end-to-end path (real PR → clone → claude → post) is verified only by a manual
run. When you touch a side-effecting module, test its command construction with a
fake, not the real subprocess.

## Test suite

`tests/` holds 12 files, one per `src/pr_review/` module (98 tests total):

- **test_target.py** — `parse_target`: PR URL, trailing-slash URL, `owner/repo#N`
  short form, whitespace stripping, and a parametrized rejection of malformed
  input. Asserts `Target` value equality.
- **test_payload.py** — `Payload`/`Comment` `to_dict` shape; `parse_payload` happy
  path and the `comments`-default; its validation rejections (invalid JSON,
  missing/non-string body, comment missing `path`, non-string body, non-integer
  `line`); and `cap_comments` splitting at the 8-comment cap.
- **test_review_types.py** — the `ReviewType` registry: `test-gap` and `infracode`
  are registered, `get_review_type` returns the named instance, each type's
  instructions carry the required output-contract/cap markers, and an unknown
  name raises `ValueError`.
- **test_reviewers.py** — the `Reviewer` registry (`claude` and `codex` registered,
  each with a `default_model`, unknown raises), `Reviewer.command` argv for both
  agents (codex omits `--model` when empty), the shared `build_review_prompt`, and
  `_review_env` (trusts the clone's `mise.toml`). The `review()` calls shell out to
  `claude`/`codex` and are not unit-tested.
- **test_collate.py** — `DeterministicMergeCollator`: single-job identity
  passthrough, empty-jobs placeholder, two-job merge (sorted provenance headers +
  concatenated comments), and cap re-application with an overflow section across
  the merged set.
- **test_checkout.py** — `clone_pr` builds the exact `git clone --filter=blob:none`
  / `gh pr checkout` / `gh pr view` sequence with the right `cwd`, via an injected
  `FakeRunner` + `mkdtemp` (no network); and `cleanup` removes the workdir.
- **test_output.py** — `decide_mode` across the print-only / post-without-prompting
  / TTY matrix; `render` emits the body plus `path:line` comment anchors;
  `post_review` builds the `gh api .../reviews --method POST --input` call via a
  fake runner; and the not-posted path writes the payload to a real temp file and
  names it in the hint.
- **test_orchestrator.py** — `run_reviews` with in-process `FakeReviewer`/`FakeType`
  (no subprocess): single-job passthrough, two-job merge (model in label),
  empty-model label, and graceful failure — a raising job is captured in
  `RunResult.failures` (not raised), partial failures keep the successes and note
  them in the body, and an all-failed run yields `payload=None`.
- **test_cli.py** — `config_from_args` option parsing (`--model agent[=models]`
  repeatable → `(agent, model)` pairs, `--review-type` lists, per-agent
  `--claude-flags`/`--codex-flags`, the booleans), `build_jobs` (the
  `(agent,model) × review_type` matrix with per-agent flags), `resolve_agent_models`
  and `resolve_review_types` (explicit / prompt on TTY / exit-2 without one), and
  the `help` word aliasing to `--help`, plus `--synthesis-model` / `--no-synthesis` parsing and `build_collator` (synthesis vs deterministic, judge command).
- **test_prompts.py** — `select_from_menu` (numbers / names / empty-default /
  dedupe / invalid), `choose_review_types` (wraps it), and `choose_agent_models`
  (pick agents, then per-agent models with defaults). The `/dev/tty` wrappers are
  the thin shells, verified manually.
- **test_terminal.py** — `terminal.can_prompt` / `open_interactive`: detection
  prefers `/dev/tty` but falls back to stdin/stderr when `/dev/tty` can't be
  opened (screen / detached sessions), and reports no-terminal only when neither
  works.
- **test_synthesis.py** — `serialize_findings` (sources labelled `<agent> (<model>)
  [<type>]` with counts), `build_synthesis_prompt` (context + findings + dedupe/
  verify/stats instructions), and `LLMSynthesisCollator.collate` with an injected
  fake runner (single-job passthrough, judge runs for >1 job, and fall-back to the
  deterministic merge when the judge raises).
