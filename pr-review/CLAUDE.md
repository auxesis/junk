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

Pure logic is unit-tested directly. The three real side effects — `git clone`,
the `claude` CLI review, and the `gh api` post — are never executed in the suite:
the shells around them are tested through injected fake runners, and the true
end-to-end path (real PR → clone → claude → post) is verified only by a manual
run. When you touch a side-effecting module, test its command construction with a
fake, not the real subprocess.

## Test suite

`tests/` holds 9 files, one per `src/pr_review/` module (43 tests total):

- **test_target.py** — `parse_target`: PR URL, trailing-slash URL, `owner/repo#N`
  short form, whitespace stripping, and a parametrized rejection of malformed
  input. Asserts `Target` value equality.
- **test_payload.py** — `Payload`/`Comment` `to_dict` shape; `parse_payload` happy
  path and the `comments`-default; its validation rejections (invalid JSON,
  missing/non-string body, comment missing `path`, non-string body, non-integer
  `line`); and `cap_comments` splitting at the 8-comment cap.
- **test_review_types.py** — the `ReviewType` registry: `test-gap` is registered,
  `get_review_type` returns the named instance, its instructions contain the
  required schema/cap markers, and an unknown name raises `ValueError`.
- **test_reviewers.py** — the `Reviewer` registry (`claude` registered, unknown
  raises) and the pure `ClaudeReviewer.build_prompt` (carries run context + the
  type's instructions). `review()` shells out to `claude` and is not unit-tested.
- **test_collate.py** — `DeterministicMergeCollator`: single-job identity
  passthrough, empty-jobs placeholder, two-job merge (sorted provenance headers +
  concatenated comments), and cap re-application with an overflow section across
  the merged set.
- **test_checkout.py** — `clone_pr` builds the exact `git clone --filter=blob:none`
  / `gh pr checkout` / `gh pr view` sequence with the right `cwd`, via an injected
  `FakeRunner` + `mkdtemp` (no network); and `cleanup` removes the workdir.
- **test_output.py** — `decide_mode` across the print-only / post-without-prompting
  / TTY matrix; `render` emits the body plus `path:line` comment anchors; and
  `post_review` builds the `gh api .../reviews --method POST --input` call via a
  fake runner.
- **test_orchestrator.py** — `run_reviews` with in-process `FakeReviewer`/`FakeType`
  (no subprocess): single-job passthrough, two-job merge, and failure attribution
  (a raising reviewer surfaces a `RuntimeError` naming the `reviewer/type`).
- **test_cli.py** — `config_from_args` option parsing (`--agent`/`--type` lists,
  `--model`, `--post-without-prompting`, `--print-only`, `--keep-clone`,
  `--claude-flags=` shlex-split), the `help` word aliasing to `--help`, that
  `--help` advertises each option's default, and `build_jobs` (agent × type
  cross-product; unknown name raises).
