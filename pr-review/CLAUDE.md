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

`tests/` holds 20 files, one per `src/pr_review/` module (238 tests total):

- **test_target.py** — `parse_target`: PR URL, trailing-slash URL, `owner/repo#N`
  short form, whitespace stripping, and a parametrized rejection of malformed
  input. Asserts `Target` value equality.
- **test_payload.py** — `Payload`/`Comment` `to_dict` shape; `parse_payload` happy
  path and the `comments`-default; its validation rejections (invalid JSON,
  missing/non-string body, comment missing `path`, non-string body, non-integer
  `line`); `cap_comments` splitting at the 8-comment cap; `Source`, `Comment.sources`
  (never in `to_dict`), and `payload_from_dict`.
- **test_review_types.py** — the `ReviewType` registry: `test-gap` and `infracode`
  are registered, `get_review_type` returns the named instance, their instructions
  carry the required output-contract/cap markers, and an unknown name raises
  `ValueError`. The four per-language types (`golang`, `typescript`, `rust`,
  `python`) are covered by one parametrized set driven by the `LANGUAGE_TYPES`
  table — registration, the shared output/cap/severity contract, each rubric's
  own axes (goroutines and `%w`; `satisfies` and `as const`; `unsafe` and
  `unwrap()`; mutable defaults and bare excepts), the `test-gap` deferral for
  coverage findings, and the opportunistic-toolchain wording — plus the
  attribution guards: the vendored MIT `LICENSE` is present, each skill has its
  `SKILL.md` and five `references/*.md`, and every rubric's header agrees with its
  `PROVENANCE.md` on the pinned upstream commit. Adding a language type means
  adding one row to that table.
