# pr-review — pull request context (design)

**Date:** 2026-09-24
**Status:** Approved, ready for implementation planning
**Builds on:** plain-language review text and attribution (2026-09-24).
**Glossary:** `CONTEXT.md` (pull request context, stack, later pull request, discussion, context filter).
**Decision record:** `docs/adr/0002-post-replies-in-threads-not-atomically.md`.

## Problem

pr-review reviews a diff and nothing else.
`reviewers/_run.py:_build_context` gives a reviewer the repository, the pull request number, the base commit and the payload path.
Nothing fetches the pull request's description, its discussion, its linked issues or the other pull requests in its stack.
The synthesis judge sees none of it either.

On one reviewed pull request, the first of a six-deep stack, the author went through every finding pr-review posted and answered each one.
Their answers fell into four groups:

1. **Done later in the stack:** the next pull request, or one further up, already makes the change.
2. **Deliberate, and explained in the description or a linked ADR:** the finding called a design choice a gap.
3. **Worth a follow-up.**
4. **Worth fixing now.**

Only group 4 was useful. The author's own summary was that pr-review did not have the product document, the related issues or the other pull requests in the stack, so many of its comments missed the point.
The description of that pull request already had the stack map, the linked ADRs and the tracking issue.

## Goal

pr-review knows what the people on the pull request know before it posts: the description, the linked GitHub issues, the discussion so far, and what the other pull requests in the stack change.
A finding that a later pull request fixes, that the discussion already raised, or that the author has answered or deferred is not posted.
A finding that proves the author's answer wrong is posted as a reply to that answer.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Sources | The description, the discussion, the stack, and GitHub issues linked from the description | Linear issues and outside documents need a second system and credentials. The description often summarises them. |
| How context is used | Reviewers get it before they review, **and** a context filter checks every finding afterwards | Reviewers ignore context they are only told about; the filter can be tested. |
| Reading later code | Every pull request in the stack is fetched into the clone as `refs/stack/<n>`; the filter runs as an agent with tools | The filter checks real code, not a description of it, and can name the pull request that fixed a finding. |
| Closed-unmerged pull requests | Fetched, but never count as a fix | Their code will not land. |
| Author answers | Drop the finding unless the code proves the answer wrong. A "deliberate" or "deferred" answer drops it unless it is a correctness or security bug with evidence in the code | Respects the author's decisions, and still catches "pretty sure this is used later" when it is not. |
| Who is "the author" | The pull request author's login, including agent replies posted under it | Other people's replies count as "already raised", not as a decision. |
| A finding that disputes an answer | A reply in the answer's review thread | The conversation stays in one place. See ADR 0002. |
| Reply cap | 3, separate from the 8 inline comments | A reply exists only when an answer was proven wrong, so replies should be rare and important. |
| Posting order | The review, then each reply | See **Posting**. |
| Reviewer input | A context file in `.git/pr-review/`, plus a short summary in the prompt | Keeps prompts short; reviewers look things up when needed. |
| Stack discovery | GitHub's native stack first, then the base-branch chain | Most stacks made before the stacked pull requests preview are chains of base branches. |
| Dropped findings | Listed in the collapsed "How this review was made" block, with the reason and a link | The author can check the filter's reasoning without re-running pr-review. |

## Pull request context

### What is gathered

A new module, `pr_review/context.py`, gathers the context after the clone and before the reviewers run.

| Part | Source |
|---|---|
| Description | `gh api repos/{o}/{r}/pulls/{n}`: `title`, `body`, `user.login` |
| Linked issues | `#N` references and `closes` / `fixes` / `resolves #N` keywords in the description. Each one is fetched with `gh api repos/{o}/{r}/issues/{N}`, and kept only if it is an issue and not a pull request. |
| Discussion: issue comments | `gh api --paginate repos/{o}/{r}/issues/{n}/comments` |
| Discussion: review bodies | `gh api --paginate repos/{o}/{r}/pulls/{n}/reviews` (bodies that are not empty) |
| Discussion: review threads | `gh api --paginate repos/{o}/{r}/pulls/{n}/comments`, grouped by `in_reply_to_id` into threads |
| Stack | See **Stack discovery** |

Every discussion entry records its `id`, `html_url`, author login, `is_author` (the login matches the pull request author), creation time and body.
Review threads also record `path` and `line`, so the filter can match a thread to a finding on the same lines.
pr-review's own earlier reviews are part of the discussion, so running pr-review twice does not post the same finding twice.

### Stack discovery

