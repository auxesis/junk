from pr_review.payload import Comment, Payload
from pr_review.synthesis import build_synthesis_prompt, serialize_findings


def test_serialize_findings_labels_sources_with_counts():
    jobs = [
        ("claude (opus)", "test-gap",
         Payload(body="b1", comments=[Comment("a.py", 3, "gap one"), Comment("a.py", 9, "gap two")])),
        ("codex", "infracode",
         Payload(body="b2", comments=[Comment("infra.tf", 5, "iam bloat")])),
    ]
    text = serialize_findings(jobs)
    assert "claude (opus) [test-gap] — 2 finding(s)" in text
    assert "codex [infracode] — 1 finding(s)" in text
    assert "a.py:3 — gap one" in text
    assert "infra.tf:5 — iam bloat" in text


def test_build_synthesis_prompt_has_context_findings_and_instructions():
    prompt = build_synthesis_prompt(
        owner="o", repo="r", number=7, base="main",
        payload_path="/tmp/p.json", findings="FINDINGS_HERE",
    )
    assert "Repository: o/r" in prompt
    assert "/tmp/p.json" in prompt
    assert "# Synthesis Review" in prompt
    assert "## Review stats" in prompt
    assert "HARD CAP: 8 inline comments" in prompt
    assert "FINDINGS_HERE" in prompt
