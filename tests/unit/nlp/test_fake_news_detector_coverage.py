"""Coverage-focused tests for src/nlp/fake_news_detector.py.

Complements ``test_fake_news_detection.py`` by covering the code paths it does
not reach: the ``FakeNewsDataset`` ``__len__`` / ``__getitem__`` tokenisation,
the DeBERTa and generic-AutoModel branches of ``_load_model``, LIAR-dataset
CSV loading, ``batch_predict`` / ``evaluate_on_dataset`` aggregation, the
lazy-load branch inside ``predict_trustworthiness``, and the ``main`` demo.

All transformer models, tokenizers and torch inference calls are mocked, so no
weights are downloaded and no GPU is required.
"""

# --- Warm up heavy C-extension imports BEFORE coverage traces them. ----------
import torch  # noqa: E402,F401

try:
    import torch._dynamo  # noqa: E402,F401
except Exception:
    pass
try:
    from transformers import pipeline as _warm_pipeline  # noqa: E402,F401
except Exception:
    pass
# -----------------------------------------------------------------------------

import os  # noqa: E402
import sys  # noqa: E402
from unittest.mock import MagicMock, Mock, patch  # noqa: E402

import pytest  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.fake_news_detector as mod  # noqa: E402
from nlp.fake_news_detector import (  # noqa: E402
    FakeNewsConfig,
    FakeNewsDataset,
    FakeNewsDetector,
)


@pytest.fixture
def detector():
    return FakeNewsDetector(model_name="roberta-base", use_pretrained=False)


# --------------------------------------------------------------------------- #
# FakeNewsDataset (lines 51-70)
# --------------------------------------------------------------------------- #
class TestFakeNewsDataset:
    def test_len_and_getitem(self):
        tokenizer = MagicMock()
        tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2, 3, 4]]),
            "attention_mask": torch.tensor([[1, 1, 1, 1]]),
        }
        ds = FakeNewsDataset(["hello world", "another"], [1, 0], tokenizer, max_length=8)
        assert len(ds) == 2
        item = ds[0]
        assert set(item.keys()) == {"input_ids", "attention_mask", "labels"}
        assert item["labels"].item() == 1
        # tokenizer must be invoked with truncation/padding config
        tokenizer.assert_called_once()
        _, kwargs = tokenizer.call_args
        assert kwargs["truncation"] is True
        assert kwargs["max_length"] == 8


# --------------------------------------------------------------------------- #
# _load_model DeBERTa + generic AutoModel branches (lines 167-177)
# --------------------------------------------------------------------------- #
class TestLoadModelBranches:
    def test_deberta_branch(self):
        det = FakeNewsDetector(model_name="microsoft/deberta-base", use_pretrained=False)
        with patch.object(mod, "DebertaTokenizer") as tok, patch.object(
            mod, "DebertaForSequenceClassification"
        ) as model:
            tok.from_pretrained.return_value = MagicMock()
            built = MagicMock()
            model.from_pretrained.return_value = built
            det._load_model()
            tok.from_pretrained.assert_called_once_with("microsoft/deberta-base")
            model.from_pretrained.assert_called_once_with(
                "microsoft/deberta-base", num_labels=2
            )
            built.to.assert_called_once()

    def test_generic_automodel_branch(self):
        det = FakeNewsDetector(model_name="bert-base-uncased", use_pretrained=False)
        with patch.object(mod, "AutoTokenizer") as tok, patch.object(
            mod, "AutoModelForSequenceClassification"
        ) as model:
            tok.from_pretrained.return_value = MagicMock()
            built = MagicMock()
            model.from_pretrained.return_value = built
            det._load_model()
            tok.from_pretrained.assert_called_once_with("bert-base-uncased")
            model.from_pretrained.assert_called_once_with(
                "bert-base-uncased", num_labels=2
            )


