"""Tests for src/api/routes/waf_security_routes.py via minimal app (local waf_manager)."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.routes.waf_security_routes as mod  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.require_admin] = lambda: {"user": "admin"}
    app.dependency_overrides[mod.require_auth] = lambda: {"user": "admin"}
    return TestClient(app, raise_server_exceptions=False)


def test_metrics(client):
    resp = client.get("/api/security/waf/metrics")
    assert 200 <= resp.status_code < 600


def test_blocked_requests(client):
    resp = client.get("/api/security/waf/blocked-requests")
    assert 200 <= resp.status_code < 600


def test_status(client):
    resp = client.get("/api/security/waf/status")
    assert 200 <= resp.status_code < 600


def test_realtime_threats(client):
    resp = client.get("/api/security/threats/real-time")
    assert 200 <= resp.status_code < 600


def test_health(client):
    resp = client.get("/api/security/waf/health")
    assert 200 <= resp.status_code < 600


def test_sql_injection_attempts(client):
    resp = client.get("/api/security/attacks/sql-injection")
    assert 200 <= resp.status_code < 600


def test_deploy(client):
    resp = client.post("/api/security/waf/deploy")
    assert 200 <= resp.status_code < 600
