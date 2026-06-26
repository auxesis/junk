"""Interactive selection of review types and agent/model pairs."""
from __future__ import annotations

import sys
from collections.abc import Callable

from pr_review import terminal


def select_from_menu(
    available: list[str],
    reader: Callable[[], str],
    writer: Callable[[str], None],
    *,
    default: str,
    what: str,
) -> list[str]:
    """Render a numbered menu and parse a comma-separated reply of numbers/names.

    Empty input selects `default`. Unknown names / out-of-range numbers raise
    `ValueError`. Results are de-duplicated, preserving order.
    """
    writer(f"Select {what}(s):\n")
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
            raise ValueError(f"unknown {what}: {tok}")

    seen: set[str] = set()
    result: list[str] = []
    for name in selected:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result or [default]


def choose_review_types(
    available: list[str],
    reader: Callable[[], str],
    writer: Callable[[str], None],
    *,
    default: str = "test-gap",
) -> list[str]:
    return select_from_menu(available, reader, writer, default=default, what="review type")


def choose_agent_models(
    agents: list[str],
    default_model: Callable[[str], str],
    reader: Callable[[], str],
    writer: Callable[[str], None],
) -> list[tuple[str, str]]:
    chosen = select_from_menu(agents, reader, writer, default="claude", what="agent")
    pairs: list[tuple[str, str]] = []
    for agent in chosen:
        dm = default_model(agent)
        writer(f"Models for {agent} (comma-separated) [default: {dm}]: ")
        reply = reader().strip()
        models = [m.strip() for m in reply.split(",") if m.strip()] if reply else [dm]
        for model in models:
            if (agent, model) not in pairs:
                pairs.append((agent, model))
    return pairs


def prompt_review_types_via_tty(available: list[str]) -> list[str]:
    io = terminal.open_interactive()
    if io is None:
        print(
            "pr-review: no terminal to prompt for --review-type.\n"
            f"  pass one, e.g. --review-type {','.join(available)}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    read_line, write, close = io
    try:
        for _ in range(3):
            try:
                return choose_review_types(available, read_line, write)
            except ValueError as exc:
                write(f"  {exc}\n")
        raise SystemExit("pr-review: no valid review type selected")
    finally:
        close()


def prompt_agent_models_via_tty(
    agents: list[str], default_model: Callable[[str], str]
) -> list[tuple[str, str]]:
    io = terminal.open_interactive()
    if io is None:
        print(
            "pr-review: no terminal to prompt for --model.\n"
            "  pass one, e.g. --model claude=claude-opus-4-8",
            file=sys.stderr,
        )
        raise SystemExit(2)
    read_line, write, close = io
    try:
        for _ in range(3):
            try:
                return choose_agent_models(agents, default_model, read_line, write)
            except ValueError as exc:
                write(f"  {exc}\n")
        raise SystemExit("pr-review: no valid agent/model selected")
    finally:
        close()
