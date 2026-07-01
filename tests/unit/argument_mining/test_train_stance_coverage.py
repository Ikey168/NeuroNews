"""
Coverage tests for src/argument_mining/train_stance.py — the 4-class stance
classification training entrypoint.

The transformers stack (AutoTokenizer / AutoModelForSequenceClassification /
Trainer / TrainingArguments / DataCollatorWithPadding / pipeline) is fully
mocked so that NO model download and NO fine-tuning ever happen.  The real
topic-encoding / label-mapping / dataset construction / metric computation /
per-source-type evaluation / artefact writing and argparse/main orchestration
paths are exercised with real assertions.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import src.argument_mining.train_stance as ts  # noqa: E402
from src.argument_mining.dataset import STANCE_LABELS  # noqa: E402

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
# Fakes
# ---------------------------------------------------------------------------

class _FakeTokenizer:
    def __init__(self) -> None:
        self.saved_to: list[str] = []
        self.seen_texts: list = []

    def __call__(self, texts, **kw):
        if isinstance(texts, str):
            texts = [texts]
        self.seen_texts.extend(texts)
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


def _make_pipeline_factory(label: str = "LABEL_2"):
    def factory(*a, **k):
        def _run(texts, **kw):
            return [{"label": label, "score": 0.9} for _ in texts]

        return _run

    return factory


class _RecordingTrainer:
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
        assert len(self.train_dataset) > 0
        item = self.eval_dataset[0]
        assert "input_ids" in item and "labels" in item
        # 4-class logits: rows argmax -> [0, 1, 2, 3]; labels the same -> perfect.
        logits = np.array(
            [
                [3.0, 0.0, 0.0, 0.0],
                [0.0, 3.0, 0.0, 0.0],
                [0.0, 0.0, 3.0, 0.0],
                [0.0, 0.0, 0.0, 3.0],
            ]
        )
        lbls = np.array([0, 1, 2, 3])
        self.cm_result = self.compute_metrics((logits, lbls))
        return {"eval_f1_macro": 0.72, "eval_loss": 0.2}


def _balanced_examples(reps: int = 5):
    """(text, topic, stance, source_type). All four stance classes, all news
    so the validation split has >=2 examples of the same source type."""
    out = []
    for i in range(reps):
        for s in STANCE_LABELS:
            out.append(
                (f"{s} sentence number {i} long enough here now", f"topic{i}", s, "news")
            )
    return out


def _patched_train(examples, output_dir, **kwargs):
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
        metrics = ts.train(examples, output_dir, **kwargs)
    return metrics, tok, model, ta


# ---------------------------------------------------------------------------
# train()
# ---------------------------------------------------------------------------

class TestTrain:
    def test_returns_eval_and_per_source_metrics(self, tmp_path):
        out = tmp_path / "stance_model"
        metrics, _tok, _model, _ta = _patched_train(
            _balanced_examples(), out, epochs=1, batch_size=2
        )
        assert metrics["eval_f1_macro"] == 0.72
        assert metrics["per_source_type"]
        assert set(metrics["per_source_type"]) <= {"news"}

    def test_topic_is_prepended_with_sep(self, tmp_path):
        out = tmp_path / "stance_model"
        _, tok, _model, _ta = _patched_train(_balanced_examples(), out, epochs=1)
        # The encoder should receive "<topic> [SEP] <text>" formatted inputs.
        assert any("[SEP]" in t for t in tok.seen_texts)
        assert any(t.startswith("topic") for t in tok.seen_texts)

    def test_training_was_invoked(self, tmp_path):
        _patched_train(_balanced_examples(), tmp_path / "m", epochs=1)
        trainer = _RecordingTrainer.last_instance
        assert trainer is not None and trainer.train_called is True

    def test_compute_metrics_perfect_predictions(self, tmp_path):
        _patched_train(_balanced_examples(), tmp_path / "m", epochs=1)
        cm = _RecordingTrainer.last_instance.cm_result
        assert set(cm) == {"f1_macro", "f1_weighted"}
        assert cm["f1_macro"] == pytest.approx(1.0)
        assert cm["f1_weighted"] == pytest.approx(1.0)

    def test_writes_label_map_and_metrics(self, tmp_path):
        out = tmp_path / "stance_model"
        _patched_train(_balanced_examples(), out, epochs=1)
        label_map = json.loads((out / "label_map.json").read_text())
        assert label_map == {str(i): s for i, s in enumerate(STANCE_LABELS)}
        assert label_map["0"] == "supportive"
        saved = json.loads((out / "eval_metrics.json").read_text())
        assert saved["eval_f1_macro"] == 0.72

    def test_model_and_tokenizer_saved(self, tmp_path):
        out = tmp_path / "stance_model"
        _, tok, model, _ = _patched_train(_balanced_examples(), out, epochs=1)
        model.save_pretrained.assert_called_once_with(str(out))
        assert str(out) in tok.saved_to

    def test_training_arguments_use_stance_metric(self, tmp_path):
        out = tmp_path / "stance_model"
        _, _, _, ta = _patched_train(_balanced_examples(), out, epochs=3, batch_size=8)
        kwargs = ta.call_args.kwargs
        assert kwargs["output_dir"] == str(out)
        assert kwargs["num_train_epochs"] == 3
        assert kwargs["metric_for_best_model"] == "f1_macro"


# ---------------------------------------------------------------------------
# _eval_per_source_type()
# ---------------------------------------------------------------------------

class TestEvalPerSourceType:
    def test_insufficient_examples_note(self):
        tok = _FakeTokenizer()
        model = _make_fake_model()
        with patch("transformers.pipeline", side_effect=_make_pipeline_factory()):
            res = ts._eval_per_source_type(
                model,
                tok,
                val_inputs=["topic [SEP] only one long enough here"],
                val_labels=[0],
                val_source_types=["news"],
            )
        assert res["news"]["f1_macro"] is None
        assert res["news"]["n"] == 1
        assert "insufficient" in res["news"]["note"]

    def test_single_label_class_is_insufficient(self):
        tok = _FakeTokenizer()
        model = _make_fake_model()
        with patch("transformers.pipeline", side_effect=_make_pipeline_factory()):
            res = ts._eval_per_source_type(
                model,
                tok,
                val_inputs=["t [SEP] a long enough here", "t [SEP] b long enough here"],
                val_labels=[1, 1],
                val_source_types=["news", "news"],
            )
        assert res["news"]["f1_macro"] is None

    def test_f1_macro_computed_from_pipeline_labels(self):
        # pipeline returns LABEL_2 for every input -> preds all == 2.
        # labels [2, 3] -> one correct, one wrong.
        tok = _FakeTokenizer()
        model = _make_fake_model()
        with patch("transformers.pipeline", side_effect=_make_pipeline_factory("LABEL_2")):
            res = ts._eval_per_source_type(
                model,
                tok,
                val_inputs=["t [SEP] a long enough here", "t [SEP] b long enough here"],
                val_labels=[2, 3],
                val_source_types=["news", "news"],
            )
        assert res["news"]["n"] == 2
        assert isinstance(res["news"]["f1_macro"], float)
        assert 0.0 <= res["news"]["f1_macro"] <= 1.0

    def test_label_index_parsed_from_pipeline_string(self):
        # LABEL_1 -> pred 1 for all inputs; labels [1, 0] -> macro F1 in (0,1).
        tok = _FakeTokenizer()
        model = _make_fake_model()
        with patch("transformers.pipeline", side_effect=_make_pipeline_factory("LABEL_1")):
            res = ts._eval_per_source_type(
                model,
                tok,
                val_inputs=["t [SEP] a long enough here", "t [SEP] b long enough here"],
                val_labels=[1, 0],
                val_source_types=["news", "news"],
            )
        # preds == [1, 1]; only first correct.
        assert res["news"]["f1_macro"] == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_default_orchestration(self, tmp_path, monkeypatch):
        out = tmp_path / "out"
        monkeypatch.setattr(
            sys, "argv", ["train_stance", "--output", str(out), "--epochs", "1"]
        )
        fake_examples = _balanced_examples()
        captured = {}

        def fake_train(**kwargs):
            captured.update(kwargs)
            return {
                "eval_f1_macro": 0.71,
                "per_source_type": {"news": {"f1_macro": 0.6, "n": 4}},
            }

        with patch(
            "src.argument_mining.dataset.load_stance_dataset",
            return_value=fake_examples,
        ) as loader, patch.object(ts, "train", side_effect=fake_train):
            ts.main()

        loader.assert_called_once()
        assert captured["output_dir"] == out
        assert captured["epochs"] == 1
        assert captured["examples"] == fake_examples

    def test_main_below_target_warns(self, tmp_path, monkeypatch, caplog):
        import logging

        out = tmp_path / "out"
        monkeypatch.setattr(sys, "argv", ["train_stance", "--output", str(out)])
        with patch(
            "src.argument_mining.dataset.load_stance_dataset",
            return_value=_balanced_examples(),
        ), patch.object(
            ts,
            "train",
            return_value={
                "eval_f1_macro": 0.10,
                "per_source_type": {
                    "news": {"f1_macro": 0.5, "n": 4},
                    "blog": {"f1_macro": None, "n": 1, "note": "insufficient"},
                },
            },
        ):
            with caplog.at_level(logging.WARNING):
                ts.main()
        assert any("below the 0.70 target" in r.message for r in caplog.records)

    def test_main_passes_cli_hyperparams(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        out = tmp_path / "out"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "train_stance", "--data", str(data_dir), "--output", str(out),
                "--base-model", "bert-base-uncased", "--batch-size", "16",
                "--lr", "3e-5", "--epochs", "2",
            ],
        )
        with patch(
            "src.argument_mining.dataset.load_stance_dataset",
            return_value=_balanced_examples(),
        ) as loader, patch.object(
            ts, "train",
            return_value={
                "eval_f1_macro": 0.9,
                "per_source_type": {"news": {"f1_macro": 0.8, "n": 4}},
            },
        ) as trn:
            ts.main()
        loader.assert_called_once_with(data_dir)
        kwargs = trn.call_args.kwargs
        assert kwargs["base_model"] == "bert-base-uncased"
        assert kwargs["batch_size"] == 16
        assert kwargs["lr"] == pytest.approx(3e-5)
        assert kwargs["epochs"] == 2


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
    trainer.evaluate.return_value = {"eval_f1_macro": 0.9}
    with patch(
        "src.argument_mining.dataset.load_stance_dataset",
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
        runpy.run_module("src.argument_mining.train_stance", run_name="__main__")
    # The artefacts must have been written by the mocked training run.
    assert (out / "label_map.json").exists()
    assert (out / "eval_metrics.json").exists()
