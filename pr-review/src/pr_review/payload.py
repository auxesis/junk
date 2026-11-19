"""PR review payload: model, JSON validation, and the inline-comment cap."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

MAX_INLINE_COMMENTS = 8


@dataclass(frozen=True)
class Source:
    """The job that raised a finding. Internal to pr-review; never posted."""

    agent: str
    model: str
    review_type: str


@dataclass
class Comment:
    path: str
    line: int
    body: str
    side: str = "RIGHT"
    sources: list[Source] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"path": self.path, "line": self.line, "side": self.side, "body": self.body}


@dataclass
class Reply:
    """A finding posted as a reply in an existing review thread.

    `in_reply_to` is the thread's top-level comment, the only id GitHub accepts;
    `answer_id` is the author's entry the finding answers, which may be a reply.
    """

    in_reply_to: int
    body: str
    sources: list[Source] = field(default_factory=list)
    answer_id: int | None = None

    def to_dict(self) -> dict:
        return {"body": self.body}


@dataclass
class Payload:
    body: str
    comments: list[Comment] = field(default_factory=list)
    event: str = "COMMENT"
    replies: list[Reply] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "body": self.body,
            "comments": [c.to_dict() for c in self.comments],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def parse_payload(text: str) -> Payload:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"payload is not valid JSON: {e}") from e
    return payload_from_dict(data)


def payload_from_dict(data: object) -> Payload:
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    if not isinstance(data.get("body"), str):
        raise ValueError("payload must have a string 'body'")
    comments = parse_comments(data.get("comments", []), "comments")
    return Payload(body=data["body"], comments=comments, event=data.get("event", "COMMENT"))


def parse_comments(raw: object, key: str) -> list[Comment]:
    if not isinstance(raw, list):
        raise ValueError(f"payload '{key}' must be a list")
    comments: list[Comment] = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            raise ValueError(f"{key}[{i}] must be an object")
        try:
            path = c["path"]
            line = c["line"]
            body = c["body"]
        except KeyError as e:
            raise ValueError(f"{key}[{i}] missing field {e}") from e
        if not isinstance(path, str):
            raise ValueError(f"{key}[{i}] 'path' must be a string")
        if not isinstance(body, str):
            raise ValueError(f"{key}[{i}] 'body' must be a string")
        side = c.get("side", "RIGHT")
        if not isinstance(side, str):
            raise ValueError(f"{key}[{i}] 'side' must be a string")
        try:
            line_int = int(line)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{key}[{i}] 'line' must be an integer: {e}") from e
        comments.append(Comment(path=path, line=line_int, body=body, side=side))
    return comments


def cap_comments(
    comments: list[Comment], limit: int = MAX_INLINE_COMMENTS
) -> tuple[list[Comment], list[Comment]]:
    return comments[:limit], comments[limit:]
