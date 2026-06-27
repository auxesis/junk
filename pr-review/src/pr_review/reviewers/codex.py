"""Codex headless reviewer (wraps `codex exec`)."""
from __future__ import annotations

from pr_review.reviewers.base import Reviewer, register


class CodexReviewer(Reviewer):
    name = "codex"
    # gpt-5.5 is available on ChatGPT-account auth (gpt-5-codex is NOT). Override
    # per run with `--model codex=<id>` (e.g. gpt-5.4, gpt-5.4-mini). An empty
    # model still falls through to codex's own configured default.
    default_model = "gpt-5.5"

    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        cmd = ["codex", "exec"]
        if model:
            cmd += ["--model", model]
        cmd += ["--dangerously-bypass-approvals-and-sandbox", *extra_flags]
        return cmd


register(CodexReviewer())
