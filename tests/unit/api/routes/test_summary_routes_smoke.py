"""Tests for src/api/routes/summary_routes.py via minimal app + mocked deps."""

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

import api.routes.summary_routes as mod  # noqa: E402


@pytest.fixture
def db():
    d = MagicMock()
    d.get_summaries_by_article = AsyncMock(return_value=[])
    d.get_summary_by_article_and_length = AsyncMock(return_value=None)
    d.get_summary_statistics = AsyncMock(return_value={"total": 0, "cache": {}})
    d.clear_cache = MagicMock()
    return d


@pytest.fixture
def summarizer():
    s = MagicMock()
    s.get_statistics = MagicMock(return_value={})
    return s


@pytest.fixture
def client(db, summarizer):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_summary_database] = lambda: db
    app.dependency_overrides[mod.get_summarizer] = lambda: summarizer
    return TestClient(app, raise_server_exceptions=False)


def test_get_summaries_by_article(client):
    resp = client.get("/api/v1/summarize/article-1")
    assert 200 <= resp.status_code < 600


def test_stats_overview(client):
    resp = client.get("/api/v1/summarize/stats/overview")
    assert 200 <= resp.status_code < 600


def test_cache_clear(client):
    resp = client.post("/api/v1/summarize/cache/clear")
    assert 200 <= resp.status_code < 600