# --------------------------------------------------------------------------- #
# prepare_liar_dataset CSV branch (lines 138-153)
# --------------------------------------------------------------------------- #
class TestPrepareLiarDataset:
    def test_loads_from_csv(self, detector, tmp_path, monkeypatch):
        data_file = tmp_path / "liar.tsv"
        data_file.write_text("dummy")  # existence is what matters; read is mocked

        fake_df = {
            "statement": ["stmt a", "stmt b", "stmt c"],
            "label": ["true", "false", "pants-fire"],
        }

        class FakeDF:
            def __init__(self, d):
                self._d = d

            def __getitem__(self, key):
                col = self._d[key]

                class Col(list):
                    def tolist(inner):
                        return list(col)

                return Col(col)

        monkeypatch.setattr(mod.pd, "read_csv", lambda *a, **k: FakeDF(fake_df))
        texts, labels = detector.prepare_liar_dataset(data_path=str(data_file))
        assert texts == ["stmt a", "stmt b", "stmt c"]
        # true -> 1, false -> 0, pants-fire -> 0
        assert labels == [1, 0, 0]

    def test_csv_load_failure_falls_back_to_synthetic(self, detector, tmp_path, monkeypatch):
        data_file = tmp_path / "liar.tsv"
        data_file.write_text("dummy")
        monkeypatch.setattr(
            mod.pd, "read_csv", MagicMock(side_effect=RuntimeError("parse fail"))
        )
        texts, labels = detector.prepare_liar_dataset(data_path=str(data_file))
        # Falls back to the built-in synthetic dataset.
        assert len(texts) == len(labels)
        assert len(texts) == 16


# --------------------------------------------------------------------------- #
# predict_trustworthiness lazy-load branch + batch_predict (lines 361, 411-415)
# --------------------------------------------------------------------------- #
def _wire_prediction(detector, logits):
    detector.tokenizer = MagicMock()
    detector.tokenizer.return_value = {"input_ids": Mock(), "attention_mask": Mock()}
    # input dict values need .to(device); make them mocks that return themselves
    for v in detector.tokenizer.return_value.values():
        v.to = MagicMock(return_value=v)
    model = MagicMock()
    out = Mock()
    out.logits = logits
    model.return_value = out
    detector.model = model


class TestPredictAndBatch:
    def test_predict_triggers_lazy_load(self, detector, monkeypatch):
        # model is None -> _load_model() must be invoked (line 360-361).
        loaded = {"n": 0}

        def fake_load():
            loaded["n"] += 1
            _wire_prediction(detector, torch.tensor([[0.1, 0.9]]))

        monkeypatch.setattr(detector, "_load_model", fake_load)
        result = detector.predict_trustworthiness("some article text")
        assert loaded["n"] == 1
        assert result["classification"] == "real"
        assert 0 <= result["trustworthiness_score"] <= 100
        assert result["model_used"] == "roberta-base"

    def test_predict_fake_classification(self, detector):
        _wire_prediction(detector, torch.tensor([[0.95, 0.05]]))
        result = detector.predict_trustworthiness("dubious claim")
        assert result["classification"] == "fake"
        assert result["fake_probability"] > result["real_probability"]

    def test_predict_skips_load_when_model_present(self, detector, monkeypatch):
        # model already set -> the lazy _load_model branch must be skipped (line 344).
        _wire_prediction(detector, torch.tensor([[0.2, 0.8]]))
        monkeypatch.setattr(
            detector,
            "_load_model",
            MagicMock(side_effect=AssertionError("should not reload")),
        )
        result = detector.predict_trustworthiness("already loaded model text")
        assert result["classification"] == "real"

    def test_batch_predict(self, detector, monkeypatch):
        monkeypatch.setattr(
            detector,
            "predict_trustworthiness",
            lambda text: {"classification": "real", "trustworthiness_score": 90.0},
        )
        results = detector.batch_predict(["a", "b", "c"])
        assert len(results) == 3
        assert all(r["classification"] == "real" for r in results)


# --------------------------------------------------------------------------- #
# evaluate_on_dataset (lines 430-451)
# --------------------------------------------------------------------------- #
class TestEvaluateOnDataset:
    def test_metrics_computed(self, detector, monkeypatch):
        # Map predictions so accuracy is not degenerate.
        seq = iter(
            [
                {"classification": "real"},
                {"classification": "fake"},
                {"classification": "real"},
                {"classification": "fake"},
            ]
        )
        monkeypatch.setattr(
            detector, "predict_trustworthiness", lambda text: next(seq)
        )
        texts = ["t1", "t2", "t3", "t4"]
        labels = [1, 0, 1, 0]  # perfect match with predictions above
        metrics = detector.evaluate_on_dataset(texts, labels)
        assert metrics["accuracy"] == pytest.approx(1.0)
        assert metrics["num_samples"] == 4
        assert isinstance(metrics["confusion_matrix"], list)
        assert "precision" in metrics and "recall" in metrics and "f1_score" in metrics


