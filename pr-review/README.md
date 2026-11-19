# pr-review

Review a GitHub pull request with one or more LLMs, in an **isolated clone**.

`pr-review` clones the target PR into a throwaway temp directory, fans out to one
or more `(reviewer × review-type)` jobs **in parallel**, collates and synthesises their findings
into a single review (de-duplicating across models when more than one runs), and prints it — prompting before it posts anything to the
PR. Because every run works in its own clone, you can review multiple PRs at once
without touching your working tree or colliding with another run.

Today it ships two agents (**Claude** and **Codex**, headless) and six review types:
two language-agnostic (**test-gap**: test-coverage gap analysis; **infracode**:
infrastructure-as-code review) and four per-language (**golang**, **typescript**,
**rust**, **python**), each distilled from the corresponding MIT-licensed
[claude-skills](https://github.com/Jeffallan/claude-skills) skill — see
[Vendored upstream material](#vendored-upstream-material). The multi-LLM, multi-type, and collation machinery is already built and
tested, so new agents and review types are additive — see [Developing](#developing).

---

## Requirements

- [`mise`](https://mise.jdx.dev/) — provisions Python 3.14 and `uv` for the project.
- [`git`](https://git-scm.com/)
- [`gh`](https://cli.github.com/) — authenticated (`gh auth status` must pass), and
  new enough to support `gh api --paginate --slurp` (used to read the pull
  request's discussion and stack).
- [`claude`](https://docs.claude.com/en/docs/claude-code) — the Claude Code CLI, on your `PATH`.
- [`codex`](https://github.com/openai/codex) — the OpenAI Codex CLI, on your `PATH` (only needed to run a `--model codex` job).
- [`coop`](https://github.com/trailofbits/coop) — runs the review agents in a temporary virtual machine (VM). You need it unless you pass `--no-isolation`. To set it up, follow [Run agents in a coop VM](#run-agents-in-a-coop-vm).
- [`glow`](https://github.com/charmbracelet/glow) — optional; if on your `PATH`, the review printed before the post prompt is rendered with it (`glow -p -w 100`).
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
pr-review <target> --review-type test-gap,rust \
  --model claude=claude-opus-5,claude-fable-5 \
  --model codex=gpt-5.6-terra,gpt-5.6-sol
```

- `--model claude` (no `=`) uses claude's default model (`claude-opus-5-5`);
  `--model codex` uses `gpt-5.6-terra`. Override per run with `--model codex=<id>`
  (model availability depends on your codex auth — e.g. a ChatGPT-account login
  can't use `gpt-5-codex`; `codex --model` lists what yours actually offers).
- A bare value can name several agents: `--model claude,codex` runs both with
  their default models (equivalent to `--model claude --model codex`). After an
  `agent=`, the comma separates *models* for that agent (`--model claude=opus,fable`)
  until the next `agent=`. One value can mix both: `--model claude,codex=gpt-5.6-terra`
  runs claude on its default and codex on `gpt-5.6-terra`. Bare agents go first —
  a bare name after an `agent=` is read as a model.
- Model ids are passed **verbatim** to the agent's CLI — give real ids
  (`claude-opus-5`, not `opus-5`).
- A failing job (bad model, auth, etc.) doesn't abort the run: surviving jobs
  still produce a review, failures are reported, and the exit is non-zero only
  if every job failed.
- Registered agents: `claude`, `codex`. Registered review types: `test-gap`,
  `infracode`, `golang`, `typescript`, `rust`, `python`. Unknown names fail fast,
  before any clone.
- The per-language types each defer coverage gaps to `test-gap`, so pairing them
  (`--review-type rust,test-gap`) gives complementary findings rather than
  duplicates. Each opportunistically runs that language's toolchain (`cargo
  clippy`, `tsc --noEmit`, `mypy`, `go vet`) when the clone already has it, and
  reviews by reading when it doesn't.
- Omit `--model` (or `--review-type`) to choose interactively; with no terminal
  (CI, piped stdin) the tool errors and asks you to pass the flag.
- `--claude-flags="…"` / `--codex-flags="…"` pass extra flags to that agent's CLI.

### Collating multiple models

When a run produces more than one job, pr-review runs a **synthesis pass** before
posting: a judge LLM is handed every finding (tagged by model and review-type)
plus the diff, and it de-dupes findings that overlap across models, verifies each
against the code (dropping ones it can't substantiate), and emits one review —
each comment ends with a small footer naming the models that found it
(`Found by 2 models: claude, codex`), and the body ends with a collapsed
**How this review was made** block listing every job, its review type, how many
findings it raised and how many were posted.

- `--synthesis-model AGENT[=MODEL]` — the judge (default `claude=claude-sonnet-5-5`;
  e.g. `--synthesis-model codex=gpt-5.6-terra`).
- `--no-synthesis` — skip it and raw-merge the jobs (today's behaviour).
- A single job skips synthesis; if the judge run fails, pr-review falls back to
  the raw merge so you always get a review.

### Plain language

Every comment is written for an engineer who did not write the code and does not
know this part of the system. Each one has a bold finding line, then **Impact**,
an optional **Evidence**, and **Fix**. After collation pr-review checks every
comment for listed jargon, contractions and long sentences, has a model read each
comment beside its diff lines as a new reader would, and rewrites only the
comments that reader could not act on. Anything left is listed on stderr before
you confirm the post. The rules and word list are in
`src/pr_review/plain_language/rules.json`.

Every review starts with a **Recommendation** heading that pr-review works out
from the posted findings: 🔴 fix before merging (any finding marked "Fix before
merge"), 🟡 merge after changes (any "Change before merge", or a finding with no
urgency), or 🟢 merge as it is. A failed review job is named in the heading.

- `--plain-language-model AGENT[=MODEL]` — the reader and rewriter (default: the synthesis model).
- `--no-plain-language` — skip the reader test and rewrite; the word-and-shape check still reports.

### Pull request context

Before reviewing, pr-review reads the pull request's description, the GitHub
issues it links to, its discussion (comments, review bodies and review threads),
and the other pull requests in its stack — GitHub's stacked pull requests, or a
chain of pull requests whose base is the branch below. Each pull request in the
stack is fetched into the clone as `refs/stack/<n>`.

Reviewers are told to check later pull requests before reporting something
missing, and the discussion before reporting anything. Then a context filter
checks every finding: it drops findings a later pull request fixes, that the
discussion already raised, or that the author answered or deferred, and lists
them under **Findings not posted** in the review's collapsed record. When the
code proves an author's answer wrong, the finding is posted as a reply in that
thread (at most 3 per run).

- `--no-context` — review the diff only.
- `--no-context-filter` — give reviewers the context, but do not filter findings.
- `--context-filter-model AGENT[=MODEL]` — the filter's model (default: the synthesis model).

### Run agents in a coop VM

By default, pr-review runs the review agents in a temporary coop VM.
The agents run with their permission checks turned off.
In the VM, the commands they choose to run do not run on your machine.

Each run starts its own VM, and coop copies the clone into it at `/workspace`.
Changes that the agents make in the VM do not reach the clone on your machine.
pr-review destroys the VM when the run ends.

These steps run in the VM:

- the review jobs
- the synthesis judge
- the context filter

These steps run on your machine, so the [Requirements](#requirements) still apply there:

- reading the pull request context with `gh`
- cloning the pull request
- the plain-language reader test and rewrite
- posting the review

The VM gets 1 vCPU for each review job, with at least 2 and at most 8.
The VM gets 1536 MiB of memory for each job, with at least 4096 MiB and at most 12288 MiB.

#### Set up coop

Do these steps once:

1. Install [`coop`](https://github.com/trailofbits/coop).
2. Run `coop setup`. pr-review needs `coop images` to list at least one template image.
3. Run `claude setup-token`, then `coop proxy setup`. pr-review needs coop's Anthropic proxy to be on.
4. If you run `--model codex` jobs, set up coop's OpenAI proxy. Follow [Set up Codex in the VM](#set-up-codex-in-the-vm).

Before every run, pr-review checks that `coop` runs, that it has a template image, and that the Anthropic proxy is on.
If a check fails, pr-review prints the command that fixes it and exits with status 2.
pr-review runs these checks before it clones anything.

The checks do not cover Codex.
A `--model codex` job runs `codex` inside the VM.
If Codex cannot reach OpenAI from the VM, that job fails.
The other jobs still produce a review.

#### Set up Codex in the VM

Use coop's OpenAI proxy with an OpenAI API key.
The key stays on your machine.
The proxy adds the key to Codex's requests when they leave the VM.

1. Create an API key at <https://platform.openai.com/api-keys>.
   A restricted key needs only one permission: **Responses**, set to **Write**.
   coop's proxy blocks every other OpenAI request.
2. Add credit to the OpenAI Platform account that you created the key in.
   OpenAI bills API use to that account.
   A ChatGPT plan does not pay for API use.
3. Run `coop proxy setup --openai`, and paste the key when coop asks for it.

Do not skip the proxy.
Without it, coop copies `~/.codex/auth.json` into the VM.
That file contains your ChatGPT login.
The agents in the VM can read it.

If a Codex job fails, look for one of these errors in pr-review's output:

| Codex error | Fix |
|---|---|
| `Quota exceeded. Check your plan and billing details.` | Add credit to the OpenAI Platform account that you created the key in. |
| `Missing scopes: api.responses.write` | Give the key **Responses** write permission. If you create a new key, run `coop proxy setup --openai` again. |

#### Run without the VM

Pass `--no-isolation` to run the agents on your machine.
pr-review then does not check coop or start a VM.

Without the VM, the agents can run any command that your user account can run.
The agents do not ask before they run a command.
The flags that turn off the prompts are `--dangerously-skip-permissions` for `claude` and `--dangerously-bypass-approvals-and-sandbox` for `codex`.

#### Keep the VM to inspect it

`--keep-clone` keeps the VM as well as the clone.
At the end of the run, pr-review prints the VM's name.
The name has the form `pr-review-<owner>-<repo>-<n>-<suffix>`.
To open a shell in the VM, run `coop shell <name>`.
To remove it, run `coop destroy <name>`.

Remove a kept VM when you finish with it, because the VM holds credentials.
If pr-review cannot destroy a VM at the end of a run, it prints a warning with the `coop destroy` command to run.

### Security

Context mode puts text written by any GitHub user (the description, linked
issues, comments and the other pull requests in the stack) into prompts for
agents that run with permission checks turned off. pr-review marks that text as
untrusted and tells the agents never to follow it, but that is a mitigation, not
a guarantee. Use `--no-context` on repositories where untrusted people can
comment.

### Posting behaviour

By default `pr-review` **reviews and prints, then asks** before posting to the PR:

| Mode | Trigger |
|------|---------|
| Prompt `[y/N]`, then post if confirmed | default (interactive terminal) |
| Post without prompting | `--post-without-prompting` |
| Review only — never post, never prompt | `--print-only` |
| Review only (falls back automatically) | no terminal available and `--post-without-prompting` not set |

Replies post after the review, one at a time. If one fails, the others still
post; pr-review keeps the failed reply's file, prints a command to post it,
and exits 1.

### Options

| Option | Effect | Default |
|--------|--------|---------|
| `--model agent[=models]` | Per-agent models (repeatable) | `claude=claude-opus-5-5` |
| `--codex-flags="<flags>"` | Extra flags appended to the `codex` invocation | empty |
| `--synthesis-model agent[=model]` | Judge that de-dupes/verifies findings across jobs | `claude=claude-sonnet-5-5` |
| `--no-synthesis` | Skip synthesis; raw-merge multi-job results | off |
| `--plain-language-model agent[=model]` | Reader test and rewrite model | the synthesis model |
| `--no-plain-language` | Skip the reader test and rewrite | off |
| `--no-context` | Review the diff only | off |
| `--no-context-filter` | Do not filter findings against the context | off |
| `--context-filter-model agent[=model]` | Context filter model | the synthesis model |
| `--post-without-prompting` | Post without prompting | off |
| `--print-only` | Review and print only; never post | off |
| `--claude-flags="<flags>"` | Extra flags appended to the `claude` invocation | empty |
| `--no-isolation` | Run the agents on this machine, not in a coop VM | off |
| `--keep-clone` | Keep the temp clone and the coop VM on exit (prints the clone's path and the VM's name) instead of deleting them | off |

(`--model` and `--review-type` are described above. Use the `--claude-flags="..."`
form with the `=` so the leading dashes aren't read as `pr-review` options.)

```bash
pr-review --print-only org/repo#214                   # dry run, prints the review only
pr-review --post-without-prompting org/repo#214       # non-interactive, auto-post
pr-review --keep-clone org/repo#214                   # leave the clone behind for inspection
pr-review --model claude=claude-opus-5 --claude-flags="--debug" org/repo#214
```

### What happens during a run

```
target → check that coop is ready (skipped under --no-isolation)
       → clone (blobless) into a temp dir → check out refs/pull/<n>/head detached
       → start a coop VM with a copy of the clone at /workspace (skipped under --no-isolation)
       → fan out (reviewer × type) jobs in parallel → collate (synthesise across models if >1 job) into one review
       → delete the temp clone and destroy the VM (unless --keep-clone)
       → print, then post / prompt / review-only per the rules above
```

The clone uses `git clone --filter=blob:none`: it is fast and light but keeps the
full history graph, so the reviewer's `git diff <base>...HEAD` always has its
merge-base.

The checkout deliberately avoids `gh pr checkout`, and the base is a commit sha
rather than a branch name. Both exist to make merged PRs reviewable:
`gh pr checkout` fetches the head *branch*, which GitHub deletes on merge, and a
merged PR's base branch already contains the head, so `origin/<base>...HEAD`
would diff to nothing. `refs/pull/<n>/head` and the PR's `base.sha` are both
permanent, and reproduce GitHub's own "Files changed" exactly.

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
│   ├── checkout.py         # blobless clone + detached refs/pull/<n>/head in a temp dir
│   ├── orchestrator.py     # parallel fan-out (ThreadPoolExecutor) + collate
│   ├── payload.py          # review payload model, JSON validation, comment cap
│   ├── collate.py          # Collator + DeterministicMergeCollator
│   ├── output.py           # posting-mode decision, render, gh-api post
│   ├── reviewers/          # Reviewer ABC + registry; claude.py, codex.py
│   └── review_types/       # ReviewType ABC + registry; test_gap.py, infracode.py,
│                           #   golang.py, typescript.py, rust.py, python.py
├── tests/                  # pytest suite
├── vendor/                 # upstream skills + MIT LICENSE, verbatim (never read at runtime)
└── docs/superpowers/       # design spec + implementation plan
```

### Run the tests

```bash
mise run test          # == uv run pytest
```

The suite covers the **pure logic** — target parsing, payload validation and the
comment cap, collation, the posting-mode decision, prompt building, and command
construction. No test runs a real side effect: `git clone`, the `claude` CLI
review, the `codex` CLI review and the `gh api` calls (reading the pull request
context and posting) are never executed in the suite. The shells around them are
tested through injected fake runners, and the true end-to-end path (real pull
request → clone → review → post) is verified only by a manual run.

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

Same pattern in `review_types/` (`test_gap.py`, `infracode.py` and the four
per-language types are worked examples). A review type's `instructions()` must include the JSON-payload output
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

### Vendored upstream material

The four per-language rubrics are distilled from MIT-licensed skills by Jeffallan
([claude-skills](https://github.com/Jeffallan/claude-skills)):

| Review type | Upstream skill |
|---|---|
| `golang` | `skills/golang-pro` |
| `typescript` | `skills/typescript-pro` |
| `rust` | `skills/rust-engineer` |
| `python` | `skills/python-pro` |

Each skill's `SKILL.md` and its five `references/*.md` are vendored verbatim under
`vendor/<skill>/`, with the source URL, pinned commit, skill version, and fetch
date in `vendor/<skill>/PROVENANCE.md`. The MIT `LICENSE` sits once at
`vendor/LICENSE` — one upstream repository, one grant.

Those skills teach an agent to *write* code; a review type needs instructions for
reading someone else's diff, so each rubric is authored work derived from the
upstream material, not a copy of it. The vendored text is the record of what it
derives from.

Nothing there is read at runtime — `pyproject.toml` packages only `src/pr_review`,
so the vendored text never ships in the wheel and `pr-review` gains no dependency
on it or on the network. It is there so the MIT notice travels with the copy, and
so upstream drift is a diff you can read:

```bash
mise run sync-vendor                      # every skill, from main
mise run sync-vendor SKILL=rust-engineer  # just one
mise run sync-vendor REF=v2               # or a tag / sha
```

The vendored tree is its own manifest: the task re-fetches exactly the files
already present, so you add or drop a skill by editing the tree, not the task.
Then read the diff, update the affected `PROVENANCE.md`, and adjust that review
type's rubric if the upstream guidance actually moved. The suite asserts each
rubric's header and its `PROVENANCE.md` name the same commit, so a re-sync that
forgets the rubric fails rather than rotting silently.

### Collation

`DeterministicMergeCollator` merges multiple jobs' payloads into one: bodies under
per-job headers, comments concatenated with the 8-comment cap re-applied, and any
overflow listed in the body. `LLMSynthesisCollator` (in `synthesis.py`) is the default for multi-job runs — a judge LLM de-dupes findings across models, verifies them against the diff, and emits one review. The judge returns the findings it does not post inline as structured data, and pr-review builds the "Other findings not posted as comments" bullets from each finding's first line, so the Recommendation heading reads each finding's own urgency label. `cli.py`'s `build_collator` selects it (or the deterministic merge under `--no-synthesis`).

### Design docs

The full design rationale and the task-by-task build plan live under
`docs/superpowers/`:

- `docs/superpowers/specs/2026-06-26-pr-review-multi-llm-rewrite-design.md`
- `docs/superpowers/plans/2026-06-26-pr-review-multi-llm-rewrite.md`
