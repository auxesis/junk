import pytest

from pr_review.reviewers import available, get_reviewer
from pr_review.reviewers.claude import ClaudeReviewer
from pr_review.review_types import get_review_type


def test_claude_is_registered():
    assert "claude" in available()
    assert get_reviewer("claude").name == "claude"


def test_unknown_reviewer_raises():
    with pytest.raises(ValueError):
        get_reviewer("nope")


def test_build_prompt_includes_context_and_instructions():
    prompt = ClaudeReviewer().build_prompt(
        owner="org", repo="repo", number=7, base="main",
        payload_path="/tmp/p.json", review_type=get_review_type("test-gap"),
    )
    assert "Repository: org/repo" in prompt
    assert "PR number: 7" in prompt
    assert "origin/main" in prompt
    assert "/tmp/p.json" in prompt
    assert "# Test Coverage Review" in prompt  # instructions appended
