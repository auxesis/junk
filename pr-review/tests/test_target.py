import pytest

from pr_review.target import Target, parse_target


def test_parse_pr_url():
    t = parse_target("https://github.com/org/repo/pull/214")
    assert t == Target("org", "repo", 214)


def test_parse_pr_url_trailing_slash():
    t = parse_target("https://github.com/org/repo/pull/214/")
    assert t.number == 214


def test_parse_short_form():
    t = parse_target("org/repo#9")
    assert t == Target("org", "repo", 9)
    assert t.slug == "org/repo"


def test_parse_strips_whitespace():
    assert parse_target("  org/repo#1  ").number == 1


@pytest.mark.parametrize("bad", ["org/repo", "214", "https://example.com/x", "org/repo#"])
def test_parse_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_target(bad)
