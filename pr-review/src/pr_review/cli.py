"""pr-review command-line entry point."""
from __future__ import annotations

import argparse
import shlex
import sys
from dataclasses import dataclass

from pr_review.checkout import cleanup, clone_pr
from pr_review.orchestrator import ReviewJob, run_reviews
from pr_review.reviewers import available as reviewers_available, get_reviewer
from pr_review.review_types import available as types_available, get_review_type
from pr_review.target import Target, parse_target
from pr_review import output

DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class RunConfig:
    target: Target
    reviewer_names: list[str]
    type_names: list[str]
    model: str
    extra_flags: list[str]
    yes: bool
    no_post: bool
    keep: bool


def _split(value: str) -> list[str]:
    return [s for s in (part.strip() for part in value.split(",")) if s]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr-review",
        description="Review a GitHub PR in an isolated clone with one or more LLMs.",
    )
    p.add_argument("target", help="PR URL or owner/repo#N (or 'help' for this message)")
    p.add_argument(
        "--reviewer", default="claude",
        help=f"comma-separated reviewers (available: {', '.join(reviewers_available())})",
    )
    p.add_argument(
        "--type", dest="types", default="test-gap",
        help=f"comma-separated review types (available: {', '.join(types_available())})",
    )
    p.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Claude model id (default: {DEFAULT_MODEL})",
    )
    p.add_argument(
        "--post-without-prompting", action="store_true",
        help="Post the review without the confirmation prompt",
    )
    p.add_argument(
        "--print-only", action="store_true",
        help="Print the review only; never post and never prompt",
    )
    p.add_argument(
        "--claude-flags", default="",
        help='Extra flags appended to the claude invocation, e.g. --claude-flags="--debug"',
    )
    p.add_argument(
        "--keep-clone", action="store_true",
        help="Keep the temporary clone on exit instead of deleting it",
    )
    return p


def config_from_args(argv: list[str]) -> RunConfig:
    # `pr-review help` behaves like `pr-review --help`.
    if argv and argv[0] == "help":
        argv = ["--help", *argv[1:]]
    args = build_parser().parse_args(argv)
    return RunConfig(
        target=parse_target(args.target),
        reviewer_names=_split(args.reviewer),
        type_names=_split(args.types),
        model=args.model,
        extra_flags=shlex.split(args.claude_flags),
        yes=args.post_without_prompting,
        no_post=args.print_only,
        keep=args.keep_clone,
    )


def build_jobs(cfg: RunConfig) -> list[ReviewJob]:
    return [
        ReviewJob(get_reviewer(r), get_review_type(t))
        for r in cfg.reviewer_names
        for t in cfg.type_names
    ]


def main(argv: list[str] | None = None) -> int:
    cfg = config_from_args(sys.argv[1:] if argv is None else argv)
    jobs = build_jobs(cfg)  # validates reviewer/type names before any clone

    checkout = clone_pr(cfg.target.owner, cfg.target.repo, cfg.target.number)
    print(
        f"pr-review: {cfg.target.slug}#{cfg.target.number} "
        f"base=origin/{checkout.base} jobs={len(jobs)}",
        file=sys.stderr,
    )
    try:
        payload = run_reviews(
            jobs=jobs, workdir=checkout.workdir, base=checkout.base,
            owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number,
            model=cfg.model, extra_flags=cfg.extra_flags,
        )
    finally:
        if cfg.keep:
            print(f"pr-review: kept checkout at {checkout.workdir}", file=sys.stderr)
        else:
            cleanup(checkout)

    print(output.render(payload))
    mode = output.decide_mode(
        yes=cfg.yes, no_post=cfg.no_post, has_tty=output.tty_available()
    )
    output.dispatch(mode, cfg.target, payload)
    return 0
