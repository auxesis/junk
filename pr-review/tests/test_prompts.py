import pytest

from pr_review.prompts import choose_review_types

AVAIL = ["infracode", "test-gap"]


def _reader(value):
    return lambda: value


def _sink():
    out = []
    return out, out.append


def test_choose_by_numbers():
    _, w = _sink()
    assert choose_review_types(AVAIL, _reader("1,2\n"), w) == ["infracode", "test-gap"]


def test_choose_by_names():
    _, w = _sink()
    assert choose_review_types(AVAIL, _reader("test-gap\n"), w) == ["test-gap"]


def test_choose_mixed_numbers_and_names():
    _, w = _sink()
    assert choose_review_types(AVAIL, _reader("2, infracode\n"), w) == ["test-gap", "infracode"]


def test_choose_empty_uses_default():
    _, w = _sink()
    assert choose_review_types(AVAIL, _reader("\n"), w, default="test-gap") == ["test-gap"]


def test_choose_dedupes_preserving_order():
    _, w = _sink()
    assert choose_review_types(AVAIL, _reader("test-gap,2\n"), w) == ["test-gap"]


def test_choose_rejects_unknown_name():
    _, w = _sink()
    with pytest.raises(ValueError):
        choose_review_types(AVAIL, _reader("bogus\n"), w)


def test_choose_rejects_out_of_range_number():
    _, w = _sink()
    with pytest.raises(ValueError):
        choose_review_types(AVAIL, _reader("9\n"), w)


def test_choose_writes_numbered_menu():
    out, w = _sink()
    choose_review_types(AVAIL, _reader("1\n"), w)
    text = "".join(out)
    assert "1) infracode" in text and "2) test-gap" in text
