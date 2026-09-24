# Pull Request Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pr-review knows what the people on a pull request know — its description, linked GitHub issues, discussion, and the other pull requests in its stack — and does not post findings a later pull request fixes, the discussion already raised, or the author answered; a finding that proves an author's answer wrong is posted as a reply in that thread.

**Architecture:** A new `pr_review.context` package gathers the context through `gh` before the clone, discovers the stack (GitHub's native stack, else the base-branch chain), and renders a context file into the clone's `.git/pr-review/`. The clone fetches every stack pull request as `refs/stack/<n>`. Reviewers and the synthesis judge get a short summary plus the file path. After collation a context filter (one agent call) returns a verdict per finding; code validates each verdict. Replies become a new `Payload.replies` list, go through the plain-language stage and attribution like comments, and post one by one after the review.

**Tech Stack:** Python 3.14, stdlib only, pytest, `uv`, `gh` ≥ 2.48 (`--paginate --slurp`).

**Spec:** `docs/superpowers/specs/2026-09-24-pull-request-context-design.md` (read it before starting). Glossary: `CONTEXT.md`. Decision record: `docs/adr/0002-post-replies-in-threads-not-atomically.md`.

**Depends on:** `docs/superpowers/plans/2026-09-24-plain-language-and-attribution.md` being fully implemented first. This plan uses `Source`, `run_cli_json`, `PlainLanguageStage`, `check_payload`, `RunRecord`, `finalize` and `attribution` from it.

## Global Constraints

- Python `>=3.14`; no new runtime dependencies.
- No test runs a model, `git`, `gh` or the network. Every `gh`/`git` call goes through an injected runner or a fake `GitHub` object (`CLAUDE.md`, "Testing principle").
- Run tests with `uv run pytest` from `pr-review/`.
- Stack walk depth limit: **10** in each direction.
- Reply cap: **3**, separate from the 8 inline comments.
- Context file path: `<clone>/.git/pr-review/pr-context.md`.
- Stack refs: `refs/stack/<n>`, fetched with `git fetch --filter=blob:none origin +refs/pull/<n>/head:refs/stack/<n>`.
- A closed pull request that was not merged never counts as a fix.
- Only the pull request author's login counts as "the author" (their agents post under it).
- Verdict reasons: `fixed-later`, `already-raised`, `answered`.
- Gathering context and filtering must never stop a review from being produced: every failure becomes a stderr warning.
- Text pr-review shows a reader writes negatives in full.
- Test fixtures use invented repositories, logins and numbers.
- `CLAUDE.md`'s **Test suite** walkthrough is updated in the last task.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `src/pr_review/context/__init__.py` | create | package marker |
| `src/pr_review/context/model.py` | create | `Entry`, `Thread`, `Issue`, `StackEntry`, `PullRequestContext` |
| `src/pr_review/context/github.py` | create | `GitHub`: `get`, `get_all`, `graphql` over `gh api` |
| `src/pr_review/context/discussion.py` | create | load comments, review bodies and threads; mark the author |
| `src/pr_review/context/issues.py` | create | find `#N` in the description; load the ones that are issues |
| `src/pr_review/context/stack.py` | create | `discover_stack`: native stack, else base-branch chain |
| `src/pr_review/context/gather.py` | create | `gather_context`: all of the above, failures recorded not raised |
| `src/pr_review/context/render.py` | create | stack map, context file, prompt summary, details-block lines |
| `src/pr_review/context/filter.py` | create | filter prompt, verdict validation, `ContextFilter` |
| `src/pr_review/payload.py` | modify | `Reply`; `Payload.replies` |
| `src/pr_review/checkout.py` | modify | fetch stack refs; `write_context_file` |
| `src/pr_review/reviewers/_run.py`, `reviewers/base.py` | modify | optional context summary in the review prompt |
| `src/pr_review/orchestrator.py` | modify | pass the summary to reviewers |
| `src/pr_review/synthesis.py` | modify | pass the summary to the judge |
| `src/pr_review/plain_language/stage.py` | modify | check and rewrite replies too |
| `src/pr_review/attribution.py` | modify | reply footers; stack, context and "not posted" lines |
| `src/pr_review/output.py` | modify | post the review, then each reply; files and retry hints |
| `src/pr_review/cli.py` | modify | flags; wire it all together |
| `tests/test_context_*.py`, others | create/modify | one test file per new module |

---

### Task 1: Context model and the `gh` wrapper

**Files:**
- Create: `src/pr_review/context/__init__.py`, `src/pr_review/context/model.py`, `src/pr_review/context/github.py`
- Test: `tests/test_context_github.py`

**Interfaces:**
- Produces (`model.py`):
  - `Entry(id: int, kind: str, url: str, author: str, is_author: bool, created_at: str, body: str, path: str | None = None, line: int | None = None, in_reply_to: int | None = None)` — frozen; `kind` is `"comment"`, `"review"` or `"thread"`.
  - `Thread(root: Entry, replies: list[Entry])`
  - `Issue(number: int, title: str, state: str, body: str)` — frozen
  - `StackEntry(number: int, title: str, body: str, state: str, head_sha: str, later: bool, position: int | None = None)` — frozen; `state` is `"open"`, `"merged"` or `"closed"`.
  - `PullRequestContext(number: int, title: str, body: str, author: str, issues: list[Issue], comments: list[Entry], threads: list[Thread], stack: list[StackEntry], stack_position: tuple[int, int] | None, failed: list[str])`
- Produces (`github.py`): `GitHub(owner: str, repo: str, runner=_run)` with `.owner`, `.repo`, `.get(path) -> object`, `.get_all(path) -> list`, `.graphql(query: str, **variables) -> object`. `path` is relative to `repos/{owner}/{repo}/`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_context_github.py`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_context_github.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement.** `src/pr_review/context/__init__.py`:

```python
"""What pr-review knows about a pull request beyond its diff."""
```

`src/pr_review/context/model.py`:

```python
"""The pull request context: description, discussion, linked issues and stack."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    id: int
    kind: str
    url: str
    author: str
    is_author: bool
    created_at: str
    body: str
    path: str | None = None
    line: int | None = None
    in_reply_to: int | None = None


@dataclass
class Thread:
    root: Entry
    replies: list[Entry]


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    state: str
    body: str


@dataclass(frozen=True)
class StackEntry:
    number: int
    title: str
    body: str
    state: str
    head_sha: str
    later: bool
    position: int | None = None


@dataclass
class PullRequestContext:
    number: int
    title: str
    body: str
    author: str
    issues: list[Issue]
    comments: list[Entry]
    threads: list[Thread]
    stack: list[StackEntry]
    stack_position: tuple[int, int] | None
    failed: list[str]
```

`src/pr_review/context/github.py`:

```python
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
            cmd += ["-F", f"{key}={value}"]
        return json.loads(self._runner(cmd).stdout)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_context_github.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/context tests/test_context_github.py
git commit -m "feat(pr-review): add the pull request context model and a gh wrapper"
```

---

### Task 2: Discussion

**Files:**
- Create: `src/pr_review/context/discussion.py`
- Test: `tests/test_context_discussion.py`

**Interfaces:**
- Consumes: `Entry`, `Thread` (Task 1); a `gh` object with `.get_all(path)`.
- Produces:
  - `group_threads(entries: list[Entry]) -> list[Thread]` — replies attach to the root named by `in_reply_to`; a reply whose root is missing becomes a root.
  - `load_discussion(gh, number: int, author: str) -> tuple[list[Entry], list[Thread]]` — issue comments and non-empty review bodies (sorted by `created_at`), and review threads.

- [ ] **Step 1: Write the failing tests** — create `tests/test_context_discussion.py`:

```python
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
            {"id": 1, "html_url": "u1", "user": {"login": "ada"}, "created_at": "2026-01-02", "body": "Looks good."},
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_context_discussion.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/context/discussion.py`**:

```python
"""Everything already written on a pull request, grouped the way GitHub shows it."""
from __future__ import annotations

from pr_review.context.model import Entry, Thread


def _entry(kind: str, raw: dict, author: str) -> Entry:
    login = (raw.get("user") or {}).get("login", "")
    line = raw.get("line") if raw.get("line") is not None else raw.get("original_line")
    return Entry(
        id=raw["id"],
        kind=kind,
        url=raw.get("html_url", ""),
        author=login,
        is_author=login == author,
        created_at=raw.get("created_at") or raw.get("submitted_at") or "",
        body=raw.get("body") or "",
        path=raw.get("path"),
        line=line,
        in_reply_to=raw.get("in_reply_to_id"),
    )


def group_threads(entries: list[Entry]) -> list[Thread]:
    ids = {e.id for e in entries}
    threads: dict[int, Thread] = {}
    for e in entries:
        if e.in_reply_to is None or e.in_reply_to not in ids:
            threads[e.id] = Thread(root=e, replies=[])
    for e in entries:
        if e.id not in threads:
            threads[e.in_reply_to].replies.append(e)
    return list(threads.values())


def load_discussion(gh, number: int, author: str) -> tuple[list[Entry], list[Thread]]:
    comments = [_entry("comment", c, author) for c in gh.get_all(f"issues/{number}/comments")]
    reviews = [
        _entry("review", r, author) for r in gh.get_all(f"pulls/{number}/reviews")
        if (r.get("body") or "").strip()
    ]
    review_comments = [_entry("thread", c, author) for c in gh.get_all(f"pulls/{number}/comments")]
    return sorted(comments + reviews, key=lambda e: e.created_at), group_threads(review_comments)
```

(GitHub's `in_reply_to_id` always names the thread's first comment, so one level of grouping is enough.)

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_context_discussion.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/context/discussion.py tests/test_context_discussion.py
git commit -m "feat(pr-review): load a pull request's discussion and mark the author"
```

---

### Task 3: Linked issues

**Files:**
- Create: `src/pr_review/context/issues.py`
- Test: `tests/test_context_issues.py`

**Interfaces:**
- Consumes: `Issue` (Task 1); a `gh` object with `.get(path)`.
- Produces:
  - `linked_numbers(body: str, own: int) -> list[int]` — every `#N` in order, without duplicates or `own`.
  - `load_issues(gh, numbers: list[int]) -> tuple[list[Issue], list[int]]` — the issues, and the numbers that failed to load. Pull requests are skipped silently.

- [ ] **Step 1: Write the failing tests** — create `tests/test_context_issues.py`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_context_issues.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/context/issues.py`**:

```python
"""GitHub issues the description links to (not Linear or other trackers)."""
from __future__ import annotations

import re

from pr_review.context.model import Issue

# A `#` preceded by a word character or `/` is a colour or a URL fragment.
_REF = re.compile(r"(?<![\w/&])#(\d+)\b")


def linked_numbers(body: str, own: int) -> list[int]:
    found: list[int] = []
    for m in _REF.finditer(body or ""):
        n = int(m.group(1))
        if n != own and n not in found:
            found.append(n)
    return found


def load_issues(gh, numbers: list[int]) -> tuple[list[Issue], list[int]]:
    issues: list[Issue] = []
    failed: list[int] = []
    for n in numbers:
        try:
            data = gh.get(f"issues/{n}")
        except Exception:
            failed.append(n)
            continue
        if "pull_request" in data:
            continue
        issues.append(Issue(n, data.get("title", ""), data.get("state", ""), data.get("body") or ""))
    return issues, failed
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_context_issues.py -v`
Expected: all PASS. (`https://x/y#42`: the `#` follows `y`, a word character, so it is skipped.)

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/context/issues.py tests/test_context_issues.py
git commit -m "feat(pr-review): load the GitHub issues a pull request links to"
```

---

### Task 4: Stack discovery

**Files:**
- Create: `src/pr_review/context/stack.py`
- Test: `tests/test_context_stack.py`

**Interfaces:**
- Consumes: `StackEntry` (Task 1); a `gh` object with `.owner`, `.repo`, `.get_all(path)`, `.graphql(query, **vars)`.
- Produces:
  - `MAX_DEPTH = 10`
  - `STACK_QUERY: str` — the GraphQL query.
  - `discover_stack(gh, pr: dict) -> tuple[list[StackEntry], tuple[int, int] | None]` — `pr` is the REST `pulls/{n}` object. Returns the other pull requests (earlier ones bottom-up, then later ones) and `(position, size)` for a native stack, else `None`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_context_stack.py`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_context_stack.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/context/stack.py`**:

```python
"""Find the other pull requests in a pull request's stack."""
from __future__ import annotations

from urllib.parse import quote

from pr_review.context.model import StackEntry

MAX_DEPTH = 10

STACK_QUERY = """query($o: String!, $r: String!, $n: Int!) {
  repository(owner: $o, name: $r) { pullRequest(number: $n) { stack {
    size entries(first: 100) { nodes { position pullRequest {
      number title body state headRefOid } } } } } } }"""


def _rest_state(pr: dict) -> str:
    if pr.get("merged_at"):
        return "merged"
    return "open" if pr.get("state") == "open" else "closed"


def _rest_entry(pr: dict, later: bool) -> StackEntry:
    return StackEntry(pr["number"], pr.get("title", ""), pr.get("body") or "", _rest_state(pr),
                      pr["head"]["sha"], later)


def _native(gh, number: int) -> tuple[list[StackEntry], tuple[int, int] | None]:
    data = gh.graphql(STACK_QUERY, o=gh.owner, r=gh.repo, n=number)
    stack = data["data"]["repository"]["pullRequest"]["stack"]
    nodes = sorted(stack["entries"]["nodes"], key=lambda node: node["position"])
    own = next(node["position"] for node in nodes if node["pullRequest"]["number"] == number)
    entries = [
        StackEntry(p["number"], p.get("title", ""), p.get("body") or "", p["state"].lower(),
                   p["headRefOid"], node["position"] > own, node["position"])
        for node in nodes if (p := node["pullRequest"])["number"] != number
    ]
    return entries, (own, stack["size"])


def _chain(gh, pr: dict) -> list[StackEntry]:
    seen = {pr["number"]}
    earlier: list[StackEntry] = []
    base = pr["base"]["ref"]
    default = pr["base"]["repo"]["default_branch"]
    owner = pr["base"]["repo"]["owner"]["login"]
    while base != default and len(earlier) < MAX_DEPTH:
        below = [p for p in gh.get_all(f"pulls?head={quote(f'{owner}:{base}', safe='')}&state=all")
                 if p["number"] not in seen]
        if not below:
            break
        seen.add(below[0]["number"])
        earlier.append(_rest_entry(below[0], later=False))
        base = below[0]["base"]["ref"]

    later: list[StackEntry] = []
    queue = [(pr["head"]["ref"], 0)]
    while queue:
        head, depth = queue.pop(0)
        if depth >= MAX_DEPTH:
            continue
        for p in gh.get_all(f"pulls?base={quote(head, safe='')}&state=all"):
            if p["number"] in seen or len(later) >= MAX_DEPTH:
                continue
            seen.add(p["number"])
            later.append(_rest_entry(p, later=True))
            queue.append((p["head"]["ref"], depth + 1))
    return list(reversed(earlier)) + later


def discover_stack(gh, pr: dict) -> tuple[list[StackEntry], tuple[int, int] | None]:
    native = pr.get("stack")
    if isinstance(native, dict) and native.get("size"):
        return _native(gh, pr["number"])
    return _chain(gh, pr), None
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_context_stack.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/context/stack.py tests/test_context_stack.py
git commit -m "feat(pr-review): discover a pull request's stack, native or by base branch"
```

---

### Task 5: Gather the whole context

**Files:**
- Create: `src/pr_review/context/gather.py`
- Test: `tests/test_context_gather.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `gather_context(gh, number: int) -> PullRequestContext`. Raises only if `pulls/{number}` itself cannot be read; any other part that fails is left out and named in `failed`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_context_gather.py`:

```python
import pytest

from pr_review.context.gather import gather_context

PR = {"number": 7, "title": "Add widgets", "body": "Fixes #3.", "user": {"login": "ada"},
      "head": {"ref": "w", "sha": "s7"},
      "base": {"ref": "main", "repo": {"default_branch": "main", "owner": {"login": "acme"}}}}


class FakeGitHub:
    owner, repo = "acme", "widgets"

    def __init__(self, broken=()):
        self.broken = set(broken)

    def get(self, path):
        if path in self.broken:
            raise RuntimeError(f"{path} failed")
        if path == "pulls/7":
            return PR
        return {"number": 3, "title": "Widgets are missing", "state": "open", "body": "Please add."}

    def get_all(self, path):
        if path.split("?")[0] in self.broken or path in self.broken:
            raise RuntimeError(f"{path} failed")
        return []

    def graphql(self, query, **v):
        raise AssertionError("no native stack here")


def test_gathers_description_issues_and_empty_discussion():
    ctx = gather_context(FakeGitHub(), 7)
    assert (ctx.number, ctx.title, ctx.author) == (7, "Add widgets", "ada")
    assert [i.number for i in ctx.issues] == [3]
    assert ctx.stack == [] and ctx.stack_position is None
    assert ctx.failed == []


def test_a_failed_part_is_left_out_and_named():
    ctx = gather_context(FakeGitHub(broken={"issues/7/comments", "issues/3"}), 7)
    assert ctx.comments == [] and ctx.threads == []
    assert ctx.issues == []
    assert any(f.startswith("discussion") for f in ctx.failed)
    assert "issue #3" in ctx.failed


def test_a_failed_pull_request_read_raises():
    with pytest.raises(RuntimeError):
        gather_context(FakeGitHub(broken={"pulls/7"}), 7)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_context_gather.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/context/gather.py`**:

```python
"""Gather a pull request's context; a part that fails is left out, not fatal."""
from __future__ import annotations

from pr_review.context.discussion import load_discussion
from pr_review.context.issues import linked_numbers, load_issues
from pr_review.context.model import PullRequestContext
from pr_review.context.stack import discover_stack


def gather_context(gh, number: int) -> PullRequestContext:
    pr = gh.get(f"pulls/{number}")
    author = (pr.get("user") or {}).get("login", "")
    body = pr.get("body") or ""
    failed: list[str] = []

    try:
        comments, threads = load_discussion(gh, number, author)
    except Exception as e:
        comments, threads = [], []
        failed.append(f"discussion ({e})")

    issues, missing = load_issues(gh, linked_numbers(body, number))
    failed += [f"issue #{n}" for n in missing]

    try:
        stack, position = discover_stack(gh, pr)
    except Exception as e:
        stack, position = [], None
        failed.append(f"stack ({e})")

    return PullRequestContext(
        number=number, title=pr.get("title", ""), body=body, author=author,
        issues=issues, comments=comments, threads=threads,
        stack=stack, stack_position=position, failed=failed,
    )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_context_gather.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/context/gather.py tests/test_context_gather.py
git commit -m "feat(pr-review): gather a pull request's context, leaving out parts that fail"
```

---

### Task 6: Render the context

**Files:**
- Create: `src/pr_review/context/render.py`
- Test: `tests/test_context_render.py`

**Interfaces:**
- Consumes: `PullRequestContext` and friends (Task 1).
- Produces:
  - `stack_map(ctx) -> str`
  - `render_context_file(ctx) -> str`
  - `prompt_summary(ctx, context_path: str) -> str` — starts with `## Pull request context`; contains both reviewer instructions.
  - `describe_stack(ctx) -> str` and `describe_loaded(ctx) -> str` — one line each, for the details block.

- [ ] **Step 1: Write the failing tests** — create `tests/test_context_render.py`:

```python
from pr_review.context.model import Entry, Issue, PullRequestContext, StackEntry, Thread
from pr_review.context.render import (
    describe_loaded, describe_stack, prompt_summary, render_context_file, stack_map,
)


def ctx(stack=(), position=None, failed=()):
    root = Entry(10, "thread", "https://x/r10", "bot", False, "t", "No lock.", "a.tf", 4)
    reply = Entry(11, "thread", "https://x/r11", "ada", True, "t", "Done in #8.", "a.tf", 4, 10)
    return PullRequestContext(
        number=7, title="Add widgets", body="Adds widgets.", author="ada",
        issues=[Issue(3, "Widgets are missing", "open", "Please add.")],
        comments=[Entry(1, "comment", "https://x/c1", "ada", True, "t", "Split into #8.")],
        threads=[Thread(root, [reply])],
        stack=list(stack), stack_position=position, failed=list(failed),
    )


EARLIER = StackEntry(6, "Base work", "b6", "merged", "s6", False, 1)
LATER = StackEntry(8, "Locking", "b8", "open", "s8", True, 3)


def test_stack_map_orders_earlier_this_later_and_names_refs():
    text = stack_map(ctx([EARLIER, LATER], (2, 3)))
    assert text.splitlines() == [
        "- #6 Base work (merged, earlier; ref `refs/stack/6`)",
        "- #7 Add widgets (this pull request)",
        "- #8 Locking (open, later; ref `refs/stack/8`)",
    ]


def test_stack_map_without_a_stack():
    assert stack_map(ctx()) == "This pull request is not part of a stack."


def test_context_file_has_every_part_with_ids_and_author_marks():
    text = render_context_file(ctx([LATER]))
    for expected in ("# Pull request #7: Add widgets", "## Description", "Adds widgets.",
                     "### #3 Widgets are missing (open)", "comment 1 by ada (author)",
                     "thread 10 by bot — https://x/r10", "on `a.tf:4`", "reply 11 by ada (author)",
                     "## Other pull requests in the stack", "### #8 Locking (open, later)"):
        assert expected in text, expected


def test_prompt_summary_has_the_map_description_path_and_both_instructions():
    text = prompt_summary(ctx([LATER]), "/clone/.git/pr-review/pr-context.md")
    assert text.startswith("## Pull request context")
    assert "/clone/.git/pr-review/pr-context.md" in text
    assert "- #8 Locking" in text and "Adds widgets." in text
    assert "Before you report that something is missing" in text
    assert "Before you report anything, read the discussion" in text


def test_describe_stack_and_loaded():
    assert describe_stack(ctx([EARLIER, LATER], (2, 3))) == "Stack: position 2 of 3 (#6, #7, #8)."
    assert describe_stack(ctx([LATER])) == "Stack: 0 earlier and 1 later pull request(s) (#8)."
    assert describe_stack(ctx()) == "Stack: not part of a stack."
    assert describe_loaded(ctx(failed=["issue #9"])) == (
        "Context loaded: the description, 1 linked issue(s) and 3 discussion entries. "
        "Not loaded: issue #9."
    )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_context_render.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/context/render.py`**:

```python
"""Turn a pull request's context into text for the clone, the prompts and the review."""
from __future__ import annotations

from pr_review.context.model import Entry, PullRequestContext, StackEntry


def _where(e: StackEntry) -> str:
    return "later" if e.later else "earlier"


def stack_map(ctx: PullRequestContext) -> str:
    if not ctx.stack:
        return "This pull request is not part of a stack."
    line = lambda e: f"- #{e.number} {e.title} ({e.state}, {_where(e)}; ref `refs/stack/{e.number}`)"
    return "\n".join(
        [line(e) for e in ctx.stack if not e.later]
        + [f"- #{ctx.number} {ctx.title} (this pull request)"]
        + [line(e) for e in ctx.stack if e.later]
    )


def _heading(label: str, e: Entry) -> str:
    who = f"{e.author} (author)" if e.is_author else e.author
    return f"{label} {e.id} by {who} — {e.url}"


def render_context_file(ctx: PullRequestContext) -> str:
    out = [f"# Pull request #{ctx.number}: {ctx.title}", "", f"Author: {ctx.author}", "",
           "## Stack", "", stack_map(ctx), "", "## Description", "", ctx.body or "(no description)", ""]
    out += ["## Linked issues", ""]
    for i in ctx.issues or []:
        out += [f"### #{i.number} {i.title} ({i.state})", "", i.body, ""]
    if not ctx.issues:
        out += ["(none)", ""]
    out += ["## Discussion", ""]
    for e in ctx.comments:
        out += [f"### {_heading(e.kind, e)}", "", e.body, ""]
    for t in ctx.threads:
        out += [f"### {_heading('thread', t.root)}", f"on `{t.root.path}:{t.root.line}`", "", t.root.body, ""]
        for r in t.replies:
            out += [f"#### {_heading('reply', r)}", "", r.body, ""]
    out += ["## Other pull requests in the stack", ""]
    for e in ctx.stack:
        out += [f"### #{e.number} {e.title} ({e.state}, {_where(e)})", "", e.body, ""]
    return "\n".join(out)


def prompt_summary(ctx: PullRequestContext, context_path: str) -> str:
    return f"""## Pull request context

This pull request's description and stack are below. Its full discussion, linked
issues and the other pull requests in its stack are in: {context_path}

### Stack

{stack_map(ctx)}

### Description

{ctx.body or "(no description)"}

Before you report that something is missing, check the later pull requests in the
stack: `git show refs/stack/<n>:<path>` shows a file as that pull request leaves
it, and `git diff HEAD refs/stack/<n>` shows everything it changes after this one.

Before you report anything, read the discussion in the context file. Do not
report what it already raises, or what the author has already answered.
"""


def describe_stack(ctx: PullRequestContext) -> str:
    if not ctx.stack:
        return "Stack: not part of a stack."
    if ctx.stack_position:
        numbers = sorted([e.number for e in ctx.stack] + [ctx.number])
        pos, size = ctx.stack_position
        return f"Stack: position {pos} of {size} ({', '.join(f'#{n}' for n in numbers)})."
    earlier = sum(1 for e in ctx.stack if not e.later)
    later = len(ctx.stack) - earlier
    return (f"Stack: {earlier} earlier and {later} later pull request(s) "
            f"({', '.join(f'#{e.number}' for e in ctx.stack)}).")


def describe_loaded(ctx: PullRequestContext) -> str:
    entries = len(ctx.comments) + sum(1 + len(t.replies) for t in ctx.threads)
    line = (f"Context loaded: the description, {len(ctx.issues)} linked issue(s) "
            f"and {entries} discussion entries.")
    return line + (f" Not loaded: {', '.join(ctx.failed)}." if ctx.failed else "")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_context_render.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/context/render.py tests/test_context_render.py
git commit -m "feat(pr-review): render the pull request context for the clone and the prompts"
```

---

### Task 7: Clone the stack refs and write the context file

**Files:**
- Modify: `src/pr_review/checkout.py`
- Test: `tests/test_checkout.py`

**Interfaces:**
- Produces:
  - `Checkout.stack_refs: list[int] = []` — the stack pull requests whose ref was fetched.
  - `clone_pr(owner, repo, number, *, stack: Sequence[int] = (), runner=_run, mkdtemp=None) -> Checkout` — after the base fetch, runs `git fetch --filter=blob:none origin +refs/pull/<n>/head:refs/stack/<n>` for each; a failed fetch is skipped.
  - `write_context_file(workdir: str, text: str) -> str` — writes `<workdir>/.git/pr-review/pr-context.md` and returns its path.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_checkout.py`:

```python
from pr_review.checkout import write_context_file


def test_clone_pr_fetches_each_stack_ref_after_the_base(tmp_path):
    runner = FakeRunner()
    result = clone_pr("org", "repo", 42, stack=[41, 43], runner=runner, mkdtemp=lambda: str(tmp_path))
    cmds = [c[0] for c in runner.calls]
    assert cmds[4] == ["git", "fetch", "--filter=blob:none", "origin", "+refs/pull/41/head:refs/stack/41"]
    assert cmds[5] == ["git", "fetch", "--filter=blob:none", "origin", "+refs/pull/43/head:refs/stack/43"]
    assert cmds[6] == ["git", "checkout", "--detach", "refs/remotes/origin/pr/42"]
    assert result.stack_refs == [41, 43]


def test_a_stack_ref_that_cannot_be_fetched_is_left_out(tmp_path):
    class Failing(FakeRunner):
        def __call__(self, cmd, **kw):
            if cmd[-1].endswith("refs/stack/41"):
                raise subprocess.CalledProcessError(128, cmd)
            return super().__call__(cmd, **kw)

    result = clone_pr("org", "repo", 42, stack=[41, 43], runner=Failing(), mkdtemp=lambda: str(tmp_path))
    assert result.stack_refs == [43]


def test_write_context_file_puts_it_inside_dot_git(tmp_path):
    (tmp_path / ".git").mkdir()
    path = write_context_file(str(tmp_path), "# Context")
    assert path == str(tmp_path / ".git" / "pr-review" / "pr-context.md")
    assert open(path).read() == "# Context"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_checkout.py -v`
Expected: the three new tests FAIL.

- [ ] **Step 3: Implement.** In `src/pr_review/checkout.py`, add `import os`, `from dataclasses import dataclass, field`, give `Checkout` a last field `stack_refs: list[int] = field(default_factory=list)`, add `stack: Sequence[int] = ()` to `clone_pr`'s keyword arguments, and between the base fetch and the checkout insert:

```python
    fetched: list[int] = []
    for n in stack:
        try:
            runner(["git", "fetch", "--filter=blob:none", "origin", f"+refs/pull/{n}/head:refs/stack/{n}"],
                   cwd=workdir)
        except Exception as e:
            print(f"pr-review: could not fetch #{n} from the stack ({e}); leaving it out.", file=sys.stderr)
            continue
        fetched.append(n)
```

Return `Checkout(workdir=workdir, base=base_sha, base_ref=base_ref, stack_refs=fetched)`, add `import sys`, and add:

```python
def write_context_file(workdir: str, text: str) -> str:
    """Inside .git, so no reviewer's search of the working tree finds it."""
    folder = os.path.join(workdir, ".git", "pr-review")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "pr-context.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_checkout.py -v`
Expected: all PASS (the existing `Checkout(...) ==` test still passes because `stack_refs` defaults to `[]`).

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/checkout.py tests/test_checkout.py
git commit -m "feat(pr-review): fetch every stack pull request into the clone"
```

---

### Task 8: Reviewers and the judge get the context summary

**Files:**
- Modify: `src/pr_review/reviewers/_run.py`, `src/pr_review/reviewers/base.py`, `src/pr_review/orchestrator.py`, `src/pr_review/synthesis.py`, `src/pr_review/cli.py` (`build_collator` only)
- Test: `tests/test_reviewers.py`, `tests/test_orchestrator.py`, `tests/test_synthesis.py`

**Interfaces:**
- Produces:
  - `build_review_prompt(..., context: str = "")`, `run_cli_reviewer(..., context: str = "")`, `Reviewer.review(..., context: str = "")` — the summary goes between the run context and the review-type instructions.
  - `run_reviews(..., context: str = "")` passes it to every reviewer.
  - `build_synthesis_prompt(..., context: str = "")`, `LLMSynthesisCollator(..., context: str = "")`.
  - `build_collator(cfg, *, workdir, base, context: str = "")`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_reviewers.py`:

```python
def test_build_review_prompt_places_the_context_before_the_instructions():
    from pr_review.reviewers._run import build_review_prompt
    from pr_review.review_types import get_review_type

    prompt = build_review_prompt(owner="o", repo="r", number=1, base="b", payload_path="/p",
                                 review_type=get_review_type("test-gap"), context="## Pull request context\nX")
    assert prompt.index("## Pull request context") < prompt.index("# Test Coverage Review")


def test_build_review_prompt_without_context_is_unchanged():
    from pr_review.reviewers._run import build_review_prompt
    from pr_review.review_types import get_review_type

    prompt = build_review_prompt(owner="o", repo="r", number=1, base="b", payload_path="/p",
                                 review_type=get_review_type("test-gap"))
    assert "## Pull request context" not in prompt
```

In `tests/test_orchestrator.py`, give `FakeReviewer.review` a `context=""` keyword and record it (`self.calls.append({..., "context": context})`), change `BoomReviewer.review` to accept `**kwargs` (it already does), update the `r.calls == [...]` expectation in `test_single_job_passthrough_and_per_job_args` to include `"context": ""`, and append:

```python
def test_the_context_summary_reaches_every_reviewer():
    r = FakeReviewer("claude")
    run_reviews(jobs=[ReviewJob(r, FakeType("test-gap"), "m1", [])], workdir="/wd", base="b",
                owner="o", repo="r", number=1, context="SUMMARY")
    assert r.calls[0]["context"] == "SUMMARY"
```

Append to `tests/test_synthesis.py`:

```python
def test_the_judge_gets_the_context_summary():
    prompt = build_synthesis_prompt(owner="o", repo="r", number=7, base="b", payload_path="/p",
                                    findings="F", context="## Pull request context\nX")
    assert prompt.index("## Pull request context") < prompt.index("# Synthesis Review")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_reviewers.py tests/test_orchestrator.py tests/test_synthesis.py -v`
Expected: the new tests FAIL with `TypeError: ... unexpected keyword argument 'context'`.

- [ ] **Step 3: Implement.**

`reviewers/_run.py`:

```python
def build_review_prompt(
    *, owner: str, repo: str, number: int, base: str,
    payload_path: str, review_type: ReviewType, context: str = "",
) -> str:
    run = _build_context(owner=owner, repo=repo, number=number, base=base, payload_path=payload_path)
    parts = [run, context, review_type.instructions()] if context else [run, review_type.instructions()]
    return "\n".join(parts)
```

and add `context: str = ""` to `run_cli_reviewer`, passing it to `build_review_prompt`.

`reviewers/base.py`: add `context: str = ""` to `Reviewer.review` and pass `context=context` to `run_cli_reviewer`.

`orchestrator.py`: add `context: str = ""` to `run_reviews` and pass `context=context` in `job.reviewer.review(...)`.

`synthesis.py`: add `context: str = ""` to `build_synthesis_prompt` and insert it between the run context and `_INSTRUCTIONS`:

```python
    return f"{run_context}\n{context}\n{_INSTRUCTIONS}\n{writing_rules_block()}\n## Findings to consolidate\n\n{findings}\n"
```

(rename the local `context` string that `build_synthesis_prompt` builds today to `run_context`). Add `context: str = ""` to `LLMSynthesisCollator.__init__`, store it as `self._context`, and pass `context=self._context` in `build`.

`cli.py`: `build_collator(cfg, *, workdir, base, context: str = "")` passes `context=context` to `LLMSynthesisCollator`.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/reviewers src/pr_review/orchestrator.py src/pr_review/synthesis.py src/pr_review/cli.py tests
git commit -m "feat(pr-review): give reviewers and the judge the pull request context"
```

---

### Task 9: Replies in the payload, the plain-language stage and attribution

**Files:**
- Modify: `src/pr_review/payload.py`, `src/pr_review/plain_language/stage.py`, `src/pr_review/attribution.py`
- Test: `tests/test_payload.py`, `tests/test_plain_language_stage.py`, `tests/test_attribution.py`

**Interfaces:**
- Produces:
  - `Reply(in_reply_to: int, body: str, sources: list[Source] = [])` with `to_dict() -> {"body": body}`.
  - `Payload.replies: list[Reply] = []` — never in `Payload.to_dict()`.
  - `PlainLanguageStage.apply(payload, answers: dict[int, str] | None = None)` and `check_payload(payload)` check and rewrite replies too. In `StageResult.remaining`, index `len(payload.comments) + j` is reply `j`. `answers` maps a comment id to the text of the comment being replied to; the reader sees it in place of diff lines.
  - `finalize` appends the footer to each reply as well.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_payload.py`:

```python
from pr_review.payload import Reply


def test_replies_are_not_part_of_the_review_json():
    p = Payload(body="b", replies=[Reply(10, "no", sources=[Source("claude", "m", "t")])])
    assert "replies" not in p.to_dict()
    assert Reply(10, "no").to_dict() == {"body": "no"}
```

Append to `tests/test_plain_language_stage.py`:

```python
from pr_review.payload import Reply


def test_replies_are_checked_and_rewritten_with_the_answer_as_context():
    p = payload(CLEAN)
    p.replies = [Reply(10, JARGON, sources=[SRC])]
    runner = FakeRunner(rewrite={"comments": [{"index": 1, "body": FIXED}]})
    result = stage(runner).apply(p, answers={10: "Used in the next pull request."})
    assert "Used in the next pull request." in runner.prompts[0]
    assert "### Comment 1: reply to comment 10" in runner.prompts[1]
    assert result.payload.replies[0].body == FIXED
    assert result.payload.replies[0].in_reply_to == 10
    assert result.payload.replies[0].sources == [SRC]


def test_check_payload_covers_replies():
    p = payload(CLEAN)
    p.replies = [Reply(10, JARGON)]
    assert any('"inert"' in x.detail for x in check_payload(p).remaining[1])
```

Append to `tests/test_attribution.py`:

```python
from pr_review.payload import Reply


def test_finalize_adds_the_footer_to_replies():
    p = Payload(body="V.", replies=[Reply(10, "**X.**", sources=[OPUS])])
    out = finalize(p, RunRecord(jobs=[JobRecord(OPUS, raw=1)]))
    assert out.replies[0].body == "**X.**\n\n<sub>Found by 1 model: claude</sub>"
    assert out.replies[0].in_reply_to == 10
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_payload.py tests/test_plain_language_stage.py tests/test_attribution.py -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement.**

`payload.py` — after `Comment`:

```python
@dataclass
class Reply:
    """A finding posted as a reply in an existing review thread."""

    in_reply_to: int
    body: str
    sources: list[Source] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"body": self.body}
