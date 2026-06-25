"""ReviewType seam: a named, reviewer-agnostic review prompt."""
from __future__ import annotations

from abc import ABC, abstractmethod

_REGISTRY: dict[str, "ReviewType"] = {}


class ReviewType(ABC):
    name: str

    @abstractmethod
    def instructions(self) -> str:
        """The full instruction block handed to a reviewer."""


def register(rt: ReviewType) -> ReviewType:
    _REGISTRY[rt.name] = rt
    return rt


def get_review_type(name: str) -> ReviewType:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown review type: {name!r}; available: {', '.join(sorted(_REGISTRY))}"
        ) from None


def available() -> list[str]:
    return sorted(_REGISTRY)
