from pr_review.plain_language.rules import load_rules, writing_rules_block


def test_rules_load_with_the_spec_thresholds_and_labels():
    rules = load_rules()
    assert rules.sentence_minor_words == 25
    assert rules.sentence_blocking_words == 35
    assert rules.labels == {"impact": "Impact", "evidence": "Evidence", "fix": "Fix"}
    assert rules.required_labels == ("impact", "fix")
    assert rules.urgency["block"] == "Fix before merge"


def test_every_blocking_word_matches_its_own_display_word():
    for w in load_rules().blocking_words:
        assert w.pattern.search(w.word), w.word
        assert w.instead


def test_surfaced_bans_the_verb_but_not_the_noun():
    rules = load_rules()
    word = next(w for w in rules.blocking_words if w.word == "surfaced")
    assert word.pattern.search("this bug surfaced in prod")
    assert word.pattern.search("errors surfacing in the log")
    assert not word.pattern.search("the API surfaces three methods")


def test_repo_terms_are_not_on_the_list():
    rules = load_rules()
    for term in ("drift", "root", "state lock"):
        assert not any(w.pattern.search(term) for w in rules.blocking_words), term


def test_the_block_names_every_label_threshold_word_and_urgency_phrase():
    rules, block = load_rules(), writing_rules_block()
    assert block.startswith("## How to write each comment (REQUIRED)")
    for label in rules.labels.values():
        assert f"**{label}:**" in block
    assert "25 words" in block and "35 words" in block
    for w in rules.blocking_words:
        assert f'"{w.word}"' in block
    for phrase in rules.urgency.values():
        assert f'"{phrase}:"' in block


def test_the_block_itself_writes_negatives_in_full():
    import re
    # The quoted examples of what not to write are the only contractions allowed.
    text = re.sub(r'"[^"]*"', "", writing_rules_block())
    assert not re.search(r"\b\w+n['']t\b", text)


import pytest

from pr_review.review_types import available, get_review_type


@pytest.mark.parametrize("name", available())
def test_every_review_type_includes_the_writing_rules(name):
    assert get_review_type(name).instructions().endswith(writing_rules_block())


@pytest.mark.parametrize("name", available())
def test_no_review_type_keeps_the_old_comment_shape(name):
    text = get_review_type(name).instructions()
    assert "## Each inline comment must be self-contained" not in text
    assert "**block:**" not in text
    assert "**Gap:**" not in text
    assert "**Impact:**" in text and "**Fix:**" in text
