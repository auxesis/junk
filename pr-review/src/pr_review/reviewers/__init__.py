"""Reviewers package — importing it registers the built-in reviewers."""
from pr_review.reviewers.base import Reviewer, available, get_reviewer, register
from pr_review.reviewers import claude  # noqa: F401  (registers ClaudeReviewer)
from pr_review.reviewers import codex  # noqa: F401  (registers CodexReviewer)

__all__ = ["Reviewer", "available", "get_reviewer", "register"]
