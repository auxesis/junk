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
from pr_review import output, prompts

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_AGENT = "claude"


@dataclass
class RunConfig:
    target: Target
    agent_names: list[str]
    type_names: list[str] | None  # None = --review-type omitted (resolve later)
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
        "--agent", default=DEFAULT_AGENT,
        help=(
            "comma-separated agents "
            f"(available: {', '.join(reviewers_available())}, default: {DEFAULT_AGENT})"
        ),
    )
    p.add_argument(
        "--review-type", dest="types", default=None,
        help=(
            "comma-separated review types "
            f"(available: {', '.join(types_available())}; omit to choose interactively)"
        ),
    )
    p.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Claude model id (default: {DEFAULT_MODEL})",
    )
    p.add_argument(
        "--post-without-prompting", action="store_true",
        help="Post the review without the confirmation prompt (default: false)",
    )
    p.add_argument(
        "--print-only", action="store_true",
        help="Print the review only; never post and never prompt (default: false)",
    )
    p.add_argument(
        "--claude-flags", default="",
        help='Extra flags appended to the claude invocation, e.g. --claude-flags="--debug" (default: "")',
    )
    p.add_argument(
        "--keep-clone", action="store_true",
        help="Keep the temporary clone on exit instead of deleting it (default: false)",
    )
    return p


def config_from_args(argv: list[str]) -> RunConfig:
    # `pr-review help` behaves like `pr-review --help`.
    if argv and argv[0] == "help":
        argv = ["--help", *argv[1:]]
    args = build_parser().parse_args(argv)
    return RunConfig(
        target=parse_target(args.target),
        agent_names=_split(args.agent),
        type_names=_split(args.types) if args.types is not None else None,
        model=args.model,
        extra_flags=shlex.split(args.claude_flags),
        yes=args.post_without_prompting,
        no_post=args.print_only,
        keep=args.keep_clone,
    )


def resolve_review_types(
    type_names: list[str] | None,
    *,
    has_tty: bool,
    prompt_fn=prompts.prompt_review_types_via_tty,
) -> list[str]:
    """Return the review types to run, prompting interactively if unspecified.

    If `--review-type` was given, use it. Otherwise prompt on an interactive
    terminal; with no terminal, error (exit 2) rather than guessing.
    """
    if type_names is not None:
        return type_names
    if not has_tty:
        print(
            "pr-review: no terminal to prompt for --review-type.\n"
            f"  pass one, e.g. --review-type {','.join(types_available())}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return prompt_fn(types_available())


def build_jobs(cfg: RunConfig) -> list[ReviewJob]:
    return [
        ReviewJob(get_reviewer(a), get_review_type(t))
        for a in cfg.agent_names
        for t in cfg.type_names or []
    ]


def main(argv: list[str] | None = None) -> int:
    cfg = config_from_args(sys.argv[1:] if argv is None else argv)
    cfg.type_names = resolve_review_types(
        cfg.type_names, has_tty=output.tty_available()
    )
    jobs = build_jobs(cfg)  # validates agent/type names before any clone

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
