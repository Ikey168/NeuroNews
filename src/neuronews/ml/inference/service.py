"""Inference service wrapping ML models for production-like usage.

Focuses on:
 - Input validation & preprocessing
 - Single & batch inference
 - Warmup & lightweight caching metadata
 - Performance metrics (basic)
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..models.fake_news_detection import FakeNewsDetector
from ..validation.input_validator import InputValidator, ValidationError
from ..preprocessing import text_cleaner


class InferenceService:
    """High-level inference orchestration layer."""

    def __init__(
        self,
        detector: Optional[FakeNewsDetector] = None,
        validator: Optional[InputValidator] = None,
        warm: bool = True,
    ):
        self.detector = detector or FakeNewsDetector()
        self.validator = validator or InputValidator()
        self._ready = False
        self._stats = {
            "total_requests": 0,
            "avg_latency_ms": 0.0,
            "last_latency_ms": None,
            "warmup_time_ms": None,
        }
        if warm:
            self.warmup()

    def warmup(self):
        start = time.time()
        # Run a trivial prediction to load model weights / pipeline
        try:
            self.detector.predict_veracity("warmup", "model initialization")
        except Exception:  # pragma: no cover - defensive
            pass
        self._ready = True
        self._stats["warmup_time_ms"] = (time.time() - start) * 1000
        return self._ready

    def is_ready(self) -> bool:
        return self._ready

    def infer(self, title: str, content: str) -> Dict[str, Any]:
        """Run single article inference with validation & preprocessing."""
        start = time.time()
        title_c, content_c = text_cleaner.clean(title, content)
        va = self.validator.validate(title_c, content_c)
        try:
            result = self.detector.predict_veracity(va.title, va.content)
        except Exception as e:  # pragma: no cover - defensive catch
            result = {
                "is_real": True,
                "confidence": 0.0,
                "error": f"model_error: {e}",
            }
        latency_ms = (time.time() - start) * 1000
        self._update_stats(latency_ms)
        return {
            "title": va.title,
            "content_len": len(va.content),
            "latency_ms": latency_ms,
            **result,
        }

    def infer_batch(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        outputs = []
        for art in articles:
            try:
                res = self.infer(art.get("title", ""), art.get("content", ""))
                res["article_id"] = art.get("id")
            except ValidationError as e:
                res = {
                    "error": str(e),
                    "article_id": art.get("id"),
                    "is_real": True,
                    "confidence": 0.0,
                }
            outputs.append(res)
        return outputs

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def _update_stats(self, latency_ms: float):
        s = self._stats
        n = s["total_requests"]
        s["avg_latency_ms"] = (s["avg_latency_ms"] * n + latency_ms) / (n + 1)
        s["total_requests"] = n + 1
        s["last_latency_ms"] = latency_ms
