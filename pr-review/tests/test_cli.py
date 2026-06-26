import pytest

from pr_review.cli import build_jobs, config_from_args
from pr_review.target import Target


def test_config_defaults():
    cfg = config_from_args(["org/repo#3"])
    assert cfg.target == Target("org", "repo", 3)
    assert cfg.agent_models == [("claude", "claude-opus-4-8")]
    assert cfg.type_names is None
    assert cfg.flags_by_agent == {}
    assert cfg.yes is False and cfg.no_post is False and cfg.keep is False


def test_model_bare_agent_uses_default_model():
    cfg = config_from_args(["--model", "codex", "org/repo#1"])
    assert cfg.agent_models == [("codex", "gpt-5-codex")]


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


def test_model_unknown_agent_raises():
    with pytest.raises(ValueError):
        config_from_args(["--model", "ghost=x", "org/repo#1"])


def test_flags_by_agent_parsing():
    cfg = config_from_args([
        "--claude-flags=--foo --bar", "--codex-flags=--oss", "org/repo#1",
    ])
    assert cfg.flags_by_agent == {"claude": ["--foo", "--bar"], "codex": ["--oss"]}


def test_help_shows_default_values(capsys):
    with pytest.raises(SystemExit):
        config_from_args(["--help"])
    out = capsys.readouterr().out
    assert "claude-opus-4-8" in out
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
