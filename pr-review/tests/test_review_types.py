from pathlib import Path

import pytest

from pr_review.review_types import available, get_review_type

REPO = Path(__file__).resolve().parents[1]
VENDOR = REPO / "vendor"


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


# --- the language review types distilled from the vendored skills ---

# review type -> (vendored skill dir, module, axes the rubric must name,
#                 toolchain commands it may run opportunistically)
LANGUAGE_TYPES = {
    "golang": (
        "golang-pro", "golang",
        ("goroutine", "context.Context", "%w", "-race", "generic", "internal/"),
        ("go vet", "golangci-lint"),
    ),
    "typescript": (
        "typescript-pro", "typescript",
        ("any", "strict", "satisfies", "discriminated union", "as const", "unknown"),
        ("tsc --noEmit", "eslint"),
    ),
    "rust": (
        "rust-engineer", "rust",
        ("unsafe", "unwrap()", "Result", "lifetime", "clone", "async"),
        ("cargo clippy", "cargo fmt"),
    ),
    "python": (
        "python-pro", "python",
        ("type hint", "mutable default", "bare except", "async", "dataclass", "pathlib"),
        ("mypy", "ruff"),
    ),
}


@pytest.mark.parametrize("name", sorted(LANGUAGE_TYPES))
def test_language_type_is_registered(name):
    assert name in available()
    assert get_review_type(name).name == name


@pytest.mark.parametrize("name", sorted(LANGUAGE_TYPES))
def test_language_type_instructions_contain_the_shared_contract(name):
    text = get_review_type(name).instructions()
    assert "## Output (REQUIRED)" in text
    assert "HARD CAP: 8 inline comments" in text
    assert "## Severity ladder" in text


@pytest.mark.parametrize("name", sorted(LANGUAGE_TYPES))
def test_language_type_names_its_language_specific_axes(name):
    """Each rubric is distilled from one skill's references; the axes those cover
    have to survive into the prompt as something reviewable in a diff."""
    text = get_review_type(name).instructions().lower()
    for axis in LANGUAGE_TYPES[name][2]:
        assert axis.lower() in text, f"{name}: {axis}"


@pytest.mark.parametrize("name", sorted(LANGUAGE_TYPES))
def test_language_type_defers_coverage_findings_to_test_gap(name):
    """Every upstream skill carries testing guidance that overlaps the test-gap
    type. Each rubric keeps the language-specific facts and hands coverage back."""
    assert "test-gap" in get_review_type(name).instructions()


@pytest.mark.parametrize("name", sorted(LANGUAGE_TYPES))
def test_language_type_runs_the_toolchain_only_when_it_is_there(name):
    """Real diagnostics beat guesses, but a clone without a toolchain must not turn
    into a review full of setup noise."""
    text = get_review_type(name).instructions()
    for cmd in LANGUAGE_TYPES[name][3]:
        assert cmd in text, f"{name}: {cmd}"
    assert "never report" in text.lower()


@pytest.mark.parametrize("name", sorted(LANGUAGE_TYPES))
def test_language_type_attributes_its_pinned_upstream_commit(name):
    """Each rubric is derived work; its header must name what it derives from, at a
    revision someone can actually diff against."""
    import importlib

    skill, module = LANGUAGE_TYPES[name][0], LANGUAGE_TYPES[name][1]
    doc = importlib.import_module(f"pr_review.review_types.{module}").__doc__
    commit = "efebc44c90ae6eb3b36ff1c53802a765418481b9"
    assert commit in doc, name
    assert "MIT" in doc and "Jeffallan/claude-skills" in doc, name
    assert skill in doc, name
    provenance = (VENDOR / skill / "PROVENANCE.md").read_text(encoding="utf-8")
    assert commit in provenance, name


@pytest.mark.parametrize("name", sorted(LANGUAGE_TYPES))
def test_vendored_skill_material_is_present(name):
    """MIT: the notice travels with the copy. Without the vendored text there is
    nothing in the tree backing the attribution in the rubric's header."""
    skill = LANGUAGE_TYPES[name][0]
    assert (VENDOR / skill / "SKILL.md").read_text(encoding="utf-8").strip()
    assert len(list((VENDOR / skill / "references").glob("*.md"))) == 5


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        get_review_type("does-not-exist")
