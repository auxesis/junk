"""Review types package — importing it registers the built-in types."""
from pr_review.review_types.base import (
    ReviewType,
    available,
    get_review_type,
    register,
)
from pr_review.review_types import test_gap  # noqa: F401  (registers TestGapType)
from pr_review.review_types import infracode  # noqa: F401  (registers InfracodeType)
from pr_review.review_types import golang  # noqa: F401  (registers GolangType)

__all__ = ["ReviewType", "available", "get_review_type", "register"]
