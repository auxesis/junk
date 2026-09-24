import pytest

from pr_review.payload import (
    MAX_INLINE_COMMENTS,
    Comment,
    Payload,
    Source,
    cap_comments,
    parse_payload,
    payload_from_dict,
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


def test_parse_rejects_comment_non_string_body():
    with pytest.raises(ValueError):
        parse_payload('{"body":"b","comments":[{"path":"x.py","line":1,"body":42}]}')


def test_parse_rejects_comment_non_integer_line():
    with pytest.raises(ValueError):
        parse_payload('{"body":"b","comments":[{"path":"x.py","line":"abc","body":"g"}]}')


def test_sources_never_reach_the_github_payload():
    c = Comment("a.py", 3, "gap", sources=[Source("claude", "opus", "test-gap")])
    assert "sources" not in c.to_dict()
    assert "sources" not in Payload(body="b", comments=[c]).to_json()


def test_comment_sources_default_to_empty_and_are_not_shared():
    a, b = Comment("a.py", 1, "x"), Comment("b.py", 2, "y")
    a.sources.append(Source("claude", "m", "t"))
    assert b.sources == []


def test_source_is_hashable_and_compares_by_value():
    assert Source("claude", "m", "t") == Source("claude", "m", "t")
    assert len({Source("claude", "m", "t"), Source("claude", "m", "t")}) == 1


def test_payload_from_dict_matches_parse_payload():
    data = {"body": "b", "comments": [{"path": "x.py", "line": 2, "body": "g"}]}
    p = payload_from_dict(data)
    assert p.body == "b"
    assert p.comments[0].path == "x.py"


def test_payload_from_dict_rejects_a_non_object():
    with pytest.raises(ValueError, match="JSON object"):
        payload_from_dict(["not", "an", "object"])
