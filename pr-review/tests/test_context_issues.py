from pr_review.context.issues import linked_numbers, load_issues


def test_finds_references_and_closing_keywords_once_each():
    body = "Closes #12. Part of #30, see #12 and [#31](https://x/pull/31). Not #7 (itself)."
    assert linked_numbers(body, own=7) == [12, 30, 31]


def test_ignores_colours_headings_and_url_fragments():
    assert linked_numbers("## Heading\ncolour #12ab34 and https://x/y#42", own=1) == []


class FakeGitHub:
    def get(self, path):
        n = int(path.split("/")[1])
        if n == 99:
            raise RuntimeError("404")
        if n == 31:
            return {"number": 31, "title": "A pull request", "state": "open", "pull_request": {}}
        return {"number": n, "title": f"Issue {n}", "state": "open", "body": None}


def test_loads_issues_skips_pull_requests_and_reports_failures():
    issues, failed = load_issues(FakeGitHub(), [12, 31, 99])
    assert [(i.number, i.title, i.body) for i in issues] == [(12, "Issue 12", "")]
    assert failed == [99]
