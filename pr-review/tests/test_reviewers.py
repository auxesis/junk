import pytest

from pr_review.reviewers import available, get_reviewer
from pr_review.reviewers._run import build_review_prompt
from pr_review.review_types import get_review_type


def test_claude_is_registered():
    assert "claude" in available()
    assert get_reviewer("claude").name == "claude"


def test_claude_default_model():
    assert get_reviewer("claude").default_model == "claude-opus-4-8"


def test_unknown_reviewer_raises():
    with pytest.raises(ValueError):
        get_reviewer("nope")


def test_build_review_prompt_includes_context_and_instructions():
    prompt = build_review_prompt(
        owner="org", repo="repo", number=7, base="main",
        payload_path="/tmp/p.json", review_type=get_review_type("test-gap"),
    )
    assert "Repository: org/repo" in prompt
    assert "PR number: 7" in prompt
    assert "origin/main" in prompt
    assert "/tmp/p.json" in prompt
    assert "# Test Coverage Review" in prompt


def test_codex_is_registered():
    assert "codex" in available()
    assert get_reviewer("codex").name == "codex"


def test_codex_default_model():
    assert get_reviewer("codex").default_model == "gpt-5-codex"
