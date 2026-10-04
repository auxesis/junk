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


def test_build_review_prompt_places_the_context_before_the_instructions():
    prompt = build_review_prompt(owner="o", repo="r", number=1, base="b", payload_path="/p",
                                 review_type=get_review_type("test-gap"), context="## Pull request context\nX")
    assert prompt.index("## Pull request context") < prompt.index("# Test Coverage Review")


def test_build_review_prompt_without_context_is_unchanged():
    prompt = build_review_prompt(owner="o", repo="r", number=1, base="b", payload_path="/p",
                                 review_type=get_review_type("test-gap"))
    assert "## Pull request context" not in prompt


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


def test_claude_known_models_include_the_default():
    r = get_reviewer("claude")
    assert r.default_model in r.known_models
    assert "claude-sonnet-5" in r.known_models


def test_codex_known_models_include_the_default():
    r = get_reviewer("codex")
    assert r.default_model in r.known_models


def test_claude_available_models_uses_the_live_api(monkeypatch):
    import pr_review.reviewers.claude as cl

    monkeypatch.setattr(cl, "fetch_live_models", lambda: ["claude-opus-5", "claude-new"])
    assert get_reviewer("claude").available_models() == ["claude-opus-5", "claude-new"]


def test_claude_available_models_falls_back_when_the_api_fails(monkeypatch):
    import pr_review.reviewers.claude as cl

    def boom():
        raise RuntimeError("no network")

    monkeypatch.setattr(cl, "fetch_live_models", boom)
    r = get_reviewer("claude")
    assert r.available_models() == r.known_models


def test_claude_available_models_falls_back_when_the_api_is_empty(monkeypatch):
    import pr_review.reviewers.claude as cl

    monkeypatch.setattr(cl, "fetch_live_models", lambda: [])
    r = get_reviewer("claude")
    assert r.available_models() == r.known_models


def test_codex_available_models_uses_the_live_api(monkeypatch):
    import pr_review.reviewers.codex as cx

    monkeypatch.setattr(cx, "fetch_live_models", lambda: ["gpt-5.6-terra", "gpt-5.9-x"])
    assert get_reviewer("codex").available_models() == ["gpt-5.6-terra", "gpt-5.9-x"]


def test_codex_available_models_falls_back_when_the_api_fails(monkeypatch):
    import pr_review.reviewers.codex as cx

    def boom():
        raise RuntimeError("no network")

    monkeypatch.setattr(cx, "fetch_live_models", boom)
    r = get_reviewer("codex")
    assert r.available_models() == r.known_models


def test_codex_available_models_falls_back_when_the_api_is_empty(monkeypatch):
    import pr_review.reviewers.codex as cx

    monkeypatch.setattr(cx, "fetch_live_models", lambda: [])
    r = get_reviewer("codex")
    assert r.available_models() == r.known_models


def test_cli_default_model_tracks_the_claude_reviewer():
    """cli.DEFAULT_MODEL (the no---model default and the synthesis judge) must not
    be a second copy of the claude reviewer's default that can drift from it."""
    from pr_review.cli import DEFAULT_MODEL

    assert DEFAULT_MODEL == get_reviewer("claude").default_model
