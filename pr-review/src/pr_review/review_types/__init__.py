"""Review types package — importing it registers the built-in types."""
from pr_review.review_types.base import (
    ReviewType,
    available,
    get_review_type,
    register,
)
from pr_review.review_types import test_gap  # noqa: F401  (registers TestGapType)

__all__ = ["ReviewType", "available", "get_review_type", "register"]
