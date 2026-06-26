"""Terminal detection and interactive prompt I/O.

Prompts prefer the controlling terminal (`/dev/tty`) so they work even when
stdout is captured. But `/dev/tty` is not always openable even when the user has
a real terminal — some GNU screen, container, and detached-session setups expose
a usable stdin tty while `open("/dev/tty")` fails with ENXIO. In that case we fall
back to stdin/stderr. Only when neither works do we report "no terminal".
"""
from __future__ import annotations

import sys
from collections.abc import Callable

# (read_line, write, close)
InteractiveIO = tuple[Callable[[], str], Callable[[str], None], Callable[[], None]]


def _flushed_writer(stream) -> Callable[[str], None]:
    def write(text: str) -> None:
        stream.write(text)
        stream.flush()

    return write


def open_interactive() -> InteractiveIO | None:
    """Return (read_line, write, close) for prompting the user, or None.

    Tries the controlling terminal first, then stdin/stderr, then gives up.
    """
    try:
        tty = open("/dev/tty", "r+")
    except OSError:
        tty = None
    if tty is not None:
        return (lambda: tty.readline(), _flushed_writer(tty), tty.close)
    if sys.stdin.isatty():
        return (lambda: sys.stdin.readline(), _flushed_writer(sys.stderr), lambda: None)
    return None


def can_prompt() -> bool:
    """True if the user can be prompted interactively (see open_interactive)."""
    if sys.stdin.isatty():
        return True
    try:
        open("/dev/tty").close()
    except OSError:
        return False
    return True
