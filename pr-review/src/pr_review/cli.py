"""pr-review command-line entry point."""
from __future__ import annotations

import argparse
import shlex
import sys
from dataclasses import dataclass

from pr_review.attribution import RunRecord, finalize
from pr_review.checkout import cleanup, clone_pr, write_context_file
from pr_review.collate import Collator, DeterministicMergeCollator
from pr_review.context.filter import ContextFilter, FilterResult, answers_by_id
from pr_review.context.gather import gather_context
from pr_review.context.github import GitHub
from pr_review.context.render import (
    describe_dropped, describe_loaded, describe_stack, prompt_summary, render_context_file,
)
from pr_review.orchestrator import ReviewJob, run_reviews
from pr_review.plain_language.stage import PlainLanguageStage, check_payload, format_report
from pr_review.reviewers import available as reviewers_available, get_reviewer
from pr_review.review_types import available as types_available, get_review_type
from pr_review.synthesis import LLMSynthesisCollator
from pr_review.target import Target, parse_target
from pr_review import output, prompts

# The no---model default and the synthesis judge both key off claude; read it
# from the registry so bumping the reviewer bumps these too.
DEFAULT_MODEL = get_reviewer("claude").default_model


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
    plain_language_model: tuple[str, str] | None
    no_plain_language: bool
    no_context: bool
    no_context_filter: bool
    context_filter_model: tuple[str, str] | None


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
        # "agent=model" opens an agent; a bare token after one is another model
        # for that agent, a bare token before any "=" is an agent on its default.
        groups: list[tuple[str, list[str]]] = []
        seen_eq = False
        for token in _split(value):
            head, sep, model = (s.strip() for s in token.partition("="))
            if sep:
                seen_eq = True
                groups.append((head, [model] if model else []))
            elif seen_eq:
                groups[-1][1].append(token)
            else:
                groups.append((token, []))
        for agent, models in groups:
            reviewer = get_reviewer(agent)  # validates agent; raises ValueError
            for model in models or [reviewer.default_model]:
                add(agent, model)
    return pairs


