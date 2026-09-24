"""Find the diff lines a comment is attached to, as a reader on GitHub sees them."""
from __future__ import annotations

import re
import subprocess

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _file_sections(diff: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    in_header = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_header, current = True, None
        elif in_header:
            # An added line can itself start with "+++ ", so only the header's
            # "+++ " names the file.
            if line.startswith("+++ "):
                in_header = False
                name = line[4:]
                if name.startswith("b/"):
                    current = sections.setdefault(name[2:], [])
        elif current is not None:
            current.append(line)
    return sections


def hunk_for(diff: str, path: str, line: int, context: int = 20) -> str:
    hunks: list[tuple[str, list[tuple[int | None, str]]]] = []
    new = 0
    for text in _file_sections(diff).get(path, []):
        m = _HUNK.match(text)
        if m:
            new = int(m.group(1))
            hunks.append((text, []))
        elif not hunks or text.startswith("\\"):
            continue
        elif text.startswith("-"):
            hunks[-1][1].append((None, text))
        else:
            hunks[-1][1].append((new, text))
            new += 1
    for header, rows in hunks:
        idx = next((i for i, (n, _) in enumerate(rows) if n == line), None)
        if idx is not None:
            window = rows[max(0, idx - context): idx + context + 1]
            return "\n".join([header, *(t for _, t in window)])
    return ""


def git_diff(workdir: str, base: str, runner=subprocess.run) -> str:
    res = runner(
        ["git", "diff", f"{base}...HEAD"],
        cwd=workdir, capture_output=True, text=True, check=True,
    )
    return res.stdout
