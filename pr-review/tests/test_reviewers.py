import pytest

from pr_review.reviewers import available, get_reviewer
from pr_review.reviewers._run import _review_env, build_review_prompt
from pr_review.review_types import get_review_type


def test_claude_is_registered():
    assert "claude" in available()
    assert get_reviewer("claude").name == "claude"


def test_claude_default_model():
    assert get_reviewer("claude").default_model == "claude-opus-4-8"


def test_unknown_reviewer_raises():
    with pytest.raises(ValueError):
        get_reviewer("nope")


def test_build_review_prompt_includes_context_and_instructions():
    prompt = build_review_prompt(
        owner="org", repo="repo", number=7, base="main",
        payload_path="/tmp/p.json", review_type=get_review_type("test-gap"),
    )
    assert "Repository: org/repo" in prompt
    assert "PR number: 7" in prompt
    assert "origin/main" in prompt
    assert "/tmp/p.json" in prompt
    assert "# Test Coverage Review" in prompt


def test_codex_is_registered():
    assert "codex" in available()
    assert get_reviewer("codex").name == "codex"


def test_codex_default_model():
    # Empty = defer to codex's own configured default model.
    assert get_reviewer("codex").default_model == ""


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
    assert cmd[-1] == "--foo"


def test_codex_command_omits_model_when_empty():
    cmd = get_reviewer("codex").command("", [])
    assert cmd == ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]


def test_codex_command_includes_model_when_given():
    cmd = get_reviewer("codex").command("gpt-5", ["--oss"])
    assert cmd[:4] == ["codex", "exec", "--model", "gpt-5"]
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert cmd[-1] == "--oss"
