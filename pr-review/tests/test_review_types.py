from pathlib import Path

import pytest

from pr_review.review_types import available, get_review_type

REPO = Path(__file__).resolve().parents[1]
VENDOR = REPO / "vendor" / "golang-pro"


def test_test_gap_is_registered():
    assert "test-gap" in available()


def test_get_returns_instance_with_name():
    rt = get_review_type("test-gap")
    assert rt.name == "test-gap"


def test_instructions_contain_schema_and_cap():
    text = get_review_type("test-gap").instructions()
    assert "## Output (REQUIRED)" in text
    assert "HARD CAP: 8 inline comments" in text


def test_infracode_is_registered():
    assert "infracode" in available()
    assert get_review_type("infracode").name == "infracode"


def test_infracode_instructions_contain_domain_and_contract():
    text = get_review_type("infracode").instructions()
    assert "Infrastructure-as-Code Review" in text
    assert "## Output (REQUIRED)" in text
    assert "HARD CAP: 8 inline comments" in text


def test_golang_is_registered():
    assert "golang" in available()
    assert get_review_type("golang").name == "golang"


def test_golang_instructions_contain_domain_and_contract():
    text = get_review_type("golang").instructions()
    assert "Go Review" in text
    assert "## Output (REQUIRED)" in text
    assert "HARD CAP: 8 inline comments" in text


def test_golang_instructions_name_the_go_specific_axes():
    """The rubric is distilled from golang-pro's references; each one has to
    survive into the prompt as something reviewable in a diff."""
    text = get_review_type("golang").instructions()
    for axis in ("goroutine", "context.Context", "%w", "-race", "generic", "internal/"):
        assert axis in text, axis


def test_golang_defers_coverage_findings_to_test_gap():
    """golang-pro's testing.md overlaps the test-gap type. The rubric keeps the
    Go-specific testing facts and hands uncovered-branch hunting back."""
    text = get_review_type("golang").instructions()
    assert "test-gap" in text


def test_golang_runs_the_toolchain_only_when_it_is_there():
    """`go vet` / `golangci-lint` findings beat guessed ones, but a clone without a
    toolchain must not turn into a review full of setup noise."""
    text = get_review_type("golang").instructions()
    assert "go vet" in text
    assert "golangci-lint" in text
    assert "never report" in text.lower()


def test_vendored_upstream_license_is_present():
    """MIT: the notice travels with the copy. If this file goes, the attribution
    in golang.py is no longer backed by anything in the tree."""
    licence = (VENDOR / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in licence
    assert "Copyright (c)" in licence


def test_golang_module_attributes_the_pinned_upstream_commit():
    """The rubric is derived work; its header must name what it derives from, at a
    revision someone can actually diff against."""
    import pr_review.review_types.golang as mod

    commit = "efebc44c90ae6eb3b36ff1c53802a765418481b9"
    assert commit in mod.__doc__
    assert "MIT" in mod.__doc__
    assert "Jeffallan/claude-skills" in mod.__doc__
    assert commit in (VENDOR / "PROVENANCE.md").read_text(encoding="utf-8")


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        get_review_type("does-not-exist")
