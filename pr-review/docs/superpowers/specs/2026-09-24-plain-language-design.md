# pr-review — plain-language review text and attribution (design)

**Date:** 2026-09-24
**Status:** Approved, ready for implementation planning
**Builds on:** cross-model synthesis collation (2026-06-27).
**Glossary:** `CONTEXT.md` (target reader, finding line, Impact / Evidence / Fix, repo term, reader test, blocking / minor problem).
**Decision record:** `docs/adr/0001-plain-language-rewrites-only-blocking-problems.md`.

## Problem

Posted reviews are hard to read without help.
A person should not need a language model to understand what a language model wrote on their pull request.
Phrases from real posted comments include "reconstructed client-side", "the guard is inert" and "route both paths through one check".

A spike on 2026-09-24 measured the problem over 60 comments pr-review posted in the previous 90 days:

| Measure | Before | After one rewrite |
|---|---|---|
| Comments failing the word-and-shape check | 59 / 60 | 28 / 60 |
| Sentences over 25 words | 117 | 30 |
| Negative contractions | 16 | 0 |
| Phrases the reader test flagged | 335 | 166 |
| Comments with no reader flags | 0 | 7 |
| Code blocks changed by the rewrite | – | 0 |
| Total length | – | +23% |

Four lessons from the spike shape this design:

1. Almost every comment fails, so the fix must start in the reviewer and synthesis prompts. A check after the fact is only a safety net.
2. The reader test always finds something. Only problems that stop the reader acting can trigger work.
3. A word list has false positives: "drift" is a real term in drift detection. The list must be short, and it must allow repo terms.
4. A rewrite can change meaning: it changed "root" (a directory with its own Terraform state) to "root module", which is a different thing.

The spike also found reviewers putting prose inside code fences ("new series starts landing"), where a rule that keeps code fences unchanged also keeps the jargon.

## Goal

Every comment and review body pr-review posts can be read and acted on by the **target reader**.
The target reader is an engineer on the team who did not write the code, does not know this part of the system, and may not have English as a first language.

The standards are ISO 24495-1 (plain language: the reader can find, understand and use the text) and the writing rules of ASD-STE100 (Simplified Technical English: sentence length, one idea per sentence, active voice, one term for one thing).
Both are copyrighted, so pr-review paraphrases their rules and cites clause numbers; it does not copy their text.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Target reader | An engineer on the team who does not know this part of the system and may not have English as a first language | This is the reader ASD-STE100 was designed for. Exact technical names stay; slang and metaphor go. |
| Where rules apply | In every review-type prompt and the synthesis prompt, and again in a check after collation | Spike lesson 1: the writer produces the problem. |
| Enforcement | A deterministic word-and-shape check, plus a model reader test | The check catches known problems cheaply and can be unit-tested. The reader test catches new jargon that no list can hold. |
| What triggers a rewrite | Blocking problems only | Spike lesson 2. |
| Rewrites | One batched pass, then the deterministic check runs again | Keeps the cost at two extra model calls per run at most. |
| Problems left after the rewrite | Post anyway; list them on stderr before the confirm prompt | Blocking the post would have stopped nearly every review in the spike. |
| Comment shape | A bold finding line, then `**Impact:**`, optional `**Evidence:**`, then `**Fix:**` | ISO 24495-1 findability: a fixed order and labels let a reader jump to what they need, and Python can check that the labels are present. |
| Repo terms | Keep the word, define it once if the diff shows its meaning, never swap it for another term | Spike lesson 4. |
| Reader-test input | Each comment beside its diff hunk; no tools, no repo access | The reader stands in for a person reading the pull request on GitHub. |
| Batching | One reader-test call for all comments and the body; one rewrite call for all comments with a blocking problem | Two calls at most, whatever the comment count. The 8-comment cap limits the risk of one comment's context affecting another's verdict. |
| Review stats | Moved into a collapsed "How this review was made" `<details>` block at the end of the body, on every run; not checked | Stats, review types and failed jobs describe how pr-review works, not the pull request. |
| Model attribution | A `<sub>` footer at the end of each comment, written by code, not by a model | The reader needs the finding first. Code keeps the format the same every run. |

## Comment shape

~~~markdown
**`DEPLOY_REGION` is not set in any environment file, so the deploy task cannot run.**

**Impact:** Every `deploy` run stops at its first check, with the error `DEPLOY_REGION is not set`.

**Evidence:** `load_settings()` requires the variable (`src/deploy/settings.py:42`). The variable is set only in `tests/fixtures/`.

**Fix:** Set the variable in each environment's `mise.toml`:

```toml
[env]
DEPLOY_REGION = "ap-southeast-2"
```
~~~

