"""The reader test: a model reads each comment as the target reader would."""
from __future__ import annotations

from dataclasses import dataclass, field

from pr_review.payload import Comment

_INSTRUCTIONS = """# Reader test

You are the reader of a pull request review: an engineer on the team who did not
write this code, does not know this part of the system, and may not have English
as a first language. You see each comment beside the diff lines it is attached
to, as you would on GitHub. Do not read any other file and do not run any
command other than writing the output file.

For each comment, answer from the comment and its diff lines alone:
1. What is wrong?
2. What breaks, and when?
3. What should I change?

Then list its problems:
- "blocking": you could not answer one of the three questions, or you had to
  guess what a word or phrase means to answer it. Name the phrase and say why.
- "minor": the comment was harder to read than it needed to be, but you could
  still act on it.
Exact technical names (identifiers, commands, file paths, product names and real
engineering terms) are not problems.

For the review body, answer one question: what must I do before this pull
request merges? List its blocking and minor problems the same way.

Write ONLY this JSON to the output file:
{"comments": [{"index": 0, "what_wrong": "...", "what_breaks": "...",
   "what_to_change": "...", "blocking": ["phrase: why"], "minor": ["phrase: why"]}],
 "body": {"what_to_do_before_merge": "...", "blocking": [], "minor": []}}
"""


@dataclass
class Verdict:
    blocking: list[str] = field(default_factory=list)
    minor: list[str] = field(default_factory=list)


@dataclass
class ReaderResult:
    comments: dict[int, Verdict]
    body: Verdict


def build_reader_prompt(
    *, payload_path: str, comments: list[tuple[int, Comment, str]], body: str
) -> str:
    parts = [f"Output file to write: {payload_path}\n", _INSTRUCTIONS, "## Comments\n"]
    for index, comment, hunk in comments:
        parts.append(
            f"### Comment {index}: {comment.path}:{comment.line}\n\n"
            f"Diff lines:\n```diff\n{hunk or '(no diff lines found)'}\n```\n\n"
            f"Comment:\n<<<\n{comment.body}\n>>>\n"
        )
    parts.append(f"## Review body\n\n<<<\n{body}\n>>>\n")
    return "\n".join(parts)


def _strings(value: object) -> list[str]:
    return [s for s in value if isinstance(s, str)] if isinstance(value, list) else []


def parse_reader_result(data: object) -> ReaderResult:
    if not isinstance(data, dict):
        raise ValueError("reader result must be a JSON object")
    comments: dict[int, Verdict] = {}
    raw = data.get("comments")
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and isinstance(item.get("index"), int):
            comments[item["index"]] = Verdict(_strings(item.get("blocking")), _strings(item.get("minor")))
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    return ReaderResult(comments, Verdict(_strings(body.get("blocking")), _strings(body.get("minor"))))
