"""Coverage tests for src/api/routes/veracity_routes.py.

Mounts the router on a fresh app and monkeypatches the module-level
detector / connection helpers so the endpoint bodies and the
store_veracity_result / get_snowflake_connection / get_detector helpers all
execute. Targets the remaining uncovered lines beyond the smoke test.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.veracity_routes as mod


ANALYSIS = {
    "trustworthiness_score": 72.5,
    "classification": "real",
    "confidence": 88.0,
    "fake_probability": 12.0,
    "real_probability": 88.0,
    "model_used": "roberta-base",
}


def _client(monkeypatch, detector=None, store_result=True):
    if detector is None:
        detector = MagicMock()
        detector.model_name = "roberta-base"
        detector.predict_trustworthiness = MagicMock(return_value=ANALYSIS)
    monkeypatch.setattr(mod, "get_detector", lambda: detector)
    monkeypatch.setattr(
        mod, "store_veracity_result", lambda *a, **k: store_result
    )
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app, raise_server_exceptions=False)


# --- get_detector -------------------------------------------------------

def test_get_detector_initializes(monkeypatch):
    monkeypatch.setattr(mod, "_detector", None)
    fake = object()
    created = {}

    def fake_ctor(model_name):
        created["name"] = model_name
        return fake

    monkeypatch.setattr(mod, "FakeNewsDetector", fake_ctor)
    monkeypatch.setenv("FAKE_NEWS_MODEL", "custom-model")
    d = mod.get_detector()
    assert d is fake
    assert created["name"] == "custom-model"
    # Second call returns cached instance (no re-init)
    assert mod.get_detector() is fake


# --- get_snowflake_connection ------------------------------------------

def test_get_snowflake_connection_success(monkeypatch):
    import src.database.local_analytics_connector as lac

    sentinel = object()
    monkeypatch.setattr(lac, "get_shared_connection", lambda: sentinel)
    assert mod.get_snowflake_connection() is sentinel


def test_get_snowflake_connection_failure(monkeypatch):
    import src.database.local_analytics_connector as lac

    def boom():
        raise RuntimeError("no db")

    monkeypatch.setattr(lac, "get_shared_connection", boom)
    assert mod.get_snowflake_connection() is None


# --- store_veracity_result ---------------------------------------------

def test_store_veracity_result_with_conn():
    conn = MagicMock()
    conn.execute_query = MagicMock(return_value=None)
    ok = mod.store_veracity_result("a1", ANALYSIS, redshift_conn=conn)
    assert ok is True
    # create table + insert = two execute_query calls
    assert conn.execute_query.call_count == 2


def test_store_veracity_result_no_conn(monkeypatch):
    monkeypatch.setattr(mod, "get_snowflake_connection", lambda: None)
    assert mod.store_veracity_result("a1", ANALYSIS) is False


def test_store_veracity_result_uses_default_conn(monkeypatch):
    conn = MagicMock()
    conn.execute_query = MagicMock(return_value=None)
    monkeypatch.setattr(mod, "get_snowflake_connection", lambda: conn)
    assert mod.store_veracity_result("a1", ANALYSIS) is True


def test_store_veracity_result_exception():
    conn = MagicMock()
    conn.execute_query = MagicMock(side_effect=RuntimeError("insert failed"))
    assert mod.store_veracity_result("a1", ANALYSIS, redshift_conn=conn) is False


# --- /news_veracity -----------------------------------------------------

def test_news_veracity_success_analysis_source(monkeypatch):
    # store succeeds -> source == "analysis"
    client = _client(monkeypatch, store_result=True)
    resp = client.get(
        "/api/veracity/news_veracity",
        params={"article_id": "a1", "text": "some article text"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["article_id"] == "a1"
    assert body["status"] == "success"
    assert body["source"] == "analysis"
    assert body["veracity_analysis"]["classification"] == "real"


def test_news_veracity_cache_source(monkeypatch):
    # store fails -> source == "cache"
    client = _client(monkeypatch, store_result=False)
    resp = client.get(
        "/api/veracity/news_veracity",
        params={"article_id": "a2", "text": "text"},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "cache"


def test_news_veracity_error_500(monkeypatch):
    detector = MagicMock()
    detector.predict_trustworthiness = MagicMock(side_effect=RuntimeError("model boom"))
    client = _client(monkeypatch, detector=detector)
    resp = client.get(
        "/api/veracity/news_veracity",
        params={"article_id": "a3", "text": "text"},
    )
    assert resp.status_code == 500
    assert "Failed to analyze article veracity" in resp.json()["detail"]


# --- /batch_veracity ----------------------------------------------------

def test_batch_veracity_empty_400(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/api/veracity/batch_veracity", json={"articles": []})
    assert resp.status_code == 400
    assert resp.json()["error"] == "Articles list cannot be empty"


def test_batch_veracity_success(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(
        "/api/veracity/batch_veracity",
        json={
            "articles": [
                {"article_id": "b1", "text": "t1"},
                {"article_id": "b2", "text": "t2"},
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_processed"] == 2
    assert body["status"] == "success"
    assert all(r["status"] == "success" for r in body["results"])


def test_batch_veracity_per_article_error(monkeypatch):
    detector = MagicMock()
    detector.model_name = "roberta-base"

    def predict(text):
        if text == "bad":
            raise ValueError("bad article")
        return ANALYSIS

    detector.predict_trustworthiness = MagicMock(side_effect=predict)
    client = _client(monkeypatch, detector=detector)
    resp = client.post(
        "/api/veracity/batch_veracity",
        json={
            "articles": [
                {"article_id": "ok", "text": "good"},
                {"article_id": "err", "text": "bad"},
            ]
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    statuses = {r["article_id"]: r["status"] for r in results}
    assert statuses["ok"] == "success"
    assert statuses["err"] == "error"
    err_entry = next(r for r in results if r["article_id"] == "err")
    assert "bad article" in err_entry["error"]


def test_batch_veracity_outer_error_500(monkeypatch):
    # get_detector raising triggers the outer try/except -> 500
    def boom():
        raise RuntimeError("detector unavailable")

    monkeypatch.setattr(mod, "get_detector", boom)
    monkeypatch.setattr(mod, "store_veracity_result", lambda *a, **k: True)
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/veracity/batch_veracity",
        json={"articles": [{"article_id": "x", "text": "t"}]},
    )
    assert resp.status_code == 500
    assert "Failed to process batch veracity analysis" in resp.json()["detail"]


# --- /veracity_stats ----------------------------------------------------

def test_veracity_stats(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/api/veracity/veracity_stats", params={"days": 30})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["statistics"]["days_covered"] == 30
    assert body["statistics"]["total_analyzed"] == 1000


# --- /model_info --------------------------------------------------------

def test_model_info_roberta(monkeypatch):
    detector = MagicMock()
    detector.model_name = "roberta-base"
    client = _client(monkeypatch, detector=detector)
    resp = client.get("/api/veracity/model_info")
    assert resp.status_code == 200
    info = resp.json()["model_info"]
    assert info["architecture"] == "roberta"
    assert info["num_parameters"] == "125M"


def test_model_info_deberta_large(monkeypatch):
    detector = MagicMock()
    detector.model_name = "microsoft/deberta-large"
    client = _client(monkeypatch, detector=detector)
    resp = client.get("/api/veracity/model_info")
    assert resp.status_code == 200
    info = resp.json()["model_info"]
    assert info["architecture"] == "deberta"
    assert info["num_parameters"] == "355M"


def test_model_info_error_500(monkeypatch):
    def boom():
        raise RuntimeError("no model")

    monkeypatch.setattr(mod, "get_detector", boom)
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/veracity/model_info")
    assert resp.status_code == 500
    assert "Failed to retrieve model information" in resp.json()["detail"]
