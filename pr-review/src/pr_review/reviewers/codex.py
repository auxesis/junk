"""Codex headless reviewer (wraps `codex exec`)."""
from __future__ import annotations

from pr_review.reviewers.base import Reviewer, register


class CodexReviewer(Reviewer):
    name = "codex"
    # The 5.6 family supersedes gpt-5.5, which codex itself now labels
    # "previous-generation"; terra is its balanced agentic-coding model. All are
    # available on ChatGPT-account auth (gpt-5-codex is NOT). Override per run
    # with `--model codex=<id>` (e.g. gpt-5.6-sol, gpt-5.6-luna, gpt-5.5,
    # gpt-5.4-mini) — `codex --model` lists what your auth actually offers. An
    # empty model still falls through to codex's own configured default.
    default_model = "gpt-5.6-terra"

    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        cmd = ["codex", "exec"]
        if model:
            cmd += ["--model", model]
        cmd += ["--dangerously-bypass-approvals-and-sandbox", *extra_flags]
        return cmd


register(CodexReviewer())
