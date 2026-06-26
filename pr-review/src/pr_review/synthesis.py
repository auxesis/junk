"""LLM synthesis collation: one judge pass de-dupes and verifies findings."""
from __future__ import annotations

from pr_review.collate import Job

_INSTRUCTIONS = r"""# Synthesis Review

You are consolidating several independent reviews of the SAME pull request,
produced by different models and/or review types. Your job: produce ONE
de-duplicated, verified review. DO NOT POST ANYTHING. Your only side effect is
writing the payload file named in the context above.

## What you are given

Below, under "Findings to consolidate", are the findings from each source,
labelled `<agent> (<model>) [<review-type>]` with a raw count. The same real
issue may appear from multiple sources, worded differently or anchored to
nearby lines.

## What to do

1. Read the diff to ground yourself: `git diff origin/<base>...HEAD` (three-dot =
   exactly the changes on this branch).
2. De-duplicate: merge findings that describe the SAME issue, even when worded
   differently or anchored to slightly different lines. Treat them as one finding.
3. Verify each merged finding against the actual diff/code. DROP any finding you
   cannot substantiate from the code — these are likely hallucinations.
4. Confidence:
   - raised by 2+ models AND verified -> keep; label `[N models: a, b]`.
   - raised by 1 model AND verified -> keep; label `[single-source: <model>]`.
   - raised by 1 model AND not verifiable -> drop.
5. HARD CAP: 8 inline comments (highest-confidence first). List any overflow as a
   bullet list in the body under "## Additional findings not posted inline".

## Stats (REQUIRED)

Include a "## Review stats" section in the body with:
- one row per source: its raw finding count and how many of its findings survived.
- cross-model overlap: how many kept findings were corroborated by 2+ models.

## Output (REQUIRED)

Write the consolidated review to the payload file named in the context above, as
JSON:

  {
    "event": "COMMENT",
    "body": "<verdict + the ## Review stats section + any overflow list>",
    "comments": [
      {"path": "relative/path", "line": N, "side": "RIGHT",
       "body": "[2 models: claude, codex] **<finding>** ..."}
    ]
  }

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number. Then ALSO print the same review to stdout
in readable markdown. Writing the payload file is mandatory even when there are
zero kept findings.
"""


def serialize_findings(jobs: list[Job]) -> str:
    """Render every job's findings as text, grouped and counted per source."""
    blocks: list[str] = []
    for label, rtype, payload in jobs:
        lines = [f"### Source: {label} [{rtype}] — {len(payload.comments)} finding(s)"]
        if payload.body.strip():
            lines.append(f"Summary: {payload.body.strip()}")
        for c in payload.comments:
            lines.append(f"- {c.path}:{c.line} — {c.body}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_synthesis_prompt(
    *, owner: str, repo: str, number: int, base: str, payload_path: str, findings: str,
) -> str:
    context = (
        "You are consolidating GitHub pull request reviews. Context for this run:\n"
        f"- Repository: {owner}/{repo}\n"
        f"- PR number: {number}\n"
        f"- Base ref:  origin/{base}\n"
        "- HEAD is ALREADY checked out at the exact code to review. Do not switch branches.\n"
        f"- Payload file to write: {payload_path}\n"
    )
    return f"{context}\n{_INSTRUCTIONS}\n## Findings to consolidate\n\n{findings}\n"