- **test_reviewers.py** — the `Reviewer` registry (`claude` and `codex` registered,
  each with a `default_model`, unknown raises), `Reviewer.command` argv for both
  agents (codex omits `--model` when empty), the shared `build_review_prompt`
  (including that it names the base as a bare commit, never `origin/<ref>`), and
  `_review_env` (trusts the clone's `mise.toml`). The `review()` calls shell out to
  `claude`/`codex` and are not unit-tested; the shell around them is covered by
  **test_run.py**.
- **test_run.py** — the shared agent runner in `reviewers/_run.py`. `run_cli_payload`
  with an injected fake runner: the payload file, not the exit status, is the
  contract — a valid payload survives a non-zero exit (the `codex` EAGAIN panic:
  review done, payload written, then exit 101), while an empty / missing /
  malformed payload raises with the exit status named, and the temp payload path is
  cleaned up on both paths. `run_agent` against a trivial `sys.executable` child
  (no agent, no network): the child cannot set `O_NONBLOCK` on our stdio — the
  regression pin for the flag leak between parallel jobs — plus prompt-on-stdin,
  both child streams relayed to the sink, exit status returned, a child that never
  reads its prompt yielding a status rather than a `BrokenPipeError`, and the child
  running in the workdir with `mise` trust set. `run_cli_json` follows the same
  file-is-the-contract rules for any JSON.
- **test_collate.py** — `DeterministicMergeCollator`: single-job identity
  passthrough, empty-jobs placeholder, two-job merge (sorted provenance headers +
  concatenated comments), and cap re-application with an overflow section across
  the merged set. The overflow heading is "Other findings not posted as comments".
- **test_checkout.py** — `clone_pr` builds the exact `gh api` (base ref + sha) /
  `git clone --filter=blob:none` / `git fetch refs/pull/<n>/head` / `git fetch
  <base-sha>` / `git checkout --detach` sequence with the right `cwd`, via an
  injected `FakeRunner` + `mkdtemp` (no network); that the returned `base` is a
  commit and not a branch name (so merged PRs still diff); that unresolvable PR
  metadata raises; and `cleanup` removes the workdir.
- **test_output.py** — `decide_mode` across the print-only / post-without-prompting
  / TTY matrix; `render` emits the body plus `path:line` comment anchors;
  `post_review` builds the `gh api .../reviews --method POST --input` call via a
  fake runner and leaves the payload file on disk; the not-posted path writes the
  payload to a real temp file and names it in the hint; `dispatch` returns the exit
  code and, when the post fails, keeps the payload and names it in the retry hint
  (so a tail-end 403 doesn't cost the review); and `show_review` renders via `glow`
  when present (else plain text), with a fake `which`/`run`.
- **test_orchestrator.py** — `run_reviews` with in-process `FakeReviewer`/`FakeType`
  (no subprocess): single-job passthrough, two-job merge (model in label),
  empty-model label, and graceful failure — a raising job is captured in
  `RunResult.failures` (not raised); partial failures keep the successes and are
  recorded in `RunResult.jobs`; every comment carries its job's `Source`; and an
  all-failed run yields `payload=None`.
- **test_cli.py** — `config_from_args` option parsing (`--model agent[=models]`
  repeatable → `(agent, model)` pairs, `--review-type` lists, per-agent
  `--claude-flags`/`--codex-flags`, the booleans), `build_jobs` (the
  `(agent,model) × review_type` matrix with per-agent flags), `resolve_agent_models`
  and `resolve_review_types` (explicit / prompt on TTY / exit-2 without one), and
  the `help` word aliasing to `--help`, plus `--synthesis-model` / `--no-synthesis`
  parsing and `build_collator` (synthesis vs deterministic, judge command);
  `--plain-language-model` (defaults to the synthesis model) / `--no-plain-language`
  and `build_plain_language_stage`.
- **test_prompts.py** — `select_from_menu` (numbers / names / empty-default /
  dedupe / invalid), `choose_review_types` (wraps it), and `choose_agent_models`
  (pick agents, then per-agent models with defaults). The `/dev/tty` wrappers are
  the thin shells, verified manually.
- **test_terminal.py** — `terminal.can_prompt` / `open_interactive`: detection
  prefers `/dev/tty` but falls back to stdin/stderr when `/dev/tty` can't be
  opened (screen / detached sessions), and reports no-terminal only when neither
  works.
- **test_synthesis.py** — `serialize_findings` (sources labelled `<agent> (<model>)
  [<type>]` with counts) and `build_synthesis_prompt` (context + findings +
  instructions); `LLMSynthesisCollator.collate` with an injected fake runner:
  single-job passthrough, judge runs for >1 job, fall-back to the deterministic
  merge when the judge raises, the judge's `sources` labels map back to jobs
  (unknown labels dropped, none left warns), `ran` is true only when the judge's
  output was used, and the prompt carries the writing rules instead of label
  prefixes and a stats section (including that overflow bullets carry the finding
  line).
- **test_plain_language_rules.py** — `rules.json` loads with the spec's
  thresholds, labels and urgency phrases; every blocking word matches its display
  word; repo terms (drift, root, state lock) are not listed; the rendered block
  names every label, threshold, word and phrase and writes its own negatives in
  full; every registered review type ends with the block and no longer has the
  old comment shape.
- **test_plain_language_check.py** — the deterministic check: a plain comment
  passes; contractions, listed words, sentences over 35 words, a missing bold
  finding line and missing Impact/Fix are blocking; 26–35 words is minor;
  Evidence is optional; code is never checked; repo terms pass; list items,
  headings and tables split correctly.
- **test_plain_language_hunks.py** — `hunk_for` finds the hunk around a new-file
  line across files, ignores removed lines when counting, limits context, and
  returns nothing outside the diff; `git_diff` builds a three-dot diff in the
  workdir through a fake runner.
- **test_plain_language_reader.py** — the reader prompt shows each comment
  beside its diff lines and asks the three questions; parsing keeps
  blocking/minor per comment and for the body and ignores malformed entries.
- **test_plain_language_rewrite.py** — the rewrite prompt lists problems and
  the writing rules and asks for null when the body needs no rewrite; parsing;
  guards reject a changed code block, a dropped inline code span or an empty
  rewrite.
- **test_plain_language_stage.py** — with a fake runner: no blocking problem
  means no rewrite call; only blocking comments are sent; a reader blocking
  problem triggers a rewrite; path, line, side and sources never change; a
  guard failure keeps the original; a failed reader call still rewrites on the
  check; a failed rewrite posts as written; the check runs again after the
  rewrite; the body is rewritten; the stderr report.
- **test_attribution.py** — the footer for one source, two agents, one agent
  with two models, two review types on one model, and no source; the "How this
  review was made" block lists every job with found/posted counts or its
  failure, and mentions synthesis and plain language only when they ran; a pipe
  in an error is escaped; `finalize` appends both without changing its input.
