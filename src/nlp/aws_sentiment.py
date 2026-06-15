"""
Local lexicon-based sentiment analysis implementation.

This module provides a lightweight, pure-Python sentiment analyzer that runs
without any external services or heavy ML dependencies. It mirrors the output
shape previously produced by the AWS Comprehend-backed implementation so that
existing consumers keep working unchanged.
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# Lexicons mirror the lightweight approach used in
# ``src/scraper/async_pipelines.py::analyze_sentiment``.
POSITIVE_WORDS = {
    "good",
    "great",
    "excellent",
    "amazing",
    "wonderful",
    "fantastic",
    "positive",
    "success",
    "successful",
    "win",
    "victory",
    "progress",
    "improve",
    "improved",
    "improvement",
    "better",
    "best",
    "happy",
    "pleased",
    "excited",
    "optimistic",
    "hopeful",
    "love",
    "profit",
    "growth",
    "grew",
    "gain",
    "gains",
    "exceed",
    "exceeds",
    "strong",
    "boost",
    "benefit",
    "up",
}

NEGATIVE_WORDS = {
    "bad",
    "terrible",
    "awful",
    "horrible",
    "negative",
    "fail",
    "failure",
    "failed",
    "loss",
    "losses",
    "decline",
    "declined",
    "worse",
    "worst",
    "sad",
    "angry",
    "disappointed",
    "crisis",
    "problem",
    "issue",
    "concern",
    "worry",
    "fear",
    "hate",
    "crash",
    "crashed",
    "wipe",
    "drop",
    "dropped",
    "weak",
    "down",
    "dreadful",
}

_WORD_RE = re.compile(r"[a-zA-Z']+")


class LocalSentimentAnalyzer:
    """Local lexicon-based sentiment analysis.

    Drop-in replacement for the former AWS Comprehend analyzer. Requires no
    AWS account, no network access, and no boto3.
    """

    def __init__(self, region_name: str = "us-east-1", **kwargs: Any) -> None:
        """
        Initialize the local sentiment analyzer.

        Args:
            region_name: Accepted for API compatibility; ignored.
            **kwargs: Accepted for API compatibility; ignored.
        """
        # ``region_name`` and other kwargs are retained only so callers that
        # previously configured the AWS client do not break.
        self.region_name = region_name
        logger.info("Initialized local lexicon-based sentiment analyzer")

    def _score(self, text: str) -> Dict[str, float]:
        """Compute normalized positive/negative/neutral/mixed scores."""
        words = _WORD_RE.findall(text.lower())
        positive_count = sum(1 for word in words if word in POSITIVE_WORDS)
        negative_count = sum(1 for word in words if word in NEGATIVE_WORDS)
        total = positive_count + negative_count

        if total == 0:
            return {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0,
                "mixed": 0.0,
            }

        positive = positive_count / total
        negative = negative_count / total
        # When both polarities are present we surface a "mixed" signal.
        mixed = (
            min(positive, negative) * 2.0
            if positive_count > 0 and negative_count > 0
            else 0.0
        )

        return {
            "positive": float(positive),
            "negative": float(negative),
            "neutral": 0.0,
            "mixed": float(mixed),
        }

    def analyze(self, text: str, language_code: str = "en") -> Dict[str, Any]:
        """
        Analyze sentiment of a single text using the local lexicon.

        Args:
            text: Text to analyze.
            language_code: Accepted for API compatibility; recorded in output.

        Returns:
            Dict with sentiment analysis results.
        """
        if not text or not text.strip():
            return {
                "label": "ERROR",
                "score": 0.0,
                "text": text,
                "message": "Input text is empty or whitespace.",
                "provider": "local_lexicon",
            }

        scores = self._score(text)

        confidence_map = {
            "POSITIVE": scores["positive"],
            "NEGATIVE": scores["negative"],
            "NEUTRAL": scores["neutral"],
            "MIXED": scores["mixed"],
        }
        label = max(confidence_map, key=confidence_map.get)

        return {
            "label": label,
            "score": float(confidence_map[label]),
            "text": text,
            "all_scores": {
                "positive": scores["positive"],
                "negative": scores["negative"],
                "neutral": scores["neutral"],
                "mixed": scores["mixed"],
            },
            "provider": "local_lexicon",
            "language_code": language_code,
        }

    def analyze_batch(
        self, texts: List[str], language_code: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Analyze sentiment for multiple texts.

        Args:
            texts: List of texts to analyze.
            language_code: Language code recorded in output.

        Returns:
            List of sentiment analysis results.
        """
        if not texts:
            return []
        return [self.analyze(text, language_code=language_code) for text in texts]

    def batch_analyze(self, texts: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """Alias for analyze_batch to maintain compatibility."""
        return self.analyze_batch(texts, **kwargs)
