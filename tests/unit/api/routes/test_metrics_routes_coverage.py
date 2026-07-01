"""Coverage tests for src/api/routes/metrics_routes.py.

Covers every endpoint plus _to_prometheus branches:
- GET /metrics json (200) + prometheus text (200, both label branches) + 500
- GET /metrics/summary (200) + 500
- GET /metrics/current (200) + 500
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.metrics_routes as mod


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(mod, "_get_conn", lambda: MagicMock(name="conn"))
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# _get_conn helper
# --------------------------------------------------------------------------

def test_get_conn_returns_shared_connection():
    sentinel = MagicMock(name="shared_conn")
    with patch(
        "src.database.local_analytics_connector.get_shared_connection",
        return_value=sentinel,
    ):
        assert mod._get_conn() is sentinel


# --------------------------------------------------------------------------
# _to_prometheus (unit) — exercises both label branches directly
# --------------------------------------------------------------------------

def test_to_prometheus_with_and_without_process_label():
    rows = [
        {
            "metric_name": "cpu_percent",
            "unit": "percent",
            "value": 42.0,
            "process_name": "python",
            "pid": 1234,
        },
        {
            "metric_name": "mem_bytes",
            "unit": "bytes",
            "value": 1000,
            "process_name": None,
            "pid": None,
        },
    ]
    text = mod._to_prometheus(rows)
    assert "# HELP neuronews_cpu_percent cpu_percent (percent)" in text
    assert "# TYPE neuronews_cpu_percent gauge" in text
    # process_name present -> labelled sample
    assert 'neuronews_cpu_percent{process="python",pid="1234"} 42.0' in text
    # process_name None -> no label braces
    assert "neuronews_mem_bytes 1000" in text
    assert text.endswith("\n")


# --------------------------------------------------------------------------
# GET /metrics
# --------------------------------------------------------------------------

def test_get_metrics_json_success(client):
    rows = [
        {"metric_name": "cpu_percent", "unit": "percent", "value": 12.5},
        {"metric_name": "cpu_percent", "unit": "percent", "value": 13.0},
    ]
    with patch("src.monitoring.resource_monitor.get_metrics", return_value=rows) as m:
        resp = client.get(
            "/metrics",
            params={"n": 50, "metric_name": "cpu_percent", "since_minutes": 10},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["metrics"] == rows
    _, kwargs = m.call_args
    assert kwargs["metric_name"] == "cpu_percent"
    assert kwargs["n"] == 50
    assert kwargs["since_minutes"] == 10


def test_get_metrics_prometheus_format(client):
    rows = [
        {
            "metric_name": "cpu_percent",
            "unit": "percent",
            "value": 42.0,
            "process_name": "python",
            "pid": 1234,
        }
    ]
    with patch("src.monitoring.resource_monitor.get_metrics", return_value=rows):
        resp = client.get("/metrics", params={"fmt": "prometheus"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "neuronews_cpu_percent" in resp.text
    assert 'process="python"' in resp.text


def test_get_metrics_bad_n_422(client):
    resp = client.get("/metrics", params={"n": 0})
    assert resp.status_code == 422


def test_get_metrics_error_500(client):
    with patch(
        "src.monitoring.resource_monitor.get_metrics",
        side_effect=RuntimeError("metrics boom"),
    ):
        resp = client.get("/metrics")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "metrics boom"


# --------------------------------------------------------------------------
# GET /metrics/summary
# --------------------------------------------------------------------------

def test_get_summary_success(client):
    summary = {
        "cpu_percent": {"1h_avg": 12.0, "24h_avg": 15.0, "min": 5.0, "max": 40.0}
    }
    with patch("src.monitoring.resource_monitor.get_summary", return_value=summary):
        resp = client.get("/metrics/summary")
    assert resp.status_code == 200
    assert resp.json() == summary


def test_get_summary_empty(client):
    with patch("src.monitoring.resource_monitor.get_summary", return_value={}):
        resp = client.get("/metrics/summary")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_get_summary_error_500(client):
    with patch(
        "src.monitoring.resource_monitor.get_summary",
        side_effect=RuntimeError("summary boom"),
    ):
        resp = client.get("/metrics/summary")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "summary boom"


# --------------------------------------------------------------------------
# GET /metrics/current
# --------------------------------------------------------------------------

def test_get_current_success(client):
    rows = [
        {"metric_name": "cpu_percent", "value": 33.3, "unit": "percent"},
        {"metric_name": "mem_bytes", "value": 2048, "unit": "bytes"},
    ]
    with patch(
        "src.monitoring.resource_monitor.collect_sample", return_value=rows
    ):
        resp = client.get("/metrics/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cpu_percent"] == {"value": 33.3, "unit": "percent"}
    assert body["mem_bytes"] == {"value": 2048, "unit": "bytes"}


def test_get_current_error_500(client):
    with patch(
        "src.monitoring.resource_monitor.collect_sample",
        side_effect=RuntimeError("current boom"),
    ):
        resp = client.get("/metrics/current")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "current boom"
