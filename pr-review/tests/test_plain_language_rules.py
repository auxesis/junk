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
