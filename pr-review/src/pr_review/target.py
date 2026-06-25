"""Parse a PR target string into (owner, repo, number)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)/?$"
)
_SHORT_RE = re.compile(r"^(?P<owner>[^/\s]+)/(?P<repo>[^/#\s]+)#(?P<number>\d+)$")


@dataclass(frozen=True)
class Target:
    owner: str
    repo: str
    number: int

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_target(text: str) -> Target:
    text = text.strip()
    for rx in (_URL_RE, _SHORT_RE):
        m = rx.match(text)
        if m:
            return Target(m["owner"], m["repo"], int(m["number"]))
    raise ValueError(
        f"unrecognised PR target: {text!r}\n"
        "expected a PR URL (https://github.com/owner/repo/pull/N) or owner/repo#N"
    )
