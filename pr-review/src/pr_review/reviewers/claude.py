"""Claude headless reviewer (wraps `claude --print`)."""
from __future__ import annotations

from pr_review.reviewers.base import Reviewer, register


class ClaudeReviewer(Reviewer):
    name = "claude"
    default_model = "claude-opus-4-8"

    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        return [
            "claude", "--print", "--model", model,
            "--permission-mode", "acceptEdits", "--dangerously-skip-permissions",
            # A review needs only the built-in tools; don't load the user's MCP
            # servers (e.g. Serena, which pops a browser dashboard each run).
            "--strict-mcp-config",
            "--allowedTools", "Bash", "Read", "Grep", "Glob", "Write",
            *extra_flags,
        ]


register(ClaudeReviewer())