```

and add `replies: list[Reply] = field(default_factory=list)` as the last field of `Payload` (after `event`). `to_dict` is unchanged.

`plain_language/stage.py` — treat replies as extra comments. Add these helpers and change `check_payload` and `apply` to use them:

```python
from pr_review.payload import Comment, Payload, Reply


def _units(payload: Payload) -> list[Comment]:
    return list(payload.comments) + [
        Comment(f"reply to comment {r.in_reply_to}", 0, r.body, sources=r.sources) for r in payload.replies
    ]


def _rebuild(payload: Payload, units: list[Comment], body: str) -> Payload:
    n = len(payload.comments)
    replies = [replace(r, body=u.body) for r, u in zip(payload.replies, units[n:])]
    return Payload(body=body, comments=units[:n], event=payload.event, replies=replies)


def check_payload(payload: Payload) -> StageResult:
    return StageResult(
        payload=payload,
        remaining={i: check_comment(c.body) for i, c in enumerate(_units(payload))},
        body_remaining=check_body(payload.body),
    )
```

Replace `apply` with this version, which works on comments and replies alike (the only changes from the previous plan's version are `units`, the reply hunks, and `_rebuild`):

```python
    def apply(self, payload: Payload, answers: dict[int, str] | None = None) -> StageResult:
        units = _units(payload)
        checked = check_payload(payload)
        warnings: list[str] = []
        try:
            diff = self._diff(self._workdir, self._base)
        except Exception as e:
            warnings.append(f"could not read the diff ({e}); the reader test sees no diff lines")
            diff = ""
        n = len(payload.comments)
        hunks = {i: hunk_for(diff, c.path, c.line) for i, c in enumerate(units[:n])}
        for j, r in enumerate(payload.replies):
            hunks[n + j] = f"(the comment this replies to)\n{(answers or {}).get(r.in_reply_to, '')}"

        reader = None
        try:
            reader = parse_reader_result(self._runner(
                self._command,
                lambda path: build_reader_prompt(
                    payload_path=path,
                    comments=[(i, c, hunks[i]) for i, c in enumerate(units)],
                    body=payload.body,
                ),
                workdir=self._workdir,
            ))
        except Exception as e:
            warnings.append(f"reader test failed ({e}); rewriting on the word-and-shape check only")

        problems = {
            i: checked.remaining[i] + _reader_problems(reader.comments.get(i) if reader else None)
            for i in range(len(units))
        }
        body_problems = checked.body_remaining + _reader_problems(reader.body if reader else None)
        items = [
            RewriteItem(i, c, hunks[i], _blocking(problems[i]))
            for i, c in enumerate(units) if _blocking(problems[i])
        ]
        body_blocking = _blocking(body_problems)
        if not items and not body_blocking:
            return StageResult(payload, problems, body_problems, 0, warnings)

        try:
            new_bodies, new_body = parse_rewrite_result(self._runner(
                self._command,
                lambda path: build_rewrite_prompt(
                    payload_path=path, items=items, body=payload.body, body_problems=body_blocking,
                ),
                workdir=self._workdir,
            ))
        except Exception as e:
            warnings.append(f"rewrite failed ({e}); posting the review as written")
            return StageResult(payload, problems, body_problems, 0, warnings)

        comments = list(units)
        rewritten = 0
        for item in items:
            text = new_bodies.get(item.index)
            if text is None:
                continue
            original = comments[item.index]
            reason = guard(original.body, text)
            if reason:
                warnings.append(f"{original.path}:{original.line}: the rewrite {reason}; kept the original")
                continue
            comments[item.index] = replace(original, body=text)
            problems[item.index] = check_comment(text)
            rewritten += 1

        body = payload.body
        if body_blocking and new_body is not None:
            reason = guard(payload.body, new_body)
            if reason:
                warnings.append(f"review body: the rewrite {reason}; kept the original")
            else:
                body, body_problems = new_body, check_body(new_body)

        return StageResult(_rebuild(payload, comments, body), problems, body_problems, rewritten, warnings)
