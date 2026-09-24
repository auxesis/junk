"""Everything already written on a pull request, grouped the way GitHub shows it."""
from __future__ import annotations

from pr_review.context.model import Entry, Thread


def _entry(kind: str, raw: dict, author: str) -> Entry:
    login = (raw.get("user") or {}).get("login", "")
    line = raw.get("line") if raw.get("line") is not None else raw.get("original_line")
    return Entry(
        id=raw["id"],
        kind=kind,
        url=raw.get("html_url", ""),
        author=login,
        is_author=login == author,
        created_at=raw.get("created_at") or raw.get("submitted_at") or "",
        body=raw.get("body") or "",
        path=raw.get("path"),
        line=line,
        in_reply_to=raw.get("in_reply_to_id"),
        association=raw.get("author_association") or "",
    )


def group_threads(entries: list[Entry]) -> list[Thread]:
    ids = {e.id for e in entries}
    threads: dict[int, Thread] = {}
    for e in entries:
        if e.in_reply_to is None or e.in_reply_to not in ids:
            threads[e.id] = Thread(root=e, replies=[])
    for e in entries:
        if e.id not in threads:
            threads[e.in_reply_to].replies.append(e)
    return list(threads.values())


def load_discussion(gh, number: int, author: str) -> tuple[list[Entry], list[Thread]]:
    comments = [_entry("comment", c, author) for c in gh.get_all(f"issues/{number}/comments")]
    reviews = [
        _entry("review", r, author) for r in gh.get_all(f"pulls/{number}/reviews")
        if (r.get("body") or "").strip()
    ]
    review_comments = [_entry("thread", c, author) for c in gh.get_all(f"pulls/{number}/comments")]
    return sorted(comments + reviews, key=lambda e: e.created_at), group_threads(review_comments)
