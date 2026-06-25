from pr_review.collate import DeterministicMergeCollator
from pr_review.payload import Comment, Payload


def _job(reviewer, rtype, n_comments):
    comments = [Comment(f"{reviewer}.py", i, f"{reviewer}-gap-{i}") for i in range(n_comments)]
    return (reviewer, rtype, Payload(body=f"{reviewer} body", comments=comments))


def test_single_job_is_passthrough():
    p = Payload(body="solo", comments=[Comment("a", 1, "g")])
    out = DeterministicMergeCollator().collate([("claude", "test-gap", p)])
    assert out is p


def test_empty_jobs_returns_placeholder():
    out = DeterministicMergeCollator().collate([])
    assert out.comments == []
    assert out.body


def test_merge_two_jobs_combines_bodies_and_comments():
    jobs = [_job("codex", "test-gap", 2), _job("claude", "test-gap", 2)]
    out = DeterministicMergeCollator().collate(jobs)
    # ordered by reviewer name: claude before codex
    assert out.body.index("## test-gap — claude") < out.body.index("## test-gap — codex")
    assert len(out.comments) == 4


def test_merge_reapplies_cap_and_lists_overflow():
    jobs = [_job("claude", "test-gap", 5), _job("codex", "test-gap", 5)]
    out = DeterministicMergeCollator().collate(jobs)
    assert len(out.comments) == 8
    assert "## Additional coverage gaps not posted inline" in out.body
