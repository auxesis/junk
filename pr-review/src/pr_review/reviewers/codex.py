"""Codex headless reviewer (wraps `codex exec`)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request

from pr_review.reviewers.base import Reviewer, register

_MODELS_URL = "https://chatgpt.com/backend-api/codex/models"
_AUTH = os.path.expanduser("~/.codex/auth.json")
# The endpoint returns internal slugs (gpt-reserve, codex-auto-review) beside
# real models; only `gpt-<digit>…` ids are selectable.
_MODEL_SLUG = re.compile(r"gpt-\d")


def _client_version() -> str:
    # The endpoint 400s without client_version; codex prints "codex-cli X.Y.Z".
    out = subprocess.run(["codex", "--version"], capture_output=True, text=True, check=True).stdout
    return out.split()[-1]


def fetch_live_models() -> list[str]:
    """Model slugs the user's ChatGPT-account auth offers, via the codex backend.
    The ChatGPT OAuth token (not an API key) authenticates; /v1/models rejects it."""
    auth = json.load(open(_AUTH))
    tokens = auth.get("tokens") or {}
    token = tokens["access_token"]
    headers = {"authorization": f"Bearer {token}"}
    if tokens.get("account_id"):
        headers["chatgpt-account-id"] = tokens["account_id"]
    req = urllib.request.Request(
        f"{_MODELS_URL}?client_version={_client_version()}", headers=headers
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.load(r)
    return [m["slug"] for m in body.get("models", []) if _MODEL_SLUG.match(m.get("slug", ""))]


class CodexReviewer(Reviewer):
    name = "codex"
    default_model = "gpt-5.6-terra"
    known_models = ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.5"]

    def available_models(self) -> list[str]:
        try:
            return fetch_live_models() or list(self.known_models)
        except Exception:
            return list(self.known_models)

    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        cmd = ["codex", "exec"]
        if model:
            cmd += ["--model", model]
        cmd += ["--dangerously-bypass-approvals-and-sandbox", *extra_flags]
        return cmd


register(CodexReviewer())
