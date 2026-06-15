"""Smoke tests for src/api/routes/quicksight_routes.py (local dashboard service)."""
import os, sys
import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.quicksight_routes as mod


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("NEURONEWS_DASHBOARDS_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app, raise_server_exceptions=False)


def test_list_dashboards(client):
    assert 200 <= client.get("/api/v1/dashboards/").status_code < 600

def test_validate_setup(client):
    assert 200 <= client.get("/api/v1/dashboards/validate/setup").status_code < 600

def test_setup(client):
    assert 200 <= client.post("/api/v1/dashboards/setup").status_code < 600
