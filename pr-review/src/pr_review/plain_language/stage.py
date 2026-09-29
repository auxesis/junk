"""The plain-language stage: check, reader test, one rewrite, check again."""
from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from pr_review.payload import Comment, Payload
from pr_review.plain_language.check import BLOCKING, MINOR, Problem, check_body, check_comment
from pr_review.plain_language.hunks import git_diff, hunk_for
from pr_review.plain_language.reader import Verdict, build_reader_prompt, parse_reader_result
from pr_review.plain_language.rewrite import (
    RewriteItem, build_rewrite_prompt, guard, parse_rewrite_result,
)
from pr_review.reviewers._run import run_cli_json


@dataclass
class StageResult:
    payload: Payload
    remaining: dict[int, list[Problem]]
    body_remaining: list[Problem]
    rewritten: int = 0
    warnings: list[str] = field(default_factory=list)
    reader_ran: bool = False
    needed_rewrite: int = 0


def _units(payload: Payload) -> list[Comment]:
    return list(payload.comments) + [
        Comment(f"reply to comment {r.in_reply_to}", 0, r.body, sources=r.sources) for r in payload.replies
    ]


def _rebuild(payload: Payload, units: list[Comment], body: str) -> Payload:
    n = len(payload.comments)
    replies = [replace(r, body=u.body) for r, u in zip(payload.replies, units[n:])]
    return Payload(body=body, comments=units[:n], event=payload.event, replies=replies)


def check_payload(payload: Payload) -> StageResult:
    return StageResult(
        payload=payload,
        remaining={i: check_comment(c.body) for i, c in enumerate(_units(payload))},
        body_remaining=check_body(payload.body),
    )


def _reader_problems(verdict: Verdict | None) -> list[Problem]:
    if verdict is None:
        return []
    return ([Problem(BLOCKING, f"reader: {t}") for t in verdict.blocking]
            + [Problem(MINOR, f"reader: {t}") for t in verdict.minor])


def _blocking(problems: list[Problem]) -> list[str]:
    return [p.detail for p in problems if p.level == BLOCKING]


class PlainLanguageStage:
    def __init__(
        self,
        *,
        command: list[str],
        workdir: str,
        base: str,
        runner: Callable[..., object] = run_cli_json,
        diff: Callable[[str, str], str] = git_diff,
    ):
        self._command = command
        self._workdir = workdir
        self._base = base
        self._runner = runner
        self._diff = diff

    def apply(self, payload: Payload, answers: dict[int, str] | None = None) -> StageResult:
        units = _units(payload)
        checked = check_payload(payload)
        warnings: list[str] = []
        try:
            diff = self._diff(self._workdir, self._base)
        except Exception as e:
            warnings.append(f"could not read the diff ({e}); the reader test sees no diff lines")
            diff = ""
        hunks = {i: hunk_for(diff, c.path, c.line) for i, c in enumerate(payload.comments)}
        if diff and payload.comments and not any(hunks.values()):
            warnings.append(
                "no comment matched a line in the diff; the reader test sees no diff lines"
            )
        n = len(payload.comments)
        for j, r in enumerate(payload.replies):
            answer = r.answer_id if r.answer_id is not None else r.in_reply_to
            hunks[n + j] = f"(the comment this replies to)\n{(answers or {}).get(answer, '')}"

        # The reader and rewrite calls get no repo access (spec: "no tools, no
        # repo access"), so they run in an empty sandbox, never the clone.
        with tempfile.TemporaryDirectory(prefix="pr-review-sandbox.") as sandbox:
            reader = None
            try:
                reader = parse_reader_result(self._runner(
                    self._command,
                    lambda path: build_reader_prompt(
                        payload_path=path,
                        comments=[(i, c, hunks[i]) for i, c in enumerate(units)],
                        body=payload.body,
                    ),
                    workdir=sandbox,
                ))
            except Exception as e:
                warnings.append(f"reader test failed ({e}); rewriting on the word-and-shape check only")

            problems = {
                i: checked.remaining[i] + _reader_problems(reader.comments.get(i) if reader else None)
                for i in range(len(units))
            }
            body_problems = checked.body_remaining + _reader_problems(reader.body if reader else None)
            items = [
                RewriteItem(i, c, hunks[i], _blocking(problems[i]))
                for i, c in enumerate(units) if _blocking(problems[i])
            ]
            body_blocking = _blocking(body_problems)
            if not items and not body_blocking:
                return StageResult(payload, problems, body_problems, 0, warnings,
                                   reader_ran=reader is not None)

            try:
                new_bodies, new_body = parse_rewrite_result(self._runner(
                    self._command,
                    lambda path: build_rewrite_prompt(
                        payload_path=path, items=items, body=payload.body, body_problems=body_blocking,
                    ),
                    workdir=sandbox,
                ))
            except Exception as e:
                warnings.append(f"rewrite failed ({e}); posting the review as written")
                return StageResult(payload, problems, body_problems, 0, warnings,
                                   reader_ran=reader is not None, needed_rewrite=len(items))

        units = list(units)
        rewritten = 0
        for item in items:
            text = new_bodies.get(item.index)
            if text is None:
                continue
            original = units[item.index]
            reason = guard(original.body, text)
            if reason:
                warnings.append(f"{original.path}:{original.line}: the rewrite {reason}; kept the original")
                continue
            units[item.index] = replace(original, body=text)
            problems[item.index] = check_comment(text)
            rewritten += 1

        body = payload.body
        if body_blocking and new_body is not None:
            reason = guard(payload.body, new_body)
            if reason:
                warnings.append(f"review body: the rewrite {reason}; kept the original")
            else:
                body, body_problems = new_body, check_body(new_body)

        return StageResult(_rebuild(payload, units, body),
                           problems, body_problems, rewritten, warnings,
                           reader_ran=reader is not None, needed_rewrite=len(items))


def format_report(result: StageResult) -> str:
    lines = [f"pr-review: plain language: {w}" for w in result.warnings]
    n_comments = len(result.payload.comments)
    replies = result.payload.replies
    left = [
        f"  {c.path}:{c.line}  {p.level}: {p.detail}"
        for i, c in enumerate(result.payload.comments) for p in result.remaining.get(i, [])
    ] + [
        f"  reply to comment {r.in_reply_to}  {p.level}: {p.detail}"
        for j, r in enumerate(replies) for p in result.remaining.get(n_comments + j, [])
    ] + [f"  review body  {p.level}: {p.detail}" for p in result.body_remaining]
    if left:
        k = (
            len([i for i in range(n_comments) if result.remaining.get(i)])
            + len([j for j in range(len(replies)) if result.remaining.get(n_comments + j)])
            + (1 if result.body_remaining else 0)
        )
        n_blocking = sum(1 for line in left if "  blocking: " in line)
        n_minor = len(left) - n_blocking
        if result.needed_rewrite == 0 and n_blocking == 0:
            head = (f"no comment needed a rewrite. {k} comment(s) have minor problems, "
                    "which are reported, not rewritten:")
        else:
            head = (f"rewrote {result.rewritten} of the {result.needed_rewrite} comment(s) that "
                    f"needed it; {k} comment(s) still have problems ({n_blocking} blocking, {n_minor} minor):")
        lines.append(f"pr-review: plain language: {head}")
        lines.extend(left)
    elif result.rewritten:
        lines.append(f"pr-review: plain language: rewrote {result.rewritten} of the "
                     f"{result.needed_rewrite} comment(s) that needed it; no problems left.")
    return "\n".join(lines)
