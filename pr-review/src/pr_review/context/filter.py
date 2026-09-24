"""Drop findings the pull request's context already answers; reply where it is wrong."""
from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from pr_review.collate import _first_line
from pr_review.context.model import Entry, PullRequestContext
from pr_review.context.render import stack_map
from pr_review.payload import Comment, Payload, Reply
from pr_review.reviewers._run import run_cli_json

MAX_REPLIES = 3
_REASONS = ("fixed-later", "already-raised", "answered")

_INSTRUCTIONS = """# Context filter

You are checking findings from a review of this pull request before they are
posted. Read the context file named above: it has the description, the
discussion so far (every entry has an id, and the pull request author's entries
are marked "(author)"), and the other pull requests in the stack. The other pull
requests are fetched as git refs, listed below with their states.

For each finding, choose one verdict:

- "drop" with reason "fixed-later": code at a LATER pull request's ref fixes it.
  Check the code (`git show refs/stack/<n>:<path>`, `git diff HEAD refs/stack/<n>`).
  Give "pull_request" (its number) and "evidence" (what you saw). A closed pull
  request that was not merged never counts.
- "drop" with reason "already-raised": the discussion already raises the same
  problem, from anyone. Give "link" (the entry's URL).
- "drop" with reason "answered": the author said it is deliberate, will be done
  later, or is done elsewhere (and you confirmed that in the code). Do not use
  this when the finding is a correctness or security bug that the code shows.
  Give "link".
- "reply": the author answered it, and the code proves the answer wrong. Give
  "in_reply_to" (the id of the author's entry) and "body": the finding written as
  a reply to that answer, in the same comment shape.
- "keep": none of the above.

Only entries marked "(author)" count as answers. Other people's entries count as
already raised. Do not post anything and do not change any file except the
output file.

Write ONLY this JSON to the output file:
{"verdicts": [{"index": 0, "verdict": "keep"},
  {"index": 1, "verdict": "drop", "reason": "fixed-later", "pull_request": 42, "evidence": "..."},
  {"index": 2, "verdict": "drop", "reason": "already-raised", "link": "https://..."},
  {"index": 3, "verdict": "reply", "in_reply_to": 123, "body": "..."}]}
"""


@dataclass
class Dropped:
    finding: str
    reason: str
    link: str
    evidence: str = ""


@dataclass
class FilterResult:
    payload: Payload
    dropped: list[Dropped] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _entries(ctx: PullRequestContext) -> list[Entry]:
    return list(ctx.comments) + [e for t in ctx.threads for e in [t.root, *t.replies]]


def answers_by_id(ctx: PullRequestContext) -> dict[int, str]:
    return {e.id: e.body for e in _entries(ctx)}


def build_filter_prompt(*, payload_path: str, context_path: str, ctx: PullRequestContext, payload: Payload) -> str:
    parts = [
        f"Output file to write: {payload_path}",
        f"Context file: {context_path}\n",
        _INSTRUCTIONS,
        "## Stack refs\n",
        stack_map(ctx),
        "\n## Discussion entries by id\n",
        *[f"- {e.id}: {e.kind} by {e.author}{' (author)' if e.is_author else ''}" for e in _entries(ctx)],
        "\n## Findings\n",
    ]
    for i, c in enumerate(payload.comments):
        parts.append(f"### Finding {i}: {c.path}:{c.line}\n\n<<<\n{c.body}\n>>>\n")
    return "\n".join(parts)


def apply_verdicts(payload: Payload, data: object, ctx: PullRequestContext) -> FilterResult:
    raw = data.get("verdicts") if isinstance(data, dict) else None
    verdicts: dict[int, dict] = {}
    for v in raw if isinstance(raw, list) else []:
        if isinstance(v, dict) and isinstance(v.get("index"), int) and v["index"] not in verdicts:
            verdicts[v["index"]] = v

    fixers = {e.number for e in ctx.stack if e.later and e.state != "closed"}
    entries = {e.id: e for e in _entries(ctx)}
    kept: list[Comment] = []
    replies: list[Reply] = []
    overflow: list[str] = []
    dropped: list[Dropped] = []
    warnings: list[str] = []

    for i, c in enumerate(payload.comments):
        v = verdicts.get(i, {})
        where = f"{c.path}:{c.line}"
        if v.get("verdict") == "drop" and v.get("reason") in _REASONS:
            reason = v["reason"]
            if reason == "fixed-later":
                pr = v.get("pull_request")
                if pr not in fixers:
                    warnings.append(f"{where}: kept; #{pr} is not an open or merged later pull request")
                    kept.append(c)
                    continue
                link = f"#{pr}"
            else:
                link = v.get("link") if isinstance(v.get("link"), str) else ""
            evidence = v.get("evidence") if isinstance(v.get("evidence"), str) else ""
            dropped.append(Dropped(_first_line(c.body), reason, link, evidence))
        elif v.get("verdict") == "reply":
            target = entries.get(v.get("in_reply_to"))
            body = v.get("body") if isinstance(v.get("body"), str) and v["body"].strip() else c.body
            if target is None or not target.is_author:
                warnings.append(f"{where}: kept as a comment; the reply target is not the author's")
                kept.append(c)
            elif target.kind != "thread":
                kept.append(replace(c, body=f"{c.body.rstrip()}\n\nThis replies to [the author's answer]({target.url})."))
            elif len(replies) < MAX_REPLIES:
                replies.append(Reply(target.id, body, sources=list(c.sources)))
            else:
                overflow.append(f"- [{_first_line(body)}]({target.url})")
        else:
            kept.append(c)

    body = payload.body
    if overflow:
        body += "\n\n---\n\n## Other replies not posted\n\n" + "\n".join(overflow)
    out = Payload(body=body, comments=kept, event=payload.event, replies=list(payload.replies) + replies)
    return FilterResult(out, dropped, warnings)


class ContextFilter:
    def __init__(self, *, command: list[str], workdir: str, context_path: str,
                 runner: Callable[..., object] = run_cli_json):
        self._command = command
        self._workdir = workdir
        self._context_path = context_path
        self._runner = runner

    def apply(self, payload: Payload, ctx: PullRequestContext) -> FilterResult:
        if not payload.comments:
            return FilterResult(payload)
        try:
            data = self._runner(
                self._command,
                lambda path: build_filter_prompt(payload_path=path, context_path=self._context_path,
                                                 ctx=ctx, payload=payload),
                workdir=self._workdir,
            )
        except Exception as e:
            return FilterResult(payload, [], [f"context filter failed ({e}); every finding is kept"])
        return apply_verdicts(payload, data, ctx)
