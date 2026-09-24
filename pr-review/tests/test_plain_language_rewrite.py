import pytest

from pr_review.payload import Comment
from pr_review.plain_language.rewrite import (
    RewriteItem, build_rewrite_prompt, guard, parse_rewrite_result,
)

ORIGINAL = "**The loader is inert.**\n\nSee `load()`.\n\n```py\nload(retry=True)\n```"


def test_prompt_lists_items_with_problems_and_the_writing_rules():
    prompt = build_rewrite_prompt(
        payload_path="/tmp/o.json",
        items=[RewriteItem(2, Comment("a.py", 7, ORIGINAL), "@@ +7 @@\n+load()", ['"inert": say "does nothing"'])],
        body="Verdict.", body_problems=[],
    )
    assert "/tmp/o.json" in prompt
    assert "### Comment 2: a.py:7" in prompt
    assert '"inert": say "does nothing"' in prompt
    assert "## How to write each comment (REQUIRED)" in prompt
    assert "write null" in prompt


def test_prompt_includes_the_body_when_it_has_problems():
    prompt = build_rewrite_prompt(payload_path="/p", items=[], body="LGTM, ship it.",
                                  body_problems=["verdict is vague"])
    assert "LGTM, ship it." in prompt
    assert "verdict is vague" in prompt


def test_parse_reads_bodies_by_index_and_the_review_body():
    bodies, body = parse_rewrite_result(
        {"comments": [{"index": 2, "body": "new"}, {"index": "x", "body": "bad"}], "body": "B"}
    )
    assert bodies == {2: "new"}
    assert body == "B"


def test_parse_treats_a_missing_or_null_body_as_none():
    assert parse_rewrite_result({"comments": []}) == ({}, None)
    assert parse_rewrite_result({"comments": [], "body": None}) == ({}, None)


def test_parse_rejects_a_non_object():
    with pytest.raises(ValueError):
        parse_rewrite_result("nope")


def test_guard_accepts_a_rewrite_that_keeps_code():
    new = "**The loader does nothing.**\n\n**Impact:** x\n\n**Fix:** Call `load()`:\n\n```py\nload(retry=True)\n```"
    assert guard(ORIGINAL, new) is None


def test_guard_rejects_a_changed_code_block():
    new = ORIGINAL.replace("retry=True", "retry=False")
    assert guard(ORIGINAL, new) == "changed a code block"


def test_guard_rejects_a_dropped_inline_code_span():
    new = ORIGINAL.replace("See `load()`.", "See the loader.")
    assert guard(ORIGINAL, new) == "dropped `load()`"


def test_guard_rejects_an_empty_rewrite():
    assert guard(ORIGINAL, "   ") == "is empty"
