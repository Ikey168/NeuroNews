#!/usr/bin/env python3
"""Verify DoD requirements for the MLflow tracking helper.

This exercises a live MLflow tracking server (the ``mlrun`` context manager
logs a run and reads it back via ``MlflowClient``). It requires:
  * the ``mlflow`` package -- skipped if absent, and
  * a reachable MLflow tracking server -- skipped via a connectivity probe if
    genuinely unreachable (an external service is an absent dependency).
"""

import importlib.util
import os
import socket
import sys
from pathlib import Path

import pytest

# Repo root is two levels up: <repo>/tests/unit/<file>
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")

_HAS_MLFLOW = importlib.util.find_spec("mlflow") is not None


def _mlflow_server_available(uri: str) -> bool:
    """Probe the MLflow tracking server; report False if unreachable."""
    from urllib.parse import urlparse

    parsed = urlparse(uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        return sock.connect_ex((host, int(port))) == 0
    finally:
        sock.close()


@pytest.mark.skipif(not _HAS_MLFLOW, reason="MLflow tracking helper requires mlflow")
@pytest.mark.skipif(
    not _mlflow_server_available(TRACKING_URI),
    reason=f"MLflow tracking server not reachable at {TRACKING_URI}; DoD "
    "tracking test requires a live MLflow server",
)
def test_dod_requirements():
    """Standard tags, custom tag, params and metrics are recorded for a run."""
    from services.mlops.tracking import mlrun, setup_mlflow_env
    import mlflow
    from mlflow.tracking import MlflowClient

    setup_mlflow_env(TRACKING_URI, "dod-test")

    with mlrun("dod-test-run", tags={"test": "dod"}) as run:
        mlflow.log_param("test_param", "dod_value")
        mlflow.log_metric("test_metric", 0.95)

        client = MlflowClient()
        run_data = client.get_run(run.info.run_id)

        # Standard tags applied by the tracking helper.
        expected_tags = ["git.sha", "git.branch", "env", "hostname", "code_version"]
        missing_tags = [t for t in expected_tags if t not in run_data.data.tags]
        assert not missing_tags, f"Missing standard tags: {missing_tags}"

        # Custom tag passed through.
        assert run_data.data.tags.get("test") == "dod"

        # Parameter and metric recorded.
        assert "test_param" in run_data.data.params
        assert "test_metric" in run_data.data.metrics
