from pr_review.context.discussion import group_threads, load_discussion
from pr_review.context.model import Entry


class FakeGitHub:
    def __init__(self, pages):
        self.pages = pages

    def get_all(self, path):
        return self.pages[path]


def gh():
    return FakeGitHub({
        "issues/7/comments": [
            {"id": 1, "html_url": "u1", "user": {"login": "ada"}, "created_at": "2026-01-02", "body": "Looks good.",
             "author_association": "MEMBER"},
        ],
        "pulls/7/reviews": [
            {"id": 2, "html_url": "u2", "user": {"login": "bot"}, "submitted_at": "2026-01-01", "body": "Verdict."},
            {"id": 3, "html_url": "u3", "user": {"login": "bob"}, "submitted_at": "2026-01-03", "body": ""},
        ],
        "pulls/7/comments": [
            {"id": 10, "html_url": "u10", "user": {"login": "bot"}, "created_at": "2026-01-01",
             "body": "No lock.", "path": "a.tf", "line": 4, "in_reply_to_id": None},
            {"id": 11, "html_url": "u11", "user": {"login": "ada"}, "created_at": "2026-01-02",
             "body": "Done in the next PR.", "path": "a.tf", "line": 4, "in_reply_to_id": 10},
            {"id": 12, "html_url": "u12", "user": {"login": "ada"}, "created_at": "2026-01-02",
             "body": "Outdated.", "path": "b.tf", "line": None, "original_line": 9, "in_reply_to_id": None},
        ],
    })


def test_comments_and_review_bodies_are_merged_in_time_order_and_empty_reviews_dropped():
    comments, _ = load_discussion(gh(), 7, "ada")
    assert [(e.kind, e.id) for e in comments] == [("review", 2), ("comment", 1)]


def test_the_author_is_marked():
    comments, threads = load_discussion(gh(), 7, "ada")
    assert [e.is_author for e in comments] == [False, True]
    assert threads[0].replies[0].is_author is True
    assert threads[0].root.is_author is False


def test_review_comments_group_into_threads_with_path_and_line():
    _, threads = load_discussion(gh(), 7, "ada")
    assert [(t.root.id, [r.id for r in t.replies]) for t in threads] == [(10, [11]), (12, [])]
    assert (threads[0].root.path, threads[0].root.line) == ("a.tf", 4)
    assert threads[1].root.line == 9  # an outdated comment keeps its original line


def test_a_reply_whose_root_is_missing_becomes_a_root():
    orphan = Entry(5, "thread", "u", "x", False, "t", "b", in_reply_to=99)
    assert [t.root.id for t in group_threads([orphan])] == [5]


def test_the_author_association_is_kept_and_defaults_to_empty():
    comments, threads = load_discussion(gh(), 7, "ada")
    assert [e.association for e in comments] == ["", "MEMBER"]
    assert threads[0].root.association == ""
