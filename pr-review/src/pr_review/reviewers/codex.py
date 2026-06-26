"""Codex headless reviewer (wraps `codex exec`)."""
from __future__ import annotations

from pr_review.payload import Payload
from pr_review.reviewers._run import run_cli_reviewer
from pr_review.reviewers.base import Reviewer, register
from pr_review.review_types.base import ReviewType


class CodexReviewer(Reviewer):
    name = "codex"
    default_model = "gpt-5-codex"

    def review(
        self, *, workdir: str, base: str, owner: str, repo: str, number: int,
        review_type: ReviewType, model: str, extra_flags: list[str],
    ) -> Payload:
        cmd = [
            "codex", "exec", "--model", model,
            "--dangerously-bypass-approvals-and-sandbox",
            *extra_flags,
        ]
        return run_cli_reviewer(
            cmd, workdir=workdir, owner=owner, repo=repo, number=number,
            base=base, review_type=review_type,
        )


register(CodexReviewer())
