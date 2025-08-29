"""Basic text feature extraction helpers."""
from __future__ import annotations

from typing import Dict


def extract_basic_features(title: str, content: str) -> Dict[str, int]:
    title_words = title.strip().split() if title else []
    content_words = content.strip().split() if content else []
    return {
        "title_len": len(title),
        "content_len": len(content),
        "title_word_count": len(title_words),
        "content_word_count": len(content_words),
    }
