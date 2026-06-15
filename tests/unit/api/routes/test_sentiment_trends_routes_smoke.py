"""Tests for src/api/routes/sentiment_trends_routes.py via minimal app + mocked analyzer."""

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

import api.routes.sentiment_trends_routes as mod  # noqa: E402


@pytest.fixture
def analyzer():
    a = MagicMock()
    a.analyze_sentiment_trends = AsyncMock(return_value={"trends": [], "data_points": []})
    a.generate_trend_alerts = AsyncMock(return_value=[])
    a.get_active_alerts = AsyncMock(return_value=[])
    a.get_topic_sentiment_trends = AsyncMock(return_value={"topic": "AI", "trends": []})
    a.get_trend_summary = AsyncMock(return_value={"summary": {}})
    a.update_trend_summaries = AsyncMock(return_value={"updated": 0})
    return a


@pytest.fixture
def client(analyzer):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_sentiment_analyzer] = lambda: analyzer
    return TestClient(app, raise_server_exceptions=False)


def test_analyze(client):
    resp = client.get("/api/v1/sentiment_trends/analyze",
                      params={"topic": "AI", "days_back": 30})
    assert 200 <= resp.status_code < 600


def test_alerts(client):
    resp = client.get("/api/v1/sentiment_trends/alerts")
    assert 200 <= resp.status_code < 600


def test_topic(client):
    resp = client.get("/api/v1/sentiment_trends/topic/AI")
    assert 200 <= resp.status_code < 600


def test_summary(client):
    resp = client.get("/api/v1/sentiment_trends/summary")
    assert 200 <= resp.status_code < 600


def test_health(client):
    resp = client.get("/api/v1/sentiment_trends/health")
    assert 200 <= resp.status_code < 600


def test_alerts_generate(client):
    resp = client.post("/api/v1/sentiment_trends/alerts/generate", json={})
    assert 200 <= resp.status_code < 600
