"""Decide whether to post, render the review, and post via gh."""
from __future__ import annotations

import os
import shutil
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


def _render_with_glow(markdown: str, run=subprocess.run) -> bool:
    """Pretty-render the markdown via `glow -p -w 100`; True on success."""
    fd, path = tempfile.mkstemp(prefix="pr-review-render.", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(markdown)
        return run(["glow", "-p", "-w", "100", path]).returncode == 0
    except OSError:
        return False
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def show_review(payload: Payload, *, which=shutil.which, run=subprocess.run) -> None:
    """Show the review to the human: via `glow` if it's on PATH, else plain text."""
    markdown = render(payload)
    if which("glow") and _render_with_glow(markdown, run):
        return
    print(markdown)


def _run(cmd: Sequence[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=True, text=True, **kw)


def _write_payload_file(payload: Payload) -> str:
    """Write the review payload to a temp JSON file and return its path."""
    fd, path = tempfile.mkstemp(prefix="pr-review-payload.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload.to_json())
    return path


def post_review(target: Target, payload: Payload, *, runner=_run) -> None:
    path = _write_payload_file(payload)
    try:
        runner(
            ["gh", "api", f"repos/{target.slug}/pulls/{target.number}/reviews",
             "--method", "POST", "--input", path]
        )
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _not_posted_hint(target: Target, payload: Payload) -> str:
    # Keep the payload on disk so the user can post it manually.
    path = _write_payload_file(payload)
    return (
        f"pr-review: not posted. Payload written to:\n  {path}\n"
        f"  to post it: gh api repos/{target.slug}/pulls/{target.number}/reviews "
        f"--method POST --input {path}"
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
        print(_not_posted_hint(target, payload), file=sys.stderr)
