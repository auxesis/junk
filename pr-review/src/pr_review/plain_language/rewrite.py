"""One batched rewrite of the comments a reader could not act on."""
from __future__ import annotations

from dataclasses import dataclass

from pr_review.payload import Comment
from pr_review.plain_language.check import FENCE, INLINE_CODE
from pr_review.plain_language.rules import writing_rules_block

_INSTRUCTIONS = """# Plain-language rewrite

Rewrite each comment below, and the review body if it is included, so the reader
described in the writing rules can act on it. Fix every listed problem.

- Keep the meaning. Do not add facts that are not in the original or its diff lines.
- Keep every fenced code block exactly as it is, in the same order.
- Keep every `inline code` span.
- Keep the repository's own terms. You may define a term once, in a few words, if
  the diff lines show what it means. Never replace it with a different term.
- Keep the shape: the bold finding line first, then **Impact:**, an optional
  **Evidence:**, then **Fix:**.

Write ONLY this JSON to the output file:
{"comments": [{"index": 0, "body": "<the rewritten comment>"}], "body": "<the rewritten review body, or null>"}
"""


@dataclass
class RewriteItem:
    index: int
    comment: Comment
    hunk: str
    problems: list[str]


def build_rewrite_prompt(
    *, payload_path: str, items: list[RewriteItem], body: str, body_problems: list[str]
) -> str:
    parts = [f"Output file to write: {payload_path}\n", _INSTRUCTIONS, writing_rules_block(),
             "## Comments to rewrite\n"]
    for item in items:
        problems = "\n".join(f"- {p}" for p in item.problems)
        parts.append(
            f"### Comment {item.index}: {item.comment.path}:{item.comment.line}\n\n"
            f"Problems:\n{problems}\n\n"
            f"Diff lines:\n```diff\n{item.hunk or '(no diff lines found)'}\n```\n\n"
            f"Comment:\n<<<\n{item.comment.body}\n>>>\n"
        )
    if body_problems:
        problems = "\n".join(f"- {p}" for p in body_problems)
        parts.append(f"## Review body to rewrite\n\nProblems:\n{problems}\n\n<<<\n{body}\n>>>\n")
    else:
        parts.append("## Review body\n\nThe review body does not need rewriting; write null for it.\n")
    return "\n".join(parts)


def parse_rewrite_result(data: object) -> tuple[dict[int, str], str | None]:
    if not isinstance(data, dict):
        raise ValueError("rewrite result must be a JSON object")
    bodies: dict[int, str] = {}
    raw = data.get("comments")
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and isinstance(item.get("index"), int) and isinstance(item.get("body"), str):
            bodies[item["index"]] = item["body"]
    body = data.get("body")
    return bodies, body if isinstance(body, str) else None


def guard(original: str, rewritten: str) -> str | None:
    if not rewritten.strip():
        return "is empty"
    if [m.group(0) for m in FENCE.finditer(original)] != [m.group(0) for m in FENCE.finditer(rewritten)]:
        return "changed a code block"
    outside = FENCE.sub("", rewritten)
    for span in INLINE_CODE.findall(FENCE.sub("", original)):
        if span not in outside:
            return f"dropped {span}"
    return None
