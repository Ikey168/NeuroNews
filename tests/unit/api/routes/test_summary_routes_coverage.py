"""Comprehensive coverage tests for src/api/routes/summary_routes.py.

Mounts the router on a fresh FastAPI app and overrides get_summary_database /
get_summarizer with mocks. Exercises every endpoint and branch: cache hit,
fresh generation, batch (success + partial failure), 404, 422 validation, and
500 fallbacks.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import src.api.routes.summary_routes as mod  # noqa: E402
from src.nlp.ai_summarizer import SummaryLength, SummarizationModel  # noqa: E402

LONG_TEXT = "word " * 60  # > 100 chars, satisfies min_length + validator


def make_stored_summary():
    """A DB-row-like object as returned by get_summary_by_article_and_length."""
    return SimpleNamespace(
        id=7,
        article_id="article-1",
        summary_text="A concise summary.",
        summary_length="medium",
        model_used="t5-small",
        confidence_score=0.9,
        processing_time=0.5,
        word_count=42,
        sentence_count=3,
        compression_ratio=0.25,
        created_at=SimpleNamespace(isoformat=lambda: "2024-01-01T00:00:00"),
    )


def make_generated_summary():
    """A freshly-generated Summary object from summarizer.summarize_article."""
    return SimpleNamespace(
        text="Freshly generated summary.",
        length=SummaryLength.MEDIUM,
        model=SummarizationModel.T5,
        confidence_score=0.8,
        processing_time=0.4,
        word_count=30,
        sentence_count=2,
        compression_ratio=0.3,
        created_at="2024-01-02T00:00:00",
    )


@pytest.fixture
def db():
    d = MagicMock()
    d.get_summary_by_article_and_length = AsyncMock(return_value=None)
    d.store_summary = AsyncMock(return_value=101)
    d.get_summaries_by_article = AsyncMock(return_value=[])
    d.delete_summaries_by_article = AsyncMock(return_value=0)
    d.get_summary_statistics = AsyncMock(
        return_value={
            "total": {
                "total_summaries": 5,
                "unique_articles": 3,
                "avg_confidence": 0.85,
                "avg_processing_time": 0.5,
                "avg_word_count": 40.0,
                "avg_compression_ratio": 0.3,
            },
            "cache": {"hit_rate": 0.7},
            "short": {"count": 2},
        }
    )
    d.clear_cache = MagicMock()
    return d


@pytest.fixture
def summarizer():
    s = MagicMock()
    s.summarize_article = AsyncMock(return_value=make_generated_summary())
    s.get_model_info = MagicMock(
        return_value={"metrics": {"calls": 3}, "device": "cpu"}
    )
    s.clear_cache = MagicMock()
    return s


@pytest.fixture
def client(db, summarizer):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_summary_database] = lambda: db
    app.dependency_overrides[mod.get_summarizer] = lambda: summarizer
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST / (generate_summary)
# ---------------------------------------------------------------------------
def test_generate_summary_fresh(client, db, summarizer):
    resp = client.post(
        "/api/v1/summarize/",
        json={"article_id": "article-1", "text": LONG_TEXT, "length": "medium"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["article_id"] == "article-1"
    assert body["summary_id"] == 101
    assert body["from_cache"] is False
    assert body["summary_text"] == "Freshly generated summary."
    summarizer.summarize_article.assert_awaited()
    db.store_summary.assert_awaited()


def test_generate_summary_cache_hit(client, db):
    db.get_summary_by_article_and_length.return_value = make_stored_summary()
    resp = client.post(
        "/api/v1/summarize/",
        json={"article_id": "article-1", "text": LONG_TEXT, "length": "medium"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["from_cache"] is True
    assert body["summary_id"] == 7
    assert body["summary_text"] == "A concise summary."


def test_generate_summary_force_regenerate_skips_cache(client, db, summarizer):
    db.get_summary_by_article_and_length.return_value = make_stored_summary()
    resp = client.post(
        "/api/v1/summarize/",
        json={
            "article_id": "article-1",
            "text": LONG_TEXT,
            "length": "medium",
            "force_regenerate": True,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["from_cache"] is False
    # Cache lookup must be skipped when force_regenerate is True
    db.get_summary_by_article_and_length.assert_not_awaited()
    summarizer.summarize_article.assert_awaited()


def test_generate_summary_validation_short_text(client):
    resp = client.post(
        "/api/v1/summarize/",
        json={"article_id": "a", "text": "too short"},
    )
    assert resp.status_code == 422


def test_generate_summary_internal_error(client, summarizer):
    summarizer.summarize_article.side_effect = RuntimeError("model exploded")
    resp = client.post(
        "/api/v1/summarize/",
        json={"article_id": "article-1", "text": LONG_TEXT},
    )
    assert resp.status_code == 500
    assert "Summarization failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /batch (generate_batch_summaries)
# ---------------------------------------------------------------------------
def test_batch_all_fresh(client):
    resp = client.post(
        "/api/v1/summarize/batch",
        json={
            "articles": [
                {"article_id": "a1", "text": LONG_TEXT, "length": "medium"},
                {"article_id": "a2", "text": LONG_TEXT, "length": "short"},
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_articles"] == 2
    assert body["successful"] == 2
    assert body["failed"] == 0
    assert len(body["results"]) == 2


def test_batch_cache_hit_branch(client, db):
    db.get_summary_by_article_and_length.return_value = make_stored_summary()
    resp = client.post(
        "/api/v1/summarize/batch",
        json={"articles": [{"article_id": "a1", "text": LONG_TEXT}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["successful"] == 1
    assert body["results"][0]["from_cache"] is True


def test_batch_partial_failure(client, summarizer):
    # First call succeeds, second raises -> one success, one failure
    summarizer.summarize_article.side_effect = [
        make_generated_summary(),
        RuntimeError("fail on second"),
    ]
    resp = client.post(
        "/api/v1/summarize/batch",
        json={
            "articles": [
                {"article_id": "a1", "text": LONG_TEXT},
                {"article_id": "a2", "text": LONG_TEXT},
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_articles"] == 2
    assert body["successful"] == 1
    assert body["failed"] == 1
    assert len(body["results"]) == 1


def test_batch_too_many_articles(client):
    articles = [{"article_id": f"a{i}", "text": LONG_TEXT} for i in range(11)]
    resp = client.post("/api/v1/summarize/batch", json={"articles": articles})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /{article_id} (get_article_summaries)
# ---------------------------------------------------------------------------
def test_get_article_summaries_success(client, db):
    db.get_summaries_by_article.return_value = [make_stored_summary()]
    resp = client.get("/api/v1/summarize/article-1")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["article_id"] == "article-1"
    assert body[0]["from_cache"] is True


def test_get_article_summaries_not_found(client, db):
    db.get_summaries_by_article.return_value = []
    resp = client.get("/api/v1/summarize/missing")
    assert resp.status_code == 404
    assert "No summaries found" in resp.json()["detail"]


def test_get_article_summaries_internal_error(client, db):
    db.get_summaries_by_article.side_effect = RuntimeError("db down")
    resp = client.get("/api/v1/summarize/article-1")
    assert resp.status_code == 500
    assert "Failed to retrieve summaries" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /{article_id}/{length} (get_specific_summary)
# ---------------------------------------------------------------------------
def test_get_specific_summary_success(client, db):
    db.get_summary_by_article_and_length.return_value = make_stored_summary()
    resp = client.get("/api/v1/summarize/article-1/medium")
    assert resp.status_code == 200
    body = resp.json()
    assert body["article_id"] == "article-1"
    assert body["length"] == "medium"


def test_get_specific_summary_not_found(client, db):
    db.get_summary_by_article_and_length.return_value = None
    resp = client.get("/api/v1/summarize/article-1/short")
    assert resp.status_code == 404
    assert "No short summary found" in resp.json()["detail"]


def test_get_specific_summary_invalid_length(client):
    # length is a SummaryLength enum path param -> invalid value -> 422
    resp = client.get("/api/v1/summarize/article-1/enormous")
    assert resp.status_code == 422


def test_get_specific_summary_internal_error(client, db):
    db.get_summary_by_article_and_length.side_effect = RuntimeError("db down")
    resp = client.get("/api/v1/summarize/article-1/long")
    assert resp.status_code == 500
    assert "Failed to retrieve summary" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /{article_id} (delete_article_summaries)
# ---------------------------------------------------------------------------
def test_delete_summaries_success(client, db):
    db.delete_summaries_by_article.return_value = 4
    resp = client.delete("/api/v1/summarize/article-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted_count"] == 4
    assert body["article_id"] == "article-1"


def test_delete_summaries_not_found(client, db):
    db.delete_summaries_by_article.return_value = 0
    resp = client.delete("/api/v1/summarize/missing")
    assert resp.status_code == 404
    assert "No summaries found" in resp.json()["detail"]


def test_delete_summaries_internal_error(client, db):
    db.delete_summaries_by_article.side_effect = RuntimeError("db down")
    resp = client.delete("/api/v1/summarize/article-1")
    assert resp.status_code == 500
    assert "Failed to delete summaries" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Route-shadowing note (genuine source ordering bug):
# The parameterized routes GET /{article_id} and GET /{article_id}/{length}
# are declared BEFORE the static routes /stats/overview, /models/info and
# /health.  As a result the static routes are UNREACHABLE through the mounted
# router: /health -> matches /{article_id}, and /stats/overview & /models/info
# -> match /{article_id}/{length} (invalid SummaryLength -> 422).
# The tests below (a) assert the real shadowed behavior via the full router,
# and (b) invoke the handler coroutines directly so their bodies are covered
# with real assertions on the returned data.
# ---------------------------------------------------------------------------
def _run(coro):
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# GET /stats/overview (get_summarization_statistics) -- shadowed by /{a}/{len}
# ---------------------------------------------------------------------------
def test_statistics_route_is_shadowed(client):
    # "overview" is not a valid SummaryLength -> 422 from /{article_id}/{length}
    resp = client.get("/api/v1/summarize/stats/overview")
    assert resp.status_code == 422


def test_statistics_success(db, summarizer):
    result = _run(mod.get_summarization_statistics(db=db, summarizer=summarizer))
    assert result.total_summaries == 5
    assert result.unique_articles == 3
    # by_length excludes "total" and "cache"
    assert "short" in result.by_length
    assert "total" not in result.by_length
    assert result.cache_stats["summarizer_metrics"] == {"calls": 3}


def test_statistics_internal_error(db, summarizer):
    from fastapi import HTTPException

    db.get_summary_statistics.side_effect = RuntimeError("stats down")
    with pytest.raises(HTTPException) as exc:
        _run(mod.get_summarization_statistics(db=db, summarizer=summarizer))
    assert exc.value.status_code == 500
    assert "Failed to retrieve statistics" in exc.value.detail


# ---------------------------------------------------------------------------
# POST /cache/clear (clear_caches)
# ---------------------------------------------------------------------------
def test_clear_caches_success(client, db, summarizer):
    resp = client.post("/api/v1/summarize/cache/clear")
    assert resp.status_code == 200
    assert "cleared successfully" in resp.json()["message"]
    db.clear_cache.assert_called_once()
    summarizer.clear_cache.assert_called_once()


def test_clear_caches_internal_error(client, db):
    db.clear_cache.side_effect = RuntimeError("cache broke")
    resp = client.post("/api/v1/summarize/cache/clear")
    assert resp.status_code == 500
    assert "Failed to clear caches" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /models/info (get_model_information) -- shadowed by /{a}/{len}
# ---------------------------------------------------------------------------
def test_model_information_route_is_shadowed(client):
    # "info" is not a valid SummaryLength -> 422 from /{article_id}/{length}
    resp = client.get("/api/v1/summarize/models/info")
    assert resp.status_code == 422


def test_model_information_success(summarizer):
    result = _run(mod.get_model_information(summarizer=summarizer))
    assert "facebook/bart-large-cnn" in result["available_models"]
    assert "medium" in result["available_lengths"]
    assert result["device"] == "cpu"


def test_model_information_internal_error(summarizer):
    from fastapi import HTTPException

    summarizer.get_model_info.side_effect = RuntimeError("no model")
    with pytest.raises(HTTPException) as exc:
        _run(mod.get_model_information(summarizer=summarizer))
    assert exc.value.status_code == 500
    assert "Failed to retrieve model information" in exc.value.detail


# ---------------------------------------------------------------------------
# GET /health (health_check) -- shadowed by /{article_id}
# ---------------------------------------------------------------------------
def test_health_route_is_shadowed(client, db):
    # /health matches /{article_id} (article_id="health"); no summaries -> 404
    db.get_summaries_by_article.return_value = []
    resp = client.get("/api/v1/summarize/health")
    assert resp.status_code == 404


def test_health_check_handler():
    result = _run(mod.health_check())
    assert result["status"] == "healthy"
    assert result["service"] == "AI Article Summarization"
    assert "timestamp" in result


# ---------------------------------------------------------------------------
# Dependency getters (get_summarizer / get_summary_database)
# ---------------------------------------------------------------------------
def test_get_summarizer_lazy_init(monkeypatch):
    import asyncio

    monkeypatch.setattr(mod, "_summarizer", None)
    fake = object()
    monkeypatch.setattr(mod, "AIArticleSummarizer", lambda: fake)
    result = asyncio.get_event_loop().run_until_complete(mod.get_summarizer())
    assert result is fake
    # second call returns the cached instance
    result2 = asyncio.get_event_loop().run_until_complete(mod.get_summarizer())
    assert result2 is fake


def test_get_summary_database_lazy_init(monkeypatch):
    import asyncio

    monkeypatch.setattr(mod, "_summary_db", None)
    fake_db = MagicMock()
    fake_db.create_table = AsyncMock()
    monkeypatch.setattr(mod, "SummaryDatabase", lambda params: fake_db)
    monkeypatch.setattr(mod, "get_duckdb_path", lambda: "/tmp/x.duckdb")
    result = asyncio.get_event_loop().run_until_complete(
        mod.get_summary_database()
    )
    assert result is fake_db
    fake_db.create_table.assert_awaited()
