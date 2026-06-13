"""Input validation utilities for ML inference.

Provides lightweight validation and normalization for article inference
requests to ensure downstream components receive clean, well-formed data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


class ValidationError(ValueError):
    """Raised when input validation fails."""


@dataclass
class ValidatedArticle:
    title: str
    content: str

    def combined(self) -> str:
        return f"{self.title}. {self.content}".strip()


class InputValidator:
    """Validate and normalize article inputs for inference."""

    def __init__(self, min_title_len: int = 3, min_content_len: int = 5, max_total_len: int = 10000):
        self.min_title_len = min_title_len
        self.min_content_len = min_content_len
        self.max_total_len = max_total_len

    def validate(self, title: str, content: str) -> ValidatedArticle:
        if title is None or content is None:
            raise ValidationError("title and content are required")
        title = title.strip()
        content = content.strip()
        if len(title) < self.min_title_len:
            raise ValidationError("title too short")
        if len(content) < self.min_content_len:
            raise ValidationError("content too short")
        total_len = len(title) + len(content)
        if total_len > self.max_total_len:
            # truncate content preserving title
            allowed_content = self.max_total_len - len(title)
            content = content[:allowed_content]
        return ValidatedArticle(title=title, content=content)

    def safe(self, title: str, content: str) -> Tuple[ValidatedArticle, list]:
        """Validate but capture errors instead of raising.

        Returns (validated_article_or_partial, errors)
        """
        errors = []
        try:
            va = self.validate(title, content)
            return va, errors
        except ValidationError as e:
            errors.append(str(e))
            return ValidatedArticle(title=title or "", content=content or ""), errors
