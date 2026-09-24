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

Pure logic is unit-tested directly. The real side effects — `git clone` and
fetch, the `claude` and `codex` CLI runs, and every `gh api` call (context
reads, the review post and reply posts) — are never executed in the suite:
the shells around them are tested through injected fake runners, and the true
end-to-end path (real PR → clone → claude → post) is verified only by a manual
run. When you touch a side-effecting module, test its command construction with a
fake, not the real subprocess.

## Test suite

`tests/` holds 27 files, one per `src/pr_review/` module (334 tests total):

- **test_target.py** — `parse_target`: PR URL, trailing-slash URL, `owner/repo#N`
  short form, whitespace stripping, and a parametrized rejection of malformed
  input. Asserts `Target` value equality.
- **test_payload.py** — `Payload`/`Comment` `to_dict` shape; `parse_payload` happy
  path and the `comments`-default; its validation rejections (invalid JSON,
  missing/non-string body, comment missing `path`, non-string body, non-integer
  `line`); `cap_comments` splitting at the 8-comment cap; `Source`, `Comment.sources`
  (never in `to_dict`), and `payload_from_dict`; `Reply.to_dict` (body only, even
  with an `answer_id`) and that `Payload.replies` never reaches `to_dict`.
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
  adding one row to that table. A separate parametrized set over every
  registered type asserts the HARD CAP overflow heading is "## Other findings
  not posted as comments" (matching `collate.py` / `synthesis.py`'s `_cap_payload`)
  and neither of the two old headings is still there.
- **test_reviewers.py** — the `Reviewer` registry (`claude` and `codex` registered,
  each with a `default_model`, unknown raises), `Reviewer.command` argv for both
  agents (codex omits `--model` when empty), the shared `build_review_prompt`
  (including that it names the base as a bare commit, never `origin/<ref>`, and
  that a passed-in context summary sits before the instructions while its
  absence leaves the prompt unchanged), and `_review_env` (trusts the clone's
  `mise.toml`). The `review()` calls shell out to `claude`/`codex` and are not
  unit-tested; the shell around them is covered by **test_run.py**.
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
  metadata raises; `cleanup` removes the workdir; each pull request in the stack
  is fetched into `refs/stack/<n>` after the base, and a stack ref that cannot be
  fetched is left out of `Checkout.stack_refs` rather than failing the clone; and
  `write_context_file` writes inside `.git/pr-review/` in the clone.
- **test_context_github.py** — `GitHub.get`, `get_all` (`--paginate --slurp`,
  pages flattened) and `graphql` (integers as typed `-F` variables,
  strings and booleans as raw `-f` ones) build the right `gh api`
  argv through a fake runner.
- **test_context_discussion.py** — issue comments and non-empty review bodies
  merge in time order (an empty review body is dropped); the author is marked
  on every entry; review comments group into threads with their path and line
  (an outdated comment keeps its original line); a reply whose root comment
  is missing becomes a root itself; and each entry keeps GitHub's
  `author_association` (empty when absent).
- **test_context_issues.py** — `#N` references in a body are found once each,
  including a closing keyword and a markdown link, excluding the pull request's
  own number, a colour literal and a URL fragment; a referenced pull request is
  skipped, not loaded as an issue; and a failed issue read is reported in
  `failed` rather than raising.
- **test_context_stack.py** — a native (GitHub) stack uses its own order and
  position, and marks entries before the current pull request as earlier and
  after as later; a native stack whose GraphQL read fails falls back to the
  branch chain; with no native stack, the chain is discovered by walking base
  branches down to the repository's default branch and head branches up through
  every child, keeping every branch of a tree; a pull request already on the
  default branch with no children has no stack; the walk stops at `MAX_DEPTH`;
  and branch names are URL-encoded in the `gh api` path.
- **test_context_gather.py** — `gather_context` assembles the description,
  linked issues, discussion and stack from fakes; a failed part (discussion,
  an issue, the stack) is left out rather than raising, named in `failed` by
  part name only (so no local path reaches the posted review) and in `errors`
  with its reason; and a failed
  read of the pull request itself raises, since there is no review without it.
