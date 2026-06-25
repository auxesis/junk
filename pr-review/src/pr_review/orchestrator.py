"""Fan out (reviewer x review-type) jobs in parallel, then collate."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pr_review.collate import Collator, DeterministicMergeCollator, Job
from pr_review.payload import Payload
from pr_review.reviewers.base import Reviewer
from pr_review.review_types.base import ReviewType


@dataclass
class ReviewJob:
    reviewer: Reviewer
    review_type: ReviewType


def run_reviews(
    *,
    jobs: list[ReviewJob],
    workdir: str,
    base: str,
    owner: str,
    repo: str,
    number: int,
    model: str,
    extra_flags: list[str],
    collator: Collator | None = None,
    max_workers: int | None = None,
) -> Payload:
    collator = collator or DeterministicMergeCollator()

    def _one(job: ReviewJob) -> Job:
        try:
            payload = job.reviewer.review(
                workdir=workdir, base=base, owner=owner, repo=repo, number=number,
                review_type=job.review_type, model=model, extra_flags=extra_flags,
            )
        except Exception as e:
            raise RuntimeError(
                f"{job.reviewer.name}/{job.review_type.name} review failed: {e}"
            ) from e
        return (job.reviewer.name, job.review_type.name, payload)

    with ThreadPoolExecutor(max_workers=max_workers or len(jobs) or 1) as ex:
        results = list(ex.map(_one, jobs))
    return collator.collate(results)