1. **Native stack.** `pulls/{n}` returns `stack: {number, position, size, base}` for a pull request in a GitHub stack. GraphQL `repository.pullRequest(number).stack.entries { position pullRequest { number state title body headRefOid } }` gives every entry in order.
2. **Base-branch chain**, only when there is no native stack.
   - **Down:** follow `base.ref` to the pull request whose head is that branch, until the base is the default branch.
   - **Up:** `gh api "repos/{o}/{r}/pulls?base=<head.ref>&state=all"` lists the pull requests built on this one; repeat for each.
   - When a pull request has more than one built on it, the result is a tree, and every branch of it is kept.
   - The walk stops at a depth of 10 in each direction.
3. Each stack entry records its number, title, body, state (`open`, `merged` or `closed`), head SHA, and whether it is **earlier** or **later** than the reviewed pull request.

`discover_stack(pr, fetch) -> Stack` is a pure function over API responses, with `fetch` injected, so every case is unit-tested with fake responses.

### The clone

`checkout.clone_pr` gains an optional list of stack pull request numbers.
For each, it runs `git fetch --filter=blob:none origin +refs/pull/<n>/head:refs/stack/<n>`, the same way it fetches the reviewed pull request today.
`refs/pull/<n>/head` survives a merge and a deleted branch, so merged pull requests in the stack still resolve.

### The context file

Code writes `.git/pr-review/pr-context.md` in the clone.
It is inside `.git`, so no reviewer's search of the working tree finds it by accident.
It contains, in this order:

1. The stack map: each pull request's position, number, title, state and ref, with the reviewed one marked.
2. The description.
3. The linked issues: title, state and body.
4. The discussion, grouped by thread. Each entry shows its author, marked **(author)** where it applies, its link and its body.
5. For each other pull request in the stack: its title and description.

### Reviewer prompts

`_build_context` adds:

- the stack map and the description;
- the path of the context file;
- two instructions:
  - "Before you report that something is missing, check the later pull requests in the stack (`git show refs/stack/<n>:<path>`, `git diff HEAD refs/stack/<n>`)."
  - "Before you report anything, read the discussion in the context file. Do not report what it already raises, or what the author has already answered."

The synthesis judge gets the same additions.

## Context filter

### Where it runs

The pipeline becomes: collation, then the context filter, then the plain-language stage, then attribution, then output.
The filter runs on every path, including a single job.
It is skipped when there is no context, for example when every fetch failed or `--no-context` is set.

### How it runs

One agent call per run, in the clone, with the same tools the reviewers have.
Its input: every finding (index, `path:line`, body), the context file, and the list of stack refs with their states.
It returns JSON:

```json
{"verdicts": [
  {"index": 0, "verdict": "keep"},
  {"index": 1, "verdict": "drop", "reason": "fixed-later",
   "pull_request": 42, "evidence": "refs/stack/42:infra/backend.tf sets use_lockfile = true"},
  {"index": 2, "verdict": "drop", "reason": "already-raised", "link": "https://github.com/…#discussion_r1"},
  {"index": 3, "verdict": "drop", "reason": "answered", "link": "https://github.com/…#discussion_r2"},
  {"index": 4, "verdict": "reply", "in_reply_to": 123456789,
   "body": "<the finding, rewritten as a reply to the answer>"}
]}
```

### Verdicts

| Verdict | When | What happens |
|---|---|---|
| `keep` | None of the cases below apply. | The finding is posted. |
| `drop` `fixed-later` | The code at a **later** pull request's head fixes it, and that pull request is not closed without merging. | Listed in the details block with the pull request number and the evidence. |
| `drop` `already-raised` | The discussion already raises the same problem, from anyone, including an earlier pr-review run. | Listed in the details block with a link. |
| `drop` `answered` | The author said it is deliberate or will be done later, and it is not a correctness or security bug with evidence in the code. The author also said it is done elsewhere, and the filter confirmed that. | Listed in the details block with a link. |
| `reply` | The author answered, and the code proves the answer wrong. For example, the author said "used later in the stack", and no later pull request uses it. | Posted as a reply in the thread of the author's comment. |

Code checks every verdict before using it:

- An `index` that is not a real finding is ignored.
- A finding with no verdict is kept.
- A `fixed-later` verdict naming a pull request that is not later in the stack, or that is closed without merging, is changed to `keep`.
- A `reply` whose `in_reply_to` is not a review-thread comment by the author is changed to `keep`. The finding is posted as a new comment instead, with a link to the answer in its Evidence. Issue comments and review bodies have no threads on GitHub, so an answer given there cannot be replied to.
- Beyond 3 replies, the rest go to the body's overflow list, each with a link to its thread.

### Failure

| Failure | Result |
|---|---|
| A context fetch fails | That part is left out, and a warning goes to stderr. The run continues. |
| A stack ref cannot be fetched | That pull request is left out of the stack. It cannot be named as a fix. |
| The filter call fails or returns bad JSON | Every finding is kept, and a warning goes to stderr. |

