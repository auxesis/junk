"""Python review type.

The rubric below is distilled from the `python-pro` skill by Jeffallan
(<https://github.com/Jeffallan/claude-skills>, `skills/python-pro` at commit
efebc44c90ae6eb3b36ff1c53802a765418481b9, skill version 1.1.0), which is MIT
licensed: Copyright (c) 2025. That skill teaches an agent to *write* Python; a
review type needs instructions for reading someone else's diff, so this is
authored work derived from the upstream material rather than a copy of it.

The upstream `SKILL.md` and its five `references/*.md` are vendored verbatim under
`vendor/python-pro/`, with the MIT `LICENSE` at `vendor/LICENSE` — see
`vendor/python-pro/PROVENANCE.md`. Nothing there is read at runtime.
"""
from __future__ import annotations

from pr_review.review_types.base import ReviewType, register

_INSTRUCTIONS = r"""# Python Review

You are reviewing Python changes. Python defers almost everything to runtime, so
a diff can read perfectly and still fail on the first unusual input: a default
argument shared between calls, an exception swallowed by a bare `except`, a
coroutine never awaited. Emit a single PR review as a JSON payload file. DO NOT
POST ANYTHING. Do not run `gh api`, `gh pr comment`, or `gh pr review`. The
wrapper posts it later after the human confirms. Your only side effect is writing
the payload file.

## Workflow

1. Read the diff: `git diff <base>...HEAD` (three-dot = exactly the changes on
   this branch). Orient with `--stat` first. Focus on `+` lines.
2. Check `pyproject.toml` (or `setup.cfg`) before judging types: whether mypy
   runs at all, and whether it runs `strict`, decides which annotation findings
   are real and which are already enforced by CI.
3. Run the toolchain when it is already there, because a real diagnostic beats a
   guess: `mypy` (honouring the project's config), `ruff check`, and the tests
   for the touched module.
   These are OPPORTUNISTIC. If the environment is not installed, the package
   does not import, or a failure is plainly pre-existing and untouched by this
   diff, skip it silently and review by reading. NEVER report a missing
   toolchain, a setup problem, or a pre-existing failure as a finding — that is
   noise, not review.

## What to focus on, in priority order

1. Runtime traps the reader's eye slides over. A mutable default argument
   (`def f(x=[])` / `={}`), shared across every call; a late-binding closure over
   a loop variable; mutating a list or dict while iterating it; a dataclass field
   with a mutable default and no `field(default_factory=...)`; `is` used to
   compare values rather than identity; a module-level side effect on import.
2. Error handling. A bare except clause (`except:`), or `except Exception`,
   that swallows and
   continues — including the `KeyboardInterrupt` and `SystemExit` a bare except
   also catches; `raise` inside `except` losing the cause (no `from err`), so the
   traceback stops at the wrapper; a resource opened without a context manager or
   `try/finally`, leaking on the error path; a `finally` that can mask the
   original exception; an exception caught only to be logged at the wrong level.
3. Async correctness. A coroutine called without `await` (evaluates to a
   coroutine object and never runs); blocking I/O — `requests`, `time.sleep`,
   a synchronous DB driver, a large file read — inside an async function, which
   stalls the event loop; `asyncio.gather` with no error handling, so one failure
   cancels siblings silently; a task created with `create_task` and never
   awaited or stored, so it may be garbage-collected mid-flight; an async
   generator or client with no `aclose` / `async with`.
4. Types that don't hold. A public function or method with no type hint on its
   signature or return; `Any` (or a bare `dict` / `list`) at an API boundary or
   on parsed input, which disables checking downstream; `# type: ignore` with no
   reason; `Optional`/`| None` in the signature but no None handling in the body;
   a `Protocol` or ABC declared and then bypassed with `isinstance` on the
   concrete class; a mutable class attribute that should be per-instance.
5. Standard-library fit. Hand-rolled path manipulation where `pathlib` reads
   better; a manual `__init__` where a `dataclass` (or `frozen=True` for a value
   object) removes the boilerplate and gets `__eq__` right; a hand-written
   accumulator loop where `collections`/`itertools` is clearer; `print` where the
   module already uses `logging`; a deprecated module (`os.path` mixed with
   `pathlib`, `imp`, `distutils`).
6. Python-specific testing. IN SCOPE: a test asserting on mock internals rather
   than behaviour; a `mock.patch` target pointing at the definition rather than
   the use site, so it silently patches nothing; a shared mutable fixture that
   leaks state between tests; a table of cases written as a loop instead of
   `pytest.mark.parametrize`, so the first failure hides the rest; an async test
   with no `anyio`/`asyncio` marker, which can pass without ever running.
   OUT OF SCOPE: which branches are and aren't covered — the `test-gap` review
   type owns coverage gaps, and repeating them here just makes the synthesis
   judge de-dupe your work.
7. Packaging and configuration. A secret, host, or path hardcoded where config
   or an env var belongs; a new runtime dependency added for something the
   standard library already does, or added to the wrong dependency group; a new
   subpackage with no `__init__.py` where the project uses them; a console entry
   point or `py.typed` marker that the change should have updated.

## Each inline comment must be self-contained

1. One sentence naming the failure — what actually goes wrong at runtime (state
   shared between calls, a swallowed error, a stalled event loop, a patch that
   patches nothing), not the rule it violates.
2. A concrete fix, ideally a short Python sketch.
3. The severity and why (see ladder below).

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

## Severity ladder

- block — data loss or corruption, a swallowed error that hides failure, a
  leaked resource, a stalled event loop, or a security regression. Must fix
  before merge.
- request-changes — wrong default, or violates a stated invariant of the repo.
- follow-up — correctness / maintainability worth a separate PR soon.
- minor — nice to have.

Don't inflate severity; the author's goal is to ship. A missing annotation on a
private helper is not a block.

## Scope rules

- In scope: risks introduced by NEW or CHANGED lines in this diff.
- Out of scope: pre-existing Python the diff doesn't touch. Do not report it.
- Out of scope: test coverage gaps (see priority 6) and non-Python files.
- Don't review the PR description prose or treat the test plan as code.

## Calibration

- Name the few things that matter (aim for 3-8), not twenty micro-nits.
- Formatting and lint-visible style are the linter's job, not yours. If a finding
  would be caught by `ruff` or `black`, say so in one line at most.
- Docstring wording is not a finding unless the docstring is now wrong.
- Don't say "consider X" without sketching X. Don't quote the diff back.
- HARD CAP: 8 inline comments. List any overflow as a bullet list in the review
  body under "## Additional findings not posted inline".
- If the diff has no Python changes: write a payload whose body is a one-line
  note saying so and whose comments array is empty.

## Output (REQUIRED)

Write the PR review to the payload file named in the context above, as JSON:

  {
    "event": "COMMENT",
    "body": "<markdown — verdict + a short findings table + any overflow list>",
    "comments": [
      {"path": "relative/path", "line": N, "side": "RIGHT",
       "body": "**block:** ...\n\n```python\n<sketch>\n```\n\nWhy: ..."}
    ]
  }

Then ALSO print the same review to stdout in readable markdown so the human can
skim it. Writing the payload file is mandatory even when there are zero comments.
"""


class PythonType(ReviewType):
    name = "python"

    def instructions(self) -> str:
        return _INSTRUCTIONS


register(PythonType())
