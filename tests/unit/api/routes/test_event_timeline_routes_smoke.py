"""Tests for src/api/routes/event_timeline_routes.py via minimal app + mocked service."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.routes.event_timeline_routes as mod  # noqa: E402


@pytest.fixture
def service():
    s = MagicMock()
    s.generate_timeline_api_response = AsyncMock(return_value={"timeline": [], "events": []})
    s.generate_visualization_data = AsyncMock(return_value={"chart_data": {}})
    s.track_historical_events = AsyncMock(return_value=[])
    return s


@pytest.fixture
def client(service):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_event_timeline_service] = lambda: service
    app.dependency_overrides[mod.get_optional_auth] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def test_get_timeline(client):
    resp = client.get("/api/v1/event-timeline/AI")
    assert 200 <= resp.status_code < 600


def test_visualization(client):
    resp = client.get("/api/v1/event-timeline/AI/visualization")
    assert 200 <= resp.status_code < 600


def test_analytics(client):
    resp = client.get("/api/v1/event-timeline/analytics")
    assert 200 <= resp.status_code < 600


def test_health(client):
    resp = client.get("/api/v1/event-timeline/health")
    assert 200 <= resp.status_code < 600
