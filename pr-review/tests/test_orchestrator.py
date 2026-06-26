from pr_review.orchestrator import ReviewJob, run_reviews
from pr_review.payload import Comment, Payload


class FakeType:
    def __init__(self, name):
        self.name = name

    def instructions(self):
        return "x"


class FakeReviewer:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def review(self, *, workdir, base, owner, repo, number, review_type, model, extra_flags):
        self.calls.append({"type": review_type.name, "model": model, "flags": extra_flags})
        return Payload(body=f"{self.name}/{review_type.name}", comments=[Comment("f.py", 1, "g")])


class BoomReviewer:
    name = "boom"

    def review(self, **kwargs):
        raise RuntimeError("kaboom")


def _run(jobs):
    return run_reviews(jobs=jobs, workdir="/wd", base="main", owner="o", repo="r", number=1)


def test_single_job_passthrough_and_per_job_args():
    r = FakeReviewer("claude")
    result = _run([ReviewJob(r, FakeType("test-gap"), "m1", ["--x"])])
    assert result.failures == []
    assert result.payload.body == "claude/test-gap"
    assert r.calls == [{"type": "test-gap", "model": "m1", "flags": ["--x"]}]


def test_two_jobs_merge_label_includes_model():
    jobs = [
        ReviewJob(FakeReviewer("claude"), FakeType("test-gap"), "m1", []),
        ReviewJob(FakeReviewer("codex"), FakeType("test-gap"), "m2", []),
    ]
    result = _run(jobs)
    assert "## test-gap — claude (m1)" in result.payload.body
    assert "## test-gap — codex (m2)" in result.payload.body
    assert len(result.payload.comments) == 2


def test_empty_model_label_omits_parens():
    jobs = [
        ReviewJob(FakeReviewer("claude"), FakeType("test-gap"), "m1", []),
        ReviewJob(FakeReviewer("codex"), FakeType("test-gap"), "", []),
    ]
    result = _run(jobs)
    assert "## test-gap — codex" in result.payload.body
    assert "codex ()" not in result.payload.body


def test_all_jobs_failing_yields_no_payload():
    result = _run([ReviewJob(BoomReviewer(), FakeType("test-gap"), "m1", [])])
    assert result.payload is None
    assert len(result.failures) == 1
    label, rtype, err = result.failures[0]
    assert label == "boom (m1)"
    assert rtype == "test-gap"
    assert "kaboom" in err


def test_partial_failure_keeps_successes_and_notes_failure():
    jobs = [
        ReviewJob(FakeReviewer("claude"), FakeType("test-gap"), "m1", []),
        ReviewJob(BoomReviewer(), FakeType("infracode"), "m2", []),
    ]
    result = _run(jobs)
    assert result.payload is not None
    assert "claude/test-gap" in result.payload.body
    assert "excluded" in result.payload.body  # the failed job is noted in the body
    assert len(result.failures) == 1
    assert result.failures[0][0] == "boom (m2)"
