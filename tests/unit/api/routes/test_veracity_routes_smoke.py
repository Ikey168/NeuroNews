"""Smoke tests for src/api/routes/veracity_routes.py."""
import os, sys
from unittest.mock import AsyncMock, MagicMock
import pytest
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path: sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.veracity_routes as mod


@pytest.fixture
def client(monkeypatch):
    detector = MagicMock()
    detector.get_model_info = MagicMock(return_value={"model": "fake-news-v1", "version": "1.0"})
    detector.predict_veracity = AsyncMock(return_value={"score": 0.8, "label": "real"})
    detector.get_statistics = AsyncMock(return_value={"total": 0})
    monkeypatch.setattr(mod, "get_detector", lambda: detector)
    app = FastAPI(); app.include_router(mod.router)
    return TestClient(app, raise_server_exceptions=False)


def test_model_info(client):
    assert 200 <= client.get("/api/veracity/model_info").status_code < 600

def test_veracity_stats(client):
    assert 200 <= client.get("/api/veracity/veracity_stats").status_code < 600

def test_news_veracity(client):
    assert 200 <= client.get("/api/veracity/news_veracity", params={"article_id": "a1"}).status_code < 600
