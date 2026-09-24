"""Gather a pull request's context; a part that fails is left out, not fatal."""
from __future__ import annotations

from pr_review.context.discussion import load_discussion
from pr_review.context.issues import linked_numbers, load_issues
from pr_review.context.model import PullRequestContext
from pr_review.context.stack import discover_stack


def gather_context(gh, number: int) -> PullRequestContext:
    pr = gh.get(f"pulls/{number}")
    author = (pr.get("user") or {}).get("login", "")
    body = pr.get("body") or ""
    failed: list[str] = []
    errors: list[str] = []

    try:
        comments, threads = load_discussion(gh, number, author)
    except Exception as e:
        comments, threads = [], []
        failed.append("discussion")
        errors.append(f"discussion ({e})")

    issues, missing = load_issues(gh, linked_numbers(body, number))
    failed += [f"issue #{n}" for n in missing]
    errors += [f"issue #{n}" for n in missing]

    try:
        stack, position = discover_stack(gh, pr)
    except Exception as e:
        stack, position = [], None
        failed.append("stack")
        errors.append(f"stack ({e})")

    return PullRequestContext(
        number=number, title=pr.get("title", ""), body=body, author=author,
        issues=issues, comments=comments, threads=threads,
        stack=stack, stack_position=position, failed=failed, errors=errors,
    )
