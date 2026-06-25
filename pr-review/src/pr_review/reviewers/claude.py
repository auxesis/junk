"""Claude headless reviewer (wraps `claude --print`)."""
from __future__ import annotations

import os
import subprocess
import tempfile

from pr_review.payload import Payload, parse_payload
from pr_review.reviewers.base import Reviewer, register
from pr_review.review_types.base import ReviewType


def _build_context(*, owner: str, repo: str, number: int, base: str, payload_path: str) -> str:
    return (
        "You are reviewing a GitHub pull request. Context for this run:\n"
        f"- Repository: {owner}/{repo}\n"
        f"- PR number: {number}\n"
        f"- Base ref:  origin/{base}\n"
        "- HEAD is ALREADY checked out at the exact code to review. Do not switch branches.\n"
        f"- Payload file to write: {payload_path}\n"
    )


class ClaudeReviewer(Reviewer):
    name = "claude"

    def build_prompt(
        self, *, owner: str, repo: str, number: int, base: str,
        payload_path: str, review_type: ReviewType,
    ) -> str:
        context = _build_context(
            owner=owner, repo=repo, number=number, base=base, payload_path=payload_path
        )
        return context + "\n" + review_type.instructions()

    def review(
        self, *, workdir: str, base: str, owner: str, repo: str, number: int,
        review_type: ReviewType, model: str, extra_flags: list[str],
    ) -> Payload:
        fd, payload_path = tempfile.mkstemp(prefix="pr-review-payload.", suffix=".json")
        os.close(fd)
        try:
            prompt = self.build_prompt(
                owner=owner, repo=repo, number=number, base=base,
                payload_path=payload_path, review_type=review_type,
            )
            cmd = [
                "claude", "--print", "--model", model,
                "--permission-mode", "acceptEdits",
                "--dangerously-skip-permissions",
                "--allowedTools", "Bash", "Read", "Grep", "Glob", "Write",
                *extra_flags,
            ]
            subprocess.run(cmd, cwd=workdir, input=prompt, text=True, check=True)
            with open(payload_path) as f:
                raw = f.read()
            if not raw.strip():
                raise RuntimeError("claude produced an empty payload")
            return parse_payload(raw)
        finally:
            try:
                os.unlink(payload_path)
            except FileNotFoundError:
                pass


register(ClaudeReviewer())
