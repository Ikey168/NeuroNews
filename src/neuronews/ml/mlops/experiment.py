"""Experiment tracking facade (MLflow-like, mock-friendly)."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Optional
import time


@dataclass
class RunInfo:
    run_id: str
    params: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None


class ExperimentTracker:
    """In-memory experiment tracker to decouple from external MLflow in tests."""

    def __init__(self, experiment_name: str):
        self.experiment_name = experiment_name
        self._runs: Dict[str, RunInfo] = {}

    @contextmanager
    def start_run(self, run_id: str):
        ri = RunInfo(run_id=run_id)
        self._runs[run_id] = ri
        try:
            yield ri
        finally:
            ri.end_time = time.time()

    def log_param(self, run_id: str, key: str, value: str):
        self._runs[run_id].params[key] = value

    def log_metric(self, run_id: str, key: str, value: float):
        self._runs[run_id].metrics[key] = value

    def log_artifact(self, run_id: str, path: str, name: str):
        self._runs[run_id].artifacts[name] = path

    def get_run(self, run_id: str) -> RunInfo:
        return self._runs[run_id]

    def list_runs(self):  # pragma: no cover - convenience
        return list(self._runs.values())
