"""Coverage tests for src/api/routes/source_comparison_routes.py.

Covers every endpoint and branch:
- GET /compare_sources success (200) + 500 + 422 (missing topic)
- GET /sources/trustworthiness success (200) + invalid date_range (422)
  + backend error (500)
- GET /sources/{source}/profile success (200) + 500
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

import src.api.routes.source_comparison_routes as mod


@pytest.fixture
def client(monkeypatch):
    # Every endpoint calls _get_conn(); return a harmless stand-in so no real
    # DuckDB connection is opened.
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
# GET /compare_sources
# --------------------------------------------------------------------------

def test_compare_sources_success(client):
    payload = {
        "topic": "AI Regulation",
        "sources": [{"source": "Reuters", "article_count": 12}],
        "summary": {"total_articles": 12},
    }
    with patch(
        "src.nlp.source_comparator.compare_sources", return_value=payload
    ) as m:
        resp = client.get(
            "/compare_sources",
            params={"topic": "AI Regulation", "limit": 5, "days": 30},
        )
    assert resp.status_code == 200
    assert resp.json() == payload
    _, kwargs = m.call_args
    assert kwargs["topic"] == "AI Regulation"
    assert kwargs["limit"] == 5
    assert kwargs["days"] == 30


def test_compare_sources_missing_topic_422(client):
    resp = client.get("/compare_sources")
    assert resp.status_code == 422


def test_compare_sources_empty_topic_422(client):
    # topic has min_length=1
    resp = client.get("/compare_sources", params={"topic": ""})
    assert resp.status_code == 422


def test_compare_sources_bad_limit_422(client):
    resp = client.get("/compare_sources", params={"topic": "AI", "limit": 999})
    assert resp.status_code == 422


def test_compare_sources_backend_error_500(client):
    with patch(
        "src.nlp.source_comparator.compare_sources",
        side_effect=RuntimeError("comparator boom"),
    ):
        resp = client.get("/compare_sources", params={"topic": "AI"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "comparator boom"


# --------------------------------------------------------------------------
# GET /sources/trustworthiness
# --------------------------------------------------------------------------

def test_trustworthiness_success(client):
    rows = [
        {"source": "Reuters", "composite_score": 0.82},
        {"source": "BBC", "composite_score": 0.79},
    ]
    with patch(
        "src.nlp.source_comparator.list_source_trustworthiness", return_value=rows
    ) as m:
        resp = client.get(
            "/sources/trustworthiness",
            params={"source_type": "news", "date_range": "90d"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["date_range"] == "90d"
    assert body["sources"] == rows
    _, kwargs = m.call_args
    assert kwargs["source_type"] == "news"
    assert kwargs["date_range"] == "90d"


def test_trustworthiness_default_range(client):
    with patch(
        "src.nlp.source_comparator.list_source_trustworthiness", return_value=[]
    ):
        resp = client.get("/sources/trustworthiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["date_range"] == "30d"


def test_trustworthiness_invalid_range_422(client):
    resp = client.get(
        "/sources/trustworthiness", params={"date_range": "7d"}
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "date_range must be one of" in detail


def test_trustworthiness_backend_error_500(client):
    with patch(
        "src.nlp.source_comparator.list_source_trustworthiness",
        side_effect=RuntimeError("trust boom"),
    ):
        resp = client.get(
            "/sources/trustworthiness", params={"date_range": "all"}
        )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "trust boom"


# --------------------------------------------------------------------------
# GET /sources/{source}/profile
# --------------------------------------------------------------------------

def test_source_profile_success(client):
    profile = {
        "source": "Reuters",
        "article_count": 100,
        "avg_sentiment": 0.1,
        "cluster": "center",
    }
    with patch(
        "src.nlp.source_comparator.get_source_profile", return_value=profile
    ) as m:
        resp = client.get("/sources/Reuters/profile")
    assert resp.status_code == 200
    assert resp.json() == profile
    _, kwargs = m.call_args
    assert kwargs["source"] == "Reuters"


def test_source_profile_backend_error_500(client):
    with patch(
        "src.nlp.source_comparator.get_source_profile",
        side_effect=RuntimeError("profile boom"),
    ):
        resp = client.get("/sources/Unknown/profile")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "profile boom"
