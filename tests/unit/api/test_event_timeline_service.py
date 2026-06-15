"""Tests for src/api/event_timeline_service.py (pure logic + mocked graph)."""

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import api.event_timeline_service as mod  # noqa: E402
from api.event_timeline_service import (  # noqa: E402
    EventTimelineService,
    HistoricalEvent,
    TimelineVisualizationData,
)


@pytest.fixture
def service():
    return EventTimelineService()


def event(**over):
    base = dict(
        event_id="e1", title="Major breakthrough in AI", description="desc",
        timestamp=datetime(2026, 1, 15), topic="AI", event_type="announcement",
        entities_involved=["OpenAI", "Google"], confidence=0.8, impact_score=0.7,
    )
    base.update(over)
    return HistoricalEvent(**base)


class TestDataclasses:
    def test_historical_event_defaults(self):
        e = HistoricalEvent("e1", "t", "d", datetime.now(), "AI", "general", [])
        assert e.related_events == []
        assert e.metadata == {}

    def test_visualization_data_defaults(self):
        v = TimelineVisualizationData(
            "t1", "AI", (datetime.now(), datetime.now()), [], {}, {}
        )
        assert v.export_formats == ["json", "csv", "html"]


class TestParseTimestamp:
    @pytest.mark.parametrize("ts", [
        "2026-01-15T10:30:00.000Z",
        "2026-01-15T10:30:00Z",
        "2026-01-15T10:30:00",
        "2026-01-15 10:30:00",
        "2026-01-15",
    ])
    def test_valid_formats(self, service, ts):
        result = service._parse_timestamp(ts)
        assert result.year == 2026 and result.month == 1 and result.day == 15

    def test_invalid_falls_back_to_now(self, service):
        result = service._parse_timestamp("garbage")
        assert isinstance(result, datetime)


class TestClassifyEventType:
    @pytest.mark.parametrize("title,expected", [
        ("Company announces new product", "announcement"),
        ("New regulation on data", "regulation"),
        ("Big acquisition deal", "business_transaction"),
        ("New research study findings", "research"),
        ("Just some plain headline", "general"),
    ])
    def test_classify(self, service, title, expected):
        assert service._classify_event_type(
            {"title": [title], "content": [""], "category": [""]}
        ) == expected

    def test_classify_by_category(self, service):
        assert service._classify_event_type(
            {"title": ["x"], "content": ["y"], "category": ["technology"]}
        ) == "technology"


class TestEntityExtraction:
    def test_extracts_known_entities(self, service):
        ents = service._extract_entities_from_result(
            {"title": ["Google and Microsoft launch AI"]}
        )
        assert "Google" in ents and "Microsoft" in ents

    def test_no_entities(self, service):
        assert service._extract_entities_from_result({"title": ["nothing here"]}) == []


class TestProcessGraphResults:
    def test_process(self, service):
        results = [
            {"id": "a1", "title": ["Google announces AI"], "content": ["details"],
             "published_date": "2026-01-15", "author": "Bob", "category": [""]},
        ]
        events = service._process_graph_results(results, "AI")
        assert len(events) == 1
        assert events[0]["event_id"] == "a1"
        assert events[0]["event_type"] == "announcement"
        assert events[0]["topic"] == "AI"

    def test_generate_sample_events(self, service):
        events = service._generate_sample_events(
            "AI Technology", datetime(2026, 1, 1), datetime(2026, 3, 1)
        )
        assert 2 <= len(events) <= 5
        assert all("AI Technology" in e["title"] for e in events)


class TestImpactScore:
    @pytest.mark.asyncio
    async def test_high_impact(self, service):
        score = await service._calculate_impact_score(event())
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_enhance_event_data(self, service):
        data = {
            "event_id": "e1", "title": "Major AI breakthrough", "description": "d",
            "timestamp": datetime(2026, 1, 1), "topic": "AI",
            "event_type": "announcement", "entities_involved": ["OpenAI"],
        }
        enhanced = await service._enhance_event_data(data, include_related=True)
        assert isinstance(enhanced, HistoricalEvent)
        assert enhanced.impact_score >= 0.0


class TestVisualizationHelpers:
    def test_timeline_chart_data(self, service):
        chart = service._prepare_timeline_chart_data([event(), event(event_id="e2")])
        assert chart["type"] == "timeline"
        assert len(chart["data"]["datasets"][0]["data"]) == 2

    def test_event_clusters(self, service):
        clusters = service._generate_event_clusters([event(), event(event_id="e2")])
        assert clusters["total_clusters"] >= 1

    def test_impact_analysis(self, service):
        analysis = service._generate_impact_analysis([event(), event(event_id="e2")])
        assert analysis["total_events"] == 2
        assert "impact_statistics" in analysis

    def test_impact_analysis_empty(self, service):
        assert service._generate_impact_analysis([])["total_events"] == 0

    def test_entity_involvement_chart(self, service):
        chart = service._generate_entity_involvement_chart([event()])
        assert isinstance(chart, dict)


class TestEventDictAndAsync:
    def test_event_to_dict(self, service):
        d = service._event_to_dict(event())
        assert d["event_id"] == "e1"
        assert d["impact_score"] == 0.7
        assert "timestamp" in d

    @pytest.mark.asyncio
    async def test_check_event_exists_no_graph(self, service):
        service.graph_populator = None
        assert await service._check_event_exists("e1") is False

    @pytest.mark.asyncio
    async def test_check_event_exists_with_graph(self, service):
        gp = MagicMock()
        gp._execute_traversal = AsyncMock(return_value=[1])
        service.graph_populator = gp
        assert await service._check_event_exists("e1") is True

    @pytest.mark.asyncio
    async def test_find_related_events(self, service):
        assert await service._find_related_events(event()) == []
