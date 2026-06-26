"""Codex headless reviewer (wraps `codex exec`)."""
from __future__ import annotations

from pr_review.reviewers.base import Reviewer, register


class CodexReviewer(Reviewer):
    name = "codex"
    # Empty = let codex use its own configured default model (see codex auth).
    default_model = ""

    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        cmd = ["codex", "exec"]
        if model:
            cmd += ["--model", model]
        cmd += ["--dangerously-bypass-approvals-and-sandbox", *extra_flags]
        return cmd


register(CodexReviewer())