- **test_context_render.py** — `stack_map` orders earlier/this/later pull
  requests with their state, position and `refs/stack/<n>` ref, and reports
  "not part of a stack" when there is none; `render_context_file` includes
  every part with comment/thread ids, author associations and `(author)` marks,
  fences every untrusted body (description, issue, discussion entry, stack pull
  request) between `<<<untrusted` and `>>>`, keeps a body from closing its own
  fence, and writes "(none)" under "Other pull requests in the stack" when it is
  empty; `prompt_summary` opens with the context-file path and the stack map and
  fenced description, and carries both reviewer instructions ("Before you
  report that something is missing" / "Before you report anything, read the
  discussion") and the `UNTRUSTED_RULE`; and
  `describe_stack`, `describe_loaded` and `describe_dropped` build the
  **How this review was made** block's stack line, context-loaded line, and
  one line per dropped finding (naming the fix, the thread or the reply it was
  answered in).
- **test_context_filter.py** — `apply_verdicts` for every verdict kind: `keep`
  and a missing verdict both keep the finding; `fixed-later` drops it and
  records the pull request, but is kept (with a warning) when the named pull
  request is earlier, closed, unknown, or missing from the verdict entirely
  ("the verdict named no later pull request"); `already-raised` and `answered`
  drop with their link, but only when it is the URL of a known comment or
  thread entry (else kept, warning "the verdict linked to no known comment"),
  and `answered` only when that entry is the author's (else kept, warning "the
  linked answer is not the author's"), while `already-raised` may link to
  anyone's entry; a bad index or an unknown reason is ignored; a `reply`
  to a review-thread comment the author posted becomes a `Reply` addressed to
  the thread's top-level comment (GitHub rejects replies to replies) with
  `answer_id` naming the author's entry, while a `reply` to someone
  else's comment or to an issue comment stays a posted comment with the
  author's answer added to its **Evidence** section via `_add_evidence` (which
  inserts before **Fix** when there is no Evidence yet, appends to existing
  Evidence, and appends at the end when there is no **Fix**); replies beyond
  `MAX_REPLIES` (3) go to the body's overflow list instead; `build_filter_prompt`
  names the payload and context file paths, the stack's refs and states, each
  finding, each author's association and mark, and the `UNTRUSTED_RULE`; a failed filter call keeps every finding, and a
  response with no `verdicts` list (or a non-object response) does the same
  and warns "context filter returned no verdicts list; every finding is kept";
  and `answers_by_id` covers both top-level comments and every thread entry.
- **test_output.py** — `decide_mode` across the print-only / post-without-prompting
  / TTY matrix; `render` emits the body plus `path:line` comment anchors, then each reply
  under a "Reply to comment `<in_reply_to>`" heading;
  `post_review` builds the `gh api .../reviews --method POST --input` call via a
  fake runner and leaves the payload file on disk; the not-posted path writes the
  payload to a real temp file and names it in the hint; `dispatch` returns the exit
  code and, when the post fails, keeps the payload and names it in the retry hint
  (so a tail-end 403 does not cost the review); `show_review` renders via `glow`
  when present (else plain text), with a fake `which`/`run`; replies post one at
  a time after the review, each to `.../comments/<id>/replies`, and a posted
  reply's temp file is removed; a failed reply does not stop the others, keeps
  its own file, and is named in the retry hint, while the review and any
  already-posted replies still count as posted; a failed review posts no
  replies at all and keeps every payload file; the review-only path writes a
  file (with a retry command) for every reply as well as the review; and the
  confirm prompt names both the inline comment count and the reply count.
- **test_orchestrator.py** — `run_reviews` with in-process `FakeReviewer`/`FakeType`
  (no subprocess): single-job passthrough, two-job merge (model in label),
  empty-model label, and graceful failure — a raising job is captured in
  `RunResult.failures` (not raised); partial failures keep the successes and are
  recorded in `RunResult.jobs`; every comment carries its job's `Source`; and an
  all-failed run yields `payload=None`; and a context summary passed to
  `run_reviews` reaches every job's `review()` call.
- **test_cli.py** — `config_from_args` option parsing (`--model agent[=models]`
  repeatable → `(agent, model)` pairs, `--review-type` lists, per-agent
  `--claude-flags`/`--codex-flags`, the booleans), `build_jobs` (the
  `(agent,model) × review_type` matrix with per-agent flags), `resolve_agent_models`
  and `resolve_review_types` (explicit / prompt on TTY / exit-2 without one), and
  the `help` word aliasing to `--help`, plus `--synthesis-model` / `--no-synthesis`
  parsing and `build_collator` (synthesis vs deterministic, judge command);
  `--plain-language-model` (defaults to the synthesis model) / `--no-plain-language`
  and `build_plain_language_stage`; `--no-context` / `--no-context-filter` /
  `--context-filter-model` parsing and `build_context_filter` (follows the
  synthesis model by default; builds none under either `--no-context` or
  `--no-context-filter`); `main()`, with `clone_pr`/`gather_context`/`run_reviews`/
  `cleanup`/the stage all faked (no clone, no subprocess, no network): context
  `errors` print to stderr with their reasons; the clone is cleaned up even
  when writing the context file raises; a
  `stage.apply` exception is caught, warned on stderr, and falls back to
  `check_payload` rather than losing the review; and the plain-language report
  prints after `output.show_review`, not before.
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
  instructions), including that a pull request context summary passed in sits
  before the synthesis instructions, so the judge sees it too; `LLMSynthesisCollator.collate` with an injected fake runner:
  single-job passthrough, judge runs for >1 job, fall-back to the deterministic
  merge when the judge raises, the judge's `sources` labels map back to jobs
  (unknown labels dropped, none left warns), `ran` is true only when the judge's
  output was used, and the prompt carries the writing rules instead of label
  prefixes and a stats section (including that overflow bullets carry the finding
  line).
