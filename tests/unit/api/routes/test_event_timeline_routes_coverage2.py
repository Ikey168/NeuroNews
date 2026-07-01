"""Additional coverage for src/api/routes/event_timeline_routes.py.

Complements the existing routes smoke test by driving the branches it skips:
- start/end date parse errors and range validation
- the service-error fallback response and analytics generation
- POST /track (with Neptune storage + event limiting)
- visualization with date filters
- export in json / csv / html / invalid format
- error handlers returning 500
- the _generate_html_timeline helper

The router is mounted on a fresh FastAPI app and the service dependency is
replaced with an AsyncMock via dependency_overrides, so no real graph/NLP
backends are touched. Imports use the `src.api.*` path for a single module
identity.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import src.api.routes.event_timeline_routes as mod  # noqa: E402
from src.api.event_timeline_service import HistoricalEvent  # noqa: E402


def _event_dict(eid="e1", ts="2026-01-15T00:00:00"):
    return {
        "event_id": eid,
        "title": "Breakthrough in AI",
        "description": "d" * 250,
        "timestamp": ts,
        "topic": "AI",
        "event_type": "announcement",
        "entities_involved": ["OpenAI", "Google"],
        "confidence": 0.9,
        "impact_score": 0.7,
    }


def make_service():
    s = MagicMock()
    s.generate_timeline_api_response = AsyncMock(return_value={
        "topic": "AI",
        "timeline_span": {"start_date": None, "end_date": None},
        "total_events": 1,
        "events": [_event_dict()],
        "metadata": {"generated_at": "2026-01-01T00:00:00"},
    })
    s.generate_visualization_data = AsyncMock(return_value={
        "event_clusters": {"total_clusters": 1},
        "impact_analysis": {"total_events": 1},
        "entity_involvement": {"type": "bar"},
        "timeline_chart": {"type": "timeline"},
    })
    s.track_historical_events = AsyncMock(return_value=[])
    s.store_event_relationships = AsyncMock(return_value={
        "events_stored": 1, "relationships_created": 2, "errors": [],
    })
    return s


@pytest.fixture
def service():
    return make_service()


@pytest.fixture
def client(service):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_event_timeline_service] = lambda: service
    app.dependency_overrides[mod.get_optional_auth] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /{topic}: date parse errors + range validation
# ---------------------------------------------------------------------------
def test_invalid_start_date_returns_400(client):
    resp = client.get("/api/v1/event-timeline/AI", params={"start_date": "not-a-date"})
    assert resp.status_code == 400
    assert "start_date" in resp.json()["detail"]


def test_invalid_end_date_returns_400(client):
    resp = client.get(
        "/api/v1/event-timeline/AI",
        params={"start_date": "2026-01-01", "end_date": "garbage"})
    assert resp.status_code == 400
    assert "end_date" in resp.json()["detail"]


def test_start_after_end_returns_400(client):
    resp = client.get(
        "/api/v1/event-timeline/AI",
        params={"start_date": "2026-06-01", "end_date": "2026-01-01"})
    assert resp.status_code == 400
    assert "before end date" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /{topic}: happy path with analytics + valid dates
# ---------------------------------------------------------------------------
def test_timeline_with_analytics(client, service):
    resp = client.get(
        "/api/v1/event-timeline/AI",
        params={"start_date": "2026-01-01", "end_date": "2026-06-01",
                "include_analytics": "true", "theme": "dark"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == "AI"
    assert body["total_events"] == 1
    # Analytics assembled from generate_visualization_data output.
    assert body["analytics"]["event_clusters"] == {"total_clusters": 1}
    assert body["analytics"]["impact_analysis"] == {"total_events": 1}
    # Export options + enhanced metadata attached.
    assert body["export_options"]["json"].endswith("format=json")
    assert body["metadata"]["enhanced_api"] is True
    assert body["metadata"]["analytics_included"] is True
    # generate_visualization_data must have been called for analytics.
    service.generate_visualization_data.assert_awaited()


def test_timeline_analytics_no_valid_events(client, service):
    # Events present but all invalid (bad timestamp) -> analytics == {}.
    service.generate_timeline_api_response = AsyncMock(return_value={
        "topic": "AI",
        "timeline_span": {},
        "total_events": 1,
        "events": [{"event_id": "x", "timestamp": "not-a-timestamp"}],
        "metadata": {"generated_at": "2026-01-01T00:00:00"},
    })
    resp = client.get("/api/v1/event-timeline/AI",
                      params={"include_analytics": "true"})
    assert resp.status_code == 200
    assert resp.json()["analytics"] == {}


def test_timeline_service_error_fallback(client, service):
    # Service raises -> route builds a fallback response (still 200).
    service.generate_timeline_api_response = AsyncMock(
        side_effect=RuntimeError("service down"))
    resp = client.get("/api/v1/event-timeline/AI",
                      params={"start_date": "2026-01-01", "end_date": "2026-06-01",
                              "include_analytics": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == "AI"
    assert body["total_events"] == 0
    assert body["events"] == []
    assert body["metadata"]["service_error"] == "service down"


def test_timeline_analytics_generation_error(client, service):
    # Valid events but generate_visualization_data raises -> analytics == {}.
    service.generate_visualization_data = AsyncMock(
        side_effect=RuntimeError("viz failed"))
    resp = client.get("/api/v1/event-timeline/AI",
                      params={"include_analytics": "true"})
    assert resp.status_code == 200
    assert resp.json()["analytics"] == {}


def test_timeline_non_dict_service_response_fallback(client, service):
    # Service returns a non-dict -> ValueError inside try -> fallback response.
    service.generate_timeline_api_response = AsyncMock(return_value=["not", "a", "dict"])
    resp = client.get("/api/v1/event-timeline/AI")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_events"] == 0
    assert "service_error" in body["metadata"]


# ---------------------------------------------------------------------------
# POST /track
# ---------------------------------------------------------------------------
def test_track_events_with_storage(client, service):
    events = [HistoricalEvent(
        event_id=f"e{i}", title="t", description="d",
        timestamp=datetime(2026, 1, 1), topic="AI", event_type="announcement",
        entities_involved=[]) for i in range(3)]
    service.track_historical_events = AsyncMock(return_value=events)
    resp = client.post("/api/v1/event-timeline/track", json={
        "topic": "AI", "max_events": 100, "store_in_neptune": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["events_tracked"] == 3
    assert body["events_stored"] == 1
    assert body["relationships_created"] == 2
    assert body["timeline_id"].startswith("timeline_AI_")
    service.store_event_relationships.assert_awaited()


def test_track_events_limits_to_max(client, service):
    events = [HistoricalEvent(
        event_id=f"e{i}", title="t", description="d",
        timestamp=datetime(2026, 1, 1), topic="AI", event_type="announcement",
        entities_involved=[]) for i in range(5)]
    service.track_historical_events = AsyncMock(return_value=events)
    resp = client.post("/api/v1/event-timeline/track", json={
        "topic": "AI", "max_events": 2, "store_in_neptune": False,
    })
    assert resp.status_code == 200
    body = resp.json()
    # Trimmed to max_events; storage skipped.
    assert body["events_tracked"] == 2
    assert body["events_stored"] == 0
    service.store_event_relationships.assert_not_awaited()


def test_track_events_service_error_returns_500(client, service):
    service.track_historical_events = AsyncMock(side_effect=RuntimeError("boom"))
    resp = client.post("/api/v1/event-timeline/track", json={"topic": "AI"})
    assert resp.status_code == 500
    assert "Failed to track events" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /{topic}/visualization
# ---------------------------------------------------------------------------
def test_visualization_with_dates(client, service):
    resp = client.get(
        "/api/v1/event-timeline/AI/visualization",
        params={"start_date": "2026-01-01", "end_date": "2026-06-01",
                "chart_type": "scatter", "theme": "scientific"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == "AI"
    assert body["visualization_type"] == "scatter"
    assert body["theme"] == "scientific"
    assert "json" in body["export_formats"]


def test_visualization_limits_events(client, service):
    events = [HistoricalEvent(
        event_id=f"e{i}", title="t", description="d",
        timestamp=datetime(2026, 1, 1), topic="AI", event_type="announcement",
        entities_involved=[]) for i in range(10)]
    service.track_historical_events = AsyncMock(return_value=events)
    resp = client.get("/api/v1/event-timeline/AI/visualization",
                      params={"max_events": 3})
    assert resp.status_code == 200
    # Only the trimmed events are passed to visualization generation.
    _, kwargs = service.generate_visualization_data.await_args
    assert len(kwargs["events"]) == 3


def test_visualization_service_error_returns_500(client, service):
    service.track_historical_events = AsyncMock(side_effect=RuntimeError("no data"))
    resp = client.get("/api/v1/event-timeline/AI/visualization")
    assert resp.status_code == 500
    assert "Failed to generate visualization" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /{topic}/export
# ---------------------------------------------------------------------------
def test_export_json(client, service):
    resp = client.get("/api/v1/event-timeline/AI/export", params={"format": "json"})
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.json()["topic"] == "AI"


def test_export_csv(client, service):
    resp = client.get(
        "/api/v1/event-timeline/AI/export",
        params={"format": "csv", "start_date": "2026-01-01", "end_date": "2026-06-01"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    text = resp.text
    assert "Event ID" in text  # header row
    assert "e1" in text  # event row from the mocked events
    assert "OpenAI, Google" in text  # joined entities


def test_export_html(client, service):
    resp = client.get("/api/v1/event-timeline/AI/export", params={"format": "html"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Event Timeline: AI" in resp.text


def test_export_invalid_format_returns_400(client):
    resp = client.get("/api/v1/event-timeline/AI/export", params={"format": "pdf"})
    assert resp.status_code == 400
    assert "Format must be one of" in resp.json()["detail"]


def test_export_service_error_returns_500(client, service):
    service.generate_timeline_api_response = AsyncMock(
        side_effect=RuntimeError("export boom"))
    resp = client.get("/api/v1/event-timeline/AI/export", params={"format": "json"})
    assert resp.status_code == 500
    assert "Failed to export data" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /analytics + /health
# ---------------------------------------------------------------------------
def test_analytics_endpoint(client):
    resp = client.get("/api/v1/event-timeline/analytics",
                      params={"time_window_days": 7, "top_topics": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["time_window_days"] == 7
    assert "system_stats" in body
    assert "insights" in body


def test_health_reports_components(client):
    resp = client.get("/api/v1/event-timeline/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("healthy", "unhealthy")
    assert body["service"] == "event-timeline-api"


# ---------------------------------------------------------------------------
# _generate_html_timeline helper (called directly)
# ---------------------------------------------------------------------------
def test_generate_html_timeline_helper():
    timeline_data = {
        "total_events": 2,
        "metadata": {"generated_at": "2026-01-01T00:00:00"},
        "events": [
            _event_dict("h1"),
            _event_dict("h2", ts="2026-02-01T00:00:00"),
        ],
    }
    html = mod._generate_html_timeline("Climate", timeline_data)
    assert "<!DOCTYPE html>" in html
    assert "Event Timeline: Climate" in html
    assert "Total Events: 2" in html
    assert "Breakthrough in AI" in html  # event title rendered
    assert "timelineChart" in html  # chart canvas present


def test_generate_html_timeline_no_events():
    html = mod._generate_html_timeline("Empty", {"total_events": 0, "events": []})
    assert "Event Timeline: Empty" in html
    assert "Total Events: 0" in html


# ---------------------------------------------------------------------------
# Pydantic request-model validators
# ---------------------------------------------------------------------------
def test_event_tracking_request_end_before_start_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        mod.EventTrackingRequest(
            topic="AI",
            start_date=datetime(2026, 6, 1),
            end_date=datetime(2026, 1, 1),  # <= start -> validator raises
        )


def test_event_tracking_request_valid_dates():
    req = mod.EventTrackingRequest(
        topic="AI",
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 6, 1),
    )
    assert req.end_date > req.start_date


def test_visualization_request_invalid_theme_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        mod.TimelineVisualizationRequest(theme="neon")


def test_visualization_request_invalid_chart_type_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        mod.TimelineVisualizationRequest(chart_type="pie")


def test_visualization_request_valid():
    req = mod.TimelineVisualizationRequest(theme="dark", chart_type="scatter")
    assert req.theme == "dark"
    assert req.chart_type == "scatter"


# ---------------------------------------------------------------------------
# get_optional_auth dependency helper
# ---------------------------------------------------------------------------
def test_get_optional_auth_returns_value():
    # When AUTH_AVAILABLE the helper returns a Depends(...) object; otherwise None.
    result = mod.get_optional_auth()
    if mod.AUTH_AVAILABLE:
        assert result is not None
    else:
        assert result is None


# ---------------------------------------------------------------------------
# get_event_timeline_service: initialization failure -> 503
# ---------------------------------------------------------------------------
def test_get_event_timeline_service_init_failure(monkeypatch):
    import asyncio
    from fastapi import HTTPException

    monkeypatch.setattr(mod, "_event_timeline_service", None)

    def boom(*a, **k):
        raise RuntimeError("cannot init service")

    monkeypatch.setattr(mod, "EventTimelineService", boom)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(mod.get_event_timeline_service())
    assert ei.value.status_code == 503
    # Reset the cached global so other tests are unaffected.
    monkeypatch.setattr(mod, "_event_timeline_service", None)


# ---------------------------------------------------------------------------
# GET /{topic}: defensive response-field filling + outer 500 handler
# ---------------------------------------------------------------------------
def test_timeline_fills_missing_fields(client, service):
    # Service returns a dict with 'metadata' (needed for the .update() call) but
    # missing topic/timeline_span/total_events -> route fills them (lines 368-376).
    service.generate_timeline_api_response = AsyncMock(return_value={
        "events": [_event_dict()],
        "metadata": {"generated_at": "2026-01-01T00:00:00"},
    })
    resp = client.get("/api/v1/event-timeline/AI",
                      params={"include_analytics": "false"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == "AI"  # filled from endpoint topic
    assert body["timeline_span"] == {}  # filled default
    assert body["total_events"] == 1  # derived from len(events)


def test_timeline_fills_missing_events_key(client, service):
    # Dict has metadata (so .update works) + topic/span/total but NO 'events' key
    # -> route fills events=[] (line 374).
    service.generate_timeline_api_response = AsyncMock(return_value={
        "topic": "AI",
        "timeline_span": {},
        "total_events": 0,
        "metadata": {"generated_at": "2026-01-01T00:00:00"},
    })
    resp = client.get("/api/v1/event-timeline/AI",
                      params={"include_analytics": "false"})
    assert resp.status_code == 200
    assert resp.json()["events"] == []


def test_timeline_outer_exception_returns_500(client, service):
    # Make EventTimelineResponse construction fail by returning events that are
    # not JSON-serializable dicts after the analytics path; simplest: force the
    # response-building to raise via a non-dict metadata that breaks .update().
    service.generate_timeline_api_response = AsyncMock(return_value={
        "topic": "AI",
        "timeline_span": {},
        "total_events": 1,
        "events": [_event_dict()],
        "metadata": "not-a-dict",  # .update() on a str -> AttributeError
    })
    resp = client.get("/api/v1/event-timeline/AI",
                      params={"include_analytics": "false"})
    assert resp.status_code == 500
    assert "Internal server error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /analytics + /health error handlers
# ---------------------------------------------------------------------------
def test_analytics_error_handler(monkeypatch):
    # Force datetime.now() inside the analytics handler to raise -> 500.
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_event_timeline_service] = lambda: make_service()
    app.dependency_overrides[mod.get_optional_auth] = lambda: None
    c = TestClient(app, raise_server_exceptions=False)

    class BoomDateTime:
        @staticmethod
        def now(*a, **k):
            raise RuntimeError("clock exploded")

    monkeypatch.setattr(mod, "datetime", BoomDateTime)
    resp = c.get("/api/v1/event-timeline/analytics")
    assert resp.status_code == 500
    assert "Failed to generate analytics" in resp.json()["detail"]


def test_health_unhealthy_on_service_error(monkeypatch):
    # get_event_timeline_service raises inside health_check -> 'unhealthy'.
    app = FastAPI()
    app.include_router(mod.router)
    c = TestClient(app, raise_server_exceptions=False)

    async def boom():
        raise RuntimeError("service unavailable")

    monkeypatch.setattr(mod, "get_event_timeline_service", boom)
    resp = c.get("/api/v1/event-timeline/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert "service unavailable" in body["error"]