Gathering context and filtering can never stop a review from being produced.

## Replies and posting

### Payload

`Payload` gains `replies: list[Reply]`, where `Reply(in_reply_to: int, body: str, sources: list[Source], answer_id: int | None)`.
GitHub accepts a reply only to a thread's top-level comment, so `in_reply_to` is the root of the author's thread, and `answer_id` is the author's entry the reply answers (the root itself, or a reply in that thread).
Replies go through the plain-language stage and get the attribution footer, like comments.
The reader test sees each reply beside the answer it replies to, instead of a diff hunk.

### Posting

The review payload file stays exactly as today: the JSON body of `POST pulls/{n}/reviews`, so the existing retry hint still works.
Each reply gets its own file, `pr-review-reply.<in_reply_to>.json`, holding `{"body": …}`.

1. Post the review. If it fails, post no replies; keep every file, and print the retry commands for all of them.
2. Post each reply with `gh api repos/{o}/{r}/pulls/{n}/comments/{in_reply_to}/replies --method POST --input <file>`. A failed reply does not stop the others.
3. Delete the file of each part that posted. Keep the files that did not, and print one retry command for each.
4. Exit 0 only if everything posted. Otherwise exit 1, and say what posted and what did not: `pr-review: review posted; 1 of 2 replies failed: <reason>`.

The confirm prompt counts both: `Post this review with 5 inline comment(s) and 1 reply?`

### "How this review was made"

The block from the plain-language design gains:

- **Stack:** "position 1 of 6", with a link to each pull request, or "not part of a stack".
- **Context loaded:** the description, N linked issues, and N discussion entries; and which parts failed to load.
- **Findings not posted:** one line for each dropped finding, with its finding line, the reason and a link.
  For example: "Fixed in #42 (`infra/backend.tf`)", "Already raised in [this thread](…)", or "Answered by the author in [this reply](…)".

## CLI

- `--no-context` skips gathering and the filter. Reviewers see only the diff, as today.
- `--no-context-filter` gives reviewers the context but skips the filter.
- `--context-filter-model AGENT[=MODEL]` sets the filter's model. It defaults to the value of `--synthesis-model`.

## Testing

Following `CLAUDE.md`: no network and no model runs in the suite.

- **test_context.py**
  - `discover_stack` with fake responses: a native stack; a chain with no native stack; a tree; the depth limit; a stack entry that is merged, and one that is closed without merging; a pull request not in any stack.
  - Linked-issue parsing: `#N` and the `closes`/`fixes`/`resolves` keywords; a `#N` that is a pull request is left out.
  - Discussion grouping into threads, and `is_author` marking, including agent replies under the author's login.
  - Rendering the context file.
  - A failed fetch leaves out only its part.
- **test_checkout.py**: the `refs/stack/<n>` fetch commands.
- **test_reviewers.py**: the prompt includes the stack map, the description, the context file path and both instructions, and leaves them all out when there is no context.
- **test_context_filter.py**, with a fake runner:
  - each verdict is applied;
  - a bad index is ignored; a missing verdict keeps the finding;
  - `fixed-later` naming an earlier or closed-unmerged pull request becomes `keep`;
  - a `reply` to an issue comment or to someone other than the author becomes a new comment with a link;
  - more than 3 replies send the rest to overflow;
  - a failed call keeps every finding.
- **test_output.py**, with a fake runner:
  - the review posts, then each reply;
  - a failed review posts no replies;
  - a failed reply does not stop the others;
  - the files of parts that posted are deleted, and the rest are kept, with one retry command each;
  - the exit code;
  - the confirm prompt counts replies.
- **test_payload.py**: `Reply` serialisation; `replies` are not part of the review's JSON.
- **test_cli.py**: `--no-context`, `--no-context-filter` and `--context-filter-model`, with the default that follows `--synthesis-model`.
- `CLAUDE.md`'s test walkthrough is updated in the same change.

A manual check after implementation: run pr-review on the first pull request of a real stack whose later pull requests fix gaps in the first, and confirm those findings appear under "Findings not posted".

## Out of scope

- Linear issues, product documents and any source outside GitHub.
- Replying to answers given in issue comments or review bodies. GitHub has no threads there, so these become new comments with a link.
- Reviewing the whole stack in one run.
- Resolving or hiding earlier pr-review threads that a later run finds are fixed.

## Known limits

- The collator caps inline comments at 8 before the context filter runs. Findings already moved to the body's overflow list are not filtered, and a comment the filter drops does not free an inline slot for an overflow finding.
- Later stack entries are capped at 10 in total (`MAX_DEPTH`), not only by depth: a wide tree of later pull requests stops at 10 entries even when every branch is shallow.
