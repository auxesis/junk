"""Decide whether to post, render the review, and post via gh."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from enum import Enum

from pr_review.payload import Payload
from pr_review.target import Target
from pr_review import terminal


class PostMode(Enum):
    POST = "post"
    PROMPT = "prompt"
    REVIEW_ONLY = "review_only"


def decide_mode(*, yes: bool, no_post: bool, has_tty: bool) -> PostMode:
    if no_post:
        return PostMode.REVIEW_ONLY
    if yes:
        return PostMode.POST
    if not has_tty:
        return PostMode.REVIEW_ONLY
    return PostMode.PROMPT


def tty_available() -> bool:
    return terminal.can_prompt()


def render(payload: Payload) -> str:
    lines = [payload.body, ""]
    for c in payload.comments:
        lines.append(f"### {c.path}:{c.line}")
        lines.append(c.body)
        lines.append("")
    return "\n".join(lines)


def _run(cmd: Sequence[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=True, text=True, **kw)


def post_review(target: Target, payload: Payload, *, runner=_run) -> None:
    fd, path = tempfile.mkstemp(prefix="pr-review-post.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload.to_json())
        runner(
            ["gh", "api", f"repos/{target.slug}/pulls/{target.number}/reviews",
             "--method", "POST", "--input", path]
        )
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _manual_hint(target: Target) -> str:
    return (
        f"pr-review: not posted. To post manually:\n"
        f"  gh api repos/{target.slug}/pulls/{target.number}/reviews "
        f"--method POST --input <payload.json>"
    )


def _confirm(target: Target, n_comments: int) -> bool:
    io = terminal.open_interactive()
    if io is None:
        return False
    read_line, write, close = io
    try:
        write(
            f"\nPost this review to {target.slug}#{target.number} "
            f"with {n_comments} inline comment(s)? [y/N] "
        )
        reply = read_line().strip().lower()
    finally:
        close()
    return reply in ("y", "yes")


def dispatch(mode: PostMode, target: Target, payload: Payload, *, runner=_run) -> None:
    if mode is PostMode.POST:
        post_review(target, payload, runner=runner)
        print(f"pr-review: posted review to {target.slug}#{target.number}.", file=sys.stderr)
    elif mode is PostMode.PROMPT and _confirm(target, len(payload.comments)):
        post_review(target, payload, runner=runner)
        print(f"pr-review: posted review to {target.slug}#{target.number}.", file=sys.stderr)
    else:
        print(_manual_hint(target), file=sys.stderr)
