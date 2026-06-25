"""Collate one-or-more review payloads into a single payload."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pr_review.payload import MAX_INLINE_COMMENTS, Comment, Payload, cap_comments

Job = tuple[str, str, Payload]  # (reviewer_name, type_name, payload)


def _first_line(text: str) -> str:
    stripped = text.strip()
    return stripped.splitlines()[0] if stripped else ""


class Collator(ABC):
    @abstractmethod
    def collate(self, jobs: list[Job]) -> Payload:
        """Merge review jobs into a single payload."""


class DeterministicMergeCollator(Collator):
    def collate(self, jobs: list[Job]) -> Payload:
        if not jobs:
            return Payload(body="_No reviews were produced._", comments=[])
        if len(jobs) == 1:
            return jobs[0][2]

        ordered = sorted(jobs, key=lambda j: (j[0], j[1]))
        body_parts: list[str] = []
        all_comments: list[Comment] = []
        for reviewer, rtype, payload in ordered:
            body_parts.append(f"## {rtype} — {reviewer}\n\n{payload.body}")
            all_comments.extend(payload.comments)

        kept, overflow = cap_comments(all_comments, MAX_INLINE_COMMENTS)
        body = "\n\n---\n\n".join(body_parts)
        if overflow:
            extra = "\n".join(
                f"- `{c.path}:{c.line}` — {_first_line(c.body)}" for c in overflow
            )
            body += "\n\n---\n\n## Additional coverage gaps not posted inline\n\n" + extra
        return Payload(body=body, comments=kept)