- **test_plain_language_rules.py** — `rules.json` loads with the spec's
  thresholds, labels and urgency phrases; every blocking word matches its display
  word; "surfaced" bans the verb ("this bug surfaced") but not the noun ("the
  API surfaces three methods"); repo terms (drift, root, state lock) are not
  listed; the rendered block names every label, threshold, word and phrase,
  cites each numbered writing rule's source (ISO 24495-1 / ASD-STE100, or none
  for 8-10), rule 10 also bans a term only defined elsewhere, and the block
  writes its own negatives in full (the contraction regex covers both the
  ASCII `'` and the typographic `’`); every registered review type ends with
  the block and no longer has the old comment shape.
- **test_plain_language_check.py** — the deterministic check: a plain comment
  passes; contractions, listed words, sentences over 35 words, a missing bold
  finding line and missing Impact/Fix are blocking; 26–35 words is minor;
  Evidence is optional; code is never checked; repo terms pass; list items,
  headings and tables split correctly.
- **test_plain_language_hunks.py** — `hunk_for` finds the hunk around a new-file
  line across files, ignores removed lines when counting, limits context, and
  returns nothing outside the diff; `git_diff` builds a three-dot diff in the
  workdir through a fake runner, with the exact `--no-color --no-ext-diff
  --src-prefix=a/ --dst-prefix=b/` flags that keep it parseable regardless of
  the user's git config.
- **test_plain_language_reader.py** — the reader prompt shows each comment
  beside its diff lines and asks the three questions; parsing keeps
  blocking/minor per comment and for the body and ignores malformed entries.
- **test_plain_language_rewrite.py** — the rewrite prompt lists problems and
  the writing rules and asks for null when the body needs no rewrite; parsing;
  guards reject a changed code block, a dropped inline code span or an empty
  rewrite.
- **test_plain_language_stage.py** — `check_payload` runs the word-and-shape
  check only, with no runner call; with a fake runner: no blocking problem
  means no rewrite call; only blocking comments are sent; a reader blocking
  problem triggers a rewrite; path, line, side and sources never change; a
  guard failure keeps the original; a failed reader call still rewrites on the
  check; a failed rewrite posts as written; the check runs again after the
  rewrite; the body is rewritten; the stderr report; a non-empty diff that
  matches no comment's path/line warns; the reader and rewrite calls run in a
  fresh empty temp directory, never the clone's workdir; and `reader_ran` is
  true only when the reader call's result was parsed. Replies are treated as
  extra comments throughout: `check_payload` and `apply` check and rewrite
  them (a reply's hunk is `(the comment this replies to)` plus the `answers`
  text for its `answer_id`, else its `in_reply_to` id, never a diff hunk), `apply`'s `answers`
  parameter feeds that text to the reader prompt, and the rewritten reply
  keeps its `in_reply_to` and `sources`; `format_report` lists a reply's
  remaining problems under "reply to comment `<in_reply_to>`" and counts
  replies into both the numerator and denominator of the summary line.
- **test_attribution.py** — the footer for one source, two agents, one agent
  with two models, two review types on one model, and no source; the "How this
  review was made" block lists every job with found/posted counts or "failed"
  (never the raw error text, which can name local paths), and mentions
  synthesis and plain language only when they ran; the plain-language line
  reads "read every comment..." only when `RunRecord.reader_ran` is true, else
  "the reader test did not run; only the word-and-shape check was applied";
  the block also carries `RunRecord.stack_line` and `context_line` when set,
  and a `not_posted` list under a **Findings not posted** heading; posted
  counts include replies as well as comments; `finalize` appends both without
  changing its input, and appends the same footer to each reply while keeping
  its `in_reply_to`.
