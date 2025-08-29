"""Lightweight text preprocessing for inference inputs."""
import re
from typing import Tuple

WHITESPACE_RE = re.compile(r"\s+")


def clean(title: str, content: str) -> Tuple[str, str]:
    """Normalize whitespace and basic artifacts.

    Keeps it intentionally minimal to avoid altering semantic meaning.
    """
    title_clean = WHITESPACE_RE.sub(" ", title or "").strip()
    content_clean = WHITESPACE_RE.sub(" ", content or "").strip()
    return title_clean, content_clean
