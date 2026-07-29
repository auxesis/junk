"""pr-review command-line entry point."""
from __future__ import annotations

import argparse
import shlex
import sys
from dataclasses import dataclass

from pr_review.checkout import cleanup, clone_pr
from pr_review.collate import Collator, DeterministicMergeCollator
from pr_review.orchestrator import ReviewJob, run_reviews
from pr_review.reviewers import available as reviewers_available, get_reviewer
from pr_review.review_types import available as types_available, get_review_type
from pr_review.synthesis import LLMSynthesisCollator
from pr_review.target import Target, parse_target
from pr_review import output, prompts

DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class RunConfig:
    target: Target
    agent_models: list[tuple[str, str]] | None
    type_names: list[str] | None
    flags_by_agent: dict[str, list[str]]
    yes: bool
    no_post: bool
    keep: bool
    synthesis_model: tuple[str, str]
    no_synthesis: bool


def _split(value: str) -> list[str]:
    return [s for s in (part.strip() for part in value.split(",")) if s]


def _parse_synthesis_model(value: str) -> tuple[str, str]:
    agent, sep, model = value.partition("=")
    agent = agent.strip()
    reviewer = get_reviewer(agent)  # validates the agent; raises ValueError
    model = model.strip() if (sep and model.strip()) else reviewer.default_model
    return (agent, model)


