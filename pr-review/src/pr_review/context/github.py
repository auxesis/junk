"""A thin `gh api` wrapper, so context loading can be tested with a fake."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence

Runner = Callable[..., subprocess.CompletedProcess]


def _run(cmd: Sequence[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), check=True, text=True, capture_output=True, **kw)


class GitHub:
    def __init__(self, owner: str, repo: str, runner: Runner = _run):
        self.owner = owner
        self.repo = repo
        self._runner = runner

    def _path(self, path: str) -> str:
        return f"repos/{self.owner}/{self.repo}/{path}"

    def get(self, path: str) -> object:
        return json.loads(self._runner(["gh", "api", self._path(path)]).stdout)

    def get_all(self, path: str) -> list:
        pages = json.loads(self._runner(["gh", "api", "--paginate", "--slurp", self._path(path)]).stdout)
        return [item for page in pages for item in page]

    def graphql(self, query: str, **variables: object) -> object:
        cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            flag = "-F" if isinstance(value, int) and not isinstance(value, bool) else "-f"
            cmd += [flag, f"{key}={value}"]
        return json.loads(self._runner(cmd).stdout)
