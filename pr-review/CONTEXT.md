# pr-review

`pr-review` reviews a GitHub pull request with one or more language models and posts one review whose comments a person can read and act on without further help.

## Language

### Reviews

**Finding**:
One problem a review reports, anchored to a line of the diff and posted as one inline comment.
_Avoid_: issue, gap (except in the test-gap review type), note

**Review type**:
A named set of instructions that decides what a review looks for, such as `test-gap` or `infracode`.
_Avoid_: rubric, mode, check

**Job**:
One reviewer, one model and one review type, run once against the pull request.
_Avoid_: run, pass, task

**Synthesis**:
The step where one model merges the findings of several jobs into one review, removes duplicates and drops findings it cannot confirm in the code.
_Avoid_: judging, consolidation

**Source**:
The agent, model and review type of the job that raised a finding.
_Avoid_: provenance, origin, author

**Attribution footer**:
The small line at the end of a comment that names the models that found it.
_Avoid_: label, tag, badge

**Recommendation**:
The heading at the top of a review that says whether the pull request can merge: fix before merging, merge after changes, or merge as it is. Code works it out from the urgency of the findings that were posted.
_Avoid_: verdict, status, score

### Pull request context

**Pull request context**:
What pr-review knows about a pull request beyond its diff: its description, its discussion, its linked GitHub issues, and the other pull requests in its stack.
_Avoid_: metadata, background, PR info

**Stack**:
An ordered series of pull requests where each one targets the one below it, as GitHub's stacked pull requests define it.
_Avoid_: chain, series, train

**Later pull request**:
A pull request above the reviewed one in its stack, which may fix what the reviewed one leaves out.
_Avoid_: child PR, downstream PR, follow-up PR

**Discussion**:
Everything people and agents have already written on the pull request: comments, review bodies, review threads and their replies.
_Avoid_: conversation, thread, history

**Context filter**:
The step after collation that drops a finding when a later pull request fixes it, when the discussion already raised it, or when the author has answered or deferred it.
_Avoid_: dedupe, suppression, triage

### Plain language

**Target reader**:
An engineer on the team who did not write the code, does not know this part of the system, and may not have English as a first language.
Every sentence pr-review posts is written for this person.
_Avoid_: audience, user, the author

**Finding line**:
The first line of a comment: one bold sentence that says what is wrong.
_Avoid_: title, headline, summary, problem

**Impact**:
The labelled part of a comment that says what breaks, and when.
_Avoid_: consequence, risk, severity

**Evidence**:
The optional labelled part of a comment that shows how the reviewer knows the finding is true.
_Avoid_: proof, reasoning, context

**Fix**:
The labelled part of a comment that says what to change.
_Avoid_: recommendation, suggestion, remedy

**Repo term**:
A word the reviewed repository uses with its own meaning, such as "root" for a directory with its own Terraform state.
A comment keeps the repo's word, defines it once if the diff shows what it means, and never swaps it for a similar general term.
_Avoid_: jargon (a repo term is not jargon), domain word

**Reader test**:
A check where a model plays the target reader, sees each comment beside its diff lines, and must say what is wrong, what breaks and what to change.
_Avoid_: comprehension check, readability score

**Blocking problem**:
A plain-language problem that stops the target reader from acting on a comment, so the comment is rewritten before it is posted.
_Avoid_: error, violation, failure

**Minor problem**:
A plain-language problem that makes a comment harder to read but does not stop the target reader from acting on it; it is reported, not rewritten.
_Avoid_: warning, nit
