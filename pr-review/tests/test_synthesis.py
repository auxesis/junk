from pr_review.payload import Comment, Payload
from pr_review.synthesis import (
    LLMSynthesisCollator,
    build_synthesis_prompt,
    serialize_findings,
)


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


def _job(label, rtype, n):
    return (label, rtype, Payload(body=f"{label} body",
                                  comments=[Comment("f.py", i, f"c{i}") for i in range(n)]))


def _collator(runner):
    return LLMSynthesisCollator(
        command=["judge", "--print"], workdir="/wd",
        owner="o", repo="r", number=9, base="main", runner=runner,
    )


def test_synthesis_passthrough_for_single_job():
    p = Payload(body="solo", comments=[Comment("a", 1, "x")])

    def runner(*a, **k):
        raise AssertionError("runner must not be called for a single job")

    out = _collator(runner).collate([("claude (opus)", "test-gap", p)])
    assert out is p


def test_synthesis_runs_judge_for_multiple_jobs():
    captured = {}

    def runner(command, build_prompt, *, workdir):
        captured["command"] = command
        captured["workdir"] = workdir
        captured["prompt"] = build_prompt("/tmp/x.json")
        return Payload(body="SYNTH", comments=[Comment("a", 1, "merged")])

    jobs = [_job("claude (opus)", "test-gap", 2), _job("codex", "test-gap", 2)]
    out = _collator(runner).collate(jobs)
    assert out.body == "SYNTH"
    assert captured["command"] == ["judge", "--print"]
    assert captured["workdir"] == "/wd"
    assert "claude (opus) [test-gap]" in captured["prompt"]
    assert "/tmp/x.json" in captured["prompt"]


def test_synthesis_falls_back_to_merge_on_failure(capsys):
    def runner(*a, **k):
        raise RuntimeError("judge died")

    jobs = [_job("claude (opus)", "test-gap", 1), _job("codex", "test-gap", 1)]
    out = _collator(runner).collate(jobs)
    assert "## test-gap — claude (opus)" in out.body
    assert "## test-gap — codex" in out.body
    assert len(out.comments) == 2
    assert "synthesis failed" in capsys.readouterr().err
