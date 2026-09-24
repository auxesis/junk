import pytest

from pr_review.cli import build_jobs, config_from_args, resolve_agent_models, resolve_review_types
from pr_review.target import Target


def _patch_run(monkeypatch, *, payload, stage):
    """Patch main()'s side-effecting collaborators so it runs with no clone,
    no subprocess and no network, returning `payload` from run_reviews and
    `stage` (or None to skip building one) as the plain-language stage.

    Context gathering is patched to fail (no `gh`), so `ctx` stays None and
    the context filter is never built."""
    import pr_review.cli as cli
    from pr_review.checkout import Checkout
    from pr_review.orchestrator import RunResult

    monkeypatch.setattr(
        cli, "gather_context",
        lambda gh, number: (_ for _ in ()).throw(RuntimeError("no gh in tests")),
    )
    monkeypatch.setattr(
        cli, "clone_pr",
        lambda owner, repo, number, **kw: Checkout(workdir="/wd", base="base-sha", base_ref="main"),
    )
    monkeypatch.setattr(cli, "cleanup", lambda checkout: None)
    monkeypatch.setattr(
        cli, "run_reviews",
        lambda **kw: RunResult(payload=payload, failures=[], jobs=[]),
    )
    monkeypatch.setattr(
        cli, "build_plain_language_stage", lambda cfg, *, workdir, base: stage,
    )
    monkeypatch.setattr(cli.output, "tty_available", lambda: False)
    return cli


def test_config_defaults():
    cfg = config_from_args(["org/repo#3"])
    assert cfg.target == Target("org", "repo", 3)
    assert cfg.agent_models is None
    assert cfg.type_names is None
    assert cfg.flags_by_agent == {}
    assert cfg.yes is False and cfg.no_post is False and cfg.keep is False


def test_model_bare_agent_uses_default_model():
    cfg = config_from_args(["--model", "codex", "org/repo#1"])
    assert cfg.agent_models == [("codex", "gpt-5.6-terra")]


def test_model_explicit_and_repeatable():
    cfg = config_from_args([
        "--model", "claude=claude-opus-4-8,claude-fable-5",
        "--model", "codex=gpt-5,gpt-5.5",
        "--review-type", "test-gap",
        "org/repo#9",
    ])
    assert cfg.agent_models == [
        ("claude", "claude-opus-4-8"), ("claude", "claude-fable-5"),
        ("codex", "gpt-5"), ("codex", "gpt-5.5"),
    ]


def test_model_comma_separated_bare_agents():
    cfg = config_from_args(["--model", "claude,codex", "org/repo#1"])
    assert cfg.agent_models == [("claude", "claude-opus-5"), ("codex", "gpt-5.6-terra")]


def test_model_unknown_agent_raises():
    with pytest.raises(ValueError):
        config_from_args(["--model", "ghost=x", "org/repo#1"])


def test_model_unknown_bare_agent_raises():
    with pytest.raises(ValueError):
        config_from_args(["--model", "claude,ghost", "org/repo#1"])


def test_flags_by_agent_parsing():
    cfg = config_from_args([
        "--claude-flags=--foo --bar", "--codex-flags=--oss", "org/repo#1",
    ])
    assert cfg.flags_by_agent == {"claude": ["--foo", "--bar"], "codex": ["--oss"]}


def test_help_shows_default_values(capsys):
    with pytest.raises(SystemExit):
        config_from_args(["--help"])
    out = capsys.readouterr().out
    assert "claude-opus-5" in out
    assert "default:" in out


def test_build_jobs_full_matrix_and_per_agent_flags():
    cfg = config_from_args([
        "--model", "claude=claude-opus-4-8", "--model", "codex=gpt-5",
        "--review-type", "test-gap,infracode",
        "--claude-flags=--foo", "org/repo#1",
    ])
    jobs = build_jobs(cfg)
    # 2 (agent,model) pairs x 2 review types = 4 jobs
    assert len(jobs) == 4
    triples = {(j.reviewer.name, j.review_type.name, j.model) for j in jobs}
    assert triples == {
        ("claude", "test-gap", "claude-opus-4-8"),
        ("claude", "infracode", "claude-opus-4-8"),
        ("codex", "test-gap", "gpt-5"),
        ("codex", "infracode", "gpt-5"),
    }
    claude_job = next(j for j in jobs if j.reviewer.name == "claude")
    codex_job = next(j for j in jobs if j.reviewer.name == "codex")
    assert claude_job.extra_flags == ["--foo"]
    assert codex_job.extra_flags == []


