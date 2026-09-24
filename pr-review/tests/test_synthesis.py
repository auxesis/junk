from pr_review.payload import Comment, Payload, Source
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
    assert "Summary: b1" in text


def test_build_synthesis_prompt_has_context_findings_and_instructions():
    prompt = build_synthesis_prompt(
        owner="o", repo="r", number=7, base="deadbeef",
        payload_path="/tmp/p.json", findings="FINDINGS_HERE",
    )
    assert "Repository: o/r" in prompt
    assert "/tmp/p.json" in prompt
    assert "# Synthesis Review" in prompt
    assert "## Review stats" not in prompt
    assert "[2 models:" not in prompt
    assert '"sources"' in prompt
    assert "## How to write each comment (REQUIRED)" in prompt
    assert "## Other findings not posted as comments" in prompt
    assert "Additional findings not posted inline" not in prompt
    assert "HARD CAP: 8 inline comments" in prompt
    assert "FINDINGS_HERE" in prompt
    assert "Base commit: deadbeef" in prompt
    assert "origin/" not in prompt


def test_the_judge_gets_the_context_summary():
    prompt = build_synthesis_prompt(owner="o", repo="r", number=7, base="b", payload_path="/p",
                                    findings="F", context="## Pull request context\nX")
    assert prompt.index("## Pull request context") < prompt.index("# Synthesis Review")


def _job(label, rtype, n):
    agent = label.split(" ")[0]
    src = Source(agent, "m", rtype)
    return (label, rtype, Payload(body=f"{label} body",
                                  comments=[Comment("f.py", i, f"c{i}", sources=[src]) for i in range(n)]))


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
        return {"body": "SYNTH", "comments": [{"path": "a", "line": 1, "body": "merged"}]}

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


def test_synthesis_caps_judge_output_to_eight():
    def runner(command, build_prompt, *, workdir):
        return {"body": "SYNTH",
                "comments": [{"path": "f.py", "line": i, "body": f"c{i}"} for i in range(11)]}

    jobs = [_job("claude (opus)", "test-gap", 2), _job("codex", "test-gap", 2)]
    out = _collator(runner).collate(jobs)
    assert len(out.comments) == 8
    assert "## Other findings not posted as comments" in out.body


def test_overflow_bullets_carry_the_finding_line():
    def runner(command, build_prompt, *, workdir):
        return {"body": "SYNTH",
                "comments": [{"path": "f.py", "line": i, "body": f"**Finding {i}.**\n\nmore"} for i in range(9)]}

    out = _collator(runner).collate([_job("claude (opus)", "test-gap", 1), _job("codex", "test-gap", 1)])
    assert "- `f.py:8` — **Finding 8.**" in out.body


def test_synthesis_maps_judge_sources_back_to_jobs(capsys):
    def runner(command, build_prompt, *, workdir):
        return {"body": "SYNTH", "comments": [
            {"path": "a", "line": 1, "body": "both",
             "sources": ["claude (opus) [test-gap]", "codex [test-gap]", "ghost [x]"]},
            {"path": "b", "line": 2, "body": "nobody", "sources": ["ghost [x]"]},
        ]}

    jobs = [_job("claude (opus)", "test-gap", 1), _job("codex", "test-gap", 1)]
    collator = _collator(runner)
    out = collator.collate(jobs)
    assert out.comments[0].sources == [Source("claude", "m", "test-gap"), Source("codex", "m", "test-gap")]
    assert out.comments[1].sources == []
    assert "no known source for b:2" in capsys.readouterr().err
    assert collator.ran is True


def test_ran_is_false_for_a_single_job_and_after_a_fallback():
    single = _collator(lambda *a, **k: None)
    single.collate([_job("claude (opus)", "test-gap", 1)])
    assert single.ran is False

    def boom(*a, **k):
        raise RuntimeError("judge died")

    failed = _collator(boom)
    failed.collate([_job("claude (opus)", "test-gap", 1), _job("codex", "test-gap", 1)])
    assert failed.ran is False