```

`format_report` needs no change: a reply's `path` is `reply to comment <id>` and its `line` is `0`.

`attribution.py` — in `finalize`, add:

```python
    replies = [
        replace(r, body=f"{r.body.rstrip()}\n\n{attribution(r.sources)}")
        for r in payload.replies
    ]
    return Payload(body=body, comments=comments, event=payload.event, replies=replies)
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/payload.py src/pr_review/plain_language/stage.py src/pr_review/attribution.py tests
git commit -m "feat(pr-review): carry replies through the plain-language stage and attribution"
```

---

### Task 10: The context filter

**Files:**
- Create: `src/pr_review/context/filter.py`
- Test: `tests/test_context_filter.py`

**Interfaces:**
- Consumes: `PullRequestContext` (Task 1), `stack_map` (Task 6), `Payload`, `Reply` (Tasks 1 and 9 of the previous plan and Task 9 here), `run_cli_json`, `_first_line` from `pr_review.collate`.
- Produces:
  - `MAX_REPLIES = 3`
  - `Dropped(finding: str, reason: str, link: str, evidence: str = "")`
  - `FilterResult(payload: Payload, dropped: list[Dropped], warnings: list[str])`
  - `build_filter_prompt(*, payload_path: str, context_path: str, ctx: PullRequestContext, payload: Payload) -> str`
  - `apply_verdicts(payload: Payload, data: object, ctx: PullRequestContext) -> FilterResult` — pure; validates every verdict.
  - `ContextFilter(*, command: list[str], workdir: str, context_path: str, runner=run_cli_json)` with `.apply(payload, ctx) -> FilterResult`; a failed call keeps every finding and warns.
  - `answers_by_id(ctx) -> dict[int, str]` — every discussion entry's id → body (for the plain-language stage).

- [ ] **Step 1: Write the failing tests** — create `tests/test_context_filter.py`:

```python
from pr_review.context.filter import (
    MAX_REPLIES, ContextFilter, answers_by_id, apply_verdicts, build_filter_prompt,
)
from pr_review.context.model import Entry, PullRequestContext, StackEntry, Thread
from pr_review.payload import Comment, Payload, Source