# --------------------------------------------------------------------------- #
# train synthetic-padding + test_size branches (lines 252-276, 301-309)
# --------------------------------------------------------------------------- #
class TestTrainBranches:
    def test_train_pads_small_dataset_and_computes_metrics(self, detector, tmp_path):
        detector.model = Mock()
        detector.tokenizer = Mock()

        captured = {}

        class FakeTrainer:
            def __init__(self, **kwargs):
                # capture compute_metrics so we can exercise it directly
                captured["compute_metrics"] = kwargs.get("compute_metrics")

            def train(self):
                return None

            def evaluate(self):
                # "epoch" has no eval_ prefix -> exercises the else branch (line 344).
                return {"eval_loss": 0.2, "eval_accuracy": 0.9, "epoch": 1.0}

            def save_model(self):
                return None

        with patch.object(mod, "Trainer", FakeTrainer), patch.object(
            mod, "TrainingArguments", MagicMock()
        ):
            # Fewer than 4 samples -> triggers synthetic-padding branch (252-262).
            metrics = detector.train(
                texts=["real one", "fake one"],
                labels=[1, 0],
                num_epochs=1,
                batch_size=2,
                output_dir=str(tmp_path),
            )

        assert "accuracy" in metrics  # eval_ prefix stripped
        assert "loss" in metrics
        assert metrics["epoch"] == 1.0  # non-prefixed key passed through unchanged
        # Exercise the captured compute_metrics closure (lines 301-309).
        import numpy as np

        preds = np.array([[0.1, 0.9], [0.8, 0.2]])
        labels = np.array([1, 0])
        cm = captured["compute_metrics"]((preds, labels))
        assert cm["accuracy"] == pytest.approx(1.0)
        assert set(cm.keys()) == {"accuracy", "f1", "precision", "recall"}

    def test_train_high_validation_split_clamps_test_size(self, detector, tmp_path):
        # A large validation_split makes test_size >= len(texts) - 1, exercising
        # the clamp branch on line 267 (test_size = len(texts) // 2).
        detector.model = Mock()
        detector.tokenizer = Mock()

        class FakeTrainer:
            def __init__(self, **kwargs):
                pass

            def train(self):
                return None

            def evaluate(self):
                return {"eval_loss": 0.1, "eval_accuracy": 0.95}

            def save_model(self):
                return None

        with patch.object(mod, "Trainer", FakeTrainer), patch.object(
            mod, "TrainingArguments", MagicMock()
        ):
            metrics = detector.train(
                texts=["a real one", "a fake one", "another real", "another fake"],
                labels=[1, 0, 1, 0],
                validation_split=0.9,  # forces the clamp
                num_epochs=1,
                batch_size=2,
                output_dir=str(tmp_path),
            )
        assert "accuracy" in metrics


# --------------------------------------------------------------------------- #
# main() demo (lines 490-523)
# --------------------------------------------------------------------------- #
class TestMain:
    def test_main_runs(self, monkeypatch):
        fake_detector = MagicMock()
        fake_detector.prepare_liar_dataset.return_value = (["a", "b"], [1, 0])
        fake_detector.predict_trustworthiness.return_value = {
            "trustworthiness_score": 70.0,
            "classification": "real",
            "confidence": 80.0,
        }
        fake_detector.evaluate_on_dataset.return_value = {"accuracy": 0.9}
        monkeypatch.setattr(mod, "FakeNewsDetector", lambda **kw: fake_detector)
        # Should complete without raising.
        mod.main()
        fake_detector.prepare_liar_dataset.assert_called_once()
        assert fake_detector.predict_trustworthiness.call_count >= 1


# --------------------------------------------------------------------------- #
# Config class-level constants (lines 468-487)
# --------------------------------------------------------------------------- #
class TestConfigConstants:
    def test_class_constants(self):
        assert FakeNewsConfig.HIGH_CONFIDENCE_THRESHOLD == 80.0
        assert FakeNewsConfig.MEDIUM_CONFIDENCE_THRESHOLD == 60.0
        assert FakeNewsConfig.VERACITY_TABLE == "article_veracity"
        assert "roberta-base" in FakeNewsConfig.MODELS