def test_resolve_review_types_explicit_passthrough():
    assert resolve_review_types(
        ["test-gap"], has_tty=True, prompt_fn=lambda avail: ["unused"]
    ) == ["test-gap"]


def test_resolve_review_types_prompts_when_tty():
    seen = {}

    def fake_prompt(available):
        seen["available"] = available
        return ["infracode"]

    assert resolve_review_types(None, has_tty=True, prompt_fn=fake_prompt) == ["infracode"]
    assert "test-gap" in seen["available"]


def test_resolve_review_types_errors_without_tty(capsys):
    with pytest.raises(SystemExit) as exc:
        resolve_review_types(None, has_tty=False, prompt_fn=lambda avail: ["x"])
    assert exc.value.code == 2
    assert "--review-type" in capsys.readouterr().err


def test_resolve_agent_models_explicit_passthrough():
    pairs = [("claude", "claude-opus-5")]
    assert resolve_agent_models(pairs, has_tty=True, prompt_fn=lambda a, d: []) == pairs


def test_resolve_agent_models_prompts_when_tty():
    seen = {}

    def fake_prompt(agents, default_model):
        seen["agents"] = agents
        seen["claude_default"] = default_model("claude")
        return [("codex", "gpt-5")]

    assert resolve_agent_models(None, has_tty=True, prompt_fn=fake_prompt) == [("codex", "gpt-5")]
    assert "claude" in seen["agents"]
    assert seen["claude_default"] == "claude-opus-5"


def test_resolve_agent_models_errors_without_tty(capsys):
    with pytest.raises(SystemExit) as exc:
        resolve_agent_models(None, has_tty=False, prompt_fn=lambda a, d: [])
    assert exc.value.code == 2
    assert "--model" in capsys.readouterr().err


def test_config_synthesis_defaults():
    cfg = config_from_args(["org/repo#1"])
    assert cfg.synthesis_model == ("claude", "claude-opus-5")
    assert cfg.no_synthesis is False


def test_config_synthesis_model_override():
    cfg = config_from_args(["--synthesis-model", "codex=gpt-5", "org/repo#1"])
    assert cfg.synthesis_model == ("codex", "gpt-5")


def test_config_synthesis_bare_agent_uses_default():
    cfg = config_from_args(["--synthesis-model", "claude", "org/repo#1"])
    assert cfg.synthesis_model == ("claude", "claude-opus-5")


def test_config_no_synthesis_flag():
    cfg = config_from_args(["--no-synthesis", "org/repo#1"])
    assert cfg.no_synthesis is True


def test_build_collator_returns_synthesis_by_default():
    from pr_review.cli import build_collator
    from pr_review.synthesis import LLMSynthesisCollator

    cfg = config_from_args(["org/repo#1"])
    assert isinstance(build_collator(cfg, workdir="/wd", base="main"), LLMSynthesisCollator)


def test_build_collator_no_synthesis_returns_merge():
    from pr_review.cli import build_collator
    from pr_review.collate import DeterministicMergeCollator

    cfg = config_from_args(["--no-synthesis", "org/repo#1"])
    assert isinstance(build_collator(cfg, workdir="/wd", base="main"), DeterministicMergeCollator)


def test_build_collator_uses_the_judge_command():
    from pr_review.cli import build_collator

    cfg = config_from_args(["--synthesis-model", "codex=gpt-5", "org/repo#1"])
    collator = build_collator(cfg, workdir="/wd", base="main")
    assert collator._command[:4] == ["codex", "exec", "--model", "gpt-5"]


def test_config_plain_language_defaults():
    cfg = config_from_args(["org/repo#1"])
    assert cfg.plain_language_model is None
    assert cfg.no_plain_language is False


def test_config_plain_language_model_and_off_switch():
    cfg = config_from_args(["--plain-language-model", "codex=gpt-5", "--no-plain-language", "org/repo#1"])
    assert cfg.plain_language_model == ("codex", "gpt-5")
    assert cfg.no_plain_language is True


def test_plain_language_stage_follows_the_synthesis_model_by_default():
    from pr_review.cli import build_plain_language_stage

    cfg = config_from_args(["--synthesis-model", "codex=gpt-5", "org/repo#1"])
    stage = build_plain_language_stage(cfg, workdir="/wd", base="b")
    assert stage._command[:4] == ["codex", "exec", "--model", "gpt-5"]