SRC = Source("claude", "m", "infracode")


def ctx():
    root = Entry(10, "thread", "https://x/r10", "bot", False, "t", "Unused parameter.", "a.py", 4)
    author_reply = Entry(11, "thread", "https://x/r11", "ada", True, "t", "Used later in the stack.", "a.py", 4, 10)
    other_reply = Entry(12, "thread", "https://x/r12", "bob", False, "t", "Agreed.", "a.py", 4, 10)
    return PullRequestContext(
        number=7, title="T", body="B", author="ada", issues=[],
        comments=[Entry(1, "comment", "https://x/c1", "ada", True, "t", "Deliberate, see the ADR.")],
        threads=[Thread(root, [author_reply, other_reply])],
        stack=[StackEntry(6, "Earlier", "", "merged", "s6", False),
               StackEntry(8, "Later", "", "open", "s8", True),
               StackEntry(9, "Abandoned", "", "closed", "s9", True)],
        stack_position=None, failed=[],
    )


def payload(n=3):
    return Payload(body="Verdict.", comments=[
        Comment(f"f{i}.py", i + 1, f"**Finding {i}.**\n\n**Impact:** x\n\n**Fix:** y", sources=[SRC])
        for i in range(n)
    ])


def test_keep_and_missing_verdicts_keep_the_finding():
    out = apply_verdicts(payload(2), {"verdicts": [{"index": 0, "verdict": "keep"}]}, ctx())
    assert len(out.payload.comments) == 2 and out.dropped == []