def list_models() -> str:
    blocks = []
    for name in reviewers_available():
        reviewer = get_reviewer(name)
        lines = [
            f"  {m}" + (" (default)" if m == reviewer.default_model else "")
            for m in reviewer.available_models()
        ]
        blocks.append(f"{name}:\n" + "\n".join(lines))
    return "\n\n".join(blocks)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr-review",
        description="Review a GitHub PR in an isolated clone with one or more LLMs.",
    )
    p.add_argument("target", help="PR URL or owner/repo#N (or 'help' for this message)")
    p.add_argument(
        "--model", action="append", metavar="AGENT[=MODELS]", default=None,
        help=(
            "per-agent models, repeatable, e.g. --model claude=claude-opus-5,claude-fable-5 "
            f"(agents: {', '.join(reviewers_available())}; default: claude={DEFAULT_MODEL})"
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
        "--list-models", action="store_true",
        help="list each agent's available models (shells out to each backend) and exit",
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
    p.add_argument(
        "--plain-language-model", metavar="AGENT[=MODEL]", default=None,
        help=(
            "agent/model for the plain-language reader test and rewrite "
            "(default: the synthesis model)"
        ),
    )
    p.add_argument(
        "--no-plain-language", action="store_true",
        help=(
            "skip the plain-language reader test and rewrite; the word-and-shape "
            "check still reports (default: false)"
        ),
    )
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
        plain_language_model=(
            _parse_synthesis_model(args.plain_language_model)
            if args.plain_language_model else None
        ),
        no_plain_language=args.no_plain_language,
        no_context=args.no_context,
        no_context_filter=args.no_context_filter,
        context_filter_model=(
            _parse_synthesis_model(args.context_filter_model) if args.context_filter_model else None
        ),
    )


def build_collator(cfg: RunConfig, *, workdir: str, base: str, context: str = "") -> Collator:
    if cfg.no_synthesis:
        return DeterministicMergeCollator()
    agent, model = cfg.synthesis_model
    command = get_reviewer(agent).command(model, cfg.flags_by_agent.get(agent, []))
    return LLMSynthesisCollator(
        command=command, workdir=workdir,
        owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number, base=base,
        context=context,
    )


def _plain_language_pair(cfg: RunConfig) -> tuple[str, str]:
    return cfg.plain_language_model or cfg.synthesis_model


def build_plain_language_stage(cfg: RunConfig, *, workdir: str, base: str) -> PlainLanguageStage | None:
    if cfg.no_plain_language:
        return None
    agent, model = _plain_language_pair(cfg)
    command = get_reviewer(agent).command(model, cfg.flags_by_agent.get(agent, []))
    return PlainLanguageStage(command=command, workdir=workdir, base=base)


def build_context_filter(cfg: RunConfig, *, workdir: str, context_path: str) -> ContextFilter | None:
    if cfg.no_context or cfg.no_context_filter:
        return None
    agent, model = cfg.context_filter_model or cfg.synthesis_model
    command = get_reviewer(agent).command(model, cfg.flags_by_agent.get(agent, []))
    return ContextFilter(command=command, workdir=workdir, context_path=context_path)


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
    argv = sys.argv[1:] if argv is None else argv
    if "--list-models" in argv:
        print(list_models())
        return 0
    cfg = config_from_args(argv)
    cfg.agent_models = resolve_agent_models(
        cfg.agent_models, has_tty=output.tty_available()
    )
    cfg.type_names = resolve_review_types(
        cfg.type_names, has_tty=output.tty_available()
    )
    jobs = build_jobs(cfg)  # validates agent/type names before any clone

    ctx = None
    if not cfg.no_context:
        try:
            ctx = gather_context(GitHub(cfg.target.owner, cfg.target.repo), cfg.target.number)
        except Exception as e:
            print(f"pr-review: could not load the pull request context ({e}); "
                  "reviewing the diff only.", file=sys.stderr)
        for error in ctx.errors if ctx else []:
            print(f"pr-review: context: could not load {error}.", file=sys.stderr)

    checkout = clone_pr(cfg.target.owner, cfg.target.repo, cfg.target.number,
                        stack=[e.number for e in ctx.stack] if ctx else [])
    filtered = None
    staged = None
    missing = 0
    try:
        summary, context_path = "", ""
        if ctx:
            fetched = [e for e in ctx.stack if e.number in checkout.stack_refs]
            missing = len(ctx.stack) - len(fetched)
            ctx.stack = fetched
            context_path = write_context_file(checkout.workdir, render_context_file(ctx))
            summary = prompt_summary(ctx, context_path)

        print(
            f"pr-review: {cfg.target.slug}#{cfg.target.number} "
            f"base={checkout.base_ref}@{checkout.base[:12]} jobs={len(jobs)}",
            file=sys.stderr,
        )
        collator = build_collator(cfg, workdir=checkout.workdir, base=checkout.base, context=summary)
        stage = build_plain_language_stage(cfg, workdir=checkout.workdir, base=checkout.base)
        context_filter = (
            build_context_filter(cfg, workdir=checkout.workdir, context_path=context_path) if ctx else None
        )
        result = run_reviews(
            jobs=jobs, workdir=checkout.workdir, base=checkout.base,
            owner=cfg.target.owner, repo=cfg.target.repo, number=cfg.target.number,
            collator=collator, context=summary,
        )
        # The stage reads diff hunks from the clone, so it runs before cleanup.
        if result.payload is not None:
            filtered = (context_filter.apply(result.payload, ctx) if context_filter
                        else FilterResult(result.payload))
            answers = answers_by_id(ctx) if ctx else {}
            if stage is None:
                staged = check_payload(filtered.payload)
            else:
                try:
                    staged = stage.apply(filtered.payload, answers=answers)
                except Exception as e:
                    print(
                        f"pr-review: plain-language stage failed ({e}); "
                        "using the word-and-shape check only",
                        file=sys.stderr,
                    )
                    staged = check_payload(filtered.payload)
    finally:
        if cfg.keep:
            print(f"pr-review: kept checkout at {checkout.workdir}", file=sys.stderr)
        else:
            cleanup(checkout)

    for label, rtype, err in result.failures:
        print(f"pr-review: {label} / {rtype} failed: {err}", file=sys.stderr)

    if staged is None:
        print(
            f"pr-review: all {len(jobs)} review job(s) failed; no review produced.",
            file=sys.stderr,
        )
        return 1

    for warning in filtered.warnings:
        print(f"pr-review: context filter: {warning}", file=sys.stderr)

    agent, model = _plain_language_pair(cfg)
    record = RunRecord(
        jobs=result.jobs,
        synthesis_model=(cfg.synthesis_model[1] or cfg.synthesis_model[0])
        if getattr(collator, "ran", False) else None,
        plain_language_model=(model or agent) if stage else None,
        rewritten=staged.rewritten,
        reader_ran=staged.reader_ran,
        needed_rewrite=staged.needed_rewrite,
        body_rewritten=staged.body_rewritten,
        stack_line=describe_stack(ctx, missing=missing) if ctx else None,
        context_line=describe_loaded(ctx) if ctx else None,
        not_posted=[describe_dropped(d) for d in filtered.dropped],
    )
    payload = finalize(staged.payload, record)

    output.show_review(payload)

    report = format_report(staged)
    if report:
        print(report, file=sys.stderr)

    mode = output.decide_mode(
        yes=cfg.yes, no_post=cfg.no_post, has_tty=output.tty_available()
    )
    return output.dispatch(mode, cfg.target, payload)
