import pytest

from pr_review.review_types import available, get_review_type


def test_test_gap_is_registered():
    assert "test-gap" in available()


def test_get_returns_instance_with_name():
    rt = get_review_type("test-gap")
    assert rt.name == "test-gap"


def test_instructions_contain_schema_and_cap():
    text = get_review_type("test-gap").instructions()
    assert "## Output (REQUIRED)" in text
    assert "HARD CAP: 8 inline comments" in text


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        get_review_type("does-not-exist")
