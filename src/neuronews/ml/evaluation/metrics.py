"""Evaluation metric helpers."""
from __future__ import annotations

from typing import Sequence


def compute_accuracy(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    assert len(y_true) == len(y_pred)
    if not y_true:
        return 0.0
    correct = sum(1 for a, b in zip(y_true, y_pred) if a == b)
    return correct / len(y_true)


def compute_precision(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    # Binary precision for class 1
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    if tp + fp == 0:
        return 0.0
    return tp / (tp + fp)
