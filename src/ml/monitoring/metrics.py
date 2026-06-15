"""Basic performance & drift metrics collectors."""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Any
import statistics


class PerformanceMonitor:
    def __init__(self, window: int = 50):
        self.window = window
        self._latencies: Deque[float] = deque(maxlen=window)

    def record(self, latency_ms: float):
        self._latencies.append(latency_ms)

    def summary(self) -> Dict[str, Any]:
        if not self._latencies:
            return {"count": 0, "avg": 0.0, "p95": 0.0}
        data = list(self._latencies)
        p95_index = int(0.95 * (len(data) - 1))
        return {
            "count": len(data),
            "avg": statistics.fmean(data),
            "p95": sorted(data)[p95_index],
        }


class DriftMonitor:
    """Simple population mean drift detection using rolling stats."""

    def __init__(self, baseline_mean: float, threshold: float = 0.2):
        self.baseline_mean = baseline_mean
        self.threshold = threshold
        self._values: Deque[float] = deque(maxlen=100)

    def record(self, value: float):
        self._values.append(value)

    def is_drifted(self) -> bool:
        if not self._values:
            return False
        current_mean = sum(self._values) / len(self._values)
        if self.baseline_mean == 0:  # avoid div zero
            return False
        return abs(current_mean - self.baseline_mean) / abs(self.baseline_mean) > self.threshold

    def summary(self) -> Dict[str, Any]:  # pragma: no cover - simple
        return {"drift": self.is_drifted(), "count": len(self._values)}
