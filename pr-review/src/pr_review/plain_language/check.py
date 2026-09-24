"""The plain-language problems code can find without a model."""
from __future__ import annotations

import re
from dataclasses import dataclass

from pr_review.plain_language.rules import Rules, load_rules

BLOCKING = "blocking"
MINOR = "minor"


@dataclass(frozen=True)
class Problem:
    level: str
    detail: str


FENCE = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n.*?^[ \t]*\1[ \t]*$", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]+`")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_CONTRACTION = re.compile(r"\b[A-Za-z]+n['’]t\b")
_NEW_BLOCK = re.compile(r"^\s*([-*+]\s|\d+[.)]\s|#|>)")
_LIST_MARKER = re.compile(r"^([-*+]|\d+[.)])\s+")
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[*_`])")
_FINDING_LINE = re.compile(r"^\*\*[^*\s].*\*\*$")


def _prose(text: str) -> str:
    text = FENCE.sub("\n\n", text)
    text = INLINE_CODE.sub("CODE", text)
    text = _LINK.sub(r"\1", text)
    return text.replace("**", "")


def sentences(text: str) -> list[str]:
    """Split prose into sentences; list items, headings and quotes stand alone."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in _prose(text).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|"):
            if current:
                blocks.append(current)
                current = []
            continue
        if _NEW_BLOCK.match(line) and current:
            blocks.append(current)
            current = []
        current.append(_LIST_MARKER.sub("", stripped))
    if current:
        blocks.append(current)
    out: list[str] = []
    for block in blocks:
        out.extend(s.strip() for s in _SPLIT.split(" ".join(block)) if s.strip())
    return out


def _preview(sentence: str) -> str:
    words = sentence.split()
    return " ".join(words[:8]) + (" ..." if len(words) > 8 else "")


def check_text(text: str, rules: Rules | None = None) -> list[Problem]:
    rules = rules or load_rules()
    plain = _prose(text)
    problems = [
        Problem(BLOCKING, f'contraction "{m.group(0)}": write the negative in full')
        for m in _CONTRACTION.finditer(plain)
    ]
    for word in rules.blocking_words:
        problems.extend(
            Problem(BLOCKING, f'"{m.group(0)}": {word.instead}')
            for m in word.pattern.finditer(plain)
        )
    for s in sentences(text):
        n = len(s.split())
        if n > rules.sentence_blocking_words:
            problems.append(Problem(BLOCKING, f'sentence of {n} words ("{_preview(s)}")'))
        elif n > rules.sentence_minor_words:
            problems.append(Problem(MINOR, f'sentence of {n} words ("{_preview(s)}")'))
    return problems


def check_comment(body: str, rules: Rules | None = None) -> list[Problem]:
    rules = rules or load_rules()
    problems: list[Problem] = []
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if not _FINDING_LINE.match(first):
        problems.append(Problem(BLOCKING, "the first line is not a bold finding line"))
    for key in rules.required_labels:
        label = rules.labels[key]
        if not re.search(rf"^\*\*{re.escape(label)}:\*\*", body, re.M):
            problems.append(Problem(BLOCKING, f"no **{label}:** section"))
    return problems + check_text(body, rules)


def check_body(body: str, rules: Rules | None = None) -> list[Problem]:
    return check_text(body, rules)
