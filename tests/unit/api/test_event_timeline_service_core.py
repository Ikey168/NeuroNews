"""Tests for core logic of src/api/event_timeline_service.py."""

import os
import sys
from datetime import datetime, timedelta

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import api.event_timeline_service as ets  # noqa: E402
from api.event_timeline_service import (  # noqa: E402
    EventTimelineService,
    HistoricalEvent,
    TimelineVisualizationData,
)


@pytest.fixture
def service(monkeypatch):
    # disable component init (avoids constructing graph/NLP backends)
    monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", False, raising=False)
    monkeypatch.setattr(ets, "BASIC_COMPONENTS_AVAILABLE", False, raising=False)
    return EventTimelineService()


def event(eid="e1", ts=None, etype="announcement", impact=0.5):
    return HistoricalEvent(
        event_id=eid, title=f"Title {eid}", description="d",
        timestamp=ts or datetime(2026, 1, 15), topic="tech", event_type=etype,
        entities_involved=["x"], impact_score=impact,
    )


class TestDataclasses:
    def test_historical_event_post_init(self):
        e = HistoricalEvent(
            event_id="e", title="t", description="d", timestamp=datetime(2026, 1, 1),
            topic="tech", event_type="announcement", entities_involved=[],
        )
        assert e.related_events == []
        assert e.metadata == {}

    def test_visualization_data_defaults(self):
        v = TimelineVisualizationData(
            timeline_id="t", topic="tech",
            time_range=(datetime(2026, 1, 1), datetime(2026, 2, 1)),
            events=[], visualization_config={}, chart_data={},
        )
        assert v.export_formats == ["json", "csv", "html"]


class TestInit:
    def test_defaults(self, service):
        assert service.max_events_per_timeline == 100
        assert service.default_time_window_days == 365
        assert "default" in service.visualization_themes
        assert "dark" in service.visualization_themes

    def test_custom_config(self, monkeypatch):
        monkeypatch.setattr(ets, "ENHANCED_COMPONENTS_AVAILABLE", False, raising=False)
        monkeypatch.setattr(ets, "BASIC_COMPONENTS_AVAILABLE", False, raising=False)
        s = EventTimelineService({"max_events_per_timeline": 10})
        assert s.max_events_per_timeline == 10


class TestSampleEvents:
    def test_generates_events(self, service):
        events = service._generate_sample_events(
            "AI", datetime(2026, 1, 1), datetime(2026, 3, 1)
        )
        assert 2 <= len(events) <= 5
        assert all("id" in e and "title" in e for e in events)
        assert events[0]["category"] == "Technology"  # AI topic

    def test_general_category(self, service):
        events = service._generate_sample_events(
            "Sports", datetime(2026, 1, 1), datetime(2026, 2, 1)
        )
        assert events[0]["category"] == "General"


class TestParseTimestamp:
    @pytest.mark.parametrize("ts,year", [
        ("2026-01-15T10:30:00.000Z", 2026),
        ("2026-01-15T10:30:00Z", 2026),
        ("2026-01-15T10:30:00", 2026),
        ("2026-01-15 10:30:00", 2026),
        ("2026-01-15", 2026),
    ])
    def test_formats(self, service, ts, year):
        assert service._parse_timestamp(ts).year == year

    def test_unparseable_returns_now(self, service):
        result = service._parse_timestamp("garbage")
        assert isinstance(result, datetime)


class TestEventClusters:
    def test_clusters_by_type_and_month(self, service):
        events = [
            event("e1", datetime(2026, 1, 5), "announcement", 0.8),
            event("e2", datetime(2026, 1, 20), "announcement", 0.6),
            event("e3", datetime(2026, 2, 5), "research", 0.4),
        ]
        result = service._generate_event_clusters(events)
        assert result["total_clusters"] == 2  # announcement_2026-01, research_2026-02
        ann = [c for c in result["clusters"] if c["event_type"] == "announcement"][0]
        assert ann["event_count"] == 2
        assert ann["average_impact"] == pytest.approx(0.7)

    def test_empty(self, service):
        result = service._generate_event_clusters([])
        assert result["total_clusters"] == 0


class TestImpactAnalysis:
    def test_analysis(self, service):
        events = [event("e1", impact=0.9), event("e2", impact=0.6), event("e3", impact=0.2)]
        analysis = service._generate_impact_analysis(events)
        assert analysis["total_events"] == 3
        stats = analysis["impact_statistics"]
        assert stats["max_impact"] == 0.9
        assert stats["high_impact_events"] == 1
        assert stats["medium_impact_events"] == 1
        assert stats["low_impact_events"] == 1
        assert len(analysis["top_impact_events"]) == 3

    def test_empty(self, service):
        assert service._generate_impact_analysis([])["total_events"] == 0
