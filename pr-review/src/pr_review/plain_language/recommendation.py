"""The Recommendation heading, worked out from the findings that were posted."""
from __future__ import annotations

import re

from pr_review.payload import Payload
from pr_review.plain_language.rules import load_rules

_OVERFLOW_HEADINGS = ("## Other findings not posted as comments", "## Other replies not posted")

_BULLET_PREFIX = re.compile(r"^(?:`[^`]*`\s+—\s+)?\[?\*{0,2}")


def _finding_lines(payload: Payload) -> list[str]:
    lines = [u.body.strip().splitlines()[0] for u in [*payload.comments, *payload.replies] if u.body.strip()]
    in_overflow = False
    for line in payload.body.splitlines():
        if line.startswith("## "):
            in_overflow = line.strip() in _OVERFLOW_HEADINGS
        elif in_overflow and line.startswith("- "):
            lines.append(line[2:])
    return lines


def _level(line: str, urgency: dict[str, str]) -> str:
    text = _BULLET_PREFIX.sub("", line.strip()).strip()
    for level, phrase in urgency.items():
        if text.startswith(f"{phrase}:"):
            return level
    # A finding with no phrase can raise the recommendation, never lower it.
    return "request-changes"


def recommend(payload: Payload, *, failed_jobs: int = 0, total_jobs: int = 0) -> str:
    rules = load_rules()
    levels = {_level(line, rules.urgency) for line in _finding_lines(payload)}
    state = "red" if "block" in levels else "yellow" if "request-changes" in levels else "green"
    emoji, text = rules.recommendation[state]
    note = f" ({failed_jobs} of {total_jobs} review jobs failed)" if failed_jobs else ""
    return f"## Recommendation: {emoji} {text}{note}"