def test_fixed_later_drops_and_records_the_pull_request():
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "drop", "reason": "fixed-later", "pull_request": 8, "evidence": "refs/stack/8:a.py sets it"}]}, ctx())
    assert out.payload.comments == []
    assert out.dropped[0].finding == "**Finding 0.**"
    assert (out.dropped[0].reason, out.dropped[0].link, out.dropped[0].evidence) == ("fixed-later", "#8", "refs/stack/8:a.py sets it")


def test_fixed_later_by_an_earlier_or_closed_pull_request_is_kept():
    for pr in (6, 9, 99):
        out = apply_verdicts(payload(1), {"verdicts": [
            {"index": 0, "verdict": "drop", "reason": "fixed-later", "pull_request": pr}]}, ctx())
        assert len(out.payload.comments) == 1, pr
        assert out.warnings, pr


def test_already_raised_and_answered_drop_with_their_link():
    out = apply_verdicts(payload(2), {"verdicts": [
        {"index": 0, "verdict": "drop", "reason": "already-raised", "link": "https://x/r10"},
        {"index": 1, "verdict": "drop", "reason": "answered", "link": "https://x/c1"}]}, ctx())
    assert out.payload.comments == []
    assert [(d.reason, d.link) for d in out.dropped] == [("already-raised", "https://x/r10"), ("answered", "https://x/c1")]


def test_an_unknown_reason_or_bad_index_is_ignored():
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "drop", "reason": "vibes"}, {"index": 5, "verdict": "drop", "reason": "answered"}]}, ctx())
    assert len(out.payload.comments) == 1


def test_a_reply_to_an_author_thread_comment_becomes_a_reply():
    out = apply_verdicts(payload(1), {"verdicts": [
        {"index": 0, "verdict": "reply", "in_reply_to": 11, "body": "**No later pull request calls it.**"}]}, ctx())
    assert out.payload.comments == []
    assert [(r.in_reply_to, r.body, r.sources) for r in out.payload.replies] == [
        (11, "**No later pull request calls it.**", [SRC])]


def test_a_reply_to_someone_else_or_to_an_issue_comment_stays_a_comment_with_a_link():
    out = apply_verdicts(payload(2), {"verdicts": [
        {"index": 0, "verdict": "reply", "in_reply_to": 12, "body": "x"},
        {"index": 1, "verdict": "reply", "in_reply_to": 1, "body": "x"}]}, ctx())
    assert out.payload.replies == []
    assert len(out.payload.comments) == 2
    assert "[the author's answer](https://x/c1)" in out.payload.comments[1].body
    assert "https://x/r12" not in out.payload.comments[0].body


