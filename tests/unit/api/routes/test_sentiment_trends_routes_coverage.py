"""Comprehensive coverage tests for src/api/routes/sentiment_trends_routes.py.

The router is mounted on a *fresh* FastAPI app driven by a TestClient
(``raise_server_exceptions=False``). The ``get_sentiment_analyzer`` dependency
is overridden with an ``AsyncMock``-backed analyzer that returns *real*
dataclass instances (``TopicTrendSummary`` / ``SentimentTrendPoint`` /
``TrendAlert``) so the Pydantic response models serialise exactly as in
production. Every endpoint's success path, validation (422), not-found (404),
date-range (400) and error (500) branches are exercised with concrete
assertions on the response body.
"""

import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _install_light_nlp_stubs():
    """Register a lightweight stub for ``src.nlp.sentiment_trend_analyzer`` so
    importing the route never pulls the real analyzer's heavy import chain
    (scipy/numpy + ``src.nlp``'s package ``__init__`` -> torch/transformers,
    which crashes the interpreter under coverage's C tracer).

    The stub exposes the same public surface the route relies on:
      * the three dataclasses used to shape responses, and
      * a ``SentimentTrendAnalyzer`` whose ``__init__`` mirrors the real
        signature (so the offline ``get_sentiment_analyzer`` dependency works).
    The stub dataclasses carry exactly the fields the route reads, so the
    response models serialise identically to production.
    """
    from dataclasses import dataclass, field
    from datetime import datetime as _dt
    from typing import Any, Dict, List, Tuple

    import src  # noqa: F401

    # Register an empty src.nlp package (do NOT run its __init__, which imports
    # ner_processor -> torch). Keep __path__ so the dotted name resolves.
    if "src.nlp" not in sys.modules:
        nlp_pkg = types.ModuleType("src.nlp")
        nlp_pkg.__path__ = [os.path.join(os.path.dirname(src.__file__), "nlp")]
        sys.modules["src.nlp"] = nlp_pkg

    stub = types.ModuleType("src.nlp.sentiment_trend_analyzer")
    stub.__file__ = "<stub-sentiment-trend-analyzer>"

    @dataclass
    class SentimentTrendPoint:
        date: _dt
        topic: str
        sentiment_score: float
        sentiment_label: str
        confidence: float
        article_count: int
        source_articles: List[str] = field(default_factory=list)
        metadata: Dict[str, Any] = field(default_factory=dict)

    @dataclass
    class TrendAlert:
        alert_id: str
        topic: str
        alert_type: str
        severity: str
        current_sentiment: float
        previous_sentiment: float
        change_magnitude: float
        change_percentage: float
        confidence: float
        time_window: str
        triggered_at: _dt
        description: str
        affected_articles: List[str] = field(default_factory=list)
        metadata: Dict[str, Any] = field(default_factory=dict)

    @dataclass
    class TopicTrendSummary:
        topic: str
        time_range: Tuple[_dt, _dt]
        current_sentiment: float
        average_sentiment: float
        sentiment_volatility: float
        trend_direction: str
        trend_strength: float
        significant_changes: List[TrendAlert] = field(default_factory=list)
        data_points: List[SentimentTrendPoint] = field(default_factory=list)
        statistical_summary: Dict[str, Any] = field(default_factory=dict)

    class SentimentTrendAnalyzer:
        def __init__(
            self,
            snowflake_account="",
            snowflake_user="",
            snowflake_password="",
            snowflake_warehouse="ANALYTICS_WH",
            snowflake_database="NEURONEWS",
            snowflake_schema="PUBLIC",
            sentiment_analyzer=None,
            topic_extractor=None,
        ):
            self.conn_params = {
                "account": snowflake_account,
                "user": snowflake_user,
                "password": snowflake_password,
                "warehouse": snowflake_warehouse,
                "database": snowflake_database,
                "schema": snowflake_schema,
            }

        async def analyze_historical_trends(self, *a, **k):
            return []

        async def generate_sentiment_alerts(self, *a, **k):
            return []

        async def get_active_alerts(self, *a, **k):
            return []

        async def get_topic_trend_summary(self, *a, **k):
            return None

        async def update_topic_summaries(self, *a, **k):
            return None

    stub.SentimentTrendPoint = SentimentTrendPoint
    stub.TrendAlert = TrendAlert
    stub.TopicTrendSummary = TopicTrendSummary
    stub.SentimentTrendAnalyzer = SentimentTrendAnalyzer
    sys.modules["src.nlp.sentiment_trend_analyzer"] = stub
    return stub


