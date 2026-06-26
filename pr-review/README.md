# pr-review

Review a GitHub pull request with one or more LLMs, in an **isolated clone**.

`pr-review` clones the target PR into a throwaway temp directory, fans out to one
or more `(reviewer × review-type)` jobs **in parallel**, collates and synthesises their findings
into a single review (de-duplicating across models when more than one runs), and prints it — prompting before it posts anything to the
PR. Because every run works in its own clone, you can review multiple PRs at once
without touching your working tree or colliding with another run.

Today it ships two agents (**Claude** and **Codex**, headless) and two review types
(**test-gap**: test-coverage gap analysis; **infracode**: infrastructure-as-code
review). The multi-LLM, multi-type, and collation machinery is already built and
tested, so new agents and review types are additive — see [Developing](#developing).

---

## Requirements

- [`mise`](https://mise.jdx.dev/) — provisions Python 3.14 and `uv` for the project.
- [`git`](https://git-scm.com/)
- [`gh`](https://cli.github.com/) — authenticated (`gh auth status` must pass).
- [`claude`](https://docs.claude.com/en/docs/claude-code) — the Claude Code CLI, on your `PATH`.
- [`codex`](https://github.com/openai/codex) — the OpenAI Codex CLI, on your `PATH` (only needed to run a `--model codex` job).
- `~/bin` on your `PATH` (the install step symlinks the commands there).

---

## Install

From the project directory:

```bash
mise run install
```

This runs `uv sync` (creates the project venv from the lockfile) and symlinks the
`pr-review` command into `~/bin`.

The symlink points at a small launcher shim in `bin/`. It resolves its own real
path and runs the project through `uv run`, so the installed command **always
executes the current source with the current, lockfile-synced dependencies** — edit
the code and the next invocation picks it up; no reinstall needed.

> Prefer not to install? Run it straight from the project directory with
> `uv run pr-review <target>`.

---

## Run

```bash
pr-review <pr-url | owner/repo#N>
```

The target is **explicit** — a full PR URL or the compact `owner/repo#N` form.
There is no inference from the current directory or branch.

```bash
pr-review https://github.com/org/repo/pull/214
pr-review org/repo#214
```

Run `pr-review help` (or `pr-review --help`) to see all options.

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
  `--model codex` lets codex use its own configured default (its available
  models depend on your codex auth — e.g. a ChatGPT-account login can't use
  `gpt-5-codex`). Pin one explicitly with `--model codex=<id>`.
- Model ids are passed **verbatim** to the agent's CLI — give real ids
  (`claude-opus-4-8`, not `opus-4.8`).
- A failing job (bad model, auth, etc.) doesn't abort the run: surviving jobs
  still produce a review, failures are reported, and the exit is non-zero only
  if every job failed.
- Registered agents: `claude`, `codex`. Registered review types: `test-gap`,
  `infracode`. Unknown names fail fast, before any clone.
- Omit `--model` (or `--review-type`) to choose interactively; with no terminal
  (CI, piped stdin) the tool errors and asks you to pass the flag.
- `--claude-flags="…"` / `--codex-flags="…"` pass extra flags to that agent's CLI.

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

### Posting behaviour

By default `pr-review` **reviews and prints, then asks** before posting to the PR:

| Mode | Trigger |
|------|---------|
| Prompt `[y/N]`, then post if confirmed | default (interactive terminal) |
| Post without prompting | `--post-without-prompting` |
| Review only — never post, never prompt | `--print-only` |
| Review only (falls back automatically) | no terminal available and `--post-without-prompting` not set |

### Options

| Option | Effect | Default |
|--------|--------|---------|
| `--model agent[=models]` | Per-agent models (repeatable) | `claude=claude-opus-4-8` |
| `--codex-flags="<flags>"` | Extra flags appended to the `codex` invocation | empty |
| `--synthesis-model agent[=model]` | Judge that de-dupes/verifies findings across jobs | `claude=claude-opus-4-8` |
| `--no-synthesis` | Skip synthesis; raw-merge multi-job results | off |
| `--post-without-prompting` | Post without prompting | off |
| `--print-only` | Review and print only; never post | off |
| `--claude-flags="<flags>"` | Extra flags appended to the `claude` invocation | empty |
| `--keep-clone` | Keep the temp clone on exit (prints its path) instead of deleting it | off |

(`--model` and `--review-type` are described above. Use the `--claude-flags="..."`
form with the `=` so the leading dashes aren't read as `pr-review` options.)

```bash
pr-review --print-only org/repo#214                   # dry run, prints the review only
pr-review --post-without-prompting org/repo#214       # non-interactive, auto-post
pr-review --keep-clone org/repo#214                   # leave the clone behind for inspection
pr-review --model claude=claude-opus-4-8 --claude-flags="--debug" org/repo#214
```

### What happens during a run

```
target → clone (blobless) into a temp dir → gh pr checkout
       → fan out (reviewer × type) jobs in parallel → collate (synthesise across models if >1 job) into one review
       → print, then post / prompt / review-only per the rules above
       → delete the temp clone (unless --keep-clone)
```

The clone uses `git clone --filter=blob:none`: it is fast and light but keeps the
full history graph, so the reviewer's `git diff origin/<base>...HEAD` always has
its merge-base.

---

## Developing

### Layout

```
pr-review/
├── pyproject.toml          # project + entry point (pr-review = pr_review.cli:main)
├── mise.toml               # tasks: test, install
├── bin/                    # uv-run launcher shim (symlinked into ~/bin)
├── src/pr_review/
│   ├── cli.py              # arg/env parsing → RunConfig → orchestrate → output
│   ├── target.py           # parse PR URL / owner/repo#N
│   ├── checkout.py         # blobless clone + gh pr checkout into a temp dir
│   ├── orchestrator.py     # parallel fan-out (ThreadPoolExecutor) + collate
│   ├── payload.py          # review payload model, JSON validation, comment cap
│   ├── collate.py          # Collator + DeterministicMergeCollator
│   ├── output.py           # posting-mode decision, render, gh-api post
│   ├── reviewers/          # Reviewer ABC + registry; claude.py, codex.py
│   └── review_types/       # ReviewType ABC + registry; test_gap.py, infracode.py
├── tests/                  # pytest suite
└── docs/superpowers/       # design spec + implementation plan
```

### Run the tests

```bash
mise run test          # == uv run pytest
```

The suite covers the **pure logic** — target parsing, payload validation and the
comment cap, collation, the posting-mode decision, prompt building, and command
construction (with injected fake runners). The side-effecting shells (`git clone`,
the `claude` call, the `gh api` post) are thin wrappers verified by a manual
end-to-end run, not by the unit suite.

### Extending: add a reviewer (LLM backend)

Reviewers are looked up by name from a registry, so a new backend is a new file
plus one registration line — no change to the core.

```python
# src/pr_review/reviewers/codex.py
from pr_review.payload import Payload
from pr_review.reviewers.base import Reviewer, register


class CodexReviewer(Reviewer):
    name = "codex"

    def review(self, *, workdir, base, owner, repo, number,
               review_type, model, extra_flags) -> Payload:
        # run your backend over `workdir`, parse its output into a Payload
        ...


register(CodexReviewer())
```

Then import it for its registration side-effect in
`src/pr_review/reviewers/__init__.py` (alongside the existing `claude` import).
After that, `--model codex` (and `--model claude --model codex`, which runs both)
just works.

### Extending: add a review type

Same pattern in `review_types/` (`test_gap.py` and `infracode.py` are worked
examples). A review type's `instructions()` must include the JSON-payload output
contract (write the payload file, don't post, anchor comments at `path:line`,
8-comment cap) — copy the `## Output (REQUIRED)` section from an existing type:

```python
# src/pr_review/review_types/security.py
from pr_review.review_types.base import ReviewType, register


class SecurityType(ReviewType):
    name = "security"

    def instructions(self) -> str:
        return "..."   # domain guidance + the shared output contract


register(SecurityType())
```

Import it in `src/pr_review/review_types/__init__.py`, and `--review-type security`
becomes available.

### Collation

`DeterministicMergeCollator` merges multiple jobs' payloads into one: bodies under
per-job headers, comments concatenated with the 8-comment cap re-applied, and any
overflow listed in the body. `LLMSynthesisCollator` (in `synthesis.py`) is the default for multi-job runs — a judge LLM de-dupes findings across models, verifies them against the diff, and emits one review; `cli.py`'s `build_collator` selects it (or the deterministic merge under `--no-synthesis`).

### Design docs

The full design rationale and the task-by-task build plan live under
`docs/superpowers/`:

- `docs/superpowers/specs/2026-06-26-pr-review-multi-llm-rewrite-design.md`
- `docs/superpowers/plans/2026-06-26-pr-review-multi-llm-rewrite.md`
