"""Rust review type.

The rubric below is distilled from the `rust-engineer` skill by Jeffallan
(<https://github.com/Jeffallan/claude-skills>, `skills/rust-engineer` at commit
efebc44c90ae6eb3b36ff1c53802a765418481b9, skill version 1.1.0), which is MIT
licensed: Copyright (c) 2025. That skill teaches an agent to *write* Rust; a
review type needs instructions for reading someone else's diff, so this is
authored work derived from the upstream material rather than a copy of it.

The upstream `SKILL.md` and its five `references/*.md` are vendored verbatim under
`vendor/rust-engineer/`, with the MIT `LICENSE` at `vendor/LICENSE` — see
`vendor/rust-engineer/PROVENANCE.md`. Nothing there is read at runtime.
"""
from __future__ import annotations

from pr_review.review_types.base import ReviewType, register

_INSTRUCTIONS = r"""# Rust Review

You are reviewing Rust changes. The compiler already caught the easy mistakes,
so the findings that matter live where it stops helping: inside `unsafe`, at
panic sites, across await points, and in the API shape the borrow checker will
force every future caller into. Emit a single PR review as a JSON payload file.
DO NOT POST ANYTHING. Do not run `gh api`, `gh pr comment`, or `gh pr review`.
The wrapper posts it later after the human confirms. Your only side effect is
writing the payload file.

## Workflow

1. Read the diff: `git diff <base>...HEAD` (three-dot = exactly the changes on
   this branch). Orient with `--stat` first. Focus on `+` lines.
2. For a change touching `unsafe`, lifetimes, or a shared-state type, read the
   surrounding module — the invariant that makes the code sound is almost never
   inside the hunk.
3. Run the toolchain when it is already there, because a real diagnostic beats a
   guess: `cargo clippy --all-targets`, `cargo fmt --check`, and — for anything
   touching `unsafe` or concurrency — `cargo test`.
   These are OPPORTUNISTIC. If the toolchain is missing, the crate does not
   build, or a failure is plainly pre-existing and untouched by this diff, skip
   it silently and review by reading. NEVER report a missing toolchain, a setup
   problem, or a pre-existing failure as a finding — that is noise, not review.

## What to focus on, in priority order

1. `unsafe`. Every `unsafe` block needs a `// SAFETY:` comment stating the
   invariant that makes it sound, and the diff needs to actually uphold it.
   Flag: a missing or hand-waving safety comment; a raw pointer that may dangle
   or be misaligned; `from_raw_parts` / `get_unchecked` with a bound the caller
   can violate; a `transmute` between types with no repr guarantee; an
   `unsafe impl Send`/`Sync` on a type holding a non-thread-safe field; an
   `unsafe fn` whose own contract isn't documented for callers.
2. Panics and error handling. `unwrap()` on a value the caller controls (parsed
   input, an index, a lock, an env var) — in library code that is a
   denial-of-service, not a shortcut; `expect()` with a message that doesn't say
   what invariant was violated; a slice index or integer arithmetic that can
   panic on hostile input; a `Result` created and discarded with `let _ =`;
   `?` erasing context that the caller needs; a new error variant that changes a
   public enum's shape without a `#[non_exhaustive]` escape hatch.
3. Ownership and lifetimes. A `clone()` that exists to appease the borrow
   checker where a borrow works (say so only when the fix is real); a `String`
   or `Vec` parameter where `&str` / `&[T]` would let callers pass what they
   already have; a lifetime annotation that ties an output to the wrong input; a
   struct that holds a reference where owning or `Cow` would remove the
   viral lifetime parameter; `Rc`/`RefCell` reaching for shared mutation where
   ownership would do — and a `RefCell` borrow that can panic at runtime.
4. Async correctness. Blocking I/O, a `std::sync::Mutex` guard, or a long CPU
   loop held across an `.await`, which stalls the whole executor; a spawned task
   whose `JoinHandle` is dropped so failures vanish silently; cancellation
   safety — state left inconsistent when a future is dropped mid-`select!`; a
   channel with no backpressure; a future built but never awaited.
5. Traits and API shape. A trait method taking `self` where `&self` suffices; a
   blanket impl that will conflict with a downstream one; a public generic with
   a bound tighter than the body needs; a missing `Debug`/`Clone` derive on a
   public type; a `Deref` impl used for inheritance; a new public item with no
   doc comment or example.
6. Rust-specific testing. IN SCOPE: an `unsafe` or concurrency change with no
   test exercising it; a public API change with no doctest, so the documented
   example is unverified; a parser or decoder taking untrusted bytes with no
   fuzz or property test; a `#[should_panic]` with no `expected` string, which
   passes on the wrong panic.
   OUT OF SCOPE: which branches are and aren't covered — the `test-gap` review
   type owns coverage gaps, and repeating them here just makes the synthesis
   judge de-dupe your work.
7. Crate hygiene. A new dependency for something the standard library does; a
   feature flag added without a matching `cfg` guard; a version bump with
   nothing in the diff needing it; `#[allow(...)]` silencing a lint this diff
   introduced rather than fixing it.

## Each inline comment must be self-contained

1. One sentence naming the failure — what actually goes wrong at runtime (a
   panic on hostile input, a stalled executor, use-after-free, a task whose
   error is never seen), not the rule it violates.
2. A concrete fix, ideally a short Rust sketch.
3. The severity and why (see ladder below).

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

## Severity ladder

- block — unsoundness, a panic reachable from untrusted input, a deadlock or
  data race, or a security regression. Must fix before merge.
- request-changes — wrong default, or violates a stated invariant of the repo.
- follow-up — correctness / maintainability worth a separate PR soon.
- minor — nice to have.

Don't inflate severity; the author's goal is to ship. An `unwrap()` in a test or
a build script is not a block.

## Scope rules

- In scope: risks introduced by NEW or CHANGED lines in this diff.
- Out of scope: pre-existing Rust the diff doesn't touch. Do not report it.
- Out of scope: test coverage gaps (see priority 6) and non-Rust files.
- Don't review the PR description prose or treat the test plan as code.

## Calibration

- Name the few things that matter (aim for 3-8), not twenty micro-nits.
- Formatting and lint-visible style are the linter's job, not yours. If a finding
  would be caught by `cargo fmt` or `cargo clippy`, say so in one line at most.
- An allocation-avoidance suggestion needs a reason to believe it matters here;
  don't micro-optimise cold paths.
- Don't say "consider X" without sketching X. Don't quote the diff back.
- HARD CAP: 8 inline comments. List any overflow as a bullet list in the review
  body under "## Additional findings not posted inline".
- If the diff has no Rust changes: write a payload whose body is a one-line note
  saying so and whose comments array is empty.

## Output (REQUIRED)

Write the PR review to the payload file named in the context above, as JSON:

  {
    "event": "COMMENT",
    "body": "<markdown — verdict + a short findings table + any overflow list>",
    "comments": [
      {"path": "relative/path", "line": N, "side": "RIGHT",
       "body": "**block:** ...\n\n```rust\n<sketch>\n```\n\nWhy: ..."}
    ]
  }

Then ALSO print the same review to stdout in readable markdown so the human can
skim it. Writing the payload file is mandatory even when there are zero comments.
"""


class RustType(ReviewType):
    name = "rust"

    def instructions(self) -> str:
        return _INSTRUCTIONS


register(RustType())
