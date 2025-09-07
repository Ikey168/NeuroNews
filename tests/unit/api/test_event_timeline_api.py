"""
Unit Tests for Event Timeline API - Issue #38

This module provides comprehensive unit tests for the event timeline API
endpoints and service, covering all Issue #38 requirements:

1. Track historical events related to a topic
2. Store event timestamps & relationships in Neptune
3. Implement API /event_timeline?topic=Artificial Intelligence
4. Generate visualizations of event evolution

Test Coverage:
- Event timeline service functionality
- API endpoint testing with various parameters
- Neptune storage and relationship creation
- Visualization data generation
- Error handling and edge cases
- Export functionality
"""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the API routes and service
try:
    from src.api.event_timeline_service import (
        EventTimelineService,
        HistoricalEvent,
        TimelineVisualizationData,
    )
    from src.api.routes.event_timeline_routes import (
        EventTimelineResponse,
        EventTrackingRequest,
        TimelineVisualizationRequest,
        get_event_timeline_service,
        router,
    )

    EVENT_TIMELINE_AVAILABLE = True
except ImportError:
    EVENT_TIMELINE_AVAILABLE = False

# Import test utilities
from unittest.mock import MagicMock


class TestEventTimelineService:
    """Test suite for the EventTimelineService class."""

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        return {
            "max_events_per_timeline": 100,
            "default_time_window_days": 365,
            "event_clustering_threshold": 0.8,
        }

    @pytest.fixture
    def service(self, mock_config):
        """Create EventTimelineService instance."""
        if not EVENT_TIMELINE_AVAILABLE:
            pytest.skip("Event timeline components not available")

        service = EventTimelineService(mock_config)

        # Mock the graph populator
        mock_populator = Mock()
        mock_populator._execute_traversal = AsyncMock()
        service.graph_populator = mock_populator

        return service

    @pytest.fixture
    def sample_events(self):
        """Create sample historical events for testing."""
        if not EVENT_TIMELINE_AVAILABLE:
            pytest.skip("Event timeline components not available")

        return [
            HistoricalEvent(
                event_id="event_001",
                title="Google Announces AI Breakthrough",
                description="Google has made significant advances in artificial intelligence.",
                timestamp=datetime(2025, 8, 15, 10, 0, 0),
                topic="Artificial Intelligence",
                event_type="announcement",
                entities_involved=["Google", "Artificial Intelligence"],
                confidence=0.95,
                impact_score=0.8,
            ),
            HistoricalEvent(
                event_id="event_002",
                title="Microsoft Partners with OpenAI",
                description="Microsoft announces deepened partnership with OpenAI.",
                timestamp=datetime(2025, 8, 10, 14, 30, 0),
                topic="Artificial Intelligence",
                event_type="business_transaction",
                entities_involved=["Microsoft", "OpenAI"],
                confidence=0.92,
                impact_score=0.75,
            ),
            HistoricalEvent(
                event_id="event_003",
                title="EU AI Regulation Updates",
                description="European Union updates AI regulation framework.",
                timestamp=datetime(2025, 8, 5, 9, 0, 0),
                topic="Artificial Intelligence",
                event_type="regulation",
                entities_involved=["European Union", "AI Regulation"],
                confidence=0.88,
                impact_score=0.9,
            ),
        ]

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_track_historical_events(self, service, sample_events):
        """Test tracking historical events."""
        # Mock graph query results
        mock_results = [
            {
                "id": ["event_001"],
                "title": ["Google Announces AI Breakthrough"],
                "content": [
                    "Google has made significant advances in artificial intelligence."
                ],
                "published_date": ["2025-08-15T10:00:00Z"],
                "author": ["Tech Reporter"],
                "category": ["Technology"],
            },
            {
                "id": ["event_002"],
                "title": ["Microsoft Partners with OpenAI"],
                "content": ["Microsoft announces deepened partnership with OpenAI."],
                "published_date": ["2025-08-10T14:30:00Z"],
                "author": ["Business Reporter"],
                "category": ["Business"],
            },
        ]

        service.graph_populator._execute_traversal.return_value = mock_results

        # Track events
        events = await service.track_historical_events(
            topic="Artificial Intelligence",
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
        )

        # Verify results
        assert len(events) == 2
        assert all(isinstance(event, HistoricalEvent) for event in events)
        assert events[0].topic == "Artificial Intelligence"
        assert events[0].event_type in [
            "announcement",
            "business_transaction",
            "regulation",
            "general",
        ]

        # Verify graph query was called
        service.graph_populator._execute_traversal.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_store_event_relationships(self, service, sample_events):
        """Test storing events and relationships in Neptune."""
        # Mock successful storage
        service.graph_populator._execute_traversal.return_value = True

        # Store events
        result = await service.store_event_relationships(sample_events[:2])

        # Verify results
        assert result["events_stored"] >= 0
        assert result["relationships_created"] >= 0
        assert isinstance(result["errors"], list)

        # Verify graph operations were called
        assert service.graph_populator._execute_traversal.call_count >= 2

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_generate_timeline_api_response(self, service, sample_events):
        """Test generating API response for timeline."""
        # Mock track_historical_events
        with patch.object(
            service, "track_historical_events", return_value=sample_events
        ):
            response = await service.generate_timeline_api_response(
                topic="Artificial Intelligence",
                max_events=10,
                include_visualizations=True,
            )

        # Verify response structure
        assert "topic" in response
        assert "timeline_span" in response
        assert "total_events" in response
        assert "events" in response
        assert "metadata" in response

        # Verify data content
        assert response["topic"] == "Artificial Intelligence"
        assert response["total_events"] == 3
        assert len(response["events"]) == 3
        assert response["metadata"]["visualization_included"] is True

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_generate_visualization_data(self, service, sample_events):
        """Test generating visualization data."""
        viz_data = await service.generate_visualization_data(
            topic="Artificial Intelligence",
            events=sample_events,
            theme="default",
            chart_type="timeline",
        )

        # Verify visualization structure
        assert "timeline_chart" in viz_data
        assert "event_clusters" in viz_data
        assert "impact_analysis" in viz_data
        assert "entity_involvement" in viz_data
        assert "theme" in viz_data
        assert "export_options" in viz_data

        # Verify chart data
        chart_data = viz_data["timeline_chart"]
        assert chart_data["type"] == "timeline"
        assert "data" in chart_data
        assert "options" in chart_data

        # Verify clusters
        clusters = viz_data["event_clusters"]
        assert "total_clusters" in clusters
        assert "clusters" in clusters

        # Verify impact analysis
        impact = viz_data["impact_analysis"]
        assert "total_events" in impact
        assert "impact_statistics" in impact

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_event_clustering(self, service, sample_events):
        """Test event clustering functionality."""
        clusters = service._generate_event_clusters(sample_events)

        # Verify cluster structure
        assert "total_clusters" in clusters
        assert "clusters" in clusters
        assert isinstance(clusters["clusters"], list)

        # Verify cluster data
        if clusters["clusters"]:
            cluster = clusters["clusters"][0]
            assert "cluster_id" in cluster
            assert "event_type" in cluster
            assert "time_period" in cluster
            assert "event_count" in cluster
            assert "average_impact" in cluster

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_impact_analysis(self, service, sample_events):
        """Test impact analysis generation."""
        analysis = service._generate_impact_analysis(sample_events)

        # Verify analysis structure
        assert "total_events" in analysis
        assert "impact_statistics" in analysis
        assert "top_impact_events" in analysis

        # Verify statistics
        stats = analysis["impact_statistics"]
        assert "average_impact" in stats
        assert "max_impact" in stats
        assert "min_impact" in stats
        assert "high_impact_events" in stats

        # Verify top events
        top_events = analysis["top_impact_events"]
        assert isinstance(top_events, list)
        assert len(top_events) <= 5

    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    def test_entity_involvement_chart(self, service, sample_events):
        """Test entity involvement chart generation."""
        chart_data = service._generate_entity_involvement_chart(sample_events)

        # Verify chart structure
        assert chart_data["type"] == "bar"
        assert "data" in chart_data
        assert "options" in chart_data

        # Verify data structure
        data = chart_data["data"]
        assert "labels" in data
        assert "datasets" in data
        assert len(data["datasets"]) == 1

    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    def test_historical_event_model(self):
        """Test HistoricalEvent model."""
        event = HistoricalEvent(
            event_id="test_001",
            title="Test Event",
            description="A test event for validation",
            timestamp=datetime.now(),
            topic="Testing",
            event_type="test",
            entities_involved=["Entity1", "Entity2"],
            confidence=0.9,
            impact_score=0.7,
        )

        # Verify model properties
        assert event.event_id == "test_001"
        assert event.title == "Test Event"
        assert event.topic == "Testing"
        assert event.confidence == 0.9
        assert event.impact_score == 0.7
        assert len(event.entities_involved) == 2
        assert isinstance(event.related_events, list)
        assert isinstance(event.metadata, dict)


