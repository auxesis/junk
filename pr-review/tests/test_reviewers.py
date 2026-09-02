import pytest

from pr_review.reviewers import available, get_reviewer
from pr_review.reviewers._run import _review_env, build_review_prompt
from pr_review.review_types import get_review_type


def test_claude_is_registered():
    assert "claude" in available()
    assert get_reviewer("claude").name == "claude"


def test_claude_default_model():
    assert get_reviewer("claude").default_model == "claude-opus-5"


def test_unknown_reviewer_raises():
    with pytest.raises(ValueError):
        get_reviewer("nope")


def test_build_review_prompt_includes_context_and_instructions():
    prompt = build_review_prompt(
        owner="org", repo="repo", number=7, base="deadbeef",
        payload_path="/tmp/p.json", review_type=get_review_type("test-gap"),
    )
    assert "Repository: org/repo" in prompt
    assert "PR number: 7" in prompt
    assert "/tmp/p.json" in prompt
    assert "# Test Coverage Review" in prompt


def test_build_review_prompt_names_the_base_as_a_bare_commit():
    """The base is a commit, so the prompt must not prefix it with `origin/`."""
    prompt = build_review_prompt(
        owner="org", repo="repo", number=7, base="deadbeef",
        payload_path="/tmp/p.json", review_type=get_review_type("test-gap"),
    )
    assert "Base commit: deadbeef" in prompt
    assert "origin/" not in prompt


def test_codex_is_registered():
    assert "codex" in available()
    assert get_reviewer("codex").name == "codex"


def test_codex_default_model():
    assert get_reviewer("codex").default_model == "gpt-5.6-terra"


def test_review_env_trusts_the_clone_for_mise(monkeypatch):
    monkeypatch.delenv("MISE_TRUSTED_CONFIG_PATHS", raising=False)
    env = _review_env("/tmp/clone")
    assert env["MISE_TRUSTED_CONFIG_PATHS"] == "/tmp/clone"


def test_review_env_prepends_to_existing_trusted_paths(monkeypatch):
    monkeypatch.setenv("MISE_TRUSTED_CONFIG_PATHS", "/already/trusted")
    env = _review_env("/tmp/clone")
    assert env["MISE_TRUSTED_CONFIG_PATHS"] == "/tmp/clone:/already/trusted"


def test_claude_command_includes_model_and_flags():
    cmd = get_reviewer("claude").command("claude-opus-4-8", ["--foo"])
    assert cmd[:4] == ["claude", "--print", "--model", "claude-opus-4-8"]
    assert "--dangerously-skip-permissions" in cmd
    assert "--strict-mcp-config" in cmd  # no MCP servers (e.g. Serena) for reviews
    assert cmd[-1] == "--foo"


def test_codex_command_omits_model_when_empty():
    cmd = get_reviewer("codex").command("", [])
    assert cmd == ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]


def test_codex_command_includes_model_when_given():
    cmd = get_reviewer("codex").command("gpt-5", ["--oss"])
    assert cmd[:4] == ["codex", "exec", "--model", "gpt-5"]
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert cmd[-1] == "--oss"


def test_cli_default_model_tracks_the_claude_reviewer():
    """cli.DEFAULT_MODEL (the no---model default and the synthesis judge) must not
    be a second copy of the claude reviewer's default that can drift from it."""
    from pr_review.cli import DEFAULT_MODEL

    assert DEFAULT_MODEL == get_reviewer("claude").default_model