def test_replies_beyond_the_cap_go_to_the_overflow_list():
    n = MAX_REPLIES + 1
    out = apply_verdicts(payload(n), {"verdicts": [
        {"index": i, "verdict": "reply", "in_reply_to": 11, "body": f"**Reply {i}.**"} for i in range(n)]}, ctx())
    assert len(out.payload.replies) == MAX_REPLIES
    assert f"- [**Reply {n - 1}.**](https://x/r11)" in out.payload.body


def test_the_prompt_names_refs_states_findings_and_the_context_file():
    prompt = build_filter_prompt(payload_path="/o.json", context_path="/c.md", ctx=ctx(), payload=payload(1))
    for expected in ("/o.json", "/c.md", "refs/stack/8", "(closed, later", "### Finding 0: f0.py:1",
                     '"fixed-later"', '"already-raised"', '"answered"', '"reply"', "(author)"):
        assert expected in prompt, expected


def test_a_failed_filter_call_keeps_every_finding():
    def boom(*a, **k):
        raise RuntimeError("down")

    out = ContextFilter(command=["j"], workdir="/wd", context_path="/c.md", runner=boom).apply(payload(2), ctx())
    assert len(out.payload.comments) == 2
    assert "context filter failed" in out.warnings[0]


def test_answers_by_id_covers_comments_and_every_thread_entry():
    assert answers_by_id(ctx()) == {1: "Deliberate, see the ADR.", 10: "Unused parameter.",
                                    11: "Used later in the stack.", 12: "Agreed."}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_context_filter.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/pr_review/context/filter.py`**:

```python
"""Drop findings the pull request's context already answers; reply where it is wrong."""
from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from pr_review.collate import _first_line
from pr_review.context.model import Entry, PullRequestContext
from pr_review.context.render import stack_map
from pr_review.payload import Comment, Payload, Reply
from pr_review.reviewers._run import run_cli_json

MAX_REPLIES = 3
_REASONS = ("fixed-later", "already-raised", "answered")

_INSTRUCTIONS = """# Context filter

You are checking findings from a review of this pull request before they are
posted. Read the context file named above: it has the description, the
discussion so far (every entry has an id, and the pull request author's entries
are marked "(author)"), and the other pull requests in the stack. The other pull
requests are fetched as git refs, listed below with their states.

For each finding, choose one verdict:

- "drop" with reason "fixed-later": code at a LATER pull request's ref fixes it.
  Check the code (`git show refs/stack/<n>:<path>`, `git diff HEAD refs/stack/<n>`).
  Give "pull_request" (its number) and "evidence" (what you saw). A closed pull
  request that was not merged never counts.
- "drop" with reason "already-raised": the discussion already raises the same
  problem, from anyone. Give "link" (the entry's URL).
- "drop" with reason "answered": the author said it is deliberate, will be done
  later, or is done elsewhere (and you confirmed that in the code). Do not use
  this when the finding is a correctness or security bug that the code shows.
  Give "link".
- "reply": the author answered it, and the code proves the answer wrong. Give
  "in_reply_to" (the id of the author's entry) and "body": the finding written as
  a reply to that answer, in the same comment shape.
- "keep": none of the above.

Only entries marked "(author)" count as answers. Other people's entries count as
already raised. Do not post anything and do not change any file except the
output file.

Write ONLY this JSON to the output file:
{"verdicts": [{"index": 0, "verdict": "keep"},
  {"index": 1, "verdict": "drop", "reason": "fixed-later", "pull_request": 42, "evidence": "..."},
  {"index": 2, "verdict": "drop", "reason": "already-raised", "link": "https://..."},
  {"index": 3, "verdict": "reply", "in_reply_to": 123, "body": "..."}]}
"""


@dataclass
class Dropped:
    finding: str
    reason: str
    link: str
    evidence: str = ""


@dataclass
class FilterResult:
    payload: Payload
    dropped: list[Dropped] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _entries(ctx: PullRequestContext) -> list[Entry]:
    return list(ctx.comments) + [e for t in ctx.threads for e in [t.root, *t.replies]]


def answers_by_id(ctx: PullRequestContext) -> dict[int, str]:
    return {e.id: e.body for e in _entries(ctx)}


def build_filter_prompt(*, payload_path: str, context_path: str, ctx: PullRequestContext, payload: Payload) -> str:
    parts = [
        f"Output file to write: {payload_path}",
        f"Context file: {context_path}\n",
        _INSTRUCTIONS,
        "## Stack refs\n",
        stack_map(ctx),
        "\n## Discussion entries by id\n",
        *[f"- {e.id}: {e.kind} by {e.author}{' (author)' if e.is_author else ''}" for e in _entries(ctx)],
        "\n## Findings\n",
    ]
    for i, c in enumerate(payload.comments):
        parts.append(f"### Finding {i}: {c.path}:{c.line}\n\n<<<\n{c.body}\n>>>\n")
    return "\n".join(parts)


def apply_verdicts(payload: Payload, data: object, ctx: PullRequestContext) -> FilterResult:
    raw = data.get("verdicts") if isinstance(data, dict) else None
    verdicts: dict[int, dict] = {}
    for v in raw if isinstance(raw, list) else []:
        if isinstance(v, dict) and isinstance(v.get("index"), int) and v["index"] not in verdicts:
            verdicts[v["index"]] = v

    fixers = {e.number for e in ctx.stack if e.later and e.state != "closed"}
    entries = {e.id: e for e in _entries(ctx)}
    kept: list[Comment] = []
    replies: list[Reply] = []
    overflow: list[str] = []
    dropped: list[Dropped] = []
    warnings: list[str] = []

    for i, c in enumerate(payload.comments):
        v = verdicts.get(i, {})
        where = f"{c.path}:{c.line}"
        if v.get("verdict") == "drop" and v.get("reason") in _REASONS:
            reason = v["reason"]
            if reason == "fixed-later":
                pr = v.get("pull_request")
                if pr not in fixers:
                    warnings.append(f"{where}: kept; #{pr} is not an open or merged later pull request")
                    kept.append(c)
                    continue
                link = f"#{pr}"
            else:
                link = v.get("link") if isinstance(v.get("link"), str) else ""
            evidence = v.get("evidence") if isinstance(v.get("evidence"), str) else ""
            dropped.append(Dropped(_first_line(c.body), reason, link, evidence))
        elif v.get("verdict") == "reply":
            target = entries.get(v.get("in_reply_to"))
            body = v.get("body") if isinstance(v.get("body"), str) and v["body"].strip() else c.body
            if target is None or not target.is_author:
                warnings.append(f"{where}: kept as a comment; the reply target is not the author's")
                kept.append(c)
            elif target.kind != "thread":
                kept.append(replace(c, body=f"{c.body.rstrip()}\n\nThis replies to [the author's answer]({target.url})."))
            elif len(replies) < MAX_REPLIES:
                replies.append(Reply(target.id, body, sources=list(c.sources)))
            else:
                overflow.append(f"- [{_first_line(body)}]({target.url})")
        else:
            kept.append(c)

    body = payload.body
    if overflow:
        body += "\n\n---\n\n## Other replies not posted\n\n" + "\n".join(overflow)
    out = Payload(body=body, comments=kept, event=payload.event, replies=list(payload.replies) + replies)
    return FilterResult(out, dropped, warnings)


class ContextFilter:
    def __init__(self, *, command: list[str], workdir: str, context_path: str,
                 runner: Callable[..., object] = run_cli_json):
        self._command = command
        self._workdir = workdir
        self._context_path = context_path
        self._runner = runner

    def apply(self, payload: Payload, ctx: PullRequestContext) -> FilterResult:
        if not payload.comments:
            return FilterResult(payload)
        try:
            data = self._runner(
                self._command,
                lambda path: build_filter_prompt(payload_path=path, context_path=self._context_path,
                                                 ctx=ctx, payload=payload),
                workdir=self._workdir,
            )
        except Exception as e:
            return FilterResult(payload, [], [f"context filter failed ({e}); every finding is kept"])
        return apply_verdicts(payload, data, ctx)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_context_filter.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/context/filter.py tests/test_context_filter.py
git commit -m "feat(pr-review): add the context filter and validate its verdicts in code"
```

---

### Task 11: Post the review, then each reply

**Files:**
- Modify: `src/pr_review/output.py`
- Test: `tests/test_output.py`

**Interfaces:**
- Consumes: `Payload.replies`, `Reply` (Task 9).
- Produces:
  - `_write_reply_file(reply: Reply) -> str` — `pr-review-reply.<in_reply_to>.<random>.json` holding `{"body": …}`.
  - `_reply_command(target, reply_id: int, path: str) -> list[str]` — `gh api repos/<slug>/pulls/<n>/comments/<id>/replies --method POST --input <path>`.
  - `dispatch(...)` posts the review; if that fails, posts no replies, keeps every file and prints a retry command for each; otherwise posts each reply, deletes the file of each that posted, keeps the rest with a retry command each, and returns `1` if anything failed.
  - The confirm prompt says `with N inline comment(s) and M reply(ies)` when there are replies.
  - Review-only mode writes the reply files too and prints a command for each.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_output.py`:

