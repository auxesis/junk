"""LLM synthesis collation: one judge pass de-dupes and verifies findings."""
from __future__ import annotations

import sys
from collections.abc import Callable

from pr_review.collate import Collator, DeterministicMergeCollator, Job, _first_line
from pr_review.payload import Payload, Source, cap_comments, payload_from_dict
from pr_review.plain_language.rules import writing_rules_block
from pr_review.reviewers._run import run_cli_json

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

1. Read the diff to ground yourself: `git diff <base>...HEAD` (three-dot =
   exactly the changes on this branch).
2. De-duplicate: merge findings that describe the SAME issue, even when worded
   differently or anchored to slightly different lines. Treat them as one finding.
3. Verify each merged finding against the actual diff/code. DROP any finding you
   cannot substantiate from the code — these are likely hallucinations.
4. Keep a finding only if you verified it against the code. A finding raised by
   two or more models is more likely to be real, but verify it too.
5. HARD CAP: 8 inline comments (highest-confidence first). List any overflow as a
   bullet list in the body under "## Other findings not posted as comments".

## Output (REQUIRED)

Write the consolidated review to the payload file named in the context above, as
JSON:

  {
    "event": "COMMENT",
    "body": "<verdict + any overflow list>",
    "comments": [
      {"path": "relative/path", "line": N, "side": "RIGHT",
       "sources": ["<label> [<review-type>]", "..."],
       "body": "**<finding line>**\n\n**Impact:** ...\n\n**Evidence:** ...\n\n**Fix:** ..."}
    ]
  }

"sources" lists every source whose findings this comment merges, each written
exactly as it appears after "### Source: " below, up to but not including " — ".
Do not name models in the comment body; pr-review adds that itself.

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


def _cap_payload(payload: Payload) -> Payload:
    """Enforce the inline-comment cap on a synthesised payload (defensive)."""
    kept, overflow = cap_comments(payload.comments)
    if overflow:
        payload.comments = kept
        payload.body += (
            "\n\n---\n\n## Other findings not posted as comments\n\n"
            + "\n".join(f"- `{c.path}:{c.line}` — {_first_line(c.body)}" for c in overflow)
        )
    return payload


def build_synthesis_prompt(
    *, owner: str, repo: str, number: int, base: str, payload_path: str, findings: str,
    context: str = "",
) -> str:
    run_context = (
        "You are consolidating GitHub pull request reviews. Context for this run:\n"
        f"- Repository: {owner}/{repo}\n"
        f"- PR number: {number}\n"
        f"- Base commit: {base}\n"
        "- HEAD is ALREADY checked out at the exact code to review. Do not switch branches.\n"
        f"- Payload file to write: {payload_path}\n"
    )
    parts = [run_context, context] if context else [run_context]
    return "\n".join(parts) + (
        f"\n{_INSTRUCTIONS}\n{writing_rules_block()}\n## Findings to consolidate\n\n{findings}\n"
    )


def _sources_by_key(jobs: list[Job]) -> dict[str, Source]:
    by_key: dict[str, Source] = {}
    for label, rtype, payload in jobs:
        for c in payload.comments:
            if c.sources:
                by_key[f"{label} [{rtype}]"] = c.sources[0]
                break
    return by_key


def _map_sources(labels: object, by_key: dict[str, Source]) -> list[Source]:
    found: list[Source] = []
    for label in labels if isinstance(labels, list) else []:
        source = by_key.get(label) if isinstance(label, str) else None
        if source is not None and source not in found:
            found.append(source)
    return found


class LLMSynthesisCollator(Collator):
    def __init__(
        self,
        *,
        command: list[str],
        workdir: str,
        owner: str,
        repo: str,
        number: int,
        base: str,
        runner: Callable[..., object] = run_cli_json,
        context: str = "",
    ):
        self._command = command
        self._workdir = workdir
        self._owner = owner
        self._repo = repo
        self._number = number
        self._base = base
        self._runner = runner
        self._context = context
        self.ran = False

    def collate(self, jobs: list[Job]) -> Payload:
        if len(jobs) <= 1:
            return DeterministicMergeCollator().collate(jobs)

        findings = serialize_findings(jobs)

        def build(payload_path: str) -> str:
            return build_synthesis_prompt(
                owner=self._owner, repo=self._repo, number=self._number,
                base=self._base, payload_path=payload_path, findings=findings,
                context=self._context,
            )

        try:
            data = self._runner(self._command, build, workdir=self._workdir)
            payload = payload_from_dict(data)
        except Exception as e:
            print(
                f"pr-review: synthesis failed ({self._command[0]}: {e}); "
                "falling back to the raw merge.",
                file=sys.stderr,
            )
            return DeterministicMergeCollator().collate(jobs)

        by_key = _sources_by_key(jobs)
        raw = data.get("comments")
        raw = raw if isinstance(raw, list) else []
        for i, comment in enumerate(payload.comments):
            entry = raw[i] if i < len(raw) and isinstance(raw[i], dict) else {}
            comment.sources = _map_sources(entry.get("sources"), by_key)
            if not comment.sources:
                print(
                    f"pr-review: synthesis gave no known source for "
                    f"{comment.path}:{comment.line}; its footer will say pr-review.",
                    file=sys.stderr,
                )
        self.ran = True
        return _cap_payload(payload)
