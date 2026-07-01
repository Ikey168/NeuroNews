"""Coverage tests for src/api/routes/report_routes.py.

Mounts the report router on a fresh FastAPI app and drives every endpoint via
TestClient(raise_server_exceptions=False). The endpoints import their report /
subscription helpers *inside* the handler bodies, so we patch those helpers on
their source modules (where they are looked up at call time).

Subscription CRUD is exercised against a REAL in-memory DuckDB by patching the
connector used inside src.reports.subscriptions.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import types
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The report modules themselves are lightweight (fastapi/pydantic/duckdb only).
import src.reports.generate_report as gr
import src.reports.subscriptions as subsmod


def _load_report_routes():
    """Load report_routes.py WITHOUT executing src/api/routes/__init__.py.

    The routes package __init__ eagerly imports many sibling route modules that
    pull in torch. torch + coverage's C tracer segfault during GC in this
    environment (the repo's other route smoke tests hit the same crash under
    ``--cov``). Loading the single module file with lightweight stub parent
    packages keeps torch out of the process, so coverage runs cleanly.
    """
    name = "src.api.routes.report_routes"
    if name in sys.modules:
        return sys.modules[name]
    for pkg in ("src", "src.api", "src.api.routes"):
        if pkg not in sys.modules:
            stub = types.ModuleType(pkg)
            stub.__path__ = []  # mark as package
            sys.modules[pkg] = stub
    spec = importlib.util.spec_from_file_location(
        name, "/home/user/Noesis/src/api/routes/report_routes.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


routes = _load_report_routes()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def duck_subs(monkeypatch):
    """Back src.reports.subscriptions with a real in-memory DuckDB."""
    import duckdb

    conn = duckdb.connect(":memory:")
    lock = threading.Lock()
    monkeypatch.setattr(subsmod, "get_shared_connection", lambda: conn)
    monkeypatch.setattr(subsmod, "_LOCK", lock)
    monkeypatch.setattr(subsmod, "_schema_done", False)
    monkeypatch.setattr(subsmod, "_custom_schema_done", False)
    yield conn
    conn.close()


def _report_data(topic="Nvidia", period="last_7_days"):
    return gr.ReportData(
        topic=topic,
        period=period,
        generated_at="2026-01-01 00:00 UTC",
        total_articles=2,
        avg_sentiment=0.15,
        positive_pct=50.0,
        negative_pct=50.0,
        neutral_pct=0.0,
        top_sources=["Reuters"],
        articles=[
            gr.ArticleRow("a1", "Nvidia up", "http://x/1", "Reuters",
                          "Technology", "2026-01-01 00:00", "positive", 0.8),
            gr.ArticleRow("a2", "Nvidia down", "http://x/2", "Bloomberg",
                          "Business", "2026-01-02 00:00", "negative", -0.5),
        ],
    )


# ---------------------------------------------------------------------------
# GET /generate
# ---------------------------------------------------------------------------

def test_generate_json_success(client, monkeypatch):
    monkeypatch.setattr(gr, "_fetch_report_data", lambda t, p: _report_data(t, p))
    resp = client.get("/api/v1/reports/generate", params={"topic": "Nvidia"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == "Nvidia"
    assert body["stats"]["total_articles"] == 2
    assert body["stats"]["top_sources"] == ["Reuters"]
    assert len(body["articles"]) == 2
    assert body["articles"][0]["article_id"] == "a1"


def test_generate_csv_success(client, monkeypatch):
    monkeypatch.setattr(gr, "generate_csv", lambda t, p: b"article_id,title\r\na1,Nvidia up\r\n")
    resp = client.get(
        "/api/v1/reports/generate",
        params={"topic": "Nvidia", "format": "csv"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "report_nvidia_last_7_days.csv" in resp.headers["content-disposition"]
    assert b"article_id" in resp.content


def test_generate_pdf_success(client, monkeypatch):
    monkeypatch.setattr(gr, "generate_pdf", lambda t, p: b"%PDF-1.4 body")
    resp = client.get(
        "/api/v1/reports/generate",
        params={"topic": "Nvidia", "format": "pdf"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == b"%PDF-1.4 body"


def test_generate_invalid_period(client):
    resp = client.get(
        "/api/v1/reports/generate",
        params={"topic": "Nvidia", "period": "bogus"},
    )
    assert resp.status_code == 422
    assert "Invalid period" in resp.json()["detail"]


def test_generate_invalid_format(client):
    resp = client.get(
        "/api/v1/reports/generate",
        params={"topic": "Nvidia", "format": "xml"},
    )
    assert resp.status_code == 422
    assert "Invalid format" in resp.json()["detail"]


def test_generate_missing_topic(client):
    # topic is required with min_length=1 -> FastAPI validation 422
    resp = client.get("/api/v1/reports/generate")
    assert resp.status_code == 422


def test_generate_value_error_mapped_422(client, monkeypatch):
    def boom(t, p):
        raise ValueError("bad period internal")
    monkeypatch.setattr(gr, "_fetch_report_data", boom)
    resp = client.get("/api/v1/reports/generate", params={"topic": "Nvidia"})
    assert resp.status_code == 422
    assert "bad period internal" in resp.json()["detail"]


def test_generate_runtime_error_mapped_500(client, monkeypatch):
    def boom(t, p):
        raise RuntimeError("fpdf2 is required")
    monkeypatch.setattr(gr, "generate_pdf", boom)
    resp = client.get(
        "/api/v1/reports/generate",
        params={"topic": "Nvidia", "format": "pdf"},
    )
    assert resp.status_code == 500
    assert "fpdf2 is required" in resp.json()["detail"]


def test_generate_generic_exception_mapped_500(client, monkeypatch):
    def boom(t, p):
        raise KeyError("weird")
    monkeypatch.setattr(gr, "_fetch_report_data", boom)
    resp = client.get("/api/v1/reports/generate", params={"topic": "Nvidia"})
    assert resp.status_code == 500
    assert "Report generation failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /subscribe + subscription CRUD (real DuckDB)
# ---------------------------------------------------------------------------

def test_subscribe_success(client, duck_subs):
    resp = client.post(
        "/api/v1/reports/subscribe",
        json={"email": "a@ex.com", "topic": "Nvidia", "frequency": "weekly", "format": "pdf"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "created"
    assert body["subscription"]["email"] == "a@ex.com"
    assert body["subscription"]["id"]


def test_subscribe_defaults(client, duck_subs):
    resp = client.post(
        "/api/v1/reports/subscribe",
        json={"email": "b@ex.com", "topic": "Tesla"},
    )
    assert resp.status_code == 201
    sub = resp.json()["subscription"]
    assert sub["frequency"] == "weekly"
    assert sub["format"] == "pdf"


def test_subscribe_invalid_frequency(client, duck_subs):
    resp = client.post(
        "/api/v1/reports/subscribe",
        json={"email": "a@ex.com", "topic": "Nvidia", "frequency": "daily"},
    )
    assert resp.status_code == 422  # pydantic validator


def test_subscribe_invalid_format(client, duck_subs):
    resp = client.post(
        "/api/v1/reports/subscribe",
        json={"email": "a@ex.com", "topic": "Nvidia", "format": "html"},
    )
    assert resp.status_code == 422


def test_subscribe_internal_error_500(client, monkeypatch):
    monkeypatch.setattr(
        subsmod, "create_subscription",
        MagicMock(side_effect=RuntimeError("db down")),
    )
    resp = client.post(
        "/api/v1/reports/subscribe",
        json={"email": "a@ex.com", "topic": "Nvidia"},
    )
    assert resp.status_code == 500
    assert "db down" in resp.json()["detail"]


def test_list_subscriptions_all_and_filtered(client, duck_subs):
    client.post("/api/v1/reports/subscribe",
                json={"email": "a@ex.com", "topic": "Nvidia"})
    client.post("/api/v1/reports/subscribe",
                json={"email": "b@ex.com", "topic": "Tesla"})

    resp = client.get("/api/v1/reports/subscriptions")
    assert resp.status_code == 200
    assert len(resp.json()["subscriptions"]) == 2

    resp2 = client.get("/api/v1/reports/subscriptions", params={"email": "a@ex.com"})
    assert len(resp2.json()["subscriptions"]) == 1


def test_list_subscriptions_error_500(client, monkeypatch):
    monkeypatch.setattr(
        subsmod, "list_subscriptions",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    resp = client.get("/api/v1/reports/subscriptions")
    assert resp.status_code == 500


def test_get_subscription_success_with_stats(client, duck_subs):
    created = client.post(
        "/api/v1/reports/subscribe",
        json={"email": "a@ex.com", "topic": "Nvidia"},
    ).json()["subscription"]
    resp = client.get(f"/api/v1/reports/subscriptions/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subscription"]["id"] == created["id"]
    assert body["delivery_stats"]["total_sent"] == 0


def test_get_subscription_not_found(client, duck_subs):
    resp = client.get("/api/v1/reports/subscriptions/deadbeef")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_get_subscription_error_500(client, monkeypatch):
    monkeypatch.setattr(
        subsmod, "get_subscription",
        MagicMock(side_effect=RuntimeError("kaboom")),
    )
    resp = client.get("/api/v1/reports/subscriptions/x1")
    assert resp.status_code == 500


def test_unsubscribe_success(client, duck_subs):
    created = client.post(
        "/api/v1/reports/subscribe",
        json={"email": "a@ex.com", "topic": "Nvidia"},
    ).json()["subscription"]
    resp = client.delete(f"/api/v1/reports/subscriptions/{created['id']}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "id": created["id"]}
    # now gone
    assert client.get(
        f"/api/v1/reports/subscriptions/{created['id']}"
    ).status_code == 404


def test_unsubscribe_not_found(client, duck_subs):
    resp = client.delete("/api/v1/reports/subscriptions/nope")
    assert resp.status_code == 404


def test_unsubscribe_error_500(client, monkeypatch):
    monkeypatch.setattr(
        subsmod, "get_subscription",
        MagicMock(side_effect=RuntimeError("explode")),
    )
    resp = client.delete("/api/v1/reports/subscriptions/x1")
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /trigger/{frequency}
# ---------------------------------------------------------------------------

def test_trigger_success(client, monkeypatch):
    import src.reports.scheduler as sched
    monkeypatch.setattr(sched, "trigger_now", lambda freq: 3)
    resp = client.post("/api/v1/reports/trigger/weekly")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "triggered"
    assert body["frequency"] == "weekly"
    assert body["subscriptions_processed"] == 3


def test_trigger_invalid_frequency(client):
    resp = client.post("/api/v1/reports/trigger/hourly")
    assert resp.status_code == 422
    assert "frequency must be one of" in resp.json()["detail"]


def test_trigger_error_500(client, monkeypatch):
    import src.reports.scheduler as sched
    monkeypatch.setattr(
        sched, "trigger_now",
        MagicMock(side_effect=RuntimeError("scheduler down")),
    )
    resp = client.post("/api/v1/reports/trigger/monthly")
    assert resp.status_code == 500
    assert "scheduler down" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /custom_report
# ---------------------------------------------------------------------------

def test_custom_report_json_success(client, monkeypatch):
    monkeypatch.setattr(
        gr, "fetch_custom_report_data",
        lambda f: _report_data(topic="Custom", period="last_7_days"),
    )
    resp = client.get(
        "/api/v1/reports/custom_report",
        params={"entity": "Tesla", "keywords": "chip, gpu", "date_range": "last_7_days"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == "Custom"
    assert body["filters_applied"]["keywords"] == ["Tesla", "chip", "gpu"]
    assert body["stats"]["total_articles"] == 2
    assert len(body["articles"]) == 2


def test_custom_report_csv(client, monkeypatch):
    monkeypatch.setattr(gr, "generate_custom_csv", lambda f: b"article_id,title\r\n")
    resp = client.get(
        "/api/v1/reports/custom_report",
        params={"entity": "Tesla", "format": "csv"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "custom_report_tesla.csv" in resp.headers["content-disposition"]


def test_custom_report_pdf(client, monkeypatch):
    monkeypatch.setattr(gr, "generate_custom_pdf", lambda f: b"%PDF-1.4 custom")
    resp = client.get(
        "/api/v1/reports/custom_report",
        params={"entity": "Tesla", "keywords": "gpu", "format": "pdf"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "custom_report_tesla_gpu.pdf" in resp.headers["content-disposition"]


def test_custom_report_no_keywords(client):
    resp = client.get("/api/v1/reports/custom_report")
    assert resp.status_code == 422
    assert "at least one" in resp.json()["detail"].lower()


def test_custom_report_invalid_date_range(client):
    resp = client.get(
        "/api/v1/reports/custom_report",
        params={"entity": "Tesla", "date_range": "last_year"},
    )
    assert resp.status_code == 422
    assert "Invalid date_range" in resp.json()["detail"]


def test_custom_report_invalid_sentiment(client):
    resp = client.get(
        "/api/v1/reports/custom_report",
        params={"entity": "Tesla", "sentiment": "angry"},
    )
    assert resp.status_code == 422
    assert "Invalid sentiment" in resp.json()["detail"]


def test_custom_report_invalid_format(client):
    resp = client.get(
        "/api/v1/reports/custom_report",
        params={"entity": "Tesla", "format": "xml"},
    )
    assert resp.status_code == 422
    assert "format must be" in resp.json()["detail"]


def test_custom_report_value_error_422(client, monkeypatch):
    def boom(f):
        raise ValueError("Invalid date format")
    monkeypatch.setattr(gr, "fetch_custom_report_data", boom)
    resp = client.get("/api/v1/reports/custom_report", params={"entity": "Tesla"})
    assert resp.status_code == 422
    assert "Invalid date format" in resp.json()["detail"]


def test_custom_report_generic_error_500(client, monkeypatch):
    def boom(f):
        raise KeyError("weird")
    monkeypatch.setattr(gr, "fetch_custom_report_data", boom)
    resp = client.get("/api/v1/reports/custom_report", params={"entity": "Tesla"})
    assert resp.status_code == 500
    assert "Custom report failed" in resp.json()["detail"]


def test_custom_report_all_sentiment_and_filters(client, monkeypatch):
    captured = {}

    def fake_fetch(f):
        captured["filter"] = f
        return _report_data(topic="Custom")

    monkeypatch.setattr(gr, "fetch_custom_report_data", fake_fetch)
    resp = client.get(
        "/api/v1/reports/custom_report",
        params={
            "entity": "Tesla",
            "sentiment": "all",
            "sentiment_min": -0.5,
            "sentiment_max": 0.5,
            "source": "Reuters",
            "category": "Technology",
            "date_from": "2026-01-01",
            "date_to": "2026-02-01",
            "limit": 10,
            "title": "My Report",
        },
    )
    assert resp.status_code == 200
    # sentiment "all" is normalised to None inside the handler
    assert captured["filter"].sentiment is None
    assert captured["filter"].source == "Reuters"
    assert captured["filter"].limit == 10
    assert captured["filter"].report_title == "My Report"


# ---------------------------------------------------------------------------
# Custom schedule endpoints
# ---------------------------------------------------------------------------

def test_create_schedule_success(client, duck_subs):
    resp = client.post(
        "/api/v1/reports/schedules",
        json={
            "name": "Chip watch",
            "email": "a@ex.com",
            "frequency": "weekly",
            "format": "pdf",
            "keywords": ["Nvidia", "AMD"],
            "date_range": "last_30_days",
            "sentiment": "positive",
            "limit": 50,
        },
    )
    assert resp.status_code == 201
    sched = resp.json()["schedule"]
    assert sched["name"] == "Chip watch"
    assert sched["filters"]["keywords"] == ["Nvidia", "AMD"]
    assert sched["filters"]["limit"] == 50


def test_create_schedule_empty_keywords(client, duck_subs):
    resp = client.post(
        "/api/v1/reports/schedules",
        json={"name": "X", "email": "a@ex.com", "keywords": []},
    )
    assert resp.status_code == 422  # keywords validator


def test_create_schedule_invalid_frequency(client, duck_subs):
    resp = client.post(
        "/api/v1/reports/schedules",
        json={"name": "X", "email": "a@ex.com", "keywords": ["a"], "frequency": "daily"},
    )
    assert resp.status_code == 422


def test_create_schedule_invalid_format(client, duck_subs):
    resp = client.post(
        "/api/v1/reports/schedules",
        json={"name": "X", "email": "a@ex.com", "keywords": ["a"], "format": "html"},
    )
    assert resp.status_code == 422


def test_create_schedule_error_500(client, monkeypatch):
    monkeypatch.setattr(
        subsmod, "create_custom_schedule",
        MagicMock(side_effect=RuntimeError("db down")),
    )
    resp = client.post(
        "/api/v1/reports/schedules",
        json={"name": "X", "email": "a@ex.com", "keywords": ["a"]},
    )
    assert resp.status_code == 500
    assert "db down" in resp.json()["detail"]


def test_list_schedules_all_and_filtered(client, duck_subs):
    client.post("/api/v1/reports/schedules",
                json={"name": "A", "email": "a@ex.com", "keywords": ["x"]})
    client.post("/api/v1/reports/schedules",
                json={"name": "B", "email": "b@ex.com", "keywords": ["y"]})

    resp = client.get("/api/v1/reports/schedules")
    assert resp.status_code == 200
    assert len(resp.json()["schedules"]) == 2

    resp2 = client.get("/api/v1/reports/schedules", params={"email": "a@ex.com"})
    assert len(resp2.json()["schedules"]) == 1


def test_list_schedules_error_500(client, monkeypatch):
    monkeypatch.setattr(
        subsmod, "list_custom_schedules",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    resp = client.get("/api/v1/reports/schedules")
    assert resp.status_code == 500


def test_delete_schedule_success(client, duck_subs):
    sched = client.post(
        "/api/v1/reports/schedules",
        json={"name": "A", "email": "a@ex.com", "keywords": ["x"]},
    ).json()["schedule"]
    resp = client.delete(f"/api/v1/reports/schedules/{sched['id']}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "id": sched["id"]}


def test_delete_schedule_not_found(client, duck_subs):
    resp = client.delete("/api/v1/reports/schedules/missing")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_delete_schedule_error_500(client, monkeypatch):
    monkeypatch.setattr(
        subsmod, "get_custom_schedule",
        MagicMock(side_effect=RuntimeError("explode")),
    )
    resp = client.delete("/api/v1/reports/schedules/x1")
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /track/open/{token}
# ---------------------------------------------------------------------------

def test_track_open_returns_gif(client, duck_subs):
    resp = client.get("/api/v1/reports/track/open/some-token")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/gif"
    assert resp.content == routes._TRACKING_PIXEL
    assert "no-store" in resp.headers["cache-control"]


def test_track_open_swallows_errors(client, monkeypatch):
    monkeypatch.setattr(
        subsmod, "record_open",
        MagicMock(side_effect=RuntimeError("db exploded")),
    )
    # Must still return the pixel, never a 500.
    resp = client.get("/api/v1/reports/track/open/whatever")
    assert resp.status_code == 200
    assert resp.content == routes._TRACKING_PIXEL
