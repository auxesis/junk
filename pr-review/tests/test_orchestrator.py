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
        self.calls.append((review_type.name, workdir))
        return Payload(body=f"{self.name}/{review_type.name}",
                       comments=[Comment("f.py", 1, "g")])


def test_run_reviews_single_job_passthrough():
    r = FakeReviewer("claude")
    out = run_reviews(
        jobs=[ReviewJob(r, FakeType("test-gap"))],
        workdir="/wd", base="main", owner="o", repo="r", number=1,
        model="m", extra_flags=[],
    )
    assert out.body == "claude/test-gap"
    assert r.calls == [("test-gap", "/wd")]


def test_run_reviews_two_jobs_merge():
    jobs = [
        ReviewJob(FakeReviewer("claude"), FakeType("test-gap")),
        ReviewJob(FakeReviewer("codex"), FakeType("test-gap")),
    ]
    out = run_reviews(
        jobs=jobs, workdir="/wd", base="main", owner="o", repo="r", number=1,
        model="m", extra_flags=[],
    )
    assert "## test-gap — claude" in out.body
    assert "## test-gap — codex" in out.body
    assert len(out.comments) == 2


class BoomReviewer:
    name = "boom"

    def review(self, **kwargs):
        raise RuntimeError("kaboom")


def test_run_reviews_attributes_failing_job():
    jobs = [ReviewJob(BoomReviewer(), FakeType("test-gap"))]
    with pytest.raises(RuntimeError, match="boom/test-gap"):
        run_reviews(
            jobs=jobs, workdir="/wd", base="main", owner="o", repo="r",
            number=1, model="m", extra_flags=[],
        )
