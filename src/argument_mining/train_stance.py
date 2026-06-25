"""
Train the stance classification model.

Fine-tunes distilbert-base-uncased for 4-class stance classification:
  supportive / critical / neutral / ambiguous

Topic context is prepended to each sentence as:
    "<topic> [SEP] <sentence>"

Uses the labelled dataset from issue #109 when available; falls back to the
synthetic bootstrap set defined in dataset.py.

Usage:
    python -m src.argument_mining.train_stance
    python -m src.argument_mining.train_stance --data data/argument_mining --epochs 5
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
_DEFAULT_OUTPUT = Path("models/stance_classifier")


def _eval_per_source_type(
    model,
    tokenizer,
    val_inputs: List[str],
    val_labels: List[int],
    val_source_types: List[str],
) -> Dict[str, dict]:
    """Run stance inference per source_type on the validation split."""
    from sklearn.metrics import f1_score
    from transformers import pipeline as hf_pipeline

    pipe = hf_pipeline(
        "text-classification",
        model=model,
        tokenizer=tokenizer,
        device=-1,
    )

    by_type: dict = defaultdict(lambda: ([], []))
    for inp, label, stype in zip(val_inputs, val_labels, val_source_types):
        by_type[stype][0].append(inp)
        by_type[stype][1].append(label)

    per_type: Dict[str, dict] = {}
    for stype, (stexts, slabels) in sorted(by_type.items()):
        if len(stexts) < 2 or len(set(slabels)) < 2:
            per_type[stype] = {
                "f1_macro": None,
                "n": len(stexts),
                "note": "insufficient examples for reliable F1",
            }
            continue
        raw = pipe(stexts, truncation=True, max_length=128, batch_size=16)
        preds = [int(p["label"].split("_")[1]) for p in raw]
        type_f1 = float(f1_score(slabels, preds, average="macro"))
        per_type[stype] = {"f1_macro": type_f1, "n": len(stexts)}
        logger.info("  %-12s  F1-macro = %.4f  (n=%d)", stype, type_f1, len(stexts))

    return per_type


def train(
    examples: List[Tuple[str, str, str, str]],
    output_dir: Path,
    base_model: str = _DEFAULT_BASE_MODEL,
    epochs: int = 3,
    batch_size: int = 8,
    lr: float = 2e-5,
) -> dict:
    """Fine-tune and save a stance classification model. Returns evaluation metrics."""
    import numpy as np
    import torch
    from sklearn.metrics import f1_score
    from sklearn.model_selection import train_test_split
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DataCollatorWithPadding,
        Trainer,
        TrainingArguments,
    )
    from src.argument_mining.dataset import STANCE2ID, STANCE_LABELS

    # Encode topic into the input: "<topic> [SEP] <text>"
    inputs = [f"{topic} [SEP] {text}" for text, topic, _, _ in examples]
    labels = [STANCE2ID[stance] for _, _, stance, _ in examples]
    source_types = [e[3] for e in examples]

    _split = train_test_split(
        inputs, labels, source_types,
        test_size=0.2, random_state=42, stratify=labels,
    )
    train_inputs: List[str] = list(_split[0])
    val_inputs: List[str] = list(_split[1])
    train_labels: List[int] = list(_split[2])
    val_labels: List[int] = list(_split[3])
    val_source_types: List[str] = list(_split[5])
    logger.info(
        "Training set: %d examples  Validation: %d examples", len(train_inputs), len(val_inputs)
    )

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model, num_labels=len(STANCE_LABELS)
    )

    def encode(batch_texts: List[str], batch_labels: List[int]) -> dict:
        enc = tokenizer(batch_texts, truncation=True, max_length=128, padding=False)
        enc["labels"] = batch_labels
        return enc

    class _Dataset(torch.utils.data.Dataset):
        def __init__(self, enc: dict) -> None:
            self._enc = enc

        def __len__(self) -> int:
            return len(self._enc["input_ids"])

        def __getitem__(self, idx: int) -> dict:
            return {k: torch.tensor(v[idx]) for k, v in self._enc.items()}

    train_ds = _Dataset(encode(train_inputs, train_labels))
    val_ds = _Dataset(encode(val_inputs, val_labels))

    def compute_metrics(eval_pred):
        logits, lbls = eval_pred
        preds = np.argmax(logits, axis=1)
        return {
            "f1_macro": f1_score(lbls, preds, average="macro"),
            "f1_weighted": f1_score(lbls, preds, average="weighted"),
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
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=compute_metrics,
    )

    trainer.train()
    eval_result = trainer.evaluate()
    logger.info("Overall validation metrics: %s", eval_result)

    logger.info("Cross-format evaluation:")
    per_type = _eval_per_source_type(
        model=trainer.model,
        tokenizer=tokenizer,
        val_inputs=val_inputs,
        val_labels=val_labels,
        val_source_types=val_source_types,
    )
    metrics: dict = {**eval_result, "per_source_type": per_type}

    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    (output_dir / "label_map.json").write_text(
        json.dumps({str(i): s for i, s in enumerate(STANCE_LABELS)}, indent=2)
    )
    (output_dir / "eval_metrics.json").write_text(json.dumps(metrics, indent=2))
    logger.info("Model saved to %s", output_dir)

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train stance classification model")
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Directory containing stance.parquet from #109 dataset (optional)",
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

    from src.argument_mining.dataset import load_stance_dataset
    examples = load_stance_dataset(args.data)
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

    overall_f1 = metrics.get("eval_f1_macro", 0.0)
    if overall_f1 >= 0.70:
        logger.info("Target met: F1-macro %.4f >= 0.70", overall_f1)
    else:
        logger.warning(
            "F1-macro %.4f below the 0.70 target — collect more data from the #109 dataset",
            overall_f1,
        )

    per_type = metrics.get("per_source_type", {})
    for stype, m in sorted(per_type.items()):
        f1 = m.get("f1_macro")
        if f1 is None:
            logger.warning("  %-12s  F1-macro unavailable — %s", stype, m.get("note", ""))
        else:
            logger.info("  %-12s  F1-macro %.4f", stype, f1)


if __name__ == "__main__":
    main()
