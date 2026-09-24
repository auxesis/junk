from pr_review.context.model import Entry, Issue, PullRequestContext, StackEntry, Thread
from pr_review.context.render import (
    describe_loaded, describe_stack, prompt_summary, render_context_file, stack_map,
)


def ctx(stack=(), position=None, failed=()):
    root = Entry(10, "thread", "https://x/r10", "bot", False, "t", "No lock.", "a.tf", 4)
    reply = Entry(11, "thread", "https://x/r11", "ada", True, "t", "Done in #8.", "a.tf", 4, 10)
    return PullRequestContext(
        number=7, title="Add widgets", body="Adds widgets.", author="ada",
        issues=[Issue(3, "Widgets are missing", "open", "Please add.")],
        comments=[Entry(1, "comment", "https://x/c1", "ada", True, "t", "Split into #8.")],
        threads=[Thread(root, [reply])],
        stack=list(stack), stack_position=position, failed=list(failed),
    )


EARLIER = StackEntry(6, "Base work", "b6", "merged", "s6", False, 1)
LATER = StackEntry(8, "Locking", "b8", "open", "s8", True, 3)


def test_stack_map_orders_earlier_this_later_and_names_refs():
    text = stack_map(ctx([EARLIER, LATER], (2, 3)))
    assert text.splitlines() == [
        "- #6 Base work (merged, earlier; position 1; ref `refs/stack/6`)",
        "- #7 Add widgets (this pull request, position 2 of 3)",
        "- #8 Locking (open, later; position 3; ref `refs/stack/8`)",
    ]


def test_stack_map_without_a_stack():
    assert stack_map(ctx()) == "This pull request is not part of a stack."


def test_stack_map_without_positions_or_stack_position():
    unpositioned_earlier = StackEntry(6, "Base work", "b6", "merged", "s6", False)
    unpositioned_later = StackEntry(8, "Locking", "b8", "open", "s8", True)
    text = stack_map(ctx([unpositioned_earlier, unpositioned_later]))
    assert text.splitlines() == [
        "- #6 Base work (merged, earlier; ref `refs/stack/6`)",
        "- #7 Add widgets (this pull request)",
        "- #8 Locking (open, later; ref `refs/stack/8`)",
    ]


def test_context_file_has_every_part_with_ids_and_author_marks():
    text = render_context_file(ctx([LATER]))
    for expected in ("# Pull request #7: Add widgets", "## Description", "Adds widgets.",
                     "### #3 Widgets are missing (open)", "comment 1 by ada (author)",
                     "thread 10 by bot — https://x/r10", "on `a.tf:4`", "reply 11 by ada (author)",
                     "## Other pull requests in the stack", "### #8 Locking (open, later)"):
        assert expected in text, expected


def test_context_file_shows_none_for_empty_stack():
    text = render_context_file(ctx())
    assert "## Other pull requests in the stack" in text
    assert "(none)" in text


def test_prompt_summary_has_the_map_description_path_and_both_instructions():
    text = prompt_summary(ctx([LATER]), "/clone/.git/pr-review/pr-context.md")
    assert text.startswith("## Pull request context")
    assert "/clone/.git/pr-review/pr-context.md" in text
    assert "- #8 Locking" in text and "Adds widgets." in text
    assert "Before you report that something is missing" in text
    assert "Before you report anything, read the discussion" in text


def test_describe_stack_and_loaded():
    assert describe_stack(ctx([EARLIER, LATER], (2, 3))) == "Stack: position 2 of 3 (#6, #7, #8)."
    assert describe_stack(ctx([LATER])) == "Stack: 0 earlier and 1 later pull request(s) (#8)."
    assert describe_stack(ctx()) == "Stack: not part of a stack."
    assert describe_loaded(ctx(failed=["issue #9"])) == (
        "Context loaded: the description, 1 linked issue(s) and 3 discussion entries. "
        "Not loaded: issue #9."
    )
