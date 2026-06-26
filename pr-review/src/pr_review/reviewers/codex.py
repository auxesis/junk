"""Codex headless reviewer (wraps `codex exec`)."""
from __future__ import annotations

from pr_review.payload import Payload
from pr_review.reviewers._run import run_cli_reviewer
from pr_review.reviewers.base import Reviewer, register
from pr_review.review_types.base import ReviewType


class CodexReviewer(Reviewer):
    name = "codex"
    # Empty = let codex use its own configured default model. Codex's model
    # availability depends on the auth (a ChatGPT-account login can't use
    # `gpt-5-codex`), so deferring to codex's own choice "just works"; pin one
    # with `--model codex=<id>`.
    default_model = ""

    def review(
        self, *, workdir: str, base: str, owner: str, repo: str, number: int,
        review_type: ReviewType, model: str, extra_flags: list[str],
    ) -> Payload:
        cmd = ["codex", "exec"]
        if model:
            cmd += ["--model", model]
        cmd += ["--dangerously-bypass-approvals-and-sandbox", *extra_flags]
        return run_cli_reviewer(
            cmd, workdir=workdir, owner=owner, repo=repo, number=number,
            base=base, review_type=review_type,
        )


register(CodexReviewer())
