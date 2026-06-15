"""Simplified training orchestration for tests."""
from __future__ import annotations

from typing import List, Dict, Any
from ..mlops.experiment import ExperimentTracker
from ..registry.registry import ModelRegistry


class SimpleTrainer:
    """Mock-friendly trainer that logs params/metrics and registers model."""

    def __init__(self, tracker: ExperimentTracker, registry: ModelRegistry):
        self.tracker = tracker
        self.registry = registry

    def train(self, run_id: str, data: List[Dict[str, Any]], epochs: int = 2):
        with self.tracker.start_run(run_id):
            self.tracker.log_param(run_id, "epochs", str(epochs))
            accuracy = 0.0
            for epoch in range(epochs):
                # Simulate improving accuracy
                accuracy = 0.5 + (epoch + 1) * 0.1
                self.tracker.log_metric(run_id, f"acc_epoch_{epoch+1}", accuracy)
            model_obj = {"weights": [1, 2, 3], "final_acc": accuracy}
            registered = self.registry.register("fake_news_detector", model_obj)
            return registered, accuracy
