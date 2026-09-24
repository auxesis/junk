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
