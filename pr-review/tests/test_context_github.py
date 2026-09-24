import json
import subprocess

from pr_review.context.github import GitHub


class Runner:
    def __init__(self, stdout):
        self.stdout, self.calls = stdout, []

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout=self.stdout, stderr="")


def test_get_prefixes_the_repository_path():
    runner = Runner('{"number": 7}')
    assert GitHub("acme", "widgets", runner=runner).get("pulls/7") == {"number": 7}
    assert runner.calls == [["gh", "api", "repos/acme/widgets/pulls/7"]]


def test_get_all_paginates_and_flattens_pages():
    runner = Runner(json.dumps([[{"id": 1}], [{"id": 2}]]))
    assert GitHub("acme", "widgets", runner=runner).get_all("issues/7/comments") == [{"id": 1}, {"id": 2}]
    assert runner.calls == [["gh", "api", "--paginate", "--slurp", "repos/acme/widgets/issues/7/comments"]]


def test_graphql_passes_the_query_and_typed_variables():
    runner = Runner('{"data": {}}')
    GitHub("acme", "widgets", runner=runner).graphql("query { x }", n=7, o="acme")
    assert runner.calls == [["gh", "api", "graphql", "-f", "query=query { x }", "-F", "n=7", "-F", "o=acme"]]
