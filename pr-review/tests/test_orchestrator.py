import pytest

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


def _run(jobs):
    return run_reviews(jobs=jobs, workdir="/wd", base="main", owner="o", repo="r", number=1)


def test_single_job_passthrough_and_per_job_args():
    r = FakeReviewer("claude")
    out = _run([ReviewJob(r, FakeType("test-gap"), "m1", ["--x"])])
    assert out.body == "claude/test-gap"
    assert r.calls == [{"type": "test-gap", "model": "m1", "flags": ["--x"]}]


def test_two_jobs_merge_label_includes_model():
    jobs = [
        ReviewJob(FakeReviewer("claude"), FakeType("test-gap"), "m1", []),
        ReviewJob(FakeReviewer("codex"), FakeType("test-gap"), "m2", []),
    ]
    out = _run(jobs)
    assert "## test-gap — claude (m1)" in out.body
    assert "## test-gap — codex (m2)" in out.body
    assert len(out.comments) == 2


class BoomReviewer:
    name = "boom"

    def review(self, **kwargs):
        raise RuntimeError("kaboom")


def test_run_reviews_attributes_failing_job():
    jobs = [ReviewJob(BoomReviewer(), FakeType("test-gap"), "m1", [])]
    with pytest.raises(RuntimeError, match=r"boom \(m1\)/test-gap"):
        _run(jobs)
