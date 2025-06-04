"""Minimal sentiment analysis utilities used in tests."""

import logging
from typing import Dict, List, Optional
from importlib import import_module

logger = logging.getLogger(__name__)

def pipeline(*args: object, **kwargs: object):
    """Shallow wrapper around ``transformers.pipeline``.

    This exists so tests can monkeypatch it without importing the heavy
    ``transformers`` dependency when it's not installed.  If the library is not
    available a :class:`RuntimeError` is raised.
    """
    try:
        transformers = import_module("transformers")
    except Exception as exc:  # pragma: no cover - transformers not installed
        raise RuntimeError("transformers is not available") from exc

    return transformers.pipeline(*args, **kwargs)


class SentimentAnalyzer:
    """A very small rule based sentiment analyzer used for tests."""

    DEFAULT_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"

    POSITIVE_WORDS = {
        "exceed", "growth", "grew", "profit", "excellent",
        "love", "good", "great", "positive", "up", "wonderful", "amazing",
    }
    NEGATIVE_WORDS = {
        "crash", "wipe", "loss", "decline", "bad",
        "terrible", "hate", "negative", "down", "dreadful",
    }

    def __init__(self, model_name: Optional[str] = None, **_: object) -> None:
        if model_name and model_name != self.DEFAULT_MODEL:
            raise ValueError(f"Unsupported model: {model_name}")
        self.model_name = model_name or self.DEFAULT_MODEL

        # Try to create a Hugging Face pipeline if transformers is installed.
        # This allows existing tests to monkeypatch ``pipeline``.
        try:
            self.pipeline = pipeline("sentiment-analysis", model=self.model_name)
        except Exception as exc:  # pragma: no cover - optional dependency missing
            logger.debug("Falling back to rule-based analyzer: %s", exc)
            self.pipeline = None

    def preprocess_text(self, text: str) -> str:
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        cleaned = " ".join(text.strip().split())
        if cleaned == "":
            raise ValueError("text must not be empty")
        return cleaned

    def _classify(self, text: str) -> str:
        lowered = text.lower()
        if any(word in lowered for word in self.POSITIVE_WORDS):
            return "POSITIVE"
        if any(word in lowered for word in self.NEGATIVE_WORDS):
            return "NEGATIVE"
        return "NEUTRAL"

    def analyze(self, text: str) -> Dict[str, object]:
        if text is None or not str(text).strip():
            return {
                "label": "ERROR",
                "score": 0.0,
                "text": text,
                "message": "Input text is empty or whitespace.",
            }
        if self.pipeline:
            try:
                result = self.pipeline(text)
                if isinstance(result, list):
                    result = result[0]
                return {
                    "label": str(result.get("label", "NEUTRAL")).upper(),
                    "score": float(result.get("score", 0.0)),
                    "text": text,
                }
            except Exception as exc:  # pragma: no cover - runtime error
                logger.debug("Pipeline inference failed: %s", exc)

        label = self._classify(text)
        score = 1.0 if label != "NEUTRAL" else 0.5
        return {"label": label, "score": score, "text": text}

    def analyze_batch(self, texts: List[str]) -> List[Dict[str, object]]:
        valid_texts = [t for t in texts if t and str(t).strip()]

        if self.pipeline and valid_texts:
            try:
                raw_results = self.pipeline(valid_texts)
                processed: List[Dict[str, object]] = []
                result_idx = 0
                for original in texts:
                    if original and str(original).strip():
                        item = raw_results[result_idx]
                        processed.append({
                            "label": str(item.get("label", "NEUTRAL")).upper(),
                            "score": float(item.get("score", 0.0)),
                            "text": original,
                        })
                        result_idx += 1
                    else:
                        processed.append({
                            "label": "ERROR",
                            "score": 0.0,
                            "text": original,
                            "message": "Input text is empty or whitespace.",
                        })
                return processed
            except Exception as exc:  # pragma: no cover - runtime error
                logger.debug("Pipeline batch inference failed: %s", exc)

        return [self.analyze(t) for t in texts]

    # maintain backwards compatibility
    batch_analyze = analyze_batch


def create_analyzer(model_name: Optional[str] = None, **kwargs: object) -> SentimentAnalyzer:
    """Factory used by tests and application code."""

    if kwargs:
        logger.debug("Ignoring additional parameters for create_analyzer: %s", kwargs)

    return SentimentAnalyzer(model_name=model_name)
