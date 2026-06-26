import pytest

from pr_review.prompts import choose_agent_models, choose_review_types, select_from_menu

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


def _scripted(lines):
    it = iter(lines)
    return lambda: next(it)


_DM = {"claude": "claude-opus-4-8", "codex": "gpt-5-codex"}


def test_select_from_menu_by_number_and_name():
    _, w = _sink()
    assert select_from_menu(
        ["claude", "codex"], _reader("1,codex\n"), w, default="claude", what="agent"
    ) == ["claude", "codex"]


def test_select_from_menu_empty_uses_default():
    _, w = _sink()
    assert select_from_menu(
        ["claude", "codex"], _reader("\n"), w, default="claude", what="agent"
    ) == ["claude"]


def test_select_from_menu_rejects_unknown():
    _, w = _sink()
    with pytest.raises(ValueError):
        select_from_menu(["claude"], _reader("nope\n"), w, default="claude", what="agent")


def test_choose_agent_models_defaults():
    _, w = _sink()
    pairs = choose_agent_models(
        ["claude", "codex"], lambda a: _DM[a], _scripted(["\n", "\n"]), w
    )
    assert pairs == [("claude", "claude-opus-4-8")]


def test_choose_agent_models_explicit():
    _, w = _sink()
    pairs = choose_agent_models(
        ["claude", "codex"], lambda a: _DM[a],
        _scripted(["claude,codex\n", "claude-opus-4-8,claude-fable-5\n", "gpt-5\n"]), w,
    )
    assert pairs == [
        ("claude", "claude-opus-4-8"), ("claude", "claude-fable-5"), ("codex", "gpt-5"),
    ]
