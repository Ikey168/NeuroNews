"""
Train the narrative frame classifier.

Fine-tunes distilbert-base-uncased for multi-label frame classification:
  economic / security / humanitarian / legal / political / scientific / other

Multi-label training uses BCEWithLogitsLoss + sigmoid output so a document can
carry more than one frame simultaneously.

Uses the labelled dataset from issue #109 when available; falls back to the
synthetic bootstrap set defined in dataset.py.

Usage:
    python -m src.argument_mining.train_frames
    python -m src.argument_mining.train_frames --data data/argument_mining --epochs 5
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_BASE_MODEL = "distilbert-base-uncased"
_DEFAULT_OUTPUT = Path("models/frame_classifier")


def _eval_per_source_type(
    model,
    tokenizer,
    val_texts: List[str],
    val_labels_bin: "np.ndarray",  # type: ignore[name-defined]
    val_source_types: List[str],
) -> Dict[str, dict]:
    """Run frame inference per source_type on the validation split."""
    import numpy as np
    from sklearn.metrics import f1_score
    import torch

    model.eval()
    by_type: dict = defaultdict(lambda: ([], []))
    for text, lbl, stype in zip(val_texts, val_labels_bin, val_source_types):
        by_type[stype][0].append(text)
        by_type[stype][1].append(lbl)

    per_type: Dict[str, dict] = {}
    for stype, (stexts, slabels) in sorted(by_type.items()):
        if len(stexts) < 2:
            per_type[stype] = {
                "f1_macro": None,
                "n": len(stexts),
                "note": "insufficient examples for reliable F1",
            }
            continue
        enc = tokenizer(stexts, truncation=True, max_length=128, padding=True, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits
        preds = (torch.sigmoid(logits).cpu().numpy() >= 0.5).astype(int)
        lbls_arr = np.stack(slabels)
        type_f1 = float(f1_score(lbls_arr, preds, average="macro"))
        per_type[stype] = {"f1_macro": type_f1, "n": len(stexts)}
        logger.info("  %-12s  F1-macro = %.4f  (n=%d)", stype, type_f1, len(stexts))

    return per_type


def train(
    examples: List[Tuple[str, str, List[str]]],
    output_dir: Path,
    base_model: str = _DEFAULT_BASE_MODEL,
    epochs: int = 3,
    batch_size: int = 8,
    lr: float = 2e-5,
) -> dict:
    """Fine-tune and save a frame classifier. Returns evaluation metrics."""
    import numpy as np
    import torch
    from sklearn.metrics import f1_score
    from sklearn.model_selection import train_test_split
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )
    from src.argument_mining.dataset import FRAME_LABELS, FRAME2ID

    texts = [e[0] for e in examples]
    source_types = [e[1] for e in examples]

    # Build binary label vectors
    def _to_bin(frames: List[str]) -> List[int]:
        v = [0] * len(FRAME_LABELS)
        for f in frames:
            if f in FRAME2ID:
                v[FRAME2ID[f]] = 1
        return v

    labels_bin = [_to_bin(e[2]) for e in examples]

    _split = train_test_split(
        texts, labels_bin, source_types,
        test_size=0.2, random_state=42,
    )
    train_texts: List[str] = list(_split[0])
    val_texts: List[str] = list(_split[1])
    train_labels = list(_split[2])
    val_labels = list(_split[3])
    val_source_types: List[str] = list(_split[5])
    logger.info(
        "Training set: %d examples  Validation: %d examples", len(train_texts), len(val_texts)
    )

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model,
        num_labels=len(FRAME_LABELS),
        problem_type="multi_label_classification",
    )

    def encode(batch_texts: List[str], batch_labels: List[List[int]]) -> dict:
        enc = tokenizer(batch_texts, truncation=True, max_length=128, padding=False)
        enc["labels"] = [list(map(float, l)) for l in batch_labels]
        return enc

    class _Dataset(torch.utils.data.Dataset):
        def __init__(self, enc: dict) -> None:
            self._enc = enc

        def __len__(self) -> int:
            return len(self._enc["input_ids"])

        def __getitem__(self, idx: int) -> dict:
            item = {k: torch.tensor(v[idx]) for k, v in self._enc.items() if k != "labels"}
            item["labels"] = torch.tensor(self._enc["labels"][idx], dtype=torch.float)
            return item

    train_ds = _Dataset(encode(train_texts, train_labels))
    val_ds = _Dataset(encode(val_texts, val_labels))

    def compute_metrics(eval_pred):
        logits, lbls = eval_pred
        preds = (1 / (1 + np.exp(-logits)) >= 0.5).astype(int)
        return {
            "f1_macro": f1_score(lbls, preds, average="macro"),
            "f1_micro": f1_score(lbls, preds, average="micro"),
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=lr,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        logging_steps=10,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
        compute_metrics=compute_metrics,
    )

    trainer.train()
    eval_result = trainer.evaluate()
    logger.info("Overall validation metrics: %s", eval_result)

    logger.info("Cross-format evaluation:")
    val_labels_arr = np.array(val_labels)
    per_type = _eval_per_source_type(
        model=trainer.model,
        tokenizer=tokenizer,
        val_texts=val_texts,
        val_labels_bin=val_labels_arr,
        val_source_types=val_source_types,
    )
    metrics: dict = {**eval_result, "per_source_type": per_type}

    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    (output_dir / "label_map.json").write_text(
        json.dumps({str(i): f for i, f in enumerate(FRAME_LABELS)}, indent=2)
    )
    (output_dir / "eval_metrics.json").write_text(json.dumps(metrics, indent=2))
    logger.info("Model saved to %s", output_dir)

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train narrative frame classifier")
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Directory containing frames.parquet from #109 dataset (optional)",
    )
    parser.add_argument(
        "--output", type=Path, default=_DEFAULT_OUTPUT,
        help="Output directory for the trained model",
    )
    parser.add_argument("--base-model", default=_DEFAULT_BASE_MODEL)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-5)
    args = parser.parse_args()

    from src.argument_mining.dataset import load_frame_dataset
    examples = load_frame_dataset(args.data)
    logger.info(
        "Loaded %d examples (%s)",
        len(examples),
        f"from {args.data}" if args.data else "synthetic bootstrap",
    )

    metrics = train(
        examples=examples,
        output_dir=args.output,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )

    f1 = metrics.get("eval_f1_macro", 0.0)
    if f1 >= 0.75:
        logger.info("Target met: F1-macro %.4f >= 0.75", f1)
    else:
        logger.warning(
            "F1-macro %.4f below the 0.75 target — collect more data from the #109 dataset",
            f1,
        )


if __name__ == "__main__":
    main()