- **Finding line** (required): one bold sentence that says what is wrong. There is no `Problem:` label; the finding line is the problem.
- **Urgency:** a review type with a severity ladder starts the finding line with a plain phrase for the level, never the ladder's own name: block is "Fix before merge:", request-changes is "Change before merge:", follow-up is "Fix in a follow-up:", and minor is "Optional:". For example: `**Fix before merge: `DEPLOY_REGION` is not set in any environment file, so the deploy task cannot run.**`. The phrases live in `rules.json`.
- **Impact** (required): what breaks, and when.
- **Evidence** (optional): how the reviewer knows. Leave it out when the finding line says everything, for example "no test calls `seal()` with an empty key".
- **Fix** (required): what to change. Code goes here, and only here.
- **test-gap:** the gap is the finding line. Impact is what could break without anyone noticing. Fix is the test sketch followed by the expected result, which replaces the old `Expected:` line.
- The attribution footer (see **Attribution**) goes in a `<sub>` line after Fix. Code adds it after the plain-language stage, so the stage never sees it.

## Review body shape

1. **Recommendation heading**, written by code (see **Recommendation**).
2. **Verdict:** one or two plain sentences that say what must change before merging, if anything, and what can wait.
3. Any out-of-scope notes the review type allows, written to the same rules.
4. **Overflow findings** (above the 8-comment cap): a bullet for each, with the finding line and `path:line`. A bare `path:line` is not allowed.
5. `<details><summary>How this review was made</summary> … </details>`, on every run (see **Attribution**). Failed jobs are listed here, not in a line in the body.

## Writing rules

The rules go in one place and are rendered into every prompt.
Each rule names its source.

1. Write for the target reader. (ISO 24495-1, principle: the reader gets what they need)
2. Put the most important information first: finding line, then Impact, then Evidence, then Fix. (ISO 24495-1, principle: the reader can find what they need)
3. Keep one idea in each sentence. (ASD-STE100, Sentences)
4. Keep sentences short. Most are under 20 words. Split a sentence over 25 words unless it is a list of paths or a quoted message. Never write one over 35 words. (ASD-STE100: 20 words for procedures, 25 for descriptions)
5. Use the active voice, and say who or what does the action. (ASD-STE100, Verbs)
6. Write negatives in full: "does not", "cannot", never "doesn't" or "can't". (ISO 24495-1)
7. Use literal words. No metaphor, no programmer slang. Say what happens: "the alert does not fire", not "the guard is inert". (ISO 24495-1, principle: the reader can understand what they find)
8. Use one term for one thing. Keep the repository's own words, and define a repo term once, in a few words, if the diff shows what it means. Never replace a term with a similar general one. (ASD-STE100, Words)
9. Keep exact technical names: identifiers, commands, file paths, product names, and real engineering terms such as "state lock". Put code names in backticks.
10. Use code fences for code, commands and command output only. Never put explanation inside a fence.
11. Each comment must make sense alone. Do not refer to "the above", another comment, or a term only defined elsewhere.

Rules cite a standard by section name, not clause number.
The implementation must not add clause numbers that nobody has checked against the published text.

## Architecture

### New package: `pr_review/plain_language/`

| File | Purpose |
|---|---|
| `rules.json` | The only list of words, thresholds and labels. The check reads it, and the prompt block is rendered from it. |
| `rules.py` | Loads `rules.json`; renders the "How to write" block and the comment-shape block for the prompts. |
| `check.py` | Deterministic check. Pure functions: `check_comment(body) -> Problems` and `check_body(body) -> Problems`. |
| `reader.py` | Builds the reader-test prompt and parses its verdicts. |
| `rewrite.py` | Builds the rewrite prompt, parses the result, and applies the guards. |
| `stage.py` | `PlainLanguageStage.apply(payload, hunks) -> StageResult`, which runs check, reader test, rewrite and a second check. |

`rules.json` starts with:

- `blocking_words`: regular expressions, each with a replacement hint. The seed list comes from the spike's confirmed hits and common programmer slang, with repo-term false positives removed ("drift" is out; "silently", "gated", "blast radius", "happy path", "swallow", "surface" as a verb, "bite" and "load-bearing" are in). The implementation plan lists the full seed list for review.
- `sentence_minor_words: 25`, `sentence_blocking_words: 35`.
- `labels: {"impact": "Impact", "evidence": "Evidence", "fix": "Fix"}`, `required: ["impact", "fix"]`.

### Deterministic check

Before counting, it removes fenced code and inline code. The attribution footer and the "How this review was made" block are added after the stage, so the check never sees them.

| Problem | Level |
|---|---|
| Negative contraction (`n't`, `n’t`) | Blocking |
| Word or phrase from `blocking_words` | Blocking |
| Sentence over 35 words | Blocking |
| No bold finding line as the first line | Blocking |
| Missing `**Impact:**` or `**Fix:**` | Blocking |
| Sentence of 26 to 35 words | Minor |

The body gets the same word, contraction and sentence checks, but not the label checks.

