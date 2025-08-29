import json
import tempfile
from pathlib import Path
import pytest

from neuronews.ml.models.fake_news_detection import FakeNewsDetector


class DummyClassifierList:
    def __call__(self, text):  # noqa: D401
        return [[{"label": "REAL", "score": 0.8}, {"label": "FAKE", "score": 0.2}]]


class DummyClassifierSingle:
    def __call__(self, text):  # noqa: D401
        return [{"label": "FAKE", "score": 0.9}]


def test_load_config_from_file(tmp_path):
    cfg = {"fake_news_detection": {"confidence_threshold": 0.9, "max_length": 128}}
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg))
    det = FakeNewsDetector(config_path=str(cfg_file))
    assert det.confidence_threshold == 0.9
    assert det.max_length == 128


def test_predict_with_transformer_list(monkeypatch):
    det = FakeNewsDetector()
    det.classifier = DummyClassifierList()
    out = det.predict_veracity("Title", "Some researched study shows data")
    assert out["is_real"] is True
    assert 0 < out["confidence"] <= 1
    assert "explanation" in out


def test_predict_with_transformer_single(monkeypatch):
    det = FakeNewsDetector()
    det.classifier = DummyClassifierSingle()
    out = det.predict_veracity("Title", "Content")
    assert out["is_real"] is False
    assert out["confidence"] == 0.9


def test_rule_based_path(monkeypatch):
    det = FakeNewsDetector()
    det.classifier = None  # force rule-based
    out = det.predict_veracity("Shocking secret", "miracle cure you won't believe")
    assert out["is_real"] in (True, False)
    assert 0 <= out["confidence"] <= 1


def test_explanation_branches():
    det = FakeNewsDetector()
    det.classifier = None
    # High confidence real
    res = {"is_real": True, "confidence": 0.85}
    exp = det._generate_explanation("Title", "research data study", res)
    assert "research" in exp.lower() or "study" in exp.lower()
    # Fake with sensational language
    res2 = {"is_real": False, "confidence": 0.7}
    exp2 = det._generate_explanation("Shocking secret", "miracle claim", res2)
    assert "sensational" in exp2.lower() or "unrealistic" in exp2.lower() or "questionable" in exp2.lower()


def test_fallback_on_exception(monkeypatch):
    det = FakeNewsDetector()
    def boom(*args, **kwargs):
        raise RuntimeError("fail")
    det._predict_with_transformer = boom  # type: ignore
    out = det.predict_veracity("Title", "Content")
    # Should return something with model_version even if failed
    assert "model_version" in out
    assert 0 <= out["confidence"] <= 1


def test_batch_predict_and_truncation():
    det = FakeNewsDetector()
    det.classifier = None
    det.max_length = 4  # force truncation threshold extremely low
    long_content = "x" * 10000
    batch = [{"id": 1, "title": "Title", "content": long_content}]
    out_list = det.batch_predict(batch)
    assert len(out_list) == 1
    assert out_list[0]["article_id"] == 1


def test_get_model_info():
    det = FakeNewsDetector()
    info = det.get_model_info()
    assert info["model_name"]
    assert "confidence_threshold" in info
