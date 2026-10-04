"""Claude headless reviewer (wraps `claude --print`)."""
from __future__ import annotations

import json
import os
import urllib.request

from pr_review.reviewers.base import Reviewer, register

_MODELS_URL = "https://api.anthropic.com/v1/models?limit=1000"
_CREDENTIALS = os.path.expanduser("~/.claude/.credentials.json")


def fetch_live_models() -> list[str]:
    """Model ids the user's Claude subscription offers, via `/v1/models`. The
    subscription OAuth token (not an API key) authenticates, so the request
    carries the oauth beta header the token requires."""
    creds = json.load(open(_CREDENTIALS))
    oauth = creds.get("claudeAiOauth") or creds
    token = oauth.get("accessToken") or oauth["access_token"]
    req = urllib.request.Request(
        _MODELS_URL,
        headers={
            "authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.load(r)
    return [m["id"] for m in body.get("data", [])]


class ClaudeReviewer(Reviewer):
    name = "claude"
    default_model = "claude-opus-5-5"
    known_models = ["claude-opus-5-5", "claude-opus-5", "claude-sonnet-5", "claude-fable-5", "claude-haiku-4-5"]

    def available_models(self) -> list[str]:
        try:
            return fetch_live_models() or list(self.known_models)
        except Exception:
            return list(self.known_models)

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
