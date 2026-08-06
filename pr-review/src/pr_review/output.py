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


def _post_payload_file(target: Target, path: str, *, runner=_run) -> None:
    runner(
        ["gh", "api", f"repos/{target.slug}/pulls/{target.number}/reviews",
         "--method", "POST", "--input", path]
    )


def post_review(target: Target, payload: Payload, *, runner=_run) -> str:
    """POST the review via gh and return the payload file's path.

    The file is left on disk on purpose: posting is the tail end of an
    expensive review, so a failure here (bad token, missing permission) must
    not cost the review itself.
    """
    path = _write_payload_file(payload)
    _post_payload_file(target, path, runner=runner)
    return path


def _payload_note(target: Target, path: str, lead: str) -> str:
    return (
        f"{lead}\n  {path}\n"
        f"  to post it: gh api repos/{target.slug}/pulls/{target.number}/reviews "
        f"--method POST --input {path}"
    )


def _not_posted_hint(target: Target, payload: Payload) -> str:
    # Keep the payload on disk so the user can post it manually.
    return _payload_note(
        target, _write_payload_file(payload), "pr-review: not posted. Payload written to:"
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


def dispatch(mode: PostMode, target: Target, payload: Payload, *, runner=_run) -> int:
    """Post the review (or explain why it wasn't). Returns the exit code."""
    if mode is PostMode.POST or (
        mode is PostMode.PROMPT and _confirm(target, len(payload.comments))
    ):
        # Write the payload before posting so its path survives a failed post.
        path = _write_payload_file(payload)
        try:
            _post_payload_file(target, path, runner=runner)
        except Exception as err:
            print(f"pr-review: posting failed: {err}", file=sys.stderr)
            print(
                _payload_note(target, path, "pr-review: the review was kept at:"),
                file=sys.stderr,
            )
            return 1
        print(f"pr-review: posted review to {target.slug}#{target.number}.", file=sys.stderr)
        print(f"pr-review: payload kept at {path}", file=sys.stderr)
        return 0
    print(_not_posted_hint(target, payload), file=sys.stderr)
    return 0
