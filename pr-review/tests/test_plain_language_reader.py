import pytest

from pr_review.payload import Comment
from pr_review.plain_language.reader import build_reader_prompt, parse_reader_result


def test_prompt_shows_each_comment_beside_its_diff_lines():
    prompt = build_reader_prompt(
        payload_path="/tmp/out.json",
        comments=[(0, Comment("a.py", 3, "**Finding.**"), "@@ -1 +1 @@\n+x = 1")],
        body="Verdict: fine.",
    )
    assert "/tmp/out.json" in prompt
    assert "### Comment 0: a.py:3" in prompt
    assert "+x = 1" in prompt
    assert "**Finding.**" in prompt
    assert "Verdict: fine." in prompt
    assert "What should I change?" in prompt
    assert '"blocking"' in prompt and '"minor"' in prompt


def test_prompt_says_when_no_diff_lines_were_found():
    prompt = build_reader_prompt(payload_path="/p", comments=[(0, Comment("a", 1, "x"), "")], body="")
    assert "(no diff lines found)" in prompt


def test_parse_reads_blocking_and_minor_per_comment_and_for_the_body():
    result = parse_reader_result({
        "comments": [{"index": 1, "blocking": ["inert: had to guess"], "minor": ["long"]}],
        "body": {"blocking": [], "minor": ["verdict is vague"]},
    })
    assert result.comments[1].blocking == ["inert: had to guess"]
    assert result.comments[1].minor == ["long"]
    assert result.body.minor == ["verdict is vague"]


def test_parse_ignores_malformed_entries():
    result = parse_reader_result({
        "comments": [{"index": "zero"}, "junk", {"index": 2, "blocking": [3, "real"]}],
    })
    assert list(result.comments) == [2]
    assert result.comments[2].blocking == ["real"]
    assert result.body.blocking == []


def test_parse_rejects_a_non_object():
    with pytest.raises(ValueError):
        parse_reader_result([])
