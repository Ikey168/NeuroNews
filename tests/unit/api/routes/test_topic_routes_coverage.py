"""Coverage tests for src/api/routes/topic_routes.py.

Exercises every endpoint plus the uncovered exception/branch paths:
- get_keyword_topic_db dependency (success + 500 on connect failure)
- each endpoint success (200) and DB-error (500)
- advanced_search 400 (no params), success, and 500
- trending topics/keywords success (with filtering/sorting) + 500
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.topic_routes as mod


def _make_db():
    db = MagicMock()
    db.get_articles_by_topic = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
    db.get_articles_by_keyword = AsyncMock(return_value=[{"id": 3}])
    db.get_topic_statistics = AsyncMock(
        return_value=[{"topic": "AI", "article_count": 5}, {"topic": "ML", "article_count": 3}]
    )
    db.get_keyword_statistics = AsyncMock(
        return_value=[
            {"keyword": "gpu", "frequency": 20, "avg_score": 0.8},
            {"keyword": "llm", "frequency": 15, "avg_score": 0.9},
        ]
    )
    db.search_articles_by_content_and_topics = AsyncMock(
        return_value={"articles": [{"id": 9}], "total_count": 1}
    )
    return db


@pytest.fixture
def db():
    return _make_db()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_keyword_topic_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# get_keyword_topic_db dependency (real, un-overridden)
# --------------------------------------------------------------------------

def test_dependency_success_returns_db():
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app, raise_server_exceptions=False)
    fake_db = _make_db()
    with patch.object(mod, "create_keyword_topic_db", AsyncMock(return_value=fake_db)):
        resp = client.get("/topics/articles", params={"topic": "AI"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 2
    assert body["search_params"]["topic"] == "AI"


def test_dependency_connect_failure_returns_500():
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app, raise_server_exceptions=False)
    with patch.object(
        mod, "create_keyword_topic_db", AsyncMock(side_effect=RuntimeError("no db"))
    ):
        resp = client.get("/topics/articles", params={"topic": "AI"})
    assert resp.status_code == 500
    assert "Database connection error" in resp.json()["detail"]
    assert "no db" in resp.json()["detail"]


# --------------------------------------------------------------------------
# /topics/articles
# --------------------------------------------------------------------------

def test_articles_success(client, db):
    resp = client.get(
        "/topics/articles",
        params={"topic": "AI", "min_probability": 0.5, "limit": 10, "offset": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["articles"] == [{"id": 1}, {"id": 2}]
    assert body["total_count"] == 2
    assert body["has_more"] is False
    db.get_articles_by_topic.assert_awaited_once_with(
        topic_name="AI", min_probability=0.5, limit=10, offset=5
    )


def test_articles_missing_topic_422(client):
    resp = client.get("/topics/articles")
    assert resp.status_code == 422


def test_articles_bad_probability_422(client):
    resp = client.get("/topics/articles", params={"topic": "AI", "min_probability": 5})
    assert resp.status_code == 422


def test_articles_db_error_500(client, db):
    db.get_articles_by_topic.side_effect = ValueError("boom")
    resp = client.get("/topics/articles", params={"topic": "AI"})
    assert resp.status_code == 500
    assert "Error retrieving articles by topic" in resp.json()["detail"]


# --------------------------------------------------------------------------
# /topics/keywords/articles
# --------------------------------------------------------------------------

def test_keyword_articles_success(client, db):
    resp = client.get(
        "/topics/keywords/articles",
        params={"keyword": "gpu", "min_score": 0.3, "limit": 1, "offset": 0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    # limit == returned length -> has_more True
    assert body["has_more"] is True
    db.get_articles_by_keyword.assert_awaited_once_with(
        keyword="gpu", min_score=0.3, limit=1, offset=0
    )


def test_keyword_articles_missing_keyword_422(client):
    resp = client.get("/topics/keywords/articles")
    assert resp.status_code == 422


def test_keyword_articles_db_error_500(client, db):
    db.get_articles_by_keyword.side_effect = RuntimeError("kaboom")
    resp = client.get("/topics/keywords/articles", params={"keyword": "gpu"})
    assert resp.status_code == 500
    assert "Error retrieving articles by keyword" in resp.json()["detail"]


# --------------------------------------------------------------------------
# /topics/statistics
# --------------------------------------------------------------------------

def test_statistics_success(client, db):
    resp = client.get("/topics/statistics", params={"days": 14})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_topics"] == 2
    assert body["total_articles"] == 8  # 5 + 3
    assert body["analysis_period"]["days"] == 14


def test_statistics_bad_days_422(client):
    resp = client.get("/topics/statistics", params={"days": 0})
    assert resp.status_code == 422


def test_statistics_db_error_500(client, db):
    db.get_topic_statistics.side_effect = Exception("stat fail")
    resp = client.get("/topics/statistics")
    assert resp.status_code == 500
    assert "Error retrieving topic statistics" in resp.json()["detail"]


# --------------------------------------------------------------------------
# /topics/keywords/statistics
# --------------------------------------------------------------------------

def test_keyword_statistics_success(client, db):
    resp = client.get(
        "/topics/keywords/statistics", params={"days": 20, "min_frequency": 2}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_keywords"] == 2
    assert body["min_frequency"] == 2


def test_keyword_statistics_bad_min_frequency_422(client):
    resp = client.get("/topics/keywords/statistics", params={"min_frequency": 0})
    assert resp.status_code == 422


def test_keyword_statistics_db_error_500(client, db):
    db.get_keyword_statistics.side_effect = Exception("kw stat fail")
    resp = client.get("/topics/keywords/statistics")
    assert resp.status_code == 500
    assert "Error retrieving keyword statistics" in resp.json()["detail"]


# --------------------------------------------------------------------------
# /topics/search  (advanced_search)
# --------------------------------------------------------------------------

def test_advanced_search_no_params_400(client):
    resp = client.get("/topics/search")
    assert resp.status_code == 400
    assert "At least one search parameter" in resp.json()["detail"]


def test_advanced_search_success(client, db):
    resp = client.get(
        "/topics/search",
        params={"search_term": "regulation", "topic": "AI", "keyword": "llm"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"articles": [{"id": 9}], "total_count": 1}
    db.search_articles_by_content_and_topics.assert_awaited_once()


def test_advanced_search_db_error_500(client, db):
    db.search_articles_by_content_and_topics.side_effect = RuntimeError("search boom")
    resp = client.get("/topics/search", params={"topic": "AI"})
    assert resp.status_code == 500
    assert "Error performing advanced search" in resp.json()["detail"]


# --------------------------------------------------------------------------
# /topics/trending  (no db dependency; warehouse import inside func)
# --------------------------------------------------------------------------

def test_trending_topics_success_and_filter(client):
    topics = [
        {"topic": "AI", "article_count": 10, "avg_probability": 0.7},
        {"topic": "ML", "article_count": 8, "avg_probability": 0.9},
        {"topic": "rare", "article_count": 1, "avg_probability": 0.5},
    ]
    with patch(
        "src.database.local_warehouse_views.get_trending_topics",
        AsyncMock(return_value=topics),
    ):
        resp = client.get("/topics/trending", params={"days": 7, "min_articles": 5})
    assert resp.status_code == 200
    body = resp.json()
    # 'rare' (count 1 < 5) filtered out
    assert body["criteria"]["trending_topics_count"] == 2
    assert body["criteria"]["total_topics_found"] == 3
    # sorted by article_count desc -> AI (10) first
    assert body["trending_topics"][0]["topic"] == "AI"


def test_trending_topics_error_500(client):
    with patch(
        "src.database.local_warehouse_views.get_trending_topics",
        AsyncMock(side_effect=RuntimeError("warehouse down")),
    ):
        resp = client.get("/topics/trending")
    assert resp.status_code == 500
    assert "Error retrieving trending topics" in resp.json()["detail"]


def test_trending_topics_bad_days_422(client):
    resp = client.get("/topics/trending", params={"days": 999})
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# /topics/keywords/trending
# --------------------------------------------------------------------------

def test_trending_keywords_success(client, db):
    resp = client.get(
        "/topics/keywords/trending", params={"days": 7, "min_frequency": 5}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["criteria"]["min_frequency"] == 5
    assert body["criteria"]["total_keywords_found"] == 2
    # sorted by frequency desc -> gpu (20) first
    assert body["trending_keywords"][0]["keyword"] == "gpu"


def test_trending_keywords_error_500(client, db):
    db.get_keyword_statistics.side_effect = Exception("trend fail")
    resp = client.get("/topics/keywords/trending")
    assert resp.status_code == 500
    assert "Error retrieving trending keywords" in resp.json()["detail"]


def test_trending_keywords_bad_days_422(client):
    resp = client.get("/topics/keywords/trending", params={"days": 999})
    assert resp.status_code == 422
