"""Drop review comments whose path is not in the PR diff.

GitHub's create-review API returns 422 "Path could not be resolved" and rejects
the whole review when any inline comment names a file outside the PR diff. A
reviewer can do this by suggesting a test in an existing, unchanged file. Move
such a comment to a body bullet so the finding survives and the review posts.
"""
from __future__ import annotations

import subprocess
from dataclasses import replace

from pr_review.collate import _first_line
from pr_review.payload import Comment, Payload

_OVERFLOW_HEADING = "## Other findings not posted as comments"


def changed_paths(workdir: str, base: str, runner=subprocess.run) -> set[str]:
    res = runner(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=workdir, capture_output=True, text=True, check=True,
    )
    return {line for line in (res.stdout or "").splitlines() if line.strip()}


def guard_off_diff(payload: Payload, paths: set[str]) -> tuple[Payload, list[Comment]]:
    kept: list[Comment] = []
    dropped: list[Comment] = []
    for c in payload.comments:
        (kept if c.path in paths else dropped).append(c)
    if not dropped:
        return payload, []
    bullets = "\n".join(f"- `{c.path}:{c.line}` — {_first_line(c.body)}" for c in dropped)
    body = payload.body.rstrip()
    if _OVERFLOW_HEADING in body:
        body = f"{body}\n{bullets}"
    else:
        body = f"{body}\n\n---\n\n{_OVERFLOW_HEADING}\n\n{bullets}"
    return replace(payload, body=body, comments=kept), dropped
