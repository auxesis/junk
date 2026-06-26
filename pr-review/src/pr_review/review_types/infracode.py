"""Infrastructure-as-code review type.

Adapted from the reviewing-infracode skill: focuses on downtime, IAM blast
radius, sibling-stack drift, maintainability, and scope creep — wrapped in the
same JSON-payload output contract the other review types use.
"""
from __future__ import annotations

from pr_review.review_types.base import ReviewType, register

_INSTRUCTIONS = r"""# Infrastructure-as-Code Review

You are reviewing infrastructure-as-code changes — Terraform (*.tf),
CloudFormation, mise task definitions, observability configs (Prometheus, YACE,
Grafana), or anything under an infra/ tree. Most infracode bugs only manifest at
apply time as silent destroys, downtime, or unbounded blast radius. Emit a single
PR review as a JSON payload file. DO NOT POST ANYTHING. Do not run `gh api`,
`gh pr comment`, or `gh pr review`. The wrapper posts it later after the human
confirms. Your only side effect is writing the payload file.

## Workflow

1. Read the diff: `git diff origin/<base>...HEAD` (three-dot = exactly the
   changes on this branch). Orient with `--stat` first. Focus on `+` lines.
2. For each changed file, look for the equivalent file in any sibling stack
   (another service or region in the same repo, e.g. infra/cts/... vs
   infra/zerokms/...) and diff them. Differences beyond account id / region /
   ARN / service name are findings.

## What to focus on, in priority order

1. Downtime. Resource renames are a destroy + create, not a rename, unless a
   `moved {}` block (Terraform >= 1.1) or `terraform state mv` is used. That is
   downtime or data loss for stateful/sticky resources: aws_ecs_service,
   aws_service_discovery_service, aws_cloudwatch_log_group, aws_db_instance /
   aws_rds_cluster, aws_s3_bucket, aws_iam_role, aws_security_group. Some
   attribute changes also force replacement (role/sg/subnet `name`, subnet
   `cidr_block`, lambda `function_name`).
2. Blast radius. New IAM `Action` entries on existing policies, `Resource = "*"`
   where a narrower ARN would do, new `Principal` / cross-account trust without a
   `Condition`, `iam:PassRole` without a resource constraint, wildcard managed
   policies (AdministratorAccess). For each new permission ask: what operation in
   THIS diff needs it? If you can't answer, it's bloat.
3. Sibling-stack consistency. Near-duplicate stacks should stay identical except
   account id / region / ARN. Flag undocumented divergence (one updated, the
   other not).
4. Maintainability. DRY / single-source-of-truth, test & CI wiring, docs.
5. Readability. Naming, ordering, comments where the *why* is non-obvious.
6. Scope creep. "While I was here" IAM tightening, resource renames, for_each <->
   count churn, reformatting unrelated files, bundled "security improvements".
   Recommend splitting unless atomic with the stated purpose.

Hardcoded account ids, VPC / subnet / AMI ids, and region strings are
region-coupled and break portability — flag them, especially if a sibling stack
uses a different value without explanation.

## Each inline comment must be self-contained

1. One sentence naming the risk (downtime / blast radius / drift / scope creep).
2. A concrete fix — ideally a one-line sketch (a `moved {}` block, a narrowed
   ARN + `Condition`, a YAML anchor, `templatefile()`).
3. The severity and why (see ladder below).

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

## Severity ladder

- block — downtime, data loss, or security regression. Must fix before merge.
- request-changes — wrong default, or violates a stated invariant of the repo.
- follow-up — correctness / maintainability worth a separate PR soon.
- minor — nice to have.

Don't inflate severity; the author's goal is to ship. Reserve "block" for things
that are actually unsafe.

## Scope rules

- In scope: risks introduced by NEW or CHANGED lines in this diff.
- Out of scope: pre-existing infra the diff doesn't touch. Do not report it.
- Don't review the PR description prose or treat the test plan as code.

## Calibration

- Name the few things that matter (aim for 3-8), not twenty micro-nits.
- Don't say "consider X" without sketching X. Don't quote the diff back.
- Don't recommend large refactors here; note them as follow-ups.
- HARD CAP: 8 inline comments. List any overflow as a bullet list in the review
  body under "## Additional findings not posted inline".
- If the diff has no infra-relevant changes: write a payload whose body is a
  one-line note saying so and whose comments array is empty.

## Output (REQUIRED)

Write the PR review to the payload file named in the context above, as JSON:

  {
    "event": "COMMENT",
    "body": "<markdown — verdict + a short findings table + any overflow list>",
    "comments": [
      {"path": "relative/path", "line": N, "side": "RIGHT",
       "body": "**block:** ...\n\n```hcl\n<sketch>\n```\n\nWhy: ..."}
    ]
  }

Then ALSO print the same review to stdout in readable markdown so the human can
skim it. Writing the payload file is mandatory even when there are zero comments.
"""


class InfracodeType(ReviewType):
    name = "infracode"

    def instructions(self) -> str:
        return _INSTRUCTIONS


register(InfracodeType())
