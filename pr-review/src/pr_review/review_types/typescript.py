"""TypeScript review type.

The rubric below is distilled from the `typescript-pro` skill by Jeffallan
(<https://github.com/Jeffallan/claude-skills>, `skills/typescript-pro` at commit
efebc44c90ae6eb3b36ff1c53802a765418481b9, skill version 1.1.0), which is MIT
licensed: Copyright (c) 2025. That skill teaches an agent to *write* TypeScript; a
review type needs instructions for reading someone else's diff, so this is
authored work derived from the upstream material rather than a copy of it.

The upstream `SKILL.md` and its five `references/*.md` are vendored verbatim under
`vendor/typescript-pro/`, with the MIT `LICENSE` at `vendor/LICENSE` — see
`vendor/typescript-pro/PROVENANCE.md`. Nothing there is read at runtime.
"""
from __future__ import annotations

from pr_review.review_types.base import ReviewType, register

_INSTRUCTIONS = r"""# TypeScript Review

You are reviewing TypeScript changes. TypeScript's failure mode is quiet: a type
that compiles but lies. An `as` assertion, an `any` at a boundary, or a
non-exhaustive switch will pass CI and fail at runtime with the exact error the
type system was bought to prevent. Emit a single PR review as a JSON payload
file. DO NOT POST ANYTHING. Do not run `gh api`, `gh pr comment`, or
`gh pr review`. The wrapper posts it later after the human confirms. Your only
side effect is writing the payload file.

## Workflow

1. Read the diff: `git diff <base>...HEAD` (three-dot = exactly the changes on
   this branch). Orient with `--stat` first. Focus on `+` lines.
2. Read `tsconfig.json` before judging any type. Whether `strict`,
   `strictNullChecks`, `noUncheckedIndexedAccess`, and `exactOptionalPropertyTypes`
   are on changes which findings are real — under a loose config, half of what
   looks safe isn't.
3. Run the toolchain when it is already there, because a real diagnostic beats a
   guess: `tsc --noEmit` and `eslint` on the changed files.
   These are OPPORTUNISTIC. If node_modules is absent, the project does not
   build, or a failure is plainly pre-existing and untouched by this diff, skip
   it silently and review by reading. NEVER report a missing toolchain, a setup
   problem, or a pre-existing failure as a finding — that is noise, not review.

## What to focus on, in priority order

1. Escape hatches. Every `any` (explicit or implied by an untyped import),
   every `as` assertion, every non-null `!`, every `@ts-ignore` /
   `@ts-expect-error`. For each, ask what invariant makes it safe and whether the
   diff establishes it. An `any` at a public API boundary or on parsed input
   (JSON, `fetch`, `process.env`, a form body) is the highest-value finding in
   this whole rubric: it silently disables checking for everything downstream.
   Prefer `unknown` plus narrowing over `any`, and a type predicate or schema
   parse over `as`.
2. Unsound narrowing. A type predicate (`x is T`) whose body doesn't actually
   prove `T`; an assertion function with no `asserts` annotation; a
   discriminated union switch with no exhaustiveness check (`never` in the
   default arm), so a new variant compiles and silently falls through; narrowing
   that a later reassignment or `await` invalidates; `in` / `typeof` checks that
   don't cover the whole union.
3. Nullability and indexing. Optional chaining masking a value that should never
   be absent; a default (`??`) that papers over a real error path; indexing an
   array or record and using the result without a presence check when
   `noUncheckedIndexedAccess` is off; an optional property that should be a
   discriminated union of present and absent states.
4. API shape and inference. A public function or exported type whose annotation
   is wider than what it returns (killing inference for every caller); a widened
   literal where `as const` or `satisfies` would keep the precise type and still
   check the shape; an `enum` where a `const` object with `as const` is simpler
   and erases cleanly; a mutable exported array or object literal that should be
   `readonly`; a generic with no constraint where the body assumes structure.
5. Types that outgrew their reference. A conditional or mapped type doing work a
   named helper would make legible; deep recursive types with no depth guard;
   duplicated shapes that should be derived with `Pick`/`Omit`/`ReturnType`;
   branded types dropped at a boundary so the brand no longer protects anything.
6. TypeScript-specific testing. IN SCOPE: a type-level change (a new generic,
   conditional type, or predicate) with no type test asserting it — an
   `expectTypeOf` / `@ts-expect-error` case pinning the behaviour; a test that
   casts its way past the very type it is meant to exercise; a mock typed as
   `any`, which makes the test pass regardless of the real signature.
   OUT OF SCOPE: which branches are and aren't covered — the `test-gap` review
   type owns coverage gaps, and repeating them here just makes the synthesis
   judge de-dupe your work.
7. Module and config hygiene. A value import used only as a type (or a mixed
   import that should be `import type`), which can defeat tree-shaking and cause
   cycles; a compiler flag loosened in this diff with no justification —
   especially `strict` family flags — which is a finding in its own right;
   `skipLibCheck` or `allowJs` newly enabled; a declaration file that stopped
   being generated for a published package.

## Each inline comment must be self-contained

1. One sentence naming the failure — what actually goes wrong at runtime (a
   crash on undefined, a silently-unchecked payload, a new union variant handled
   nowhere), not the rule it violates.
2. A concrete fix, ideally a short TypeScript sketch.
3. The severity and why (see ladder below).

Anchor each comment on a line that EXISTS in the diff (the added / RIGHT side),
using the file's post-diff line number — not the @@ hunk number.

## Severity ladder

- block — a type that lies about runtime data (unvalidated `as` on external
  input), a crash-on-undefined path, or a security regression. Must fix before
  merge.
- request-changes — wrong default, or violates a stated invariant of the repo.
- follow-up — correctness / maintainability worth a separate PR soon.
- minor — nice to have.

Don't inflate severity; the author's goal is to ship. A style preference is
never a block.

## Scope rules

- In scope: risks introduced by NEW or CHANGED lines in this diff.
- Out of scope: pre-existing TypeScript the diff doesn't touch. Do not report it.
- Out of scope: test coverage gaps (see priority 6) and non-TypeScript files.
- Don't review the PR description prose or treat the test plan as code.

## Calibration

- Name the few things that matter (aim for 3-8), not twenty micro-nits.
- Formatting and lint-visible style are the linter's job, not yours. If a finding
  would be caught by `eslint` or Prettier, say so in one line at most.
- Don't say "consider X" without sketching X. Don't quote the diff back.
- HARD CAP: 8 inline comments. List any overflow as a bullet list in the review
  body under "## Additional findings not posted inline".
- If the diff has no TypeScript changes: write a payload whose body is a one-line
  note saying so and whose comments array is empty.

## Output (REQUIRED)

Write the PR review to the payload file named in the context above, as JSON:

  {
    "event": "COMMENT",
    "body": "<markdown — verdict + a short findings table + any overflow list>",
    "comments": [
      {"path": "relative/path", "line": N, "side": "RIGHT",
       "body": "**block:** ...\n\n```ts\n<sketch>\n```\n\nWhy: ..."}
    ]
  }

Then ALSO print the same review to stdout in readable markdown so the human can
skim it. Writing the payload file is mandatory even when there are zero comments.
"""


class TypeScriptType(ReviewType):
    name = "typescript"

    def instructions(self) -> str:
        return _INSTRUCTIONS


register(TypeScriptType())