### Reader test

One model call per run. Input:

- the target-reader description;
- for each comment, its index, `path:line`, body and **diff hunk**: the hunk from `git diff <base>...HEAD` that contains the anchor line, cut to about 40 lines around it;
- the review body.

The call returns JSON:

```json
{
  "comments": [
    {"index": 0,
     "what_wrong": "...", "what_breaks": "...", "what_to_change": "...",
     "blocking": ["phrase — why the reader could not act"],
     "minor": ["phrase — why it was harder to read"]}
  ],
  "body": {"what_to_do_before_merge": "...", "blocking": [], "minor": []}
}
```

A problem is **blocking** when the reader could not answer one of the three questions, or had to guess what a word means to answer it.
Everything else is **minor**.

### Rewrite

One model call, only for the comments with a blocking problem, and for the body if it has one.
The prompt contains the writing rules, the diff hunk, the original text, and the blocking problems from both checks, quoted.
The rewrite may define a repo term from the diff. It may not swap terms or add facts.

Guards, checked in code for each rewritten comment:

- the fenced code blocks are byte-identical, in the same order;
- every inline code span in the original is still present;
- `path`, `line` and `side` are unchanged (they are not in the rewrite's output at all; the stage copies them from the original).

If a guard fails, that comment keeps its original body, and the failure is reported on stderr.
Then the deterministic check runs again over the result.
The reader test does not run again.

### Stage result and reporting

`StageResult` holds the final payload and, for each comment, the problems that are left.
Before the post or confirm prompt, `cli.main` prints this to stderr:

```
pr-review: plain language: 3 of 6 comments rewritten; 2 still have problems:
  src/deploy/settings.py:12  minor: sentence of 31 words ("The three services that read ...")
  README.md:199               blocking: "happy path" (rewrite kept it)
```

### Where it runs

Collation runs, then the stage, then output.
The stage needs the checkout to read diff hunks, so `cli.main` runs it inside the `try` block, before `cleanup(checkout)`.
It runs whether collation was synthesis, the deterministic merge or a single job.

### Model runner

The reader test and the rewrite return JSON, not a `Payload`.
`reviewers/_run.py` gains `run_cli_json(cmd_prefix, build_prompt, *, workdir, runner) -> dict`, which follows the same contract as `run_cli_payload`: the file the agent was told to write is the result, a non-zero exit is reported only when the file is missing or cannot be parsed, and the temporary file is always removed.
`run_cli_payload` is rebuilt on top of it.

### Failure

| Failure | Result |
|---|---|
| Reader-test call errors or returns bad JSON | The rewrite runs on deterministic problems only; a warning goes to stderr. |
| Rewrite call errors or returns bad JSON | The payload is posted without rewrites; a warning goes to stderr. |
| One rewritten comment fails a guard | That comment keeps its original body. |

The stage can never stop a review from being produced.

### CLI

- `--no-plain-language` turns off the reader test and the rewrite. The deterministic check still runs and reports, because it costs nothing.
- `--plain-language-model AGENT[=MODEL]` sets the model for the reader test and the rewrite. It defaults to the value of `--synthesis-model`.

### Prompt changes

- `review_types/*`: the "Each inline comment must be self-contained" section is replaced by the rendered writing rules and comment shape. The type-specific content rules stay (test-gap's sketch requirement, the severity ladders).
- `synthesis.py`: the rendered block is added. The payload example uses the new shape. The `[N models: …]` / `[single-source: …]` prefix is removed from the instructions, and the judge returns `sources` for each comment (see **Attribution**). The judge no longer writes a `## Review stats` section.
- `collate.DeterministicMergeCollator`: the overflow list uses finding lines (it already does, via `_first_line`), and its heading becomes "Other findings not posted as comments".

## Testing

Following `CLAUDE.md`: no model or subprocess runs in the suite.

- **test_plain_language_check.py**: each blocking and minor problem is found; code fences and inline code are excluded; before/after fixtures written in the style of the spike's pairs, with invented code and paths, not text copied from reviewed repositories (a "before" fails, an "after" with no problems passes); repo terms such as "drift" and "root" pass.
- **test_plain_language_rules.py**: `rules.json` loads; the rendered block names every label and threshold; every registered review type's `instructions()` contains the rendered block (so a new type cannot skip it); the synthesis prompt contains it.
- **test_plain_language_stage.py**, with a fake runner:
  - no blocking problems means no rewrite call;
  - only comments with blocking problems are sent for rewrite;
  - a rewrite that changes a code fence or drops an inline code span keeps the original;
  - an error from the reader test or the rewrite falls back as the failure table says;
  - the second deterministic check runs after the rewrite;
  - a single-job payload goes through the stage;
  - `path`, `line` and `side` never change.
- **test_run.py**: `run_cli_json` follows the same contract tests as `run_cli_payload`.
- **test_cli.py**: `--no-plain-language` and `--plain-language-model` parsing, and the default that follows `--synthesis-model`.
- **Diff hunks**: extracting a hunk from a fixed diff text is a pure function and is unit-tested; running `git diff` is a thin shell, run through a fake runner.
- `CLAUDE.md`'s test walkthrough is updated in the same change.

A manual check after implementation: run pr-review on one of the spike's pull requests and compare the posted text with the spike's "before".

## Attribution

Model attribution is a detail of how pr-review works. It must not be the first thing the reader sees.

### Sources

A **source** is one job's agent, model and review type: `Source(agent, model, review_type)`.
`Comment` gains `sources: list[Source]`. It is used only inside pr-review: `Comment.to_dict()`, which builds the GitHub post, leaves it out, and reviewers never write it.

- **Single job and deterministic merge:** the orchestrator gives each comment the source of the job that produced it.
- **Synthesis:** each comment in the judge's JSON gains `"sources": ["<label>", …]`. The labels are the exact source labels used in "Findings to consolidate". Code maps each label back to its job and drops any label it does not know. If no known label is left, the footer says `Found by pr-review` and a warning goes to stderr. Code never guesses a source.

### Footer

`attribution(sources) -> str` is a pure function. It lists agent names, and adds the model only when one agent appears more than once:

```
<sub>Found by 2 models: claude, codex</sub>
<sub>Found by 2 models: claude (claude-opus-5), claude (claude-sonnet-5)</sub>
<sub>Found by 1 model: claude</sub>
```

The footer appears on every path, including single-job runs, so the reader always knows a model wrote the comment.
It does not name the review type.
Code appends it as the last step before output, after the plain-language stage.
Overflow bullets in the body get no footer.

### "How this review was made"

A collapsed `<details>` block at the end of the body, on every run, built by code from the run's data:

- a table with one row for each job: agent, model, review type, and whether the job succeeded or failed;
- for each job, the number of findings it raised and the number that were posted, counted by code from each comment's sources;
- when synthesis ran: the synthesis model, and how many posted findings two or more models raised;
- when the plain-language stage ran: its model, and the number of comments it rewrote.

The judge returns only `sources` for each comment. Code counts everything else, so the numbers do not depend on the model.
This block replaces the "⚠️ N review job(s) failed" line that `orchestrator.run_reviews` adds to the body today.

### Tests

- **test_attribution.py**: `attribution()` for one source, two agents, and one agent with two models; the details block for single-job, deterministic-merge, synthesis and partial-failure runs.
- **test_orchestrator.py**: each comment has its job's source.
- **test_synthesis.py**: judge labels map back to jobs; an unknown label is dropped; no known label gives `Found by pr-review` and a warning; the prompt no longer asks for a prefix.
- **test_payload.py**: `to_dict()` leaves out `sources`.

## Recommendation

Added 2026-09-29, after the first reviews posted with this design.

A reader should see at once whether a pull request can merge.
The body starts with a heading that code writes:

| State | Heading | When |
|---|---|---|
| red | `## Recommendation: 🔴 fix before merging` | any posted finding is "Fix before merge" |
| yellow | `## Recommendation: 🟡 merge after changes` | no "Fix before merge", and at least one posted finding is "Change before merge" or has no recognised urgency phrase |
| green | `## Recommendation: 🟢 merge as it is` | every posted finding is "Fix in a follow-up" or "Optional", or there are none |

- **Code decides, not a model.** `recommend(payload, *, failed_jobs, total_jobs)` reads the urgency phrase at the start of every posted finding: each comment's finding line, each reply's finding line, and each bullet in the body's "Other findings not posted as comments" and "Other replies not posted" lists. The most severe state wins.
- **A finding with no recognised phrase counts as "Change before merge".** test-gap has no severity ladder, so its findings land here. A missing phrase can raise the state but never lower it.
- **Findings the context filter dropped do not count;** they are not posted.
- **A failed job is named in the heading:** `## Recommendation: 🟢 merge as it is (1 of 2 review jobs failed)`. Failures in the context filter or the plain-language stage do not change the heading; they do not change what was found.
- The state names and emoji live in `rules.json`.
- The heading is added by `finalize`, after the plain-language stage, so the stage never checks or rewrites it.
- The writing rules tell the model the mapping, and tell it not to write its own recommendation heading; the model writes only the sentences under it.

### Tests

- **test_recommendation.py**: each state; the most severe finding wins; an unphrased finding gives yellow; overflow bullets and replies count; no findings gives green; the failed-jobs note.
- **test_attribution.py**: `finalize` puts the heading first.

## Out of scope

- Using stacked pull requests and existing comments as context.
- A controlled STE dictionary. The word list bans known problems; it does not restrict the reader to approved words.
- Checking the terminal output that pr-review prints for itself.