def _parse_agent_models(values: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []

    def add(agent: str, model: str) -> None:
        if (agent, model) not in pairs:
            pairs.append((agent, model))

    for value in values:
        agent_part, sep, models_str = value.partition("=")
        if sep:
            # "agent=model[,model...]" — one agent, comma-separated models.
            agent = agent_part.strip()
            reviewer = get_reviewer(agent)  # validates agent; raises ValueError
            for model in _split(models_str) or [reviewer.default_model]:
                add(agent, model)
        else:
            # bare "agent[,agent...]" — each agent uses its default model.
            for agent in _split(agent_part):
                add(agent, get_reviewer(agent).default_model)
    return pairs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr-review",
        description="Review a GitHub PR in an isolated clone with one or more LLMs.",
    )
    p.add_argument("target", help="PR URL or owner/repo#N (or 'help' for this message)")
    p.add_argument(
        "--model", action="append", metavar="AGENT[=MODELS]", default=None,
        help=(
            "per-agent models, repeatable, e.g. --model claude=claude-opus-4-8,claude-fable-5 "
            f"(agents: {', '.join(reviewers_available())}; default: claude=claude-opus-4-8)"
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
        "--post-without-prompting", action="store_true",
        help="Post the review without the confirmation prompt (default: false)",
    )
    p.add_argument(
        "--print-only", action="store_true",
        help="Print the review only; never post and never prompt (default: false)",
    )
    p.add_argument(
        "--claude-flags", default="",
        help='Extra flags for claude jobs, e.g. --claude-flags="--debug" (default: "")',
    )
    p.add_argument(
        "--codex-flags", default="",
        help='Extra flags for codex jobs, e.g. --codex-flags="--oss" (default: "")',
    )
    p.add_argument(
        "--keep-clone", action="store_true",
        help="Keep the temporary clone on exit instead of deleting it (default: false)",
    )
    p.add_argument(
        "--synthesis-model", metavar="AGENT[=MODEL]", default=None,
        help=(
            "judge agent/model that de-dupes and verifies findings across jobs "
            f"(default: claude={DEFAULT_MODEL})"
        ),
    )
    p.add_argument(
        "--no-synthesis", action="store_true",
        help="skip the synthesis pass; raw-merge multi-job results (default: false)",
    )
    return p


def config_from_args(argv: list[str]) -> RunConfig:
    # `pr-review help` behaves like `pr-review --help`.
    if argv and argv[0] == "help":
        argv = ["--help", *argv[1:]]
    args = build_parser().parse_args(argv)

    agent_models = _parse_agent_models(args.model) if args.model else None
    flags_by_agent: dict[str, list[str]] = {}
    if args.claude_flags:
        flags_by_agent["claude"] = shlex.split(args.claude_flags)
    if args.codex_flags:
        flags_by_agent["codex"] = shlex.split(args.codex_flags)

    return RunConfig(
        target=parse_target(args.target),
        agent_models=agent_models,
        type_names=_split(args.types) if args.types is not None else None,
        flags_by_agent=flags_by_agent,
        yes=args.post_without_prompting,
        no_post=args.print_only,
        keep=args.keep_clone,
        synthesis_model=(
            _parse_synthesis_model(args.synthesis_model)
            if args.synthesis_model else ("claude", DEFAULT_MODEL)
        ),
        no_synthesis=args.no_synthesis,
    )


def build_collator(cfg: RunConfig, *, workdir: str, base: str) -> Collator:
    if cfg.no_synthesis:
        return DeterministicMergeCollator()
    agent, model = cfg.synthesis_model
    command = get_reviewer(agent).command(model, cfg.flags_by_agent.get(agent, []))
    return LLMSynthesisCollator(
        command=command, workdir=workdir,
        owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number, base=base,
    )


def build_jobs(cfg: RunConfig) -> list[ReviewJob]:
    return [
        ReviewJob(get_reviewer(agent), get_review_type(t), model,
                  cfg.flags_by_agent.get(agent, []))
        for agent, model in cfg.agent_models
        for t in cfg.type_names or []
    ]


def resolve_agent_models(
    agent_models: list[tuple[str, str]] | None,
    *,
    has_tty: bool,
    prompt_fn=prompts.prompt_agent_models_via_tty,
) -> list[tuple[str, str]]:
    if agent_models is not None:
        return agent_models
    if not has_tty:
        print(
            "pr-review: no terminal to prompt for --model.\n"
            f"  pass one, e.g. --model claude={DEFAULT_MODEL}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return prompt_fn(reviewers_available(), lambda a: get_reviewer(a).default_model)


def resolve_review_types(
    type_names: list[str] | None,
    *,
    has_tty: bool,
    prompt_fn=prompts.prompt_review_types_via_tty,
) -> list[str]:
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


def main(argv: list[str] | None = None) -> int:
    cfg = config_from_args(sys.argv[1:] if argv is None else argv)
    cfg.agent_models = resolve_agent_models(
        cfg.agent_models, has_tty=output.tty_available()
    )
    cfg.type_names = resolve_review_types(
        cfg.type_names, has_tty=output.tty_available()
    )
    jobs = build_jobs(cfg)  # validates agent/type names before any clone

    checkout = clone_pr(cfg.target.owner, cfg.target.repo, cfg.target.number)
    print(
        f"pr-review: {cfg.target.slug}#{cfg.target.number} "
        f"base={checkout.base_ref}@{checkout.base[:12]} jobs={len(jobs)}",
        file=sys.stderr,
    )
    collator = build_collator(cfg, workdir=checkout.workdir, base=checkout.base)
    try:
        result = run_reviews(
            jobs=jobs, workdir=checkout.workdir, base=checkout.base,
            owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number,
            collator=collator,
        )
    finally:
        if cfg.keep:
            print(f"pr-review: kept checkout at {checkout.workdir}", file=sys.stderr)
        else:
            cleanup(checkout)

    for label, rtype, err in result.failures:
        print(f"pr-review: {label} / {rtype} failed: {err}", file=sys.stderr)

    if result.payload is None:
        print(
            f"pr-review: all {len(jobs)} review job(s) failed; no review produced.",
            file=sys.stderr,
        )
        return 1

    output.show_review(result.payload)
    mode = output.decide_mode(
        yes=cfg.yes, no_post=cfg.no_post, has_tty=output.tty_available()
    )
    output.dispatch(mode, cfg.target, result.payload)
    return 0
