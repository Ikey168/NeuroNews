"""
Coverage tests for src/argument_mining/train_frames.py — the multi-label
narrative-frame classification training entrypoint.

The transformers stack (AutoTokenizer / AutoModelForSequenceClassification /
Trainer / TrainingArguments) is fully mocked so that NO model download and NO
fine-tuning ever happen.  Unlike the claim/stance trainers, per-source-type
evaluation here calls the model directly (``model(**enc).logits`` + sigmoid),
so the fake model returns real ``torch`` tensors.  The multi-label binarisation,
dataset construction, metric computation, per-source evaluation, artefact
writing and argparse/main orchestration are exercised with real assertions.
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
torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import src.argument_mining.train_frames as tf  # noqa: E402
from src.argument_mining.dataset import FRAME_LABELS, FRAME2ID  # noqa: E402

for _name in (
    "Trainer",
    "TrainingArguments",
    "AutoTokenizer",
    "AutoModelForSequenceClassification",
):
    getattr(transformers, _name)

N_FRAMES = len(FRAME_LABELS)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeTokenizer:
    """Handles both list-mode encoding (training) and return_tensors='pt'
    encoding used by the per-source evaluation path."""

    def __init__(self) -> None:
        self.saved_to: list[str] = []

    def __call__(self, texts, **kw):
        if isinstance(texts, str):
            texts = [texts]
        data = {
            "input_ids": [[1, 2, 3] for _ in texts],
            "attention_mask": [[1, 1, 1] for _ in texts],
        }
        if kw.get("return_tensors") == "pt":
            return {k: torch.tensor(v) for k, v in data.items()}
        return data

    def save_pretrained(self, path):
        self.saved_to.append(str(path))
        Path(path).mkdir(parents=True, exist_ok=True)


def _make_fake_model(logit_value: float = 0.0):
    """A callable model whose forward returns an object with a ``.logits``
    tensor shaped (batch, N_FRAMES).  ``logit_value`` controls the sigmoid
    output: 0.0 -> 0.5 (>=0.5 threshold -> predicts every frame)."""

    class _Output:
        def __init__(self, logits):
            self.logits = logits

    model = MagicMock(name="fake_model")

    def _forward(**enc):
        n = len(enc["input_ids"])
        return _Output(torch.full((n, N_FRAMES), float(logit_value)))

    model.side_effect = _forward
    model.eval = MagicMock()
    model.save_pretrained = MagicMock(
        side_effect=lambda p: Path(p).mkdir(parents=True, exist_ok=True)
    )
    return model


class _RecordingTrainer:
    last_instance: "_RecordingTrainer | None" = None

    def __init__(
        self,
        model=None,
        args=None,
        train_dataset=None,
        eval_dataset=None,
        processing_class=None,
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
        # Multi-label datasets carry float label vectors.
        assert "input_ids" in item and "labels" in item
        assert item["labels"].dtype == torch.float
        # Drive compute_metrics with multi-label logits/labels.  Non-active
        # frames get a strongly negative logit so sigmoid(<0.5) -> not
        # predicted; active frames get a strongly positive logit.
        logits = np.full((2, N_FRAMES), -5.0)
        logits[0, 0] = 5.0  # sigmoid ~1 -> predicts frame 0
        logits[1, 1] = 5.0  # sigmoid ~1 -> predicts frame 1
        lbls = np.zeros((2, N_FRAMES))
        lbls[0, 0] = 1.0
        lbls[1, 1] = 1.0
        self.cm_result = self.compute_metrics((logits, lbls))
        return {"eval_f1_macro": 0.8, "eval_f1_micro": 0.82, "eval_loss": 0.3}


def _frame_examples():
    """(text, source_type, frames). Two source types, varied frames."""
    return [
        ("economic markets fell sharply long enough here", "news", ["economic"]),
        ("security military strike long enough here now", "news", ["security"]),
        ("humanitarian aid warning long enough here now", "news", ["humanitarian"]),
        ("legal court ruling long enough here now day", "news", ["legal"]),
        ("political vote coalition long enough here now", "news", ["political"]),
        ("scientific study findings long enough here now", "blog", ["scientific"]),
        ("other festival crowd long enough here now day", "blog", ["other"]),
        ("economic other mixed long enough here now day", "blog", ["economic", "other"]),
        ("legal political ruling long enough here now day", "blog", ["legal", "political"]),
        ("scientific economic model long enough here now", "blog", ["scientific", "economic"]),
    ]


def _patched_train(examples, output_dir, model_logit=0.0, **kwargs):
    tok = _FakeTokenizer()
    model = _make_fake_model(model_logit)
    with patch(
        "transformers.AutoTokenizer.from_pretrained", return_value=tok
    ), patch(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        return_value=model,
    ), patch(
        "transformers.TrainingArguments", MagicMock(name="TrainingArguments")
    ) as ta, patch(
        "transformers.Trainer", _RecordingTrainer
    ):
        metrics = tf.train(examples, output_dir, **kwargs)
    return metrics, tok, model, ta


# ---------------------------------------------------------------------------
# train()
# ---------------------------------------------------------------------------

class TestTrain:
    def test_returns_eval_and_per_source_metrics(self, tmp_path):
        out = tmp_path / "frame_model"
        metrics, _tok, _model, _ta = _patched_train(
            _frame_examples(), out, epochs=1, batch_size=2
        )
        assert metrics["eval_f1_macro"] == 0.8
        assert "per_source_type" in metrics
        assert metrics["per_source_type"]
        assert set(metrics["per_source_type"]) <= {"news", "blog"}

    def test_training_was_invoked(self, tmp_path):
        _patched_train(_frame_examples(), tmp_path / "m", epochs=1)
        trainer = _RecordingTrainer.last_instance
        assert trainer is not None and trainer.train_called is True

    def test_compute_metrics_multilabel_scores(self, tmp_path):
        _patched_train(_frame_examples(), tmp_path / "m", epochs=1)
        cm = _RecordingTrainer.last_instance.cm_result
        assert set(cm) == {"f1_macro", "f1_micro"}
        # Perfectly matching predictions -> micro F1 == 1.0.
        assert cm["f1_micro"] == pytest.approx(1.0)

    def test_writes_label_map_and_metrics(self, tmp_path):
        out = tmp_path / "frame_model"
        _patched_train(_frame_examples(), out, epochs=1)
        label_map = json.loads((out / "label_map.json").read_text())
        assert label_map == {str(i): f for i, f in enumerate(FRAME_LABELS)}
        assert label_map["0"] == "economic"
        saved = json.loads((out / "eval_metrics.json").read_text())
        assert saved["eval_f1_macro"] == 0.8
        assert "per_source_type" in saved

    def test_model_and_tokenizer_saved(self, tmp_path):
        out = tmp_path / "frame_model"
        _, tok, model, _ = _patched_train(_frame_examples(), out, epochs=1)
        model.save_pretrained.assert_called_once_with(str(out))
        assert str(out) in tok.saved_to

    def test_training_arguments_use_frame_metric(self, tmp_path):
        out = tmp_path / "frame_model"
        _, _, _, ta = _patched_train(_frame_examples(), out, epochs=4, batch_size=8)
        kwargs = ta.call_args.kwargs
        assert kwargs["output_dir"] == str(out)
        assert kwargs["num_train_epochs"] == 4
        assert kwargs["metric_for_best_model"] == "f1_macro"

    def test_unknown_frame_label_is_ignored(self, tmp_path):
        """A frame not in FRAME2ID must not crash binarisation; it is skipped."""
        examples = _frame_examples()
        examples[0] = (examples[0][0], "news", ["economic", "not_a_real_frame"])
        out = tmp_path / "frame_model"
        metrics, _, _, _ = _patched_train(examples, out, epochs=1)
        assert metrics["eval_f1_macro"] == 0.8


# ---------------------------------------------------------------------------
# _eval_per_source_type(): direct model-inference path
# ---------------------------------------------------------------------------

class TestEvalPerSourceType:
    def test_insufficient_examples_note(self):
        tok = _FakeTokenizer()
        model = _make_fake_model()
        val_labels = np.zeros((1, N_FRAMES), dtype=int)
        res = tf._eval_per_source_type(
            model=model,
            tokenizer=tok,
            val_texts=["only one text long enough here now"],
            val_labels_bin=val_labels,
            val_source_types=["news"],
        )
        assert res["news"]["f1_macro"] is None
        assert res["news"]["n"] == 1
        assert "insufficient" in res["news"]["note"]

    def test_f1_computed_via_model_sigmoid(self):
        # model logits 5.0 -> sigmoid ~1 -> predicts ALL frames for every text.
        tok = _FakeTokenizer()
        model = _make_fake_model(logit_value=5.0)
        # Two news texts, ground-truth label vectors: frame 0 and frame 1.
        lbl0 = np.zeros(N_FRAMES, dtype=int)
        lbl0[0] = 1
        lbl1 = np.zeros(N_FRAMES, dtype=int)
        lbl1[1] = 1
        res = tf._eval_per_source_type(
            model=model,
            tokenizer=tok,
            val_texts=["text a long enough here now", "text b long enough here now"],
            val_labels_bin=[lbl0, lbl1],
            val_source_types=["news", "news"],
        )
        assert res["news"]["n"] == 2
        assert isinstance(res["news"]["f1_macro"], float)
        assert 0.0 <= res["news"]["f1_macro"] <= 1.0
        model.eval.assert_called()

    def test_perfect_predictions_give_f1_one(self):
        # Predict all-zero (logit -5 -> sigmoid ~0 -> no frame >= 0.5) and
        # labels all-zero -> macro F1 over all-negative is 0.0 in sklearn, so
        # instead use logit high on a frame both texts share.
        tok = _FakeTokenizer()
        model = _make_fake_model(logit_value=5.0)
        lbl = np.ones(N_FRAMES, dtype=int)  # all frames active -> preds match
        res = tf._eval_per_source_type(
            model=model,
            tokenizer=tok,
            val_texts=["text a long enough here now", "text b long enough here now"],
            val_labels_bin=[lbl, lbl],
            val_source_types=["news", "news"],
        )
        assert res["news"]["f1_macro"] == pytest.approx(1.0)

    def test_two_source_types_grouped_separately(self):
        tok = _FakeTokenizer()
        model = _make_fake_model(logit_value=5.0)
        lbl_a = np.zeros(N_FRAMES, dtype=int)
        lbl_a[0] = 1
        lbl_b = np.zeros(N_FRAMES, dtype=int)
        lbl_b[1] = 1
        res = tf._eval_per_source_type(
            model=model,
            tokenizer=tok,
            val_texts=[
                "news one long enough here now day",
                "news two long enough here now day",
                "blog only one long enough here now",
            ],
            val_labels_bin=[lbl_a, lbl_b, lbl_a],
            val_source_types=["news", "news", "blog"],
        )
        # news has 2 -> real F1; blog has 1 -> insufficient note.
        assert res["news"]["n"] == 2
        assert res["news"]["f1_macro"] is not None
        assert res["blog"]["f1_macro"] is None


# ---------------------------------------------------------------------------
# Binarisation sanity via FRAME2ID
# ---------------------------------------------------------------------------

def test_frame2id_indices_stable():
    assert FRAME2ID["economic"] == 0
    assert FRAME2ID["other"] == N_FRAMES - 1
    assert len(FRAME2ID) == N_FRAMES


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_default_orchestration(self, tmp_path, monkeypatch):
        out = tmp_path / "out"
        monkeypatch.setattr(
            sys, "argv", ["train_frames", "--output", str(out), "--epochs", "1"]
        )
        fake_examples = _frame_examples()
        captured = {}

        def fake_train(**kwargs):
            captured.update(kwargs)
            return {"eval_f1_macro": 0.8, "per_source_type": {"news": {"f1_macro": 0.7, "n": 4}}}

        with patch(
            "src.argument_mining.dataset.load_frame_dataset",
            return_value=fake_examples,
        ) as loader, patch.object(tf, "train", side_effect=fake_train):
            tf.main()

        loader.assert_called_once()
        assert captured["output_dir"] == out
        assert captured["epochs"] == 1
        assert captured["examples"] == fake_examples

    def test_main_target_met_logs_info(self, tmp_path, monkeypatch, caplog):
        import logging

        out = tmp_path / "out"
        monkeypatch.setattr(sys, "argv", ["train_frames", "--output", str(out)])
        with patch(
            "src.argument_mining.dataset.load_frame_dataset",
            return_value=_frame_examples(),
        ), patch.object(
            tf, "train",
            return_value={"eval_f1_macro": 0.90, "per_source_type": {}},
        ):
            with caplog.at_level(logging.INFO):
                tf.main()
        assert any("Target met" in r.message for r in caplog.records)

    def test_main_below_target_warns(self, tmp_path, monkeypatch, caplog):
        import logging

        out = tmp_path / "out"
        monkeypatch.setattr(sys, "argv", ["train_frames", "--output", str(out)])
        with patch(
            "src.argument_mining.dataset.load_frame_dataset",
            return_value=_frame_examples(),
        ), patch.object(
            tf, "train",
            return_value={"eval_f1_macro": 0.10, "per_source_type": {}},
        ):
            with caplog.at_level(logging.WARNING):
                tf.main()
        assert any("below the 0.75 target" in r.message for r in caplog.records)

    def test_main_passes_cli_hyperparams(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        out = tmp_path / "out"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "train_frames", "--data", str(data_dir), "--output", str(out),
                "--base-model", "bert-base-uncased", "--batch-size", "16",
                "--lr", "5e-5", "--epochs", "5",
            ],
        )
        with patch(
            "src.argument_mining.dataset.load_frame_dataset",
            return_value=_frame_examples(),
        ) as loader, patch.object(
            tf, "train",
            return_value={"eval_f1_macro": 0.9, "per_source_type": {}},
        ) as trn:
            tf.main()
        loader.assert_called_once_with(data_dir)
        kwargs = trn.call_args.kwargs
        assert kwargs["base_model"] == "bert-base-uncased"
        assert kwargs["batch_size"] == 16
        assert kwargs["lr"] == pytest.approx(5e-5)
        assert kwargs["epochs"] == 5


# ---------------------------------------------------------------------------
# Running the module as __main__ (covers the `if __name__ == "__main__"` guard)
# ---------------------------------------------------------------------------

def test_module_runs_as_main(tmp_path, monkeypatch):
    out = tmp_path / "o"
    monkeypatch.setattr(
        sys, "argv", ["prog", "--output", str(out), "--epochs", "1"]
    )
    tok = _FakeTokenizer()
    model = _make_fake_model(logit_value=5.0)
    trainer = MagicMock()
    trainer.model = model
    trainer.evaluate.return_value = {"eval_f1_macro": 0.9, "eval_f1_micro": 0.9}
    with patch(
        "src.argument_mining.dataset.load_frame_dataset",
        return_value=_frame_examples(),
    ), patch(
        "transformers.AutoTokenizer.from_pretrained", return_value=tok
    ), patch(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        return_value=model,
    ), patch(
        "transformers.TrainingArguments", MagicMock()
    ), patch(
        "transformers.Trainer", MagicMock(return_value=trainer)
    ):
        runpy.run_module("src.argument_mining.train_frames", run_name="__main__")
    assert (out / "label_map.json").exists()
    assert (out / "eval_metrics.json").exists()
