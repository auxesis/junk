# rust-engineer — vendored skill

Verbatim copy of the upstream `rust-engineer` skill, kept here so the MIT notice
travels with the copy and so upstream drift is a reviewable diff.

| | |
|---|---|
| Upstream | <https://github.com/Jeffallan/claude-skills> |
| Path | `skills/rust-engineer/` |
| Commit | `efebc44c90ae6eb3b36ff1c53802a765418481b9` |
| Skill version | 1.1.0 (`metadata.version` in `SKILL.md`) |
| Author | <https://github.com/Jeffallan> |
| License | MIT — see `../LICENSE`, copied verbatim from the upstream repository root |
| Vendored | 2026-09-02 |

Files: `SKILL.md`, `references/async.md`, `references/error-handling.md`, `references/ownership.md`, `references/testing.md`, `references/traits.md`.

## What is and isn't used at runtime

Nothing here is read at runtime. `pyproject.toml` packages only `src/pr_review`,
so these files never ship in the wheel and `pr-review` has no dependency on them
or on the network.

`src/pr_review/review_types/rust.py` holds a review rubric **distilled** from these
files — the skill teaches an agent to *write* code, and a review type needs
instructions for reading a diff, so the rubric is authored work derived from the
upstream material rather than a copy of it. These files are the record of what it
was derived from, and they back the `--review-type rust` prompt.

## Re-syncing

```bash
mise run sync-vendor                    # every skill, from main
mise run sync-vendor SKILL=rust-engineer   # just this one
mise run sync-vendor REF=v2             # or a tag / sha
```

Then read the diff, decide whether the rubric in `rust.py` needs to change,
and update the commit, version, and date above in the same commit.
