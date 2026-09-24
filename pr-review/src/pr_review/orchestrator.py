"""Fan out (agent, model) x review-type jobs in parallel, then collate.

A failing job never aborts the run: its error is recorded in `RunResult.jobs`, the surviving jobs
still produce a review, and only when every job fails is there no payload.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from pr_review.attribution import JobRecord
from pr_review.collate import Collator, DeterministicMergeCollator, Job
from pr_review.payload import Payload, Source
from pr_review.reviewers.base import Reviewer
from pr_review.review_types.base import ReviewType


@dataclass
class ReviewJob:
    reviewer: Reviewer
    review_type: ReviewType
    model: str
    extra_flags: list[str]


@dataclass
class RunResult:
    payload: Payload | None  # collated successes; None when every job failed
    failures: list[tuple[str, str, str]]  # (label, review_type_name, error)
    jobs: list[JobRecord] = field(default_factory=list)


def _label(reviewer_name: str, model: str) -> str:
    return f"{reviewer_name} ({model})" if model else reviewer_name


def run_reviews(
    *,
    jobs: list[ReviewJob],
    workdir: str,
    base: str,
    owner: str,
    repo: str,
    number: int,
    collator: Collator | None = None,
    max_workers: int | None = None,
) -> RunResult:
    collator = collator or DeterministicMergeCollator()

    def _one(job: ReviewJob):
        label = _label(job.reviewer.name, job.model)
        source = Source(job.reviewer.name, job.model, job.review_type.name)
        try:
            payload = job.reviewer.review(
                workdir=workdir, base=base, owner=owner, repo=repo, number=number,
                review_type=job.review_type, model=job.model, extra_flags=job.extra_flags,
            )
            for comment in payload.comments:
                comment.sources = [source]
            return ("ok", label, job.review_type.name, payload, source)
        except Exception as e:  # a failed job must not abort the whole run
            return ("err", label, job.review_type.name, str(e), source)

    with ThreadPoolExecutor(max_workers=max_workers or len(jobs) or 1) as ex:
        outcomes = list(ex.map(_one, jobs))

    successes: list[Job] = [
        (label, rt, result) for kind, label, rt, result, _ in outcomes if kind == "ok"
    ]
    failures: list[tuple[str, str, str]] = [
        (label, rt, result) for kind, label, rt, result, _ in outcomes if kind == "err"
    ]
    records = [
        JobRecord(source, raw=len(result.comments)) if kind == "ok"
        else JobRecord(source, error=result)
        for kind, _, _, result, source in outcomes
    ]

    if not successes:
        return RunResult(payload=None, failures=failures, jobs=records)
    return RunResult(payload=collator.collate(successes), failures=failures, jobs=records)