def _load_routes_module(name):
    """Load src.api.routes.<name> from its file WITHOUT executing the routes
    package ``__init__`` (which eagerly imports ``article_routes`` -> torch)."""
    import src  # noqa: F401
    import src.api  # noqa: F401

    dotted = "src.api.routes." + name
    if dotted in sys.modules:
        return sys.modules[dotted]

    routes_dir = os.path.join(os.path.dirname(src.api.__file__), "routes")
    if "src.api.routes" not in sys.modules:
        pkg = types.ModuleType("src.api.routes")
        pkg.__path__ = [routes_dir]
        sys.modules["src.api.routes"] = pkg

    spec = importlib.util.spec_from_file_location(
        dotted, os.path.join(routes_dir, name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = module
    spec.loader.exec_module(module)
    return module


_analyzer_mod = _install_light_nlp_stubs()  # noqa: E402
SentimentTrendPoint = _analyzer_mod.SentimentTrendPoint
TopicTrendSummary = _analyzer_mod.TopicTrendSummary
TrendAlert = _analyzer_mod.TrendAlert

mod = _load_routes_module("sentiment_trends_routes")  # noqa: E402

# Sanity: the route bound to the same stub analyzer class we control.
assert mod.SentimentTrendAnalyzer is _analyzer_mod.SentimentTrendAnalyzer


# --------------------------------------------------------------------------- #
# Real dataclass builders (so Pydantic response models serialise for real)
# --------------------------------------------------------------------------- #

def _point(topic="AI", score=0.3, label="positive"):
    return SentimentTrendPoint(
        date=datetime(2026, 6, 1, 12, 0, 0),
        topic=topic,
        sentiment_score=score,
        sentiment_label=label,
        confidence=0.9,
        article_count=5,
        source_articles=["a1", "a2"],
        metadata={"note": "seed"},
    )


def _summary(topic="AI", points=None):
    pts = points if points is not None else [_point(topic), _point(topic, 0.5)]
    return TopicTrendSummary(
        topic=topic,
        time_range=(datetime(2026, 5, 1), datetime(2026, 6, 1)),
        current_sentiment=0.5,
        average_sentiment=0.4,
        sentiment_volatility=0.12,
        trend_direction="increasing",
        trend_strength=0.7,
        significant_changes=[],
        data_points=pts,
        statistical_summary={"total_articles": 42, "mean": 0.4},
    )


def _alert(topic="AI", severity="high", alert_type="significant_shift"):
    return TrendAlert(
        alert_id="al-1",
        topic=topic,
        alert_type=alert_type,
        severity=severity,
        current_sentiment=0.6,
        previous_sentiment=0.1,
        change_magnitude=0.5,
        change_percentage=500.0,
        confidence=0.88,
        time_window="7d",
        triggered_at=datetime(2026, 6, 2, 9, 0, 0),
        description="Sentiment shifted sharply positive",
        affected_articles=["a1", "a2", "a3"],
        metadata={},
    )


@pytest.fixture
def analyzer():
    a = MagicMock()
    a.analyze_historical_trends = AsyncMock(return_value=[_summary("AI"), _summary("Economy")])
    a.generate_sentiment_alerts = AsyncMock(return_value=[_alert("AI", "high")])
    a.get_active_alerts = AsyncMock(return_value=[_alert("AI", "critical")])
    a.get_topic_trend_summary = AsyncMock(return_value=_summary("AI"))
    a.update_topic_summaries = AsyncMock(return_value=None)
    # conn_params used by the health endpoint.
    a.conn_params = {"host": "localhost", "dbname": "x", "user": "u", "password": "p"}
    return a


@pytest.fixture
def client(analyzer):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_sentiment_analyzer] = lambda: analyzer
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------- #
# get_sentiment_analyzer dependency (offline stub)
# --------------------------------------------------------------------------- #

def test_get_sentiment_analyzer_returns_instance():
    import asyncio

    inst = asyncio.run(mod.get_sentiment_analyzer())
    # It builds a real analyzer with empty snowflake creds (offline-first).
    assert inst is not None
    assert hasattr(inst, "analyze_historical_trends")


def test_get_settings_placeholder():
    assert mod.get_settings() == {}


# --------------------------------------------------------------------------- #
# GET /sentiment_trends/analyze
# --------------------------------------------------------------------------- #

def test_analyze_success(client, analyzer):
    resp = client.get(
        "/api/v1/sentiment_trends/analyze",
        params={"topic": "AI", "time_granularity": "daily"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["summary_count"] == 2
    assert len(body["trend_summaries"]) == 2
    first = body["trend_summaries"][0]
    assert first["topic"] == "AI"
    assert first["data_points_count"] == 2
    assert first["trend_direction"] == "increasing"
    # trend_points flattened across summaries: 2 summaries x 2 points = 4.
    assert len(body["trend_points"]) == 4
    assert body["analysis_parameters"]["time_granularity"] == "daily"
    analyzer.analyze_historical_trends.assert_awaited_once()


def test_analyze_defaults_dates_when_absent(client, analyzer):
    resp = client.get("/api/v1/sentiment_trends/analyze")
    assert resp.status_code == 200
    # Defaults applied: start ~30d before end.
    kwargs = analyzer.analyze_historical_trends.await_args.kwargs
    span = kwargs["end_date"] - kwargs["start_date"]
    assert 29 <= span.days <= 31


def test_analyze_invalid_date_range(client):
    resp = client.get(
        "/api/v1/sentiment_trends/analyze",
        params={
            "start_date": "2026-06-01T00:00:00",
            "end_date": "2026-05-01T00:00:00",
        },
    )
    assert resp.status_code == 400
    assert "before end date" in resp.json()["detail"]


def test_analyze_date_range_too_large(client):
    resp = client.get(
        "/api/v1/sentiment_trends/analyze",
        params={
            "start_date": "2020-01-01T00:00:00",
            "end_date": "2026-01-01T00:00:00",
        },
    )
    assert resp.status_code == 400
    assert "Date range too large" in resp.json()["detail"]


def test_analyze_invalid_granularity_422(client):
    resp = client.get(
        "/api/v1/sentiment_trends/analyze",
        params={"time_granularity": "hourly"},  # not in daily|weekly|monthly
    )
    assert resp.status_code == 422


def test_analyze_internal_error_500(client, analyzer):
    analyzer.analyze_historical_trends.side_effect = RuntimeError("db exploded")
    resp = client.get("/api/v1/sentiment_trends/analyze")
    assert resp.status_code == 500
    assert "db exploded" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# POST /sentiment_trends/alerts/generate
# --------------------------------------------------------------------------- #

def test_generate_alerts_success(client, analyzer):
    resp = client.post(
        "/api/v1/sentiment_trends/alerts/generate",
        params={"topic": "AI", "lookback_days": 14},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["alerts_generated"] == 1
    assert body["severity_breakdown"]["high"] == 1
    assert body["severity_breakdown"]["critical"] == 0
    assert body["alerts"][0]["topic"] == "AI"
    assert body["alerts"][0]["affected_articles_count"] == 3
    analyzer.generate_sentiment_alerts.assert_awaited_once()
    # Background task to refresh summaries is scheduled.
    analyzer.update_topic_summaries.assert_called()


def test_generate_alerts_lookback_validation_422(client):
    resp = client.post(
        "/api/v1/sentiment_trends/alerts/generate", params={"lookback_days": 40}
    )
    assert resp.status_code == 422


def test_generate_alerts_error_500(client, analyzer):
    analyzer.generate_sentiment_alerts.side_effect = RuntimeError("alert engine down")
    resp = client.post("/api/v1/sentiment_trends/alerts/generate")
    assert resp.status_code == 500
    assert "alert engine down" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# GET /sentiment_trends/alerts
# --------------------------------------------------------------------------- #

def test_get_alerts_success(client, analyzer):
    resp = client.get(
        "/api/v1/sentiment_trends/alerts",
        params={"topic": "AI", "severity": "critical", "limit": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["total_alerts"] == 1
    assert body["query_parameters"]["severity"] == "critical"
    assert "significant_shift" in body["alert_types"]
    assert "AI" in body["topics_with_alerts"]
    analyzer.get_active_alerts.assert_awaited_once()


def test_get_alerts_include_resolved_warns_but_succeeds(client, analyzer):
    resp = client.get(
        "/api/v1/sentiment_trends/alerts", params={"include_resolved": True}
    )
    assert resp.status_code == 200
    assert resp.json()["query_parameters"]["include_resolved"] is True


def test_get_alerts_invalid_severity_422(client):
    resp = client.get(
        "/api/v1/sentiment_trends/alerts", params={"severity": "extreme"}
    )
    assert resp.status_code == 422


def test_get_alerts_limit_validation_422(client):
    resp = client.get("/api/v1/sentiment_trends/alerts", params={"limit": 999})
    assert resp.status_code == 422


def test_get_alerts_error_500(client, analyzer):
    analyzer.get_active_alerts.side_effect = RuntimeError("alert store offline")
    resp = client.get("/api/v1/sentiment_trends/alerts")
    assert resp.status_code == 500
    assert "alert store offline" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# GET /sentiment_trends/topic/{topic}
# --------------------------------------------------------------------------- #

def test_topic_trends_success(client, analyzer):
    resp = client.get("/api/v1/sentiment_trends/topic/AI", params={"days": 30})
    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == "AI"
    assert body["analysis_period_days"] == 30
    assert body["sentiment_summary"]["trend_direction"] == "increasing"
    assert body["data_quality"]["total_articles_analyzed"] == 42
    assert len(body["trend_points"]) == 2
    assert len(body["recent_alerts"]) == 1
    # Both the trend summary and the per-topic active alerts were fetched.
    analyzer.get_topic_trend_summary.assert_awaited_once()
    analyzer.get_active_alerts.assert_awaited()


def test_topic_trends_short_topic_400(client):
    resp = client.get("/api/v1/sentiment_trends/topic/A")
    assert resp.status_code == 400
    assert "at least 2 characters" in resp.json()["detail"]


def test_topic_trends_not_found_404(client, analyzer):
    analyzer.get_topic_trend_summary.return_value = None
    resp = client.get("/api/v1/sentiment_trends/topic/Unknown")
    assert resp.status_code == 404
    assert "No sentiment data found" in resp.json()["detail"]


def test_topic_trends_days_validation_422(client):
    resp = client.get("/api/v1/sentiment_trends/topic/AI", params={"days": 0})
    assert resp.status_code == 422


def test_topic_trends_error_500(client, analyzer):
    analyzer.get_topic_trend_summary.side_effect = RuntimeError("topic query failed")
    resp = client.get("/api/v1/sentiment_trends/topic/AI")
    assert resp.status_code == 500
    assert "topic query failed" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# GET /sentiment_trends/summary
# --------------------------------------------------------------------------- #

def test_summary_success(client, analyzer):
    resp = client.get("/api/v1/sentiment_trends/summary", params={"limit_topics": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["overall_metrics"]["active_topics"] == 2
    assert body["overall_metrics"]["total_alerts"] == 1
    assert len(body["topic_summaries"]) == 2
    # Severity/type breakdown populated from the single critical alert.
    assert body["alert_summary"]["breakdown"]["by_severity"]["critical"] == 1
    assert "significant_shift" in body["alert_summary"]["breakdown"]["by_type"]
    # Trending buckets present.
    assert "most_positive" in body["trending_topics"]
    assert "most_volatile" in body["trending_topics"]
    assert body["analysis_period"]["days"] == 7


def test_summary_no_topics_zero_metrics(client, analyzer):
    analyzer.analyze_historical_trends.return_value = []
    analyzer.get_active_alerts.return_value = []
    resp = client.get("/api/v1/sentiment_trends/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_metrics"]["average_sentiment"] == 0.0
    assert body["overall_metrics"]["average_volatility"] == 0.0
    assert body["overall_metrics"]["active_topics"] == 0


def test_summary_limit_validation_422(client):
    resp = client.get(
        "/api/v1/sentiment_trends/summary", params={"limit_topics": 500}
    )
    assert resp.status_code == 422


def test_summary_error_500(client, analyzer):
    analyzer.analyze_historical_trends.side_effect = RuntimeError("summary boom")
    resp = client.get("/api/v1/sentiment_trends/summary")
    assert resp.status_code == 500
    assert "summary boom" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# POST /sentiment_trends/update_summaries
# --------------------------------------------------------------------------- #

def test_update_summaries_success(client, analyzer):
    resp = client.post("/api/v1/sentiment_trends/update_summaries")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "scheduled"
    assert "update scheduled" in body["message"]
    analyzer.update_topic_summaries.assert_called()


def test_update_summaries_error_500(client, analyzer, monkeypatch):
    # Make add_task raise by breaking the background task registration path:
    # patch the analyzer attribute the route hands to add_task to raise on access.
    class _Boom:
        @property
        def update_topic_summaries(self):
            raise RuntimeError("scheduler down")

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_sentiment_analyzer] = lambda: _Boom()
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.post("/api/v1/sentiment_trends/update_summaries")
    assert resp.status_code == 500
    assert "scheduler down" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# GET /sentiment_trends/health
# --------------------------------------------------------------------------- #

def test_health_success(client, analyzer, monkeypatch):
    # Patch psycopg2.connect (module-level) to a fake connection yielding counts.
    class _Cursor:
        def __init__(self):
            self._results = [(123,), (4,), (9,)]
            self._i = 0

        def execute(self, *a, **k):
            pass

        def fetchone(self):
            row = self._results[self._i]
            self._i += 1
            return row

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Conn:
        def cursor(self):
            return _Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.psycopg2, "connect", lambda **kw: _Conn())
    resp = client.get("/api/v1/sentiment_trends/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database_connection"] == "ok"
    assert body["statistics"]["total_trend_points"] == 123
    assert body["statistics"]["active_alerts"] == 4
    assert body["statistics"]["unique_topics"] == 9


def test_health_db_failure_503(client, analyzer, monkeypatch):
    def boom(**kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(mod.psycopg2, "connect", boom)
    resp = client.get("/api/v1/sentiment_trends/health")
    assert resp.status_code == 503
    assert "Service health check failed" in resp.json()["detail"]
