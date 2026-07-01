"""
Coverage tests for src/argument_mining/train_claim.py — the claim-detection
training entrypoint.

The heavy transformers stack (AutoTokenizer / AutoModelForSequenceClassification /
Trainer / TrainingArguments / pipeline) is fully mocked so that NO model download,
NO fine-tuning and NO GPU work ever happens.  The real data-prep, dataset
construction, metric-computation, per-source-type evaluation, artefact writing and
argparse/main orchestration code paths are exercised with real assertions.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Genuinely-required numerical deps for the module under test.
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

# Ensure repo root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import src.argument_mining.train_claim as tc  # noqa: E402

# The transformers 5.x package is a lazy module: force attribute resolution up
# front so that unittest.mock.patch can reliably replace the names.
for _name in (
    "Trainer",
    "TrainingArguments",
    "DataCollatorWithPadding",
    "AutoTokenizer",
    "AutoModelForSequenceClassification",
    "pipeline",
):
    getattr(transformers, _name)


# ---------------------------------------------------------------------------
# Fakes: a tokenizer, a model and a Trainer that exercise the local closures
# ---------------------------------------------------------------------------

class _FakeTokenizer:
    """Returns fixed-length encodings; records save_pretrained calls."""

    def __init__(self) -> None:
        self.saved_to: list[str] = []

    def __call__(self, texts, **kw):
        if isinstance(texts, str):
            texts = [texts]
        return {
            "input_ids": [[1, 2, 3] for _ in texts],
            "attention_mask": [[1, 1, 1] for _ in texts],
        }

    def save_pretrained(self, path):
        self.saved_to.append(str(path))
        Path(path).mkdir(parents=True, exist_ok=True)


def _make_fake_model():
    model = MagicMock(name="fake_model")
    model.save_pretrained = MagicMock(
        side_effect=lambda p: Path(p).mkdir(parents=True, exist_ok=True)
    )
    return model


def _make_pipeline_factory(label: str = "LABEL_1"):
    """Returns a factory usable as transformers.pipeline replacement."""

    def factory(*a, **k):
        def _run(texts, **kw):
            return [{"label": label, "score": 0.9} for _ in texts]

        return _run

    return factory


class _RecordingTrainer:
    """Stand-in for transformers.Trainer.

    Captures the datasets and compute_metrics closure, and, in ``evaluate``,
    actively drives the ``_Dataset`` (``__len__`` / ``__getitem__``) and the
    ``compute_metrics`` closure so those lines are covered without any real
    training.
    """

    last_instance: "_RecordingTrainer | None" = None

    def __init__(
        self,
        model=None,
        args=None,
        train_dataset=None,
        eval_dataset=None,
        processing_class=None,
        data_collator=None,
        compute_metrics=None,
    ) -> None:
        self.model = model
        self.args = args
        self.train_dataset = train_dataset
        self.eval_dataset = eval_dataset
        self.compute_metrics = compute_metrics
        self.train_called = False
        self.cm_result = None
        _RecordingTrainer.last_instance = self

    def train(self):
        self.train_called = True

    def evaluate(self):
        # Drive the dataset closures.
        assert len(self.train_dataset) > 0
        assert len(self.eval_dataset) > 0
        item = self.eval_dataset[0]
        assert "input_ids" in item and "labels" in item
        # Drive the compute_metrics closure with binary logits/labels.
        logits = np.array([[2.0, -1.0], [-1.0, 2.0]])
        lbls = np.array([1, 1])
        self.cm_result = self.compute_metrics((logits, lbls))
        return {"eval_f1": 0.9, "eval_loss": 0.1}


def _balanced_examples():
    """(text, is_claim, source_type) with two source types, both labels each."""
    return [
        ("claim one sentence long enough to survive filtering", 1, "news"),
        ("not a claim just an opinion long enough here now", 0, "news"),
        ("claim two sentence long enough to survive filtering", 1, "news"),
        ("not a claim two opinion long enough here now day", 0, "news"),
        ("news claim three sentence long enough here now day", 1, "news"),
        ("news non claim three opinion long enough here now", 0, "news"),
        ("blog claim one sentence long enough here now today", 1, "blog"),
        ("blog non claim one opinion long enough here now day", 0, "blog"),
        ("blog claim two sentence long enough here now today", 1, "blog"),
        ("blog non claim two opinion long enough here now day", 0, "blog"),
    ]


def _patched_train(examples, output_dir, **kwargs):
    """Run tc.train with the whole transformers stack mocked out."""
    tok = _FakeTokenizer()
    model = _make_fake_model()
    with patch(
        "transformers.AutoTokenizer.from_pretrained", return_value=tok
    ), patch(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        return_value=model,
    ), patch(
        "transformers.TrainingArguments", MagicMock(name="TrainingArguments")
    ) as ta, patch(
        "transformers.DataCollatorWithPadding", MagicMock(name="DataCollator")
    ), patch(
        "transformers.Trainer", _RecordingTrainer
    ), patch(
        "transformers.pipeline", side_effect=_make_pipeline_factory()
    ):
        metrics = tc.train(examples, output_dir, **kwargs)
    return metrics, tok, model, ta


# ---------------------------------------------------------------------------
# train(): end-to-end with mocks
# ---------------------------------------------------------------------------

class TestTrain:
    def test_returns_eval_and_per_source_metrics(self, tmp_path):
        out = tmp_path / "claim_model"
        metrics, tok, model, _ta = _patched_train(
            _balanced_examples(), out, epochs=1, batch_size=2
        )
        assert metrics["eval_f1"] == 0.9
        assert "per_source_type" in metrics
        # Whichever source types land in the 20% validation split must be
        # a subset of the two present in the input, and non-empty.
        assert metrics["per_source_type"]
        assert set(metrics["per_source_type"]) <= {"news", "blog"}

    def test_training_was_invoked(self, tmp_path):
        _patched_train(_balanced_examples(), tmp_path / "m", epochs=1)
        trainer = _RecordingTrainer.last_instance
        assert trainer is not None
        assert trainer.train_called is True

    def test_compute_metrics_produces_binary_scores(self, tmp_path):
        _patched_train(_balanced_examples(), tmp_path / "m", epochs=1)
        cm = _RecordingTrainer.last_instance.cm_result
        # logits argmax -> [0, 1] vs labels [1, 1]: one correct positive.
        assert set(cm) == {"f1", "precision", "recall"}
        assert cm["precision"] == 1.0
        assert cm["recall"] == 0.5

    def test_writes_label_map_and_metrics_files(self, tmp_path):
        out = tmp_path / "claim_model"
        _patched_train(_balanced_examples(), out, epochs=1)
        label_map = json.loads((out / "label_map.json").read_text())
        assert label_map == {"0": "not_claim", "1": "claim"}
        saved = json.loads((out / "eval_metrics.json").read_text())
        assert saved["eval_f1"] == 0.9

    def test_model_and_tokenizer_saved(self, tmp_path):
        out = tmp_path / "claim_model"
        _, tok, model, _ = _patched_train(_balanced_examples(), out, epochs=1)
        model.save_pretrained.assert_called_once_with(str(out))
        assert str(out) in tok.saved_to

    def test_training_arguments_use_output_dir(self, tmp_path):
        out = tmp_path / "claim_model"
        _, _, _, ta = _patched_train(_balanced_examples(), out, epochs=2, batch_size=4)
        kwargs = ta.call_args.kwargs
        assert kwargs["output_dir"] == str(out)
        assert kwargs["num_train_epochs"] == 2
        assert kwargs["per_device_train_batch_size"] == 4
        assert kwargs["metric_for_best_model"] == "f1"


# ---------------------------------------------------------------------------
# _eval_per_source_type(): both branches
# ---------------------------------------------------------------------------

class TestEvalPerSourceType:
    def test_insufficient_examples_note(self):
        tok = _FakeTokenizer()
        model = _make_fake_model()
        with patch("transformers.pipeline", side_effect=_make_pipeline_factory()):
            res = tc._eval_per_source_type(
                model,
                tok,
                val_texts=["only one text long enough here now"],
                val_labels=[1],
                val_source_types=["news"],
            )
        assert res["news"]["f1"] is None
        assert res["news"]["n"] == 1
        assert "insufficient" in res["news"]["note"]

    def test_single_label_class_is_insufficient(self):
        # >=2 examples but only one distinct label -> still None.
        tok = _FakeTokenizer()
        model = _make_fake_model()
        with patch("transformers.pipeline", side_effect=_make_pipeline_factory()):
            res = tc._eval_per_source_type(
                model,
                tok,
                val_texts=["text a long enough here now", "text b long enough here"],
                val_labels=[1, 1],
                val_source_types=["news", "news"],
            )
        assert res["news"]["f1"] is None

    def test_f1_computed_when_all_predicted_positive(self):
        # pipeline always returns LABEL_1 -> preds all 1. Labels [1,0] ->
        # binary F1 = 2*TP/(2*TP+FP+FN) = 2/(2+1+0) = 0.6667.
        tok = _FakeTokenizer()
        model = _make_fake_model()
        with patch("transformers.pipeline", side_effect=_make_pipeline_factory("LABEL_1")):
            res = tc._eval_per_source_type(
                model,
                tok,
                val_texts=["claim text long enough here", "nonclaim text long here"],
                val_labels=[1, 0],
                val_source_types=["news", "news"],
            )
        assert res["news"]["n"] == 2
        assert res["news"]["f1"] == pytest.approx(2 / 3)

    def test_label_0_predictions_mapped_correctly(self):
        # pipeline returns LABEL_0 -> preds all 0. Labels [1,0] -> F1 = 0.0.
        tok = _FakeTokenizer()
        model = _make_fake_model()
        with patch("transformers.pipeline", side_effect=_make_pipeline_factory("LABEL_0")):
            res = tc._eval_per_source_type(
                model,
                tok,
                val_texts=["claim text long enough here", "nonclaim text long here"],
                val_labels=[1, 0],
                val_source_types=["news", "news"],
            )
        assert res["news"]["f1"] == 0.0


# ---------------------------------------------------------------------------
# main(): argparse + dataset loading + orchestration
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_default_args_uses_bootstrap(self, tmp_path, monkeypatch):
        out = tmp_path / "out"
        monkeypatch.setattr(
            sys, "argv", ["train_claim", "--output", str(out), "--epochs", "1"]
        )
        fake_examples = _balanced_examples()

        captured = {}

        def fake_train(**kwargs):
            captured.update(kwargs)
            return {"eval_f1": 0.9, "per_source_type": {"news": {"f1": 0.8, "n": 4}}}

        with patch(
            "src.argument_mining.dataset.load_claim_dataset",
            return_value=fake_examples,
        ) as loader, patch.object(tc, "train", side_effect=fake_train):
            tc.main()

        loader.assert_called_once()
        assert captured["output_dir"] == out
        assert captured["epochs"] == 1
        assert captured["examples"] == fake_examples

    def test_main_below_target_still_returns(self, tmp_path, monkeypatch, caplog):
        out = tmp_path / "out"
        monkeypatch.setattr(sys, "argv", ["train_claim", "--output", str(out)])
        with patch(
            "src.argument_mining.dataset.load_claim_dataset",
            return_value=_balanced_examples(),
        ), patch.object(
            tc,
            "train",
            return_value={
                "eval_f1": 0.10,
                "per_source_type": {
                    "news": {"f1": 0.5, "n": 4},
                    "blog": {"f1": None, "n": 1, "note": "insufficient examples"},
                },
            },
        ):
            import logging

            with caplog.at_level(logging.WARNING):
                tc.main()
        # Below-target overall F1 must emit a warning.
        assert any("below the 0.75 target" in r.message for r in caplog.records)

    def test_main_passes_data_dir_when_given(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        out = tmp_path / "out"
        monkeypatch.setattr(
            sys,
            "argv",
            ["train_claim", "--data", str(data_dir), "--output", str(out),
             "--base-model", "roberta-base", "--batch-size", "16", "--lr", "1e-4"],
        )
        with patch(
            "src.argument_mining.dataset.load_claim_dataset",
            return_value=_balanced_examples(),
        ) as loader, patch.object(
            tc, "train",
            return_value={"eval_f1": 0.9, "per_source_type": {}},
        ) as trn:
            tc.main()
        loader.assert_called_once_with(data_dir)
        kwargs = trn.call_args.kwargs
        assert kwargs["base_model"] == "roberta-base"
        assert kwargs["batch_size"] == 16
        assert kwargs["lr"] == pytest.approx(1e-4)


# ---------------------------------------------------------------------------
# Running the module as __main__ (covers the `if __name__ == "__main__"` guard)
# ---------------------------------------------------------------------------

def test_module_runs_as_main(tmp_path, monkeypatch):
    """Execute the module under run_name='__main__' with the whole stack mocked
    so the ``main()`` entrypoint under the guard is actually exercised."""
    out = tmp_path / "o"
    monkeypatch.setattr(
        sys, "argv", ["prog", "--output", str(out), "--epochs", "1"]
    )
    tok = _FakeTokenizer()
    model = _make_fake_model()
    trainer = MagicMock()
    trainer.model = model
    trainer.evaluate.return_value = {"eval_f1": 0.9}
    with patch(
        "src.argument_mining.dataset.load_claim_dataset",
        return_value=_balanced_examples(),
    ), patch(
        "transformers.AutoTokenizer.from_pretrained", return_value=tok
    ), patch(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        return_value=model,
    ), patch(
        "transformers.TrainingArguments", MagicMock()
    ), patch(
        "transformers.DataCollatorWithPadding", MagicMock()
    ), patch(
        "transformers.Trainer", MagicMock(return_value=trainer)
    ), patch(
        "transformers.pipeline", side_effect=_make_pipeline_factory()
    ):
        runpy.run_module("src.argument_mining.train_claim", run_name="__main__")
    assert (out / "label_map.json").exists()
    assert (out / "eval_metrics.json").exists()
