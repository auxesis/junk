import pytest

from pr_review.cli import build_jobs, config_from_args
from pr_review.target import Target


def test_config_defaults():
    cfg = config_from_args(["org/repo#3"])
    assert cfg.target == Target("org", "repo", 3)
    assert cfg.reviewer_names == ["claude"]
    assert cfg.type_names == ["test-gap"]
    assert cfg.model == "claude-opus-4-8"
    assert cfg.extra_flags == []
    assert cfg.yes is False and cfg.no_post is False and cfg.keep is False


def test_config_reads_options():
    cfg = config_from_args([
        "--reviewer", "claude,codex",
        "--type", "test-gap",
        "--model", "m",
        "--post-without-prompting",
        "--keep-clone",
        "--claude-flags=--foo --bar",
        "org/repo#9",
    ])
    assert cfg.reviewer_names == ["claude", "codex"]
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


def test_build_jobs_cross_product():
    cfg = config_from_args(["--reviewer", "claude", "--type", "test-gap", "org/repo#1"])
    jobs = build_jobs(cfg)
    assert len(jobs) == 1
    assert jobs[0].reviewer.name == "claude"
    assert jobs[0].review_type.name == "test-gap"


def test_build_jobs_unknown_name_raises():
    cfg = config_from_args(["--reviewer", "ghost", "org/repo#1"])
    with pytest.raises(ValueError):
        build_jobs(cfg)
