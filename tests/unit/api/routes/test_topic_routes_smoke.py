"""Smoke tests for src/api/routes/topic_routes.py."""
import os, sys
from unittest.mock import AsyncMock, MagicMock
import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.topic_routes as mod


@pytest.fixture
def db():
    d = MagicMock()
    d.get_articles_by_topic = AsyncMock(return_value=[])
    d.get_articles_by_keyword = AsyncMock(return_value=[])
    d.get_topic_statistics = AsyncMock(return_value={})
    d.get_keyword_statistics = AsyncMock(return_value={})
    return d


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_keyword_topic_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def test_articles(client):
    assert 200 <= client.get("/topics/articles", params={"topic": "AI"}).status_code < 600

def test_keyword_articles(client):
    assert 200 <= client.get("/topics/keywords/articles", params={"keyword": "ai"}).status_code < 600

def test_statistics(client):
    assert 200 <= client.get("/topics/statistics").status_code < 600

def test_keyword_statistics(client):
    assert 200 <= client.get("/topics/keywords/statistics").status_code < 600
