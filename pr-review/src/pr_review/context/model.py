"""The pull request context: description, discussion, linked issues and stack."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    id: int
    kind: str
    url: str
    author: str
    is_author: bool
    created_at: str
    body: str
    path: str | None = None
    line: int | None = None
    in_reply_to: int | None = None


@dataclass
class Thread:
    root: Entry
    replies: list[Entry]


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    state: str
    body: str


@dataclass(frozen=True)
class StackEntry:
    number: int
    title: str
    body: str
    state: str
    head_sha: str
    later: bool
    position: int | None = None


@dataclass
class PullRequestContext:
    number: int
    title: str
    body: str
    author: str
    issues: list[Issue]
    comments: list[Entry]
    threads: list[Thread]
    stack: list[StackEntry]
    stack_position: tuple[int, int] | None
    failed: list[str]
