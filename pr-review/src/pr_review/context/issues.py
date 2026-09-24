"""GitHub issues the description links to (not Linear or other trackers)."""
from __future__ import annotations

import re

from pr_review.context.model import Issue

# A `#` preceded by a word character or `/` is a colour or a URL fragment.
_REF = re.compile(r"(?<![\w/&])#(\d+)\b")


def linked_numbers(body: str, own: int) -> list[int]:
    found: list[int] = []
    for m in _REF.finditer(body or ""):
        n = int(m.group(1))
        if n != own and n not in found:
            found.append(n)
    return found


def load_issues(gh, numbers: list[int]) -> tuple[list[Issue], list[int]]:
    issues: list[Issue] = []
    failed: list[int] = []
    for n in numbers:
        try:
            data = gh.get(f"issues/{n}")
        except Exception:
            failed.append(n)
            continue
        if "pull_request" in data:
            continue
        issues.append(Issue(n, data.get("title", ""), data.get("state", ""), data.get("body") or ""))
    return issues, failed
