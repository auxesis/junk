"""PR review payload: model, JSON validation, and the inline-comment cap."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

MAX_INLINE_COMMENTS = 8


@dataclass
class Comment:
    path: str
    line: int
    body: str
    side: str = "RIGHT"

    def to_dict(self) -> dict:
        return {"path": self.path, "line": self.line, "side": self.side, "body": self.body}


@dataclass
class Payload:
    body: str
    comments: list[Comment] = field(default_factory=list)
    event: str = "COMMENT"

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
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    if not isinstance(data.get("body"), str):
        raise ValueError("payload must have a string 'body'")
    raw_comments = data.get("comments", [])
    if not isinstance(raw_comments, list):
        raise ValueError("payload 'comments' must be a list")
    comments: list[Comment] = []
    for i, c in enumerate(raw_comments):
        if not isinstance(c, dict):
            raise ValueError(f"comment {i} must be an object")
        try:
            comments.append(
                Comment(path=c["path"], line=int(c["line"]), body=c["body"],
                        side=c.get("side", "RIGHT"))
            )
        except KeyError as e:
            raise ValueError(f"comment {i} missing field {e}") from e
    return Payload(body=data["body"], comments=comments, event=data.get("event", "COMMENT"))


def cap_comments(
    comments: list[Comment], limit: int = MAX_INLINE_COMMENTS
) -> tuple[list[Comment], list[Comment]]:
    return comments[:limit], comments[limit:]
