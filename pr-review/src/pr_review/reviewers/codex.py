"""Codex headless reviewer (wraps `codex exec`)."""
from __future__ import annotations

from pr_review.reviewers.base import Reviewer, register


class CodexReviewer(Reviewer):
    name = "codex"
    # Empty = let codex use its own configured default model. Codex's model
    # availability depends on the auth (a ChatGPT-account login can't use
    # `gpt-5-codex`), so deferring to codex's own choice "just works"; pin one
    # with `--model codex=<id>`.
    default_model = ""

    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        cmd = ["codex", "exec"]
        if model:
            cmd += ["--model", model]
        cmd += ["--dangerously-bypass-approvals-and-sandbox", *extra_flags]
        return cmd


register(CodexReviewer())
