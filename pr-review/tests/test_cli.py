import pytest

from pr_review.cli import build_jobs, config_from_args, resolve_review_types
from pr_review.target import Target


def test_config_defaults():
    cfg = config_from_args(["org/repo#3"])
    assert cfg.target == Target("org", "repo", 3)
    assert cfg.agent_names == ["claude"]
    assert cfg.type_names is None          # omitted → resolved later (prompt / error)
    assert cfg.model == "claude-opus-4-8"
    assert cfg.extra_flags == []
    assert cfg.yes is False and cfg.no_post is False and cfg.keep is False


def test_config_reads_options():
    cfg = config_from_args([
        "--agent", "claude,codex",
        "--review-type", "test-gap,infracode",
        "--model", "m",
        "--post-without-prompting",
        "--keep-clone",
        "--claude-flags=--foo --bar",
        "org/repo#9",
    ])
    assert cfg.agent_names == ["claude", "codex"]
    assert cfg.type_names == ["test-gap", "infracode"]
    assert cfg.model == "m"
    assert cfg.yes is True and cfg.keep is True
    assert cfg.extra_flags == ["--foo", "--bar"]


def test_print_only_sets_no_post():
    cfg = config_from_args(["--print-only", "org/repo#1"])
    assert cfg.no_post is True and cfg.yes is False


def test_help_word_aliases_to_help_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        config_from_args(["help"])
    assert exc.value.code == 0
    assert "usage: pr-review" in capsys.readouterr().out


def test_help_shows_default_values(capsys):
    with pytest.raises(SystemExit):
        config_from_args(["--help"])
    out = capsys.readouterr().out
    assert out.count("default:") >= 6
    assert "claude-opus-4-8" in out


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


def test_build_jobs_cross_product():
    cfg = config_from_args(["--agent", "claude", "--review-type", "test-gap", "org/repo#1"])
    jobs = build_jobs(cfg)
    assert len(jobs) == 1
    assert jobs[0].reviewer.name == "claude"
    assert jobs[0].review_type.name == "test-gap"


def test_build_jobs_multi_type_cross_product():
    cfg = config_from_args(
        ["--agent", "claude", "--review-type", "test-gap,infracode", "org/repo#1"]
    )
    jobs = build_jobs(cfg)
    assert len(jobs) == 2
    assert {j.review_type.name for j in jobs} == {"test-gap", "infracode"}


def test_build_jobs_unknown_name_raises():
    cfg = config_from_args(["--agent", "ghost", "--review-type", "test-gap", "org/repo#1"])
    with pytest.raises(ValueError):
        build_jobs(cfg)
