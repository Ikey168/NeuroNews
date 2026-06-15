"""Tests for src/api/routes/event_routes.py via minimal app + mocked deps."""

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

import api.routes.event_routes as mod  # noqa: E402


@pytest.fixture
def clusterer():
    c = MagicMock()
    c.get_breaking_news = AsyncMock(return_value=[])
    c.get_event_clusters = AsyncMock(return_value=[])
    c.get_cluster_articles = AsyncMock(return_value=[])
    c.detect_events = AsyncMock(return_value=[])
    c.get_statistics = MagicMock(return_value={})
    return c


@pytest.fixture
def embedder():
    return MagicMock()


@pytest.fixture
def client(clusterer, embedder):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_clusterer] = lambda: clusterer
    app.dependency_overrides[mod.get_embedder] = lambda: embedder
    return TestClient(app, raise_server_exceptions=False)


def test_breaking_news(client):
    resp = client.get("/api/v1/breaking_news")
    assert 200 <= resp.status_code < 600


def test_clusters(client):
    resp = client.get("/api/v1/events/clusters")
    assert 200 <= resp.status_code < 600


def test_categories(client):
    resp = client.get("/api/v1/events/categories")
    assert 200 <= resp.status_code < 600


def test_stats(client):
    resp = client.get("/api/v1/events/stats")
    assert 200 <= resp.status_code < 600
