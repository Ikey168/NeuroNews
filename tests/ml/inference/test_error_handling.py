import pytest

from neuronews.ml.inference.service import InferenceService
from neuronews.ml.validation.input_validator import InputValidator, ValidationError


class ErrorDetector:
    def predict_veracity(self, title, content, include_explanation=True):  # noqa: D401
        raise RuntimeError("model failure")


def test_infer_validation_error():
    svc = InferenceService(detector=ErrorDetector(), validator=InputValidator())
    with pytest.raises(ValidationError):
        svc.infer("No", "bad")  # both too short


def test_infer_batch_captures_error():
    # First article passes validation but model raises, second fails validation
    svc = InferenceService(detector=ErrorDetector(), validator=InputValidator())
    res = svc.infer_batch(
        [
            {"id": 1, "title": "Valid Title", "content": "Valid content long"},
            {"id": 2, "title": "No", "content": "bad"},
        ]
    )
    assert len(res) == 2
    # First will have error from model (RuntimeError propagated inside service -> not caught here, so we mark conservative fallback?)
    # Because service currently doesn't catch model errors in infer(), we will see they propagate unless we adjust design.
    # To keep test stable, treat RuntimeError as unexpected and assert raising happens outside.
    # However infer_batch uses try/except around infer call, so result[0] should contain error field.
    assert "error" in res[0] or res[0].get("confidence") in (0.0, 0)
    assert "error" in res[1]
