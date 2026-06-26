"""Interactive selection of review types when --review-type is omitted."""
from __future__ import annotations

import sys
from collections.abc import Callable


def choose_review_types(
    available: list[str],
    reader: Callable[[], str],
    writer: Callable[[str], None],
    *,
    default: str = "test-gap",
) -> list[str]:
    """Render a numbered menu and parse the reply into review-type names.

    The reply is comma-separated numbers and/or names. Empty input selects the
    `default`. Unknown names or out-of-range numbers raise `ValueError`.
    """
    writer("Select review type(s):\n")
    for i, name in enumerate(available, 1):
        writer(f"  {i}) {name}\n")
    writer(f"Enter numbers or names (comma-separated) [default: {default}]: ")

    reply = reader().strip()
    if not reply:
        return [default]

    selected: list[str] = []
    for tok in (t.strip() for t in reply.split(",")):
        if not tok:
            continue
        if tok.isdigit():
            idx = int(tok) - 1
            if not 0 <= idx < len(available):
                raise ValueError(f"selection out of range: {tok}")
            selected.append(available[idx])
        elif tok in available:
            selected.append(tok)
        else:
            raise ValueError(f"unknown review type: {tok}")

    seen: set[str] = set()
    result: list[str] = []
    for name in selected:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result or [default]


def prompt_review_types_via_tty(available: list[str]) -> list[str]:
    """Prompt on /dev/tty (so it works even when stdin is consumed)."""
    try:
        tty = open("/dev/tty", "r+")
    except OSError:
        # /dev/tty's node may exist but be unusable (e.g. CI) — same outcome as
        # having no terminal: error rather than guess what to review.
        print(
            "pr-review: no terminal to prompt for --review-type.\n"
            f"  pass one, e.g. --review-type {','.join(available)}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    with tty:
        def reader() -> str:
            return tty.readline()

        def writer(text: str) -> None:
            tty.write(text)
            tty.flush()

        for _ in range(3):
            try:
                return choose_review_types(available, reader, writer)
            except ValueError as exc:
                writer(f"  {exc}\n")
        raise SystemExit("pr-review: no valid review type selected")
