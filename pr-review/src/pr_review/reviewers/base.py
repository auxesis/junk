"""Reviewer seam: an LLM backend that turns a checkout into a Payload."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pr_review.payload import Payload
from pr_review.reviewers._run import run_cli_reviewer
from pr_review.review_types.base import ReviewType

_REGISTRY: dict[str, "Reviewer"] = {}


class Reviewer(ABC):
    name: str
    default_model: str
    # Static fallback for `available_models`; default_model must be in it.
    known_models: list[str]

    @abstractmethod
    def command(self, model: str, extra_flags: list[str]) -> list[str]:
        """The CLI argv (with the model baked in) that runs this agent headless."""

    def available_models(self) -> list[str]:
        """Models for `--list-models`. Override to query the backend live."""
        return list(self.known_models)

    def review(
        self,
        *,
        workdir: str,
        base: str,
        owner: str,
        repo: str,
        number: int,
        review_type: ReviewType,
        model: str,
        extra_flags: list[str],
        context: str = "",
    ) -> Payload:
        return run_cli_reviewer(
            self.command(model, extra_flags),
            workdir=workdir, owner=owner, repo=repo, number=number,
            base=base, review_type=review_type, context=context,
        )


def register(rev: Reviewer) -> Reviewer:
    _REGISTRY[rev.name] = rev
    return rev


def get_reviewer(name: str) -> Reviewer:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown reviewer: {name!r}; available: {', '.join(sorted(_REGISTRY))}"
        ) from None


def available() -> list[str]:
    return sorted(_REGISTRY)
