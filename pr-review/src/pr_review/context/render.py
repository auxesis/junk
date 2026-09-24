"""Turn a pull request's context into text for the clone, the prompts and the review."""
from __future__ import annotations

from pr_review.context.model import Entry, PullRequestContext, StackEntry


def _where(e: StackEntry) -> str:
    return "later" if e.later else "earlier"


def stack_map(ctx: PullRequestContext) -> str:
    if not ctx.stack:
        return "This pull request is not part of a stack."
    line = lambda e: f"- #{e.number} {e.title} ({e.state}, {_where(e)}; ref `refs/stack/{e.number}`)"
    return "\n".join(
        [line(e) for e in ctx.stack if not e.later]
        + [f"- #{ctx.number} {ctx.title} (this pull request)"]
        + [line(e) for e in ctx.stack if e.later]
    )


def _heading(label: str, e: Entry) -> str:
    who = f"{e.author} (author)" if e.is_author else e.author
    return f"{label} {e.id} by {who} — {e.url}"


def render_context_file(ctx: PullRequestContext) -> str:
    out = [f"# Pull request #{ctx.number}: {ctx.title}", "", f"Author: {ctx.author}", "",
           "## Stack", "", stack_map(ctx), "", "## Description", "", ctx.body or "(no description)", ""]
    out += ["## Linked issues", ""]
    for i in ctx.issues or []:
        out += [f"### #{i.number} {i.title} ({i.state})", "", i.body, ""]
    if not ctx.issues:
        out += ["(none)", ""]
    out += ["## Discussion", ""]
    for e in ctx.comments:
        out += [f"### {_heading(e.kind, e)}", "", e.body, ""]
    for t in ctx.threads:
        out += [f"### {_heading('thread', t.root)}", f"on `{t.root.path}:{t.root.line}`", "", t.root.body, ""]
        for r in t.replies:
            out += [f"#### {_heading('reply', r)}", "", r.body, ""]
    out += ["## Other pull requests in the stack", ""]
    for e in ctx.stack:
        out += [f"### #{e.number} {e.title} ({e.state}, {_where(e)})", "", e.body, ""]
    return "\n".join(out)


def prompt_summary(ctx: PullRequestContext, context_path: str) -> str:
    return f"""## Pull request context

This pull request's description and stack are below. Its full discussion, linked
issues and the other pull requests in its stack are in: {context_path}

### Stack

{stack_map(ctx)}

### Description

{ctx.body or "(no description)"}

Before you report that something is missing, check the later pull requests in the
stack: `git show refs/stack/<n>:<path>` shows a file as that pull request leaves
it, and `git diff HEAD refs/stack/<n>` shows everything it changes after this one.

Before you report anything, read the discussion in the context file. Do not
report what it already raises, or what the author has already answered.
"""


def describe_stack(ctx: PullRequestContext) -> str:
    if not ctx.stack:
        return "Stack: not part of a stack."
    if ctx.stack_position:
        numbers = sorted([e.number for e in ctx.stack] + [ctx.number])
        pos, size = ctx.stack_position
        return f"Stack: position {pos} of {size} ({', '.join(f'#{n}' for n in numbers)})."
    earlier = sum(1 for e in ctx.stack if not e.later)
    later = len(ctx.stack) - earlier
    return (f"Stack: {earlier} earlier and {later} later pull request(s) "
            f"({', '.join(f'#{e.number}' for e in ctx.stack)}).")


def describe_loaded(ctx: PullRequestContext) -> str:
    entries = len(ctx.comments) + sum(1 + len(t.replies) for t in ctx.threads)
    line = (f"Context loaded: the description, {len(ctx.issues)} linked issue(s) "
            f"and {entries} discussion entries.")
    return line + (f" Not loaded: {', '.join(ctx.failed)}." if ctx.failed else "")