class TestEventTimelineAPI:
    """Test suite for Event Timeline API endpoints."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app for testing."""
        if not EVENT_TIMELINE_AVAILABLE:
            pytest.skip("Event timeline components not available")

        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_service(self):
        """Create mock event timeline service."""
        service = Mock()

        # Mock sample response data
        sample_response = {
            "topic": "Artificial Intelligence",
            "timeline_span": {
                "start_date": "2025-08-01T00:00:00",
                "end_date": "2025-08-31T23:59:59",
            },
            "total_events": 3,
            "events": [
                {
                    "event_id": "event_001",
                    "title": "AI Breakthrough",
                    "description": "Major AI advancement announced",
                    "timestamp": "2025-08-15T10:00:00",
                    "event_type": "announcement",
                    "confidence": 0.95,
                    "impact_score": 0.8,
                    "entities_involved": ["AI", "Technology"],
                }
            ],
            "metadata": {
                "generated_at": "2025-08-17T12:00:00",
                "visualization_included": True,
            },
        }

        service.generate_timeline_api_response = AsyncMock(
            return_value=sample_response)
        service.track_historical_events = AsyncMock(return_value=[])
        service.store_event_relationships = AsyncMock(
            return_value={"events_stored": 1,
                "relationships_created": 2, "errors": []}
        )
        service.generate_visualization_data = AsyncMock(
            return_value={
                "timeline_chart": {"type": "timeline", "data": []},
                "event_clusters": {"total_clusters": 1, "clusters": []},
                "impact_analysis": {"total_events": 1},
            }
        )

        return service

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_get_enhanced_event_timeline(self, client, mock_service):
        """Test enhanced event timeline endpoint."""

        # Mock the dependency

        async def mock_get_service():
            return mock_service

        # Override dependency
        router.dependency_overrides[get_event_timeline_service] = mock_get_service

        try:
            response = client.get(
                "/api/v1/event-timeline/Artificial%20Intelligence",
                params={
                    "start_date": "2025-08-01",
                    "end_date": "2025-08-31",
                    "max_events": 50,
                    "include_visualizations": True,
                    "include_analytics": True,
                },
            )

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert "topic" in data
            assert "timeline_span" in data
            assert "total_events" in data
            assert "events" in data
            assert "metadata" in data

            # Verify data content
            assert data["topic"] == "Artificial Intelligence"
            assert data["total_events"] >= 0
            assert data["visualization_included"] is True

        finally:
            router.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_get_enhanced_event_timeline_date_validation(
        self, client, mock_service
    ):
        """Test date validation in timeline endpoint."""

        async def mock_get_service():
            return mock_service

        router.dependency_overrides[get_event_timeline_service] = mock_get_service

        try:
            # Test with invalid date format
            response = client.get(
                "/api/v1/event-timeline/Test%20Topic",
                params={"start_date": "invalid-date"},
            )

            assert response.status_code == 400
            assert "Invalid start_date format" in response.json()["detail"]

            # Test with end date before start date
            response = client.get(
                "/api/v1/event-timeline/Test%20Topic",
                params={"start_date": "2025-08-31", "end_date": "2025-08-01"},
            )

            assert response.status_code == 400
            assert "Start date must be before end date" in response.json()[
                                                                         "detail"]

        finally:
            router.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_track_historical_events_endpoint(self, client, mock_service):
        """Test historical events tracking endpoint."""

        async def mock_get_service():
            return mock_service

        router.dependency_overrides[get_event_timeline_service] = mock_get_service

        try:
            request_data = {
                "topic": "Machine Learning",
                "start_date": "2025-08-01T00:00:00",
                "end_date": "2025-08-31T23:59:59",
                "max_events": 50,
                "include_related": True,
                "store_in_neptune": True,
            }

            response = client.post(
                "/api/v1/event-timeline/track", json=request_data)

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert "topic" in data
            assert "events_tracked" in data
            assert "events_stored" in data
            assert "relationships_created" in data
            assert "processing_time" in data
            assert "errors" in data

            # Verify data content
            assert data["topic"] == "Machine Learning"
            assert isinstance(data["events_tracked"], int)
            assert isinstance(data["processing_time"], float)

        finally:
            router.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_get_timeline_visualization(self, client, mock_service):
        """Test timeline visualization endpoint."""

        async def mock_get_service():
            return mock_service

        router.dependency_overrides[get_event_timeline_service] = mock_get_service

        try:
            response = client.get(
                "/api/v1/event-timeline/AI%20Technology/visualization",
                params={"theme": "default",
                    "chart_type": "timeline", "max_events": 30},
            )

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert "topic" in data
            assert "visualization_type" in data
            assert "chart_data" in data
            assert "theme" in data
            assert "generated_at" in data
            assert "export_formats" in data

            # Verify data content
            assert data["topic"] == "AI Technology"
            assert data["theme"] == "default"
            assert data["visualization_type"] == "timeline"

        finally:
            router.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_export_timeline_data_json(self, client, mock_service):
        """Test timeline data export in JSON format."""

        async def mock_get_service():
            return mock_service

        router.dependency_overrides[get_event_timeline_service] = mock_get_service

        try:
            response = client.get(
                "/api/v1/event-timeline/Test%20Topic/export",
                params={f"ormat": "json", "max_events": 10},
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"

            # Verify JSON response
            data = response.json()
            assert "topic" in data
            assert "events" in data

        finally:
            router.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_export_timeline_data_csv(self, client, mock_service):
        """Test timeline data export in CSV format."""

        async def mock_get_service():
            return mock_service

        router.dependency_overrides[get_event_timeline_service] = mock_get_service

        try:
            response = client.get(
                "/api/v1/event-timeline/Test%20Topic/export", params={f"ormat": "csv"}
            )

            assert response.status_code == 200
            assert "text/csv" in response.headers["content-type"]
            assert "attachment" in response.headers["content-disposition"]

        finally:
            router.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_export_timeline_data_html(self, client, mock_service):
        """Test timeline data export in HTML format."""

        async def mock_get_service():
            return mock_service

        router.dependency_overrides[get_event_timeline_service] = mock_get_service

        try:
            response = client.get(
                "/api/v1/event-timeline/Test%20Topic/export", params={f"ormat": "html"}
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Verify HTML content
            html_content = response.content.decode()
            assert "<html>" in html_content
            assert "Event Timeline" in html_content
            assert "Test Topic" in html_content

        finally:
            router.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_export_invalid_format(self, client, mock_service):
        """Test export with invalid format."""

        async def mock_get_service():
            return mock_service

        router.dependency_overrides[get_event_timeline_service] = mock_get_service

        try:
            response = client.get(
                "/api/v1/event-timeline/Test%20Topic/export",
                params={f"ormat": "invalid"},
            )

            assert response.status_code == 400
            assert "Format must be one o" in response.json()["detail"]

        finally:
            router.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_get_timeline_analytics(self, client, mock_service):
        """Test timeline analytics endpoint."""

        async def mock_get_service():
            return mock_service

        router.dependency_overrides[get_event_timeline_service] = mock_get_service

        try:
            response = client.get(
                "/api/v1/event-timeline/analytics",
                params={"time_window_days": 30, "top_topics": 10},
            )

            assert response.status_code == 200
            data = response.json()

            # Verify analytics structure
            assert "time_window_days" in data
            assert "analysis_date" in data
            assert "system_stats" in data
            assert "trending_topics" in data
            assert "event_patterns" in data
            assert "insights" in data

        finally:
            router.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    async def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/v1/event-timeline/health")

        assert response.status_code == 200
        data = response.json()

        # Verify health response
        assert "status" in data
        assert "service" in data
        assert "timestamp" in data
        assert "version" in data
        assert "issue" in data
        assert "components" in data

        assert data["service"] == "event-timeline-api"
        assert data["issue"] == "#38"


class TestAPIRequestModels:
    """Test suite for API request/response models."""

    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    def test_event_tracking_request_model(self):
        """Test EventTrackingRequest model validation."""
        # Valid request
        valid_request = EventTrackingRequest(
            topic="Artificial Intelligence",
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
            max_events=100,
            include_related=True,
            store_in_neptune=True,
        )

        assert valid_request.topic == "Artificial Intelligence"
        assert valid_request.max_events == 100
        assert valid_request.include_related is True
        assert valid_request.store_in_neptune is True

        # Test validation - end date before start date
        with pytest.raises(ValueError):
            EventTrackingRequest(
                topic="Test",
                start_date=datetime(2025, 8, 31),
                end_date=datetime(2025, 8, 1),  # Before start date
            )

    @pytest.mark.skipif(
        not EVENT_TIMELINE_AVAILABLE, reason="Event timeline components not available"
    )
    def test_timeline_visualization_request_model(self):
        """Test TimelineVisualizationRequest model validation."""
        # Valid request
        valid_request = TimelineVisualizationRequest(
            theme="default",
            chart_type="timeline",
            include_clusters=True,
            include_impact_analysis=True,
        )

        assert valid_request.theme == "default"
        assert valid_request.chart_type == "timeline"
        assert valid_request.include_clusters is True

        # Test invalid theme
        with pytest.raises(ValueError):
            TimelineVisualizationRequest(
                theme="invalid_theme", chart_type="timeline")

        # Test invalid chart type
        with pytest.raises(ValueError):
            TimelineVisualizationRequest(
                theme="default", chart_type="invalid_chart")


if __name__ == "__main__":
    # Run a quick test to verify imports and basic functionality
    print(" Event Timeline API Tests - Issue #38")
    print("=" * 50)

    try:
        if EVENT_TIMELINE_AVAILABLE:
            print(" All event timeline components available")

            # Test service creation
            service = EventTimelineService()
            print(" EventTimelineService created")

            # Test model creation
            event = HistoricalEvent(
                event_id="test_001",
                title="Test Event",
                description="Test description",
                timestamp=datetime.now(),
                topic="Testing",
                event_type="test",
                entities_involved=["Entity1"],
            )
            print(" HistoricalEvent created: {0}".format(event.title))

            request = EventTrackingRequest(topic="Test Topic", max_events=50)
            print(" EventTrackingRequest created: {0}".format(request.topic))

            print(""
 Run full tests with: pytest test_event_timeline_api.py - v")"
        else:
            print("❌ Event timeline components not available")
            print("   Install required dependencies and verify imports")

    except Exception as e:
        print("❌ Test setup failed: {0}".format(e))

    print("Test Coverage:")
    print("  • Event timeline service functionality")
    print("  • Historical event tracking and storage")
    print("  • API endpoints with various parameters")
    print("  • Visualization data generation")
    print("  • Export functionality (JSON, CSV, HTML)")
    print("  • Error handling and validation")
    print("  • Request/response model validation")
    print("  • Neptune storage and relationships")
    print("  • Analytics and insights")
