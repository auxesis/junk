from urllib.parse import quote

from pr_review.context.stack import MAX_DEPTH, discover_stack


def rest_pr(n, head, base, state="open", merged=False):
    return {"number": n, "title": f"PR {n}", "body": f"body {n}", "state": state,
            "merged_at": "2026-01-01" if merged else None,
            "head": {"ref": head, "sha": f"sha{n}"},
            "base": {"ref": base, "repo": {"default_branch": "main", "owner": {"login": "acme"}}}}


class FakeGitHub:
    owner, repo = "acme", "widgets"

    def __init__(self, prs=(), native=None):
        self.prs, self.native, self.paths = list(prs), native, []

    def get_all(self, path):
        self.paths.append(path)
        key, _, value = path.split("?")[1].split("&")[0].partition("=")
        if key == "head":
            return [p for p in self.prs if quote(f"acme:{p['head']['ref']}", safe="") == value]
        return [p for p in self.prs if quote(p["base"]["ref"], safe="") == value]

    def graphql(self, query, **variables):
        return {"data": {"repository": {"pullRequest": {"stack": self.native}}}}


def node(position, n, state="OPEN"):
    return {"position": position, "pullRequest": {
        "number": n, "title": f"PR {n}", "body": "", "state": state, "headRefOid": f"sha{n}"}}


def test_native_stack_uses_github_order_and_position():
    native = {"size": 3, "entries": {"nodes": [node(1, 10, "MERGED"), node(2, 11), node(3, 12, "CLOSED")]}}
    pr = rest_pr(11, "b", "a") | {"stack": {"number": 5, "position": 2, "size": 3}}
    entries, position = discover_stack(FakeGitHub(native=native), pr)
    assert [(e.number, e.later, e.state, e.position) for e in entries] == [
        (10, False, "merged", 1), (12, True, "closed", 3)]
    assert position == (2, 3)


def test_chain_walks_down_to_the_default_branch_and_up_through_children():
    prs = [rest_pr(1, "one", "main"), rest_pr(2, "two", "one"), rest_pr(3, "three", "two", merged=True, state="closed"),
           rest_pr(4, "four", "three")]
    entries, position = discover_stack(FakeGitHub(prs), prs[1])
    assert [(e.number, e.later, e.state) for e in entries] == [(1, False, "open"), (3, True, "merged"), (4, True, "open")]
    assert position is None


def test_chain_keeps_every_branch_of_a_tree():
    prs = [rest_pr(1, "one", "main"), rest_pr(2, "two", "one"), rest_pr(3, "three", "one")]
    entries, _ = discover_stack(FakeGitHub(prs), prs[0])
    assert sorted(e.number for e in entries if e.later) == [2, 3]


def test_a_pull_request_on_the_default_branch_with_no_children_has_no_stack():
    pr = rest_pr(1, "one", "main")
    assert discover_stack(FakeGitHub([pr]), pr) == ([], None)


def test_the_walk_stops_at_the_depth_limit():
    prs = [rest_pr(1, "b1", "main")] + [rest_pr(i, f"b{i}", f"b{i-1}") for i in range(2, 30)]
    entries, _ = discover_stack(FakeGitHub(prs), prs[0])
    assert len(entries) == MAX_DEPTH


def test_branch_names_are_url_encoded():
    gh = FakeGitHub([])
    discover_stack(gh, rest_pr(1, "feature/x y", "main"))
    assert gh.paths == ["pulls?base=feature%2Fx%20y&state=all"]


def test_a_failed_native_stack_falls_back_to_the_branch_chain():
    class NoGraphQL(FakeGitHub):
        def graphql(self, query, **variables):
            raise RuntimeError("stack field unknown")

    prs = [rest_pr(11, "b", "main"), rest_pr(12, "c", "b")]
    pr = prs[0] | {"stack": {"number": 5, "position": 1, "size": 2}}
    entries, position = discover_stack(NoGraphQL(prs), pr)
    assert [(e.number, e.later) for e in entries] == [(12, True)]
    assert position is None