```python
from pr_review.payload import Reply


def _ok(cmd, **kw):
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _paths(err):
    return [line.split("--input ", 1)[1].strip() for line in err.splitlines() if "--input " in line]


def test_replies_post_after_the_review_and_their_files_are_removed(capsys):
    calls = []

    def runner(cmd, **kw):
        calls.append(list(cmd))
        return _ok(cmd)

    p = Payload(body="b", replies=[Reply(11, "r1"), Reply(12, "r2")])
    code = dispatch(PostMode.POST, Target("org", "repo", 5), p, runner=runner)
    assert code == 0
    assert calls[0][2] == "repos/org/repo/pulls/5/reviews"
    assert calls[1][2] == "repos/org/repo/pulls/5/comments/11/replies"
    assert calls[2][2] == "repos/org/repo/pulls/5/comments/12/replies"
    reply_file = calls[1][calls[1].index("--input") + 1]
    assert not os.path.exists(reply_file)
    os.unlink(capsys.readouterr().err.split("payload kept at ", 1)[1].strip())


def test_a_failed_reply_does_not_stop_the_others_and_keeps_its_file(capsys):
    def runner(cmd, **kw):
        if "comments/11/replies" in cmd[2]:
            raise subprocess.CalledProcessError(1, cmd)
        return _ok(cmd)

    p = Payload(body="b", replies=[Reply(11, "r1"), Reply(12, "r2")])
    code = dispatch(PostMode.POST, Target("org", "repo", 5), p, runner=runner)
    err = capsys.readouterr().err
    assert code == 1
    assert "review posted; 1 of 2 replies failed" in err
    [kept] = _paths(err)
    try:
        assert "comments/11/replies" in err
        assert json.load(open(kept)) == {"body": "r1"}
    finally:
        os.unlink(kept)


def test_a_failed_review_posts_no_replies_and_keeps_everything(capsys):
    calls = []

    def runner(cmd, **kw):
        calls.append(list(cmd))
        raise subprocess.CalledProcessError(1, cmd)

    p = Payload(body="b", replies=[Reply(11, "r1")])
    code = dispatch(PostMode.POST, Target("org", "repo", 5), p, runner=runner)
    err = capsys.readouterr().err
    assert code == 1
    assert len(calls) == 1
    paths = _paths(err)
    assert len(paths) == 2
    for path in paths:
        assert os.path.exists(path)
        os.unlink(path)


def test_review_only_writes_reply_files_with_a_command_each(capsys):
    code = dispatch(PostMode.REVIEW_ONLY, Target("org", "repo", 5), Payload(body="b", replies=[Reply(11, "r1")]))
    err = capsys.readouterr().err
    assert code == 0
    paths = _paths(err)
    assert len(paths) == 2 and "comments/11/replies" in err
    for path in paths:
        os.unlink(path)


def test_the_confirm_prompt_counts_replies(monkeypatch):
    written = []
    monkeypatch.setattr(output.terminal, "open_interactive",
                        lambda: (lambda: "n", written.append, lambda: None))
    assert output._confirm(Target("org", "repo", 5), 2, 1) is False
    assert "with 2 inline comment(s) and 1 reply(ies)?" in written[0]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_output.py -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** In `src/pr_review/output.py` add `from pr_review.payload import Payload, Reply`, then:

```python
def _write_reply_file(reply: Reply) -> str:
    fd, path = tempfile.mkstemp(prefix=f"pr-review-reply.{reply.in_reply_to}.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(reply.to_dict(), f)
    return path


def _reply_command(target: Target, reply_id: int, path: str) -> list[str]:
    return ["gh", "api", f"repos/{target.slug}/pulls/{target.number}/comments/{reply_id}/replies",
            "--method", "POST", "--input", path]


def _reply_hint(target: Target, reply_id: int, path: str) -> str:
    return f"  to post the reply to comment {reply_id}: {' '.join(_reply_command(target, reply_id, path))}"
```

(add `import json` if it is not imported). Change `_confirm` to:

```python
def _confirm(target: Target, n_comments: int, n_replies: int = 0) -> bool:
    io = terminal.open_interactive()
    if io is None:
        return False
    read_line, write, close = io
    replies = f" and {n_replies} reply(ies)" if n_replies else ""
    try:
        write(
            f"\nPost this review to {target.slug}#{target.number} "
            f"with {n_comments} inline comment(s){replies}? [y/N] "
        )
        reply = read_line().strip().lower()
    finally:
        close()
    return reply in ("y", "yes")
```

Replace `dispatch` with:

```python
def dispatch(mode: PostMode, target: Target, payload: Payload, *, runner=_run) -> int:
    """Post the review, then each reply (or explain why not). Returns the exit code."""
    if mode is PostMode.POST or (
        mode is PostMode.PROMPT and _confirm(target, len(payload.comments), len(payload.replies))
    ):
        # Write the payload before posting so its path survives a failed post.
        path = _write_payload_file(payload)
        reply_files = [(r.in_reply_to, _write_reply_file(r)) for r in payload.replies]
        try:
            _post_payload_file(target, path, runner=runner)
        except Exception as err:
            print(f"pr-review: posting failed: {err}", file=sys.stderr)
            print(_payload_note(target, path, "pr-review: the review was kept at:"), file=sys.stderr)
            for reply_id, reply_path in reply_files:
                print(_reply_hint(target, reply_id, reply_path), file=sys.stderr)
            return 1
        print(f"pr-review: posted review to {target.slug}#{target.number}.", file=sys.stderr)
        print(f"pr-review: payload kept at {path}", file=sys.stderr)

        failed: list[tuple[int, str, Exception]] = []
        for reply_id, reply_path in reply_files:
            try:
                runner(_reply_command(target, reply_id, reply_path))
            except Exception as err:
                failed.append((reply_id, reply_path, err))
                continue
            os.unlink(reply_path)
        if failed:
            print(f"pr-review: review posted; {len(failed)} of {len(reply_files)} replies failed: "
                  f"{failed[0][2]}", file=sys.stderr)
            for reply_id, reply_path, _ in failed:
                print(_reply_hint(target, reply_id, reply_path), file=sys.stderr)
            return 1
        return 0

    print(_not_posted_hint(target, payload), file=sys.stderr)
    for r in payload.replies:
        print(_reply_hint(target, r.in_reply_to, _write_reply_file(r)), file=sys.stderr)
    return 0
```

- [ ] **Step 4: Run the full output test file** (the existing dispatch tests must still pass)

Run: `uv run pytest tests/test_output.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/output.py tests/test_output.py
git commit -m "feat(pr-review): post replies after the review, one by one, with retry commands"
```

---

### Task 12: The details block reports the stack, the context and what was not posted

**Files:**
- Modify: `src/pr_review/attribution.py`
- Test: `tests/test_attribution.py`

**Interfaces:**
- Produces: `RunRecord` gains `stack_line: str | None = None`, `context_line: str | None = None`, `not_posted: list[str] = []` (pre-rendered one-line descriptions). `render_details` prints `stack_line` and `context_line` as paragraphs, and `not_posted` under `**Findings not posted:**` as a bullet list.
- Also produces, in `pr_review/context/render.py`: `describe_dropped(d: Dropped) -> str`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_attribution.py`:

```python
def test_details_include_stack_context_and_findings_not_posted():
    record = RunRecord(jobs=[JobRecord(OPUS, raw=1)], stack_line="Stack: position 1 of 2 (#7, #8).",
                       context_line="Context loaded: the description.",
                       not_posted=["**No lock.** Fixed in #8 (refs/stack/8:a.tf)."])
    text = render_details(record, [])
    assert "Stack: position 1 of 2 (#7, #8)." in text
    assert "Context loaded: the description." in text
    assert "**Findings not posted:**\n\n- **No lock.** Fixed in #8 (refs/stack/8:a.tf)." in text
```

Append to `tests/test_context_render.py`:

```python
from pr_review.context.filter import Dropped
from pr_review.context.render import describe_dropped


def test_describe_dropped_says_why_and_links():
    assert describe_dropped(Dropped("**A.**", "fixed-later", "#8", "refs/stack/8:a.tf")) == (
        "**A.** Fixed in #8 (refs/stack/8:a.tf).")
    assert describe_dropped(Dropped("**B.**", "already-raised", "https://x/r1")) == (
        "**B.** Already raised in [this thread](https://x/r1).")
    assert describe_dropped(Dropped("**C.**", "answered", "https://x/c1")) == (
        "**C.** Answered by the author in [this reply](https://x/c1).")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_attribution.py tests/test_context_render.py -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** In `attribution.py`, add the three fields to `RunRecord`, and in `render_details`, before `lines += ["", "</details>"]`:

```python
    for line in (record.stack_line, record.context_line):
        if line:
            lines += ["", line]
    if record.not_posted:
        lines += ["", "**Findings not posted:**", ""] + [f"- {item}" for item in record.not_posted]
```

In `context/render.py`, add (it takes any object with `finding`, `reason`, `link` and `evidence`; it does not import `Dropped`, because `filter.py` imports `render.py`):

```python
def describe_dropped(d) -> str:
    if d.reason == "fixed-later":
        where = f" ({d.evidence})" if d.evidence else ""
        return f"{d.finding} Fixed in {d.link}{where}."
    if d.reason == "already-raised":
        return f"{d.finding} Already raised in [this thread]({d.link})."
    return f"{d.finding} Answered by the author in [this reply]({d.link})."
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_attribution.py tests/test_context_render.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/attribution.py src/pr_review/context/render.py tests
git commit -m "feat(pr-review): say which findings were not posted, and why"
```

---

### Task 13: Wire the context into the CLI

**Files:**
- Modify: `src/pr_review/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `RunConfig.no_context: bool`, `RunConfig.no_context_filter: bool`, `RunConfig.context_filter_model: tuple[str, str] | None` (None = follow `synthesis_model`).
  - Flags `--no-context`, `--no-context-filter`, `--context-filter-model AGENT[=MODEL]`.
  - `build_context_filter(cfg, *, workdir, context_path) -> ContextFilter | None`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_cli.py`:

```python
def test_config_context_defaults():
    cfg = config_from_args(["org/repo#1"])
    assert (cfg.no_context, cfg.no_context_filter, cfg.context_filter_model) == (False, False, None)


def test_config_context_flags():
    cfg = config_from_args(["--no-context", "--no-context-filter",
                            "--context-filter-model", "codex=gpt-5", "org/repo#1"])
    assert (cfg.no_context, cfg.no_context_filter, cfg.context_filter_model) == (True, True, ("codex", "gpt-5"))


def test_context_filter_follows_the_synthesis_model_by_default():
    from pr_review.cli import build_context_filter

    cfg = config_from_args(["--synthesis-model", "codex=gpt-5", "org/repo#1"])
    f = build_context_filter(cfg, workdir="/wd", context_path="/c.md")
    assert f._command[:4] == ["codex", "exec", "--model", "gpt-5"]


def test_no_context_filter_builds_no_filter():
    from pr_review.cli import build_context_filter

    for flag in ("--no-context-filter", "--no-context"):
        cfg = config_from_args([flag, "org/repo#1"])
        assert build_context_filter(cfg, workdir="/wd", context_path="/c.md") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** In `cli.py`:

Imports:

```python
from pr_review.checkout import cleanup, clone_pr, write_context_file
from pr_review.context.filter import ContextFilter, FilterResult, answers_by_id
from pr_review.context.gather import gather_context
from pr_review.context.github import GitHub
from pr_review.context.render import (
    describe_dropped, describe_loaded, describe_stack, prompt_summary, render_context_file,
)
```

`RunConfig` gains `no_context: bool`, `no_context_filter: bool`, `context_filter_model: tuple[str, str] | None`. Parser, after the plain-language flags:

```python
    p.add_argument(
        "--no-context", action="store_true",
        help="review the diff only: no description, discussion, issues or stack (default: false)",
    )
    p.add_argument(
        "--no-context-filter", action="store_true",
        help="give reviewers the context but do not filter findings against it (default: false)",
    )
    p.add_argument(
        "--context-filter-model", metavar="AGENT[=MODEL]", default=None,
        help="agent/model for the context filter (default: the synthesis model)",
    )
```

`config_from_args`:

```python
        no_context=args.no_context,
        no_context_filter=args.no_context_filter,
        context_filter_model=(
            _parse_synthesis_model(args.context_filter_model) if args.context_filter_model else None
        ),
```

Builder:

```python
def build_context_filter(cfg: RunConfig, *, workdir: str, context_path: str) -> ContextFilter | None:
    if cfg.no_context or cfg.no_context_filter:
        return None
    agent, model = cfg.context_filter_model or cfg.synthesis_model
    command = get_reviewer(agent).command(model, cfg.flags_by_agent.get(agent, []))
    return ContextFilter(command=command, workdir=workdir, context_path=context_path)
```

In `main`, replace the clone line with:

```python
    ctx = None
    if not cfg.no_context:
        try:
            ctx = gather_context(GitHub(cfg.target.owner, cfg.target.repo), cfg.target.number)
        except Exception as e:
            print(f"pr-review: could not load the pull request context ({e}); "
                  "reviewing the diff only.", file=sys.stderr)
        for part in ctx.failed if ctx else []:
            print(f"pr-review: context: could not load {part}.", file=sys.stderr)

    checkout = clone_pr(cfg.target.owner, cfg.target.repo, cfg.target.number,
                        stack=[e.number for e in ctx.stack] if ctx else [])
    summary, context_path = "", ""
    if ctx:
        ctx.stack = [e for e in ctx.stack if e.number in checkout.stack_refs]
        context_path = write_context_file(checkout.workdir, render_context_file(ctx))
        summary = prompt_summary(ctx, context_path)
```

Pass `context=summary` to `build_collator(...)` and `run_reviews(...)`. Build the filter next to the stage:

```python
    context_filter = build_context_filter(cfg, workdir=checkout.workdir, context_path=context_path) if ctx else None
```

Inside the `try`, replace the stage call with:

```python
        if result.payload is not None:
            filtered = (context_filter.apply(result.payload, ctx) if context_filter
                        else FilterResult(result.payload))
            answers = answers_by_id(ctx) if ctx else {}
            staged = (stage.apply(filtered.payload, answers=answers) if stage
                      else check_payload(filtered.payload))
```

Initialise `filtered = None` next to `staged = None`. After the `if staged is None:` block, print filter warnings:

```python
    for warning in filtered.warnings:
        print(f"pr-review: context filter: {warning}", file=sys.stderr)
```

And extend the `RunRecord(...)`:

```python
        stack_line=describe_stack(ctx) if ctx else None,
        context_line=describe_loaded(ctx) if ctx else None,
        not_posted=[describe_dropped(d) for d in filtered.dropped],
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pr_review/cli.py tests/test_cli.py
git commit -m "feat(pr-review): load the pull request context and filter findings against it"
```

---

### Task 14: Documentation

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Count the tests**

Run: `uv run pytest -q | tail -1` and `ls tests/test_*.py | wc -l`

- [ ] **Step 2: Update `CLAUDE.md`.** In **Testing principle**, change "The four real side effects — `git clone`, the `claude` CLI review, the `codex` CLI review, and the `gh api` post" to "The real side effects — `git clone` and fetch, the `claude` and `codex` CLI runs, and every `gh api` call (context reads, the review post and reply posts)". Update the header counts in **Test suite**, update the entries for **test_payload.py** (`Reply`, `replies` not in the review JSON), **test_checkout.py** (`refs/stack/<n>` fetches after the base; a failed stack fetch is left out; `write_context_file` inside `.git`), **test_reviewers.py** (the context summary sits before the instructions; absent without context), **test_orchestrator.py** (the summary reaches every reviewer), **test_synthesis.py** (the judge gets the summary), **test_plain_language_stage.py** (replies are checked and rewritten with the answer as context), **test_attribution.py** (reply footers; stack, context and "Findings not posted" lines), **test_output.py** (review then replies; a failed reply does not stop the others and keeps its file; a failed review posts no replies; review-only writes reply files; the confirm prompt counts replies), **test_cli.py** (`--no-context`, `--no-context-filter`, `--context-filter-model` and `build_context_filter`), and add:

- **test_context_github.py** — `GitHub.get`, `get_all` (`--paginate --slurp`, pages flattened) and `graphql` (typed `-F` variables) build the right `gh api` argv through a fake runner.
- **test_context_discussion.py** — issue comments and non-empty review bodies merge in time order; the author is marked; review comments group into threads with path and line (outdated comments keep their original line); an orphan reply becomes a root.
- **test_context_issues.py** — `#N` references are found once each, excluding the pull request itself, colours and URL fragments; pull requests are skipped; failed issue reads are reported.
- **test_context_stack.py** — native stack order and position; the base-branch chain walks down to the default branch and up through children; trees keep every branch; the depth limit; branch names are URL-encoded.
- **test_context_gather.py** — the full context from fakes; a failed part is left out and named; a failed pull request read raises.
- **test_context_render.py** — the stack map, the context file (ids and author marks), the prompt summary (both instructions), and the details-block lines for the stack, the context loaded and each dropped finding.
- **test_context_filter.py** — every verdict; bad indexes and unknown reasons are ignored; `fixed-later` naming an earlier, closed or unknown pull request is kept; a reply to someone else stays a comment, and a reply to an issue comment stays a comment with a link; replies beyond 3 go to the overflow list; the prompt; a failed call keeps every finding; `answers_by_id`.

- [ ] **Step 3: Update `README.md`.** Add a section after **Plain language**:

```markdown
### Pull request context

Before reviewing, pr-review reads the pull request's description, the GitHub
issues it links to, its discussion (comments, review bodies and review threads),
and the other pull requests in its stack — GitHub's stacked pull requests, or a
chain of pull requests whose base is the branch below. Each pull request in the
stack is fetched into the clone as `refs/stack/<n>`.

Reviewers are told to check later pull requests before reporting something
missing, and the discussion before reporting anything. Then a context filter
checks every finding: it drops findings a later pull request fixes, that the
discussion already raised, or that the author answered or deferred, and lists
them under **Findings not posted** in the review's collapsed record. When the
code proves an author's answer wrong, the finding is posted as a reply in that
thread (at most 3 per run).

- `--no-context` — review the diff only.
- `--no-context-filter` — give reviewers the context, but do not filter findings.
- `--context-filter-model AGENT[=MODEL]` — the filter's model (default: the synthesis model).
```

Add three rows to the **Options** table:

```markdown
| `--no-context` | Review the diff only | off |
| `--no-context-filter` | Do not filter findings against the context | off |
| `--context-filter-model agent[=model]` | Context filter model | the synthesis model |
```

In **Posting behaviour**, add: "Replies post after the review, one at a time. If one fails, the others still post; pr-review keeps the failed reply's file, prints a command to post it, and exits 1."

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest`
Expected: all PASS; counts match `CLAUDE.md`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs(pr-review): document pull request context and replies"
```

- [ ] **Step 6: Manual check (not automated).** On a stack you own where a later pull request fixes a gap in the first: run `pr-review --print-only --review-type infracode --model claude <first PR>`, and confirm the gap appears under **Findings not posted** with "Fixed in #<later>", the stderr shows no context load failures, and `--keep-clone` leaves `.git/pr-review/pr-context.md` with the discussion.
