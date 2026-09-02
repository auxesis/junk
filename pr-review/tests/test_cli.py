import pytest

from pr_review.cli import build_jobs, config_from_args, resolve_agent_models, resolve_review_types
from pr_review.target import Target


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
