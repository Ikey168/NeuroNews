import time
import pytest

from neuronews.ml.inference.service import InferenceService


class MockDetector:
    def __init__(self):
        self.calls = 0

    def predict_veracity(self, title, content, include_explanation=True):  # noqa: D401
        self.calls += 1
        return {
            "is_real": True,
            "confidence": 0.9,
            "model_version": "mock",
            "timestamp": "2025-01-01T00:00:00Z",
        }


def make_service():
    return InferenceService(detector=MockDetector(), warm=False)


def test_warmup_sets_ready():
    svc = make_service()
    assert not svc.is_ready()
    svc.warmup()
    assert svc.is_ready()
    assert svc.stats()["warmup_time_ms"] >= 0


def test_single_infer_basic():
    svc = make_service()
    out = svc.infer("Valid Title", "Some sufficient content body for inference.")
    assert out["is_real"] is True
    assert 0 <= out["confidence"] <= 1
    assert out["content_len"] > 5
    assert out["latency_ms"] >= 0


def test_batch_infer_mixed():
    svc = make_service()
    batch = [
        {"id": 1, "title": "A", "content": "short"},  # invalid title (too short)
        {"id": 2, "title": "Good Title", "content": "Adequate content value."},
    ]
    results = svc.infer_batch(batch)
    assert len(results) == 2
    r1, r2 = results
    assert "error" in r1
    assert r2["is_real"] is True
    assert r2["confidence"] == 0.9


def test_stats_update():
    svc = make_service()
    svc.infer("Valid Title", "Content long enough")
    s = svc.stats()
    assert s["total_requests"] == 1
    assert s["avg_latency_ms"] >= 0
    assert s["last_latency_ms"] >= 0


@pytest.mark.performance
def test_performance_latency_under_threshold():
    svc = make_service()
    start = time.time()
    svc.infer("Another Title", "Some other valid content body")
    elapsed_ms = (time.time() - start) * 1000
    # Given the mock, this should be very small
    assert elapsed_ms < 50
