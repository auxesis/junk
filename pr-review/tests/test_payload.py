import pytest

from pr_review.payload import (
    MAX_INLINE_COMMENTS,
    Comment,
    Payload,
    cap_comments,
    parse_payload,
)


def test_payload_to_dict_roundtrip_shape():
    p = Payload(body="hi", comments=[Comment("a.py", 3, "gap")])
    d = p.to_dict()
    assert d["event"] == "COMMENT"
    assert d["body"] == "hi"
    assert d["comments"] == [{"path": "a.py", "line": 3, "side": "RIGHT", "body": "gap"}]


def test_parse_valid_payload():
    raw = '{"event":"COMMENT","body":"b","comments":[{"path":"x.py","line":2,"side":"RIGHT","body":"g"}]}'
    p = parse_payload(raw)
    assert p.body == "b"
    assert p.comments[0].path == "x.py"
    assert p.comments[0].line == 2


def test_parse_missing_comments_defaults_empty():
    assert parse_payload('{"body":"only body"}').comments == []


def test_parse_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_payload("not json")


def test_parse_rejects_missing_body():
    with pytest.raises(ValueError):
        parse_payload('{"comments":[]}')


def test_parse_rejects_comment_missing_path():
    with pytest.raises(ValueError):
        parse_payload('{"body":"b","comments":[{"line":1,"body":"g"}]}')


def test_cap_splits_at_limit():
    comments = [Comment("f", i, "g") for i in range(10)]
    kept, overflow = cap_comments(comments)
    assert len(kept) == MAX_INLINE_COMMENTS
    assert len(overflow) == 2
