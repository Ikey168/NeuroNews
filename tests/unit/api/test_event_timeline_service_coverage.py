"""Coverage-focused tests for src/api/event_timeline_service.py.

Exercises the EventTimelineService directly (no API layer) with a mocked
graph_populator that exposes `_execute_traversal`, so the Neptune/Gremlin
branches, error handlers, and component-initialization paths that the existing
happy-path tests skip are covered.

The service is imported via the `src.api.*` path so it shares one module
identity with the routes tests, avoiding duplicate C-extension loads.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.api.event_timeline_service as ets
from src.api.event_timeline_service import (
    EventTimelineService,
    HistoricalEvent,
)


def _run(coro):
    return asyncio.run(coro)


def make_event(eid="e1", ts=None, etype="announcement", impact=0.5, entities=None,
               related=None):
    return HistoricalEvent(
        event_id=eid,
        title=f"Title {eid}",
        description="a description that is reasonably long " * 3,
        timestamp=ts or datetime(2026, 1, 15, 12, 0, 0),
        topic="tech",
        event_type=etype,
        entities_involved=entities if entities is not None else ["Google", "OpenAI"],
        confidence=0.9,
        impact_score=impact,
        related_events=related or [],
    )


@pytest.fixture
def bare_service(monkeypatch):
    """Service with component initialization disabled (no graph populator)."""
    monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", False, raising=False)
    monkeypatch.setattr(ets, "BASIC_COMPONENTS_AVAILABLE", False, raising=False)
    svc = EventTimelineService()
    assert svc.graph_populator is None
    return svc


@pytest.fixture
def graph_service(monkeypatch):
    """Service wired to a mock graph_populator exposing _execute_traversal."""
    monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", False, raising=False)
    monkeypatch.setattr(ets, "BASIC_COMPONENTS_AVAILABLE", False, raising=False)
    svc = EventTimelineService()
    gp = MagicMock()
    gp._execute_traversal = AsyncMock(return_value=[])
    svc.graph_populator = gp
    return svc, gp


# ---------------------------------------------------------------------------
# _initialize_components: enhanced / basic / none / exception paths
# ---------------------------------------------------------------------------
def test_initialize_enhanced_components(monkeypatch):
    monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", True, raising=False)
    monkeypatch.setattr(ets, "BASIC_COMPONENTS_AVAILABLE", True, raising=False)
    enh_pop = object()
    enh_ext = object()
    monkeypatch.setattr(ets, "EnhancedKnowledgeGraphPopulator",
                        lambda cfg: enh_pop, raising=False)
    monkeypatch.setattr(ets, "AdvancedEntityExtractor",
                        lambda cfg: enh_ext, raising=False)
    svc = EventTimelineService()
    assert svc.graph_populator is enh_pop
    assert svc.entity_extractor is enh_ext


def test_initialize_basic_components(monkeypatch):
    monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", False, raising=False)
    monkeypatch.setattr(ets, "BASIC_COMPONENTS_AVAILABLE", True, raising=False)
    basic_pop = object()
    basic_ext = object()
    monkeypatch.setattr(ets, "GraphBuilder", lambda cfg: basic_pop, raising=False)
    monkeypatch.setattr(ets, "EntityExtractor", lambda: basic_ext, raising=False)
    svc = EventTimelineService()
    assert svc.graph_populator is basic_pop
    assert svc.entity_extractor is basic_ext


def test_initialize_no_components(monkeypatch):
    monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", False, raising=False)
    monkeypatch.setattr(ets, "BASIC_COMPONENTS_AVAILABLE", False, raising=False)
    svc = EventTimelineService()
    assert svc.graph_populator is None
    assert svc.entity_extractor is None


def test_initialize_components_exception(monkeypatch):
    monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", True, raising=False)

    def boom(cfg):
        raise RuntimeError("cannot build populator")

    monkeypatch.setattr(ets, "EnhancedKnowledgeGraphPopulator", boom, raising=False)
    # Exception is caught inside _initialize_components; service still usable.
    svc = EventTimelineService()
    assert svc.graph_populator is None


def test_custom_config_values(monkeypatch):
    monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", False, raising=False)
    monkeypatch.setattr(ets, "BASIC_COMPONENTS_AVAILABLE", False, raising=False)
    svc = EventTimelineService({
        "max_events_per_timeline": 7,
        "default_time_window_days": 10,
        "event_clustering_threshold": 0.42,
    })
    assert svc.max_events_per_timeline == 7
    assert svc.default_time_window_days == 10
    assert svc.event_clustering_threshold == 0.42


# ---------------------------------------------------------------------------
# track_historical_events: default date range + re-raise on failure
# ---------------------------------------------------------------------------
def test_track_default_time_window(bare_service):
    # No dates -> defaults computed (end=now, start=end-window). Falls back to
    # sample events because there is no graph populator.
    events = _run(bare_service.track_historical_events("Climate"))
    assert len(events) >= 1
    assert all(isinstance(e, HistoricalEvent) for e in events)
    # Sorted chronologically.
    ts = [e.timestamp for e in events]
    assert ts == sorted(ts)


def test_track_reraises_on_query_failure(bare_service, monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("graph query failed")

    monkeypatch.setattr(bare_service, "_query_events_from_graph", boom)
    with pytest.raises(RuntimeError, match="graph query failed"):
        _run(bare_service.track_historical_events("AI"))


# ---------------------------------------------------------------------------
# _query_events_from_graph: no populator / traversal path / fallback / error
# ---------------------------------------------------------------------------
def test_query_events_no_populator_uses_samples(bare_service):
    events = _run(bare_service._query_events_from_graph(
        "AI", datetime(2026, 1, 1), datetime(2026, 3, 1)))
    assert isinstance(events, list) and events
    assert all("published_date" in e for e in events)


def test_query_events_uses_traversal(graph_service):
    svc, gp = graph_service
    gp._execute_traversal = AsyncMock(return_value=[
        {"id": ["a1"], "title": ["Google announces launch"],
         "content": ["research findings"], "published_date": ["2026-02-01T00:00:00"],
         "author": ["Jane"], "category": ["Technology"]},
    ])
    events = _run(svc._query_events_from_graph(
        "AI", datetime(2026, 1, 1), datetime(2026, 3, 1)))
    gp._execute_traversal.assert_awaited()
    assert len(events) == 1
    assert events[0]["event_id"] == "a1"
    assert events[0]["title"] == "Google announces launch"


def test_query_events_basic_builder_fallback(graph_service):
    svc, gp = graph_service
    # Populator without _execute_traversal -> sample events fallback.
    del gp._execute_traversal
    events = _run(svc._query_events_from_graph(
        "AI", datetime(2026, 1, 1), datetime(2026, 3, 1)))
    assert events and all("published_date" in e for e in events)


def test_query_events_traversal_error_falls_back(graph_service):
    svc, gp = graph_service
    gp._execute_traversal = AsyncMock(side_effect=RuntimeError("gremlin down"))
    events = _run(svc._query_events_from_graph(
        "AI", datetime(2026, 1, 1), datetime(2026, 3, 1)))
    # Exception -> sample events fallback.
    assert events and all("published_date" in e for e in events)


# ---------------------------------------------------------------------------
# _process_graph_results: list-value extraction + per-result exception
# ---------------------------------------------------------------------------
def test_process_graph_results_extracts_fields(bare_service):
    results = [
        {"id": ["x1"], "title": ["Apple regulation policy"],
         "content": ["law text"], "published_date": ["2026-05-01T00:00:00"],
         "author": ["Bob"], "source_url": ["http://x"], "category": ["Legal"]},
        {"id": [], "title": [], "content": [], "published_date": []},  # empty lists
    ]
    events = bare_service._process_graph_results(results, "Policy")
    assert len(events) == 2
    assert events[0]["event_id"] == "x1"
    assert events[0]["event_type"] == "regulation"
    assert events[0]["topic"] == "Policy"


def test_process_graph_results_skips_bad_result(bare_service, monkeypatch):
    # Force _classify_event_type to raise for one result -> that result skipped.
    calls = {"n": 0}
    orig = bare_service._classify_event_type

    def flaky(result):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("classify boom")
        return orig(result)

    monkeypatch.setattr(bare_service, "_classify_event_type", flaky)
    results = [
        {"id": ["bad"], "title": ["t"]},
        {"id": ["good"], "title": ["Google research study"]},
    ]
    events = bare_service._process_graph_results(results, "AI")
    # First raised inside the loop -> skipped; only the second survives.
    assert len(events) == 1
    assert events[0]["event_id"] == "good"


# ---------------------------------------------------------------------------
# _generate_sample_events content
# ---------------------------------------------------------------------------
def test_generate_sample_events_tech_category(bare_service):
    events = bare_service._generate_sample_events(
        "AI breakthrough", datetime(2026, 1, 1), datetime(2026, 3, 1))
    assert events
    assert events[0]["category"] == "Technology"
    # Alternating announcement/research type.
    assert events[0]["type"] == "announcement"


def test_generate_sample_events_general_category(bare_service):
    events = bare_service._generate_sample_events(
        "Sports news", datetime(2026, 1, 1), datetime(2026, 2, 1))
    assert events
    assert events[0]["category"] == "General"


# ---------------------------------------------------------------------------
# _enhance_event_data: success + exception fallback
# ---------------------------------------------------------------------------
def test_enhance_event_data_success(bare_service):
    data = {
        "event_id": "e42", "title": "Major breakthrough", "description": "d",
        "timestamp": datetime(2026, 1, 1), "topic": "AI",
        "event_type": "announcement", "entities_involved": ["OpenAI"],
        "confidence": 0.9, "metadata": {},
    }
    event = _run(bare_service._enhance_event_data(data, include_related=True))
    assert event.event_id == "e42"
    # impact_score was computed (base 0.5, boosted by 'major' + entities, * type mult)
    assert 0.0 <= event.impact_score <= 1.0
    assert event.related_events == []


def test_enhance_event_data_exception_returns_basic(bare_service, monkeypatch):
    async def boom(event):
        raise RuntimeError("impact calc failed")

    monkeypatch.setattr(bare_service, "_calculate_impact_score", boom)
    data = {
        "event_id": "e9", "title": "T", "description": "d",
        "timestamp": datetime(2026, 1, 1), "topic": "AI",
        "event_type": "general", "entities_involved": [],
    }
    event = _run(bare_service._enhance_event_data(data))
    # Basic event returned on failure -> impact_score stays default 0.0.
    assert event.event_id == "e9"
    assert event.impact_score == 0.0


# ---------------------------------------------------------------------------
# store_event_relationships + _store_event_in_neptune + _create_event_relationships
# ---------------------------------------------------------------------------
def test_store_event_relationships_success(graph_service):
    svc, gp = graph_service
    # _check_event_exists returns count 0 (not existing), then addV, then edges.
    gp._execute_traversal = AsyncMock(return_value=[0])
    ev = make_event(entities=["Google", "OpenAI"], related=["e2"])
    result = _run(svc.store_event_relationships([ev]))
    assert result["events_stored"] == 1
    # 2 entity edges + 1 related-event edge.
    assert result["relationships_created"] == 3
    assert result["errors"] == []


def test_store_event_relationships_per_event_error(graph_service, monkeypatch):
    svc, gp = graph_service

    async def boom(event, force_update):
        raise RuntimeError("neptune write failed")

    monkeypatch.setattr(svc, "_store_event_in_neptune", boom)
    ev = make_event()
    result = _run(svc.store_event_relationships([ev]))
    assert result["events_stored"] == 0
    assert len(result["errors"]) == 1
    assert "neptune write failed" in result["errors"][0]


def test_store_event_relationships_outer_error(graph_service, monkeypatch):
    svc, gp = graph_service
    # Passing a non-iterable-of-events triggers the outer try/except re-raise.
    monkeypatch.setattr(svc, "_store_event_in_neptune",
                        AsyncMock(return_value=True))

    class BadEvents:
        def __iter__(self):
            raise RuntimeError("cannot iterate events")

        def __len__(self):
            return 0

    with pytest.raises(RuntimeError, match="cannot iterate events"):
        _run(svc.store_event_relationships(BadEvents()))


def test_store_event_in_neptune_no_populator(bare_service):
    ev = make_event()
    assert _run(bare_service._store_event_in_neptune(ev)) is False


def test_store_event_in_neptune_skips_existing(graph_service):
    svc, gp = graph_service
    # count query returns >0 -> event exists -> returns True without addV.
    gp._execute_traversal = AsyncMock(return_value=[5])
    ev = make_event()
    assert _run(svc._store_event_in_neptune(ev, force_update=False)) is True


def test_store_event_in_neptune_creates_vertex(graph_service):
    svc, gp = graph_service
    gp._execute_traversal = AsyncMock(return_value=[0])
    ev = make_event()
    assert _run(svc._store_event_in_neptune(ev, force_update=True)) is True
    gp._execute_traversal.assert_awaited()


def test_store_event_in_neptune_no_traversal_support(graph_service):
    svc, gp = graph_service
    del gp._execute_traversal  # populator without traversal support
    ev = make_event()
    assert _run(svc._store_event_in_neptune(ev, force_update=True)) is False


def test_store_event_in_neptune_exception(graph_service):
    svc, gp = graph_service
    gp._execute_traversal = AsyncMock(side_effect=RuntimeError("addV failed"))
    ev = make_event()
    assert _run(svc._store_event_in_neptune(ev, force_update=True)) is False


def test_create_event_relationships_no_populator(bare_service):
    ev = make_event()
    assert _run(bare_service._create_event_relationships(ev)) == []


def test_create_event_relationships_entities_and_related(graph_service):
    svc, gp = graph_service
    gp._execute_traversal = AsyncMock(return_value=[])
    ev = make_event(entities=["Google"], related=["e2", "e3"])
    rels = _run(svc._create_event_relationships(ev))
    # 1 entity + 2 related.
    assert len(rels) == 3
    assert any("entity-Google" in r for r in rels)
    assert any("related-e2" in r for r in rels)


def test_create_event_relationships_entity_edge_error(graph_service):
    svc, gp = graph_service
    # First call (entity edge) raises; related-event edge still processed.
    gp._execute_traversal = AsyncMock(
        side_effect=[RuntimeError("entity edge failed"), []])
    ev = make_event(entities=["Google"], related=["e2"])
    rels = _run(svc._create_event_relationships(ev))
    # Entity edge failed -> not recorded; related edge succeeded.
    assert len(rels) == 1
    assert "related-e2" in rels[0]


def test_create_event_relationships_related_edge_error(graph_service):
    svc, gp = graph_service
    # Entity edge succeeds, related-event edge raises (lines 645-646).
    gp._execute_traversal = AsyncMock(
        side_effect=[[], RuntimeError("related edge failed")])
    ev = make_event(entities=["Google"], related=["e2"])
    rels = _run(svc._create_event_relationships(ev))
    # Only the entity edge recorded; related edge error swallowed.
    assert len(rels) == 1
    assert "entity-Google" in rels[0]


def test_create_event_relationships_outer_exception(graph_service):
    svc, gp = graph_service
    ev = make_event(entities=["Google"])

    # Make iterating entities_involved raise -> outer except (lines 658-660).
    class BadEntities:
        def __iter__(self):
            raise RuntimeError("entities iteration exploded")

    ev.entities_involved = BadEntities()
    rels = _run(svc._create_event_relationships(ev))
    assert rels == []


# ---------------------------------------------------------------------------
# generate_timeline_api_response: max_events limit + exception
# ---------------------------------------------------------------------------
def test_generate_timeline_response_limits_events(bare_service, monkeypatch):
    many = [make_event(eid=f"e{i}", ts=datetime(2026, 1, i + 1)) for i in range(5)]

    async def fake_track(**kwargs):
        return many

    monkeypatch.setattr(bare_service, "track_historical_events", fake_track)
    resp = _run(bare_service.generate_timeline_api_response(
        "AI", max_events=2, include_visualizations=False))
    assert resp["total_events"] == 2
    assert len(resp["events"]) == 2
    assert "visualization" not in resp


def test_generate_timeline_response_with_dates_and_viz(bare_service, monkeypatch):
    async def fake_track(**kwargs):
        return [make_event()]

    monkeypatch.setattr(bare_service, "track_historical_events", fake_track)
    start = datetime(2026, 1, 1)
    end = datetime(2026, 2, 1)
    resp = _run(bare_service.generate_timeline_api_response(
        "AI", start_date=start, end_date=end, include_visualizations=True))
    assert resp["timeline_span"]["start_date"] == start.isoformat()
    assert resp["timeline_span"]["end_date"] == end.isoformat()
    assert "visualization" in resp
    assert "timeline_chart" in resp["visualization"]


def test_generate_timeline_response_exception(bare_service, monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("track failed")

    monkeypatch.setattr(bare_service, "track_historical_events", boom)
    with pytest.raises(RuntimeError, match="track failed"):
        _run(bare_service.generate_timeline_api_response("AI"))


# ---------------------------------------------------------------------------
# generate_visualization_data: exception path
# ---------------------------------------------------------------------------
def test_generate_visualization_data_exception(bare_service, monkeypatch):
    def boom(events, theme):
        raise RuntimeError("chart prep failed")

    monkeypatch.setattr(bare_service, "_prepare_timeline_chart_data", boom)
    with pytest.raises(RuntimeError, match="chart prep failed"):
        _run(bare_service.generate_visualization_data("AI", [make_event()]))


# ---------------------------------------------------------------------------
# Visualization helper error branches
# ---------------------------------------------------------------------------
def test_prepare_timeline_chart_data_error(bare_service):
    # An event whose timestamp is not a datetime triggers the except branch.
    bad = make_event()
    bad.timestamp = "not-a-datetime"
    out = bare_service._prepare_timeline_chart_data([bad])
    assert out["type"] == "timeline"
    assert "error" in out


def test_generate_event_clusters_error(bare_service):
    bad = make_event()
    bad.timestamp = "not-a-datetime"
    out = bare_service._generate_event_clusters([bad])
    assert out["total_clusters"] == 0
    assert "error" in out


def test_generate_impact_analysis_error(bare_service):
    bad = make_event()
    bad.impact_score = "not-a-number"
    out = bare_service._generate_impact_analysis([bad])
    assert "error" in out


def test_generate_entity_involvement_chart_error(bare_service):
    bad = make_event()
    bad.entities_involved = None  # iterating None -> TypeError
    out = bare_service._generate_entity_involvement_chart([bad])
    assert out["type"] == "bar"
    assert "error" in out


# ---------------------------------------------------------------------------
# _classify_event_type: business_transaction + technology + exception
# ---------------------------------------------------------------------------
def test_classify_business_transaction(bare_service):
    result = {"title": ["Big acquisition merger"], "content": [""], "category": [""]}
    assert bare_service._classify_event_type(result) == "business_transaction"


def test_classify_technology_category(bare_service):
    result = {"title": ["something"], "content": [""], "category": ["technology news"]}
    assert bare_service._classify_event_type(result) == "technology"


def test_classify_event_type_exception(bare_service):
    # Missing list structure -> .get(...)[0] raises -> 'unknown'.
    assert bare_service._classify_event_type({"title": None}) == "unknown"


def test_classify_general_fallthrough(bare_service):
    # No keywords match and non-tech category -> 'general' (line 923).
    result = {"title": ["nothing special"], "content": ["ordinary text"],
              "category": ["lifestyle"]}
    assert bare_service._classify_event_type(result) == "general"


# ---------------------------------------------------------------------------
# _generate_impact_analysis: empty events (line 770)
# ---------------------------------------------------------------------------
def test_generate_impact_analysis_empty(bare_service):
    out = bare_service._generate_impact_analysis([])
    assert out == {"total_events": 0, "analysis": {}}


# ---------------------------------------------------------------------------
# _parse_timestamp: outer exception (lines 887-890)
# ---------------------------------------------------------------------------
def test_parse_timestamp_outer_exception(bare_service):
    # A non-string (int) makes strptime raise TypeError -> outer except -> now().
    result = bare_service._parse_timestamp(12345)
    assert isinstance(result, datetime)


# ---------------------------------------------------------------------------
# TimelineVisualizationData default export_formats (lines 86-87)
# ---------------------------------------------------------------------------
def test_timeline_visualization_data_defaults():
    tvd = ets.TimelineVisualizationData(
        timeline_id="tid", topic="AI",
        time_range=(datetime(2026, 1, 1), datetime(2026, 2, 1)),
        events=[], visualization_config={}, chart_data={},
    )
    assert tvd.export_formats == ["json", "csv", "html"]


# ---------------------------------------------------------------------------
# _extract_entities_from_result: exception branch
# ---------------------------------------------------------------------------
def test_extract_entities_exception(bare_service):
    # title stored as a non-indexable -> triggers except -> [].
    assert bare_service._extract_entities_from_result({"title": None}) == []


# ---------------------------------------------------------------------------
# _calculate_impact_score: exception fallback
# ---------------------------------------------------------------------------
def test_calculate_impact_score_exception(bare_service):
    ev = make_event()
    ev.title = None  # .lower() on None -> AttributeError -> 0.5
    assert _run(bare_service._calculate_impact_score(ev)) == 0.5


def test_calculate_impact_score_clamped(bare_service):
    ev = make_event(etype="regulation", impact=0.0,
                    entities=["a", "b", "c", "d", "e", "f"])
    ev.title = "major significant breakthrough revolutionary"
    score = _run(bare_service._calculate_impact_score(ev))
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _check_event_exists: with graph (count > 0) + no traversal + exception
# ---------------------------------------------------------------------------
def test_check_event_exists_true(graph_service):
    svc, gp = graph_service
    gp._execute_traversal = AsyncMock(return_value=[3])
    assert _run(svc._check_event_exists("e1")) is True


def test_check_event_exists_no_traversal(graph_service):
    svc, gp = graph_service
    del gp._execute_traversal
    assert _run(svc._check_event_exists("e1")) is False


def test_check_event_exists_exception(graph_service):
    svc, gp = graph_service
    gp._execute_traversal = AsyncMock(side_effect=RuntimeError("count failed"))
    assert _run(svc._check_event_exists("e1")) is False


# ---------------------------------------------------------------------------
# demo_event_timeline_service: end-to-end demo path (lines 1055-1106)
# ---------------------------------------------------------------------------
def test_demo_runs_end_to_end(monkeypatch, capsys):
    # Disable components so the demo uses sample events (no external backends).
    monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", False, raising=False)
    monkeypatch.setattr(ets, "BASIC_COMPONENTS_AVAILABLE", False, raising=False)
    _run(ets.demo_event_timeline_service())
    out = capsys.readouterr().out
    assert "Event Timeline Service Demo" in out
    assert "Tracking historical events" in out
    assert "Generating timeline API response" in out


def test_demo_handles_exception(monkeypatch, capsys):
    # Make service construction raise so the demo's except branch runs.
    def boom(*a, **k):
        raise RuntimeError("service init blew up")

    monkeypatch.setattr(ets, "EventTimelineService", boom)
    _run(ets.demo_event_timeline_service())
    out = capsys.readouterr().out
    assert "Demo failed" in out