def test_plain_language_model_overrides_the_synthesis_model():
    from pr_review.cli import build_plain_language_stage

    cfg = config_from_args(["--synthesis-model", "codex=gpt-5",
                            "--plain-language-model", "claude=claude-sonnet-5", "org/repo#1"])
    stage = build_plain_language_stage(cfg, workdir="/wd", base="b")
    assert stage._command[:4] == ["claude", "--print", "--model", "claude-sonnet-5"]


def test_no_plain_language_builds_no_stage():
    from pr_review.cli import build_plain_language_stage

    cfg = config_from_args(["--no-plain-language", "org/repo#1"])
    assert build_plain_language_stage(cfg, workdir="/wd", base="b") is None


def test_a_stage_apply_exception_falls_back_to_the_check_only(monkeypatch, capsys):
    from pr_review.payload import Comment, Payload

    payload = Payload(body="Verdict.",
                       comments=[Comment("f.py", 1, "**X.**\n\n**Impact:** y\n\n**Fix:** z")])

    class RaisingStage:
        def apply(self, payload, answers=None):
            raise RuntimeError("boom")

    cli = _patch_run(monkeypatch, payload=payload, stage=RaisingStage())
    exit_code = cli.main([
        "--model", "claude", "--review-type", "test-gap", "--print-only", "org/repo#1",
    ])

    err = capsys.readouterr().err
    assert exit_code == 0
    assert "plain-language" in err.lower() and "boom" in err


def test_the_plain_language_report_prints_after_show_review(monkeypatch, capsys):
    import sys

    from pr_review.payload import Comment, Payload
    from pr_review.plain_language.stage import StageResult

    payload = Payload(body="Verdict.",
                       comments=[Comment("f.py", 1, "**X.**\n\n**Impact:** y\n\n**Fix:** z")])

    class FakeStage:
        def apply(self, payload, answers=None):
            return StageResult(payload=payload, remaining={0: []}, body_remaining=[],
                               warnings=["a plain-language warning"])

    cli = _patch_run(monkeypatch, payload=payload, stage=FakeStage())
    monkeypatch.setattr(
        cli.output, "show_review",
        lambda payload: print("SHOW_REVIEW_CALLED", file=sys.stderr),
    )
    cli.main(["--model", "claude", "--review-type", "test-gap", "--print-only", "org/repo#1"])

    err = capsys.readouterr().err
    assert "SHOW_REVIEW_CALLED" in err and "a plain-language warning" in err
    assert err.index("SHOW_REVIEW_CALLED") < err.index("a plain-language warning")


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


def test_context_errors_print_in_full_on_stderr(monkeypatch, capsys):
    from pr_review.context.model import PullRequestContext

    cli = _patch_run(monkeypatch, payload=None, stage=None)
    ctx = PullRequestContext(number=1, title="T", body="", author="ada", issues=[], comments=[],
                             threads=[], stack=[], stack_position=None, failed=["discussion"],
                             errors=["discussion (HTTP 502 at /home/ada/.config/gh)"])
    monkeypatch.setattr(cli, "gather_context", lambda gh, number: ctx)
    monkeypatch.setattr(cli, "write_context_file", lambda workdir, text: "/wd/.git/pr-review/pr-context.md")
    cli.main(["--model", "claude", "--review-type", "test-gap", "--print-only", "org/repo#1"])

    err = capsys.readouterr().err
    assert "pr-review: context: could not load discussion (HTTP 502 at /home/ada/.config/gh)." in err


def test_the_clone_is_cleaned_up_when_writing_the_context_file_fails(monkeypatch):
    from pr_review.context.model import PullRequestContext

    cli = _patch_run(monkeypatch, payload=None, stage=None)
    ctx = PullRequestContext(number=1, title="T", body="", author="ada", issues=[], comments=[],
                             threads=[], stack=[], stack_position=None, failed=[])
    monkeypatch.setattr(cli, "gather_context", lambda gh, number: ctx)

    def disk_full(workdir, text):
        raise OSError("disk full")

    cleaned = []
    monkeypatch.setattr(cli, "write_context_file", disk_full)
    monkeypatch.setattr(cli, "cleanup", lambda checkout: cleaned.append(checkout.workdir))
    with pytest.raises(OSError):
        cli.main(["--model", "claude", "--review-type", "test-gap", "--print-only", "org/repo#1"])
    assert cleaned == ["/wd"]
