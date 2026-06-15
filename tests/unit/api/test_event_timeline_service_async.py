"""Async orchestration tests for EventTimelineService (sample-event fallback)."""

import os
import sys
from datetime import datetime, timedelta

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from api.event_timeline_service import EventTimelineService, HistoricalEvent  # noqa: E402


@pytest.fixture
def service():
    # No graph populator -> uses sample-event fallback path end-to-end
    svc = EventTimelineService()
    svc.graph_populator = None
    return svc


class TestTrackHistoricalEvents:
    @pytest.mark.asyncio
    async def test_returns_enhanced_events(self, service):
        start = datetime(2026, 1, 1)
        end = datetime(2026, 3, 1)
        events = await service.track_historical_events("AI Technology", start, end)
        assert len(events) >= 1
        assert all(isinstance(e, HistoricalEvent) for e in events)
        # chronological order
        assert events == sorted(events, key=lambda e: e.timestamp)
        # impact score computed during enhancement
        assert all(0.0 <= e.impact_score <= 1.0 for e in events)

    @pytest.mark.asyncio
    async def test_default_time_range(self, service):
        events = await service.track_historical_events("Climate")
        assert isinstance(events, list)


class TestTimelineApiResponse:
    @pytest.mark.asyncio
    async def test_full_response_with_visualization(self, service):
        resp = await service.generate_timeline_api_response(
            "AI", max_events=10, include_visualizations=True
        )
        assert resp["topic"] == "AI"
        assert resp["total_events"] >= 1
        assert isinstance(resp["events"], list)
        assert resp["metadata"]["visualization_included"] is True

    @pytest.mark.asyncio
    async def test_response_without_visualization(self, service):
        resp = await service.generate_timeline_api_response(
            "AI", include_visualizations=False
        )
        assert resp["metadata"]["visualization_included"] is False

    @pytest.mark.asyncio
    async def test_max_events_limit(self, service):
        resp = await service.generate_timeline_api_response("AI", max_events=1)
        assert resp["total_events"] <= 1


class TestVisualizationData:
    @pytest.mark.asyncio
    async def test_generate_visualization_data(self, service):
        events = await service.track_historical_events(
            "AI", datetime(2026, 1, 1), datetime(2026, 2, 1)
        )
        viz = await service.generate_visualization_data(topic="AI", events=events)
        assert isinstance(viz, dict)
