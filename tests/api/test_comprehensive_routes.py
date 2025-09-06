"""
Comprehensive API Routes Testing Suite for Issue #477

Tests all core API route classes and endpoint handlers to ensure reliable API functionality.
Includes functional testing, API contract validation, error handling, and edge cases.
"""

import os
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

# Import all route modules
from src.api.routes.news_routes import router as news_router
from src.api.routes.search_routes import router as search_router
from src.api.routes.graph_routes import router as graph_router
from src.api.routes.sentiment_routes import router as sentiment_router
from src.api.routes.event_routes import router as event_router
from src.api.routes.admin_routes import router as admin_router

# Import dependencies
from src.database.snowflake_analytics_connector import SnowflakeAnalyticsConnector
from src.knowledge_graph.graph_builder import GraphBuilder


# Test Fixtures
@pytest.fixture(autouse=True)
def mock_env_vars():
    """Set required environment variables for tests."""
    with patch.dict(
        os.environ,
        {
            "SNOWFLAKE_ACCOUNT": "test-account",
            "SNOWFLAKE_USER": "test-user", 
            "SNOWFLAKE_PASSWORD": "test-pass",
            "SNOWFLAKE_WAREHOUSE": "TEST_WH",
            "SNOWFLAKE_DATABASE": "TEST_DB",
            "SNOWFLAKE_SCHEMA": "PUBLIC",
            "NEPTUNE_ENDPOINT": "ws://test-neptune:8182/gremlin",
        },
    ):
        yield


@pytest.fixture
def app():
    """Create comprehensive test FastAPI app with all routes."""
    app = FastAPI(title="NeuroNews API Test", version="1.0.0")
    
    # Include all routers
    app.include_router(news_router)
    app.include_router(search_router)
    app.include_router(graph_router)
    app.include_router(sentiment_router)
    app.include_router(event_router)
    app.include_router(admin_router)
    
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Create mock SnowflakeAnalyticsConnector."""
    mock = AsyncMock(spec=SnowflakeAnalyticsConnector)
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()
    mock.close = AsyncMock()
    mock.execute_query = AsyncMock()
    return mock


@pytest.fixture
def mock_graph():
    """Create mock GraphBuilder."""
    mock = AsyncMock(spec=GraphBuilder)
    mock.connect = AsyncMock()
    mock.close = AsyncMock()
    mock.g = MagicMock()
    mock._execute_traversal = AsyncMock()
    return mock


@pytest.fixture
def mock_admin_user():
    """Mock admin user for authentication."""
    return {
        "sub": "admin-123",
        "role": "admin",
        "email": "admin@test.com",
        "exp": 9999999999  # Far future
    }


@pytest.fixture  
def mock_regular_user():
    """Mock regular user for authentication."""
    return {
        "sub": "user-123",
        "role": "free",
        "email": "user@test.com",
        "exp": 9999999999
    }


# Sample test data
@pytest.fixture
def sample_articles():
    """Sample article data for testing."""
    return [
        (
            "article1",
            "AI Revolution in Healthcare",
            "https://example.com/ai-healthcare",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            "TechNews",
            "Technology",
            0.8,
            "POSITIVE",
        ),
        (
            "article2", 
            "Climate Change Impact on Agriculture",
            "https://example.com/climate-agriculture",
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            "EnvironmentDaily",
            "Environment",
            -0.3,
            "NEGATIVE",
        )
    ]


@pytest.fixture
def sample_detailed_article():
    """Sample detailed article with content and entities."""
    return [
        (
            "article1",
            "AI Revolution in Healthcare",
            "https://example.com/ai-healthcare", 
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            "TechNews",
            "Technology",
            "Artificial intelligence is transforming healthcare through machine learning algorithms...",
            0.8,
            "POSITIVE",
            ["AI", "Healthcare", "Machine Learning"]
        )
    ]


# ============================================================================
# NEWS ROUTES TESTS
# ============================================================================

class TestNewsRoutes:
    """Test suite for News Routes functionality."""

    def test_get_articles_by_topic_success(self, client, mock_db, sample_articles):
        """Test successful article retrieval by topic."""
        mock_db.execute_query.return_value = sample_articles
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news/articles/topic/AI", params={"limit": 10})
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["title"] == "AI Revolution in Healthcare"
        assert data[0]["sentiment"]["score"] == 0.8

    def test_get_articles_by_topic_validation_error(self, client, mock_db):
        """Test input validation for topic search."""
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            # Invalid limit values
            response = client.get("/news/articles/topic/AI", params={"limit": 0})
            assert response.status_code == 422
            
            response = client.get("/news/articles/topic/AI", params={"limit": 101}) 
            assert response.status_code == 422

    def test_get_articles_with_filters(self, client, mock_db, sample_articles):
        """Test article retrieval with multiple filters."""
        mock_db.execute_query.return_value = sample_articles
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get(
                "/news/articles",
                params={
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-01-31T23:59:59Z", 
                    "source": "TechNews",
                    "category": "Technology"
                }
            )
        
        assert response.status_code == 200
        # Verify query parameters were used correctly
        call_args = mock_db.execute_query.call_args
        assert len(call_args[0][1]) == 4  # 4 parameters for filters

    def test_get_article_by_id_success(self, client, mock_db, sample_detailed_article):
        """Test successful retrieval of specific article."""
        mock_db.execute_query.return_value = sample_detailed_article
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news/articles/article1")
        
        assert response.status_code == 200
        article = response.json()
        assert article["id"] == "article1"
        assert article["content"] is not None
        assert "entities" in article

    def test_get_article_by_id_not_found(self, client, mock_db):
        """Test 404 response for non-existent article."""
        mock_db.execute_query.return_value = []
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news/articles/nonexistent")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_database_connection_error(self, client, mock_db):
        """Test handling of database connection errors."""
        mock_db.execute_query.side_effect = Exception("Connection failed")
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news/articles")
        
        assert response.status_code == 500
        assert "Database error" in response.json()["detail"]


# ============================================================================
# SEARCH ROUTES TESTS  
# ============================================================================

class TestSearchRoutes:
    """Test suite for Search Routes functionality."""

    def test_search_articles_basic(self, client, mock_db, sample_articles):
        """Test basic article search functionality."""
        mock_db.execute_query.side_effect = [sample_articles, [(2,)]]  # Results + count
        
        with patch("src.api.routes.search_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/search/articles", params={"q": "AI"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "AI"
        assert len(data["results"]) == 2
        assert data["total_results"] == 2

    def test_search_articles_with_filters(self, client, mock_db, sample_articles):
        """Test search with multiple filters."""
        mock_db.execute_query.side_effect = [sample_articles, [(1,)]]
        
        with patch("src.api.routes.search_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get(
                "/search/articles", 
                params={
                    "q": "AI",
                    "category": "Technology",
                    "source": "TechNews",
                    "sort_by": "date"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["filters"]["category"] == "Technology"
        assert data["filters"]["sort_by"] == "date"

    def test_search_query_validation(self, client, mock_db):
        """Test search query validation."""
        with patch("src.api.routes.search_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            # Empty query should fail
            response = client.get("/search/articles", params={"q": ""})
            assert response.status_code == 422

    def test_get_search_facets(self, client, mock_db):
        """Test search facets retrieval."""
        mock_db.execute_query.side_effect = [
            [("Technology", 10), ("Health", 5)],  # Categories
            [("TechNews", 8), ("HealthDaily", 7)]  # Sources
        ]
        
        with patch("src.api.routes.search_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/search/facets")
        
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert "sources" in data
        assert len(data["categories"]) == 2

    def test_get_search_suggestions(self, client, mock_db):
        """Test search suggestions functionality."""
        mock_db.execute_query.return_value = [
            ("AI Revolution", "TechNews", "Technology", 3),
            ("AI Healthcare", "MedNews", "Health", 2)
        ]
        
        with patch("src.api.routes.search_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/search/suggestions", params={"q": "AI"})
        
        assert response.status_code == 200
        suggestions = response.json()
        assert len(suggestions) == 2
        assert suggestions[0]["text"] == "AI Revolution"

    def test_search_error_handling(self, client, mock_db):
        """Test search error handling."""
        mock_db.execute_query.side_effect = Exception("Database error")
        
        with patch("src.api.routes.search_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/search/articles", params={"q": "test"})
        
        assert response.status_code == 500
        assert "Search error" in response.json()["detail"]


# ============================================================================
# GRAPH ROUTES TESTS
# ============================================================================

class TestGraphRoutes:
    """Test suite for Graph Routes functionality."""

    def test_get_related_entities_success(self, client, mock_graph):
        """Test successful related entities retrieval."""
        mock_graph._execute_traversal.return_value = [
            {"name": ["Related Entity 1"], "label": "Organization"},
            {"name": ["Related Entity 2"], "label": "Person"}
        ]
        
        with patch("src.api.routes.graph_routes.graph_builder_instance", mock_graph):
            response = client.get(
                "/graph/related_entities",
                params={"entity": "TestEntity", "max_depth": 2}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["entity"] == "TestEntity"
        assert len(data["related_entities"]) == 2

    def test_get_related_entities_with_filters(self, client, mock_graph):
        """Test related entities with type and relationship filters."""
        mock_graph._execute_traversal.return_value = [
            {"name": ["Filtered Entity"], "label": "Organization"}
        ]
        
        with patch("src.api.routes.graph_routes.graph_builder_instance", mock_graph):
            response = client.get(
                "/graph/related_entities",
                params={
                    "entity": "TestEntity",
                    "entity_type": "Organization",
                    "relationship_types": ["WORKS_FOR", "PARTNERS_WITH"]
                }
            )
        
        assert response.status_code == 200

    def test_get_event_timeline_success(self, client, mock_graph):
        """Test successful event timeline retrieval."""
        mock_graph._execute_traversal.return_value = [
            {
                "event_name": "Tech Conference 2024",
                "date": "2024-03-15",
                "location": "San Francisco"
            }
        ]
        
        with patch("src.api.routes.graph_routes.graph_builder_instance", mock_graph):
            response = client.get(
                "/graph/event_timeline",
                params={"topic": "Technology"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["topic"] == "Technology"
        assert len(data["events"]) == 1

    def test_graph_health_check_success(self, client, mock_graph):
        """Test successful graph database health check."""
        mock_graph._execute_traversal.return_value = [{"id": 1}]
        
        with patch("src.api.routes.graph_routes.graph_builder_instance", mock_graph):
            response = client.get("/graph/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_graph_connection_error(self, client, mock_graph):
        """Test graph database connection errors."""
        mock_graph._execute_traversal.side_effect = ConnectionError("Graph DB unavailable")
        
        with patch("src.api.routes.graph_routes.graph_builder_instance", mock_graph):
            response = client.get("/graph/health")
        
        assert response.status_code == 503
        assert "connection error" in response.json()["detail"].lower()

    def test_graph_service_unavailable(self, client):
        """Test handling when graph service is unavailable."""
        with patch("src.api.routes.graph_routes.graph_builder_instance", None):
            response = client.get("/graph/health")
        
        assert response.status_code == 503
        assert "not available" in response.json()["detail"]


# ============================================================================ 
# SENTIMENT ROUTES TESTS
# ============================================================================

class TestSentimentRoutes:
    """Test suite for Sentiment Routes functionality."""

    def test_get_sentiment_trends_basic(self, client, mock_db):
        """Test basic sentiment trends retrieval."""
        # Mock for trends query
        mock_db.execute_query.side_effect = [
            [  # Trends data
                (datetime(2024, 1, 1), "POSITIVE", 10, 0.8, 0.5, 0.9),
                (datetime(2024, 1, 1), "NEGATIVE", 5, -0.3, -0.5, -0.1)
            ],
            [  # Overall sentiment
                ("POSITIVE", 10, 0.8, 66.67),
                ("NEGATIVE", 5, -0.3, 33.33)
            ],
            [(15,)]  # Total count
        ]
        
        with patch("src.api.routes.sentiment_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news_sentiment")
        
        assert response.status_code == 200
        data = response.json()
        assert "sentiment_trends" in data
        assert "overall_sentiment" in data
        assert data["article_count"] == 15

    def test_get_sentiment_trends_with_filters(self, client, mock_db):
        """Test sentiment trends with topic and date filters."""
        mock_db.execute_query.side_effect = [[], [], [(0,)]]
        
        with patch("src.api.routes.sentiment_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get(
                "/news_sentiment",
                params={
                    "topic": "AI",
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-01-31T23:59:59Z",
                    "group_by": "week"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["topic_filter"] == "AI"
        assert data["group_by"] == "week"

    def test_get_sentiment_summary(self, client, mock_db):
        """Test sentiment summary retrieval."""
        mock_db.execute_query.return_value = [
            ("POSITIVE", 20, 0.7, 0.2),
            ("NEGATIVE", 10, -0.4, 0.3),
            ("NEUTRAL", 5, 0.0, 0.1)
        ]
        
        with patch("src.api.routes.sentiment_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news_sentiment/summary", params={"days": 7})
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_articles"] == 35
        assert "positive" in data["summary"]
        assert "negative" in data["summary"]

    def test_get_topic_sentiment_analysis(self, client, mock_db):
        """Test topic-based sentiment analysis."""
        mock_db.execute_query.return_value = [
            ("TECHNOLOGY", "POSITIVE", 15, 0.6),
            ("TECHNOLOGY", "NEGATIVE", 5, -0.3),
            ("HEALTH", "POSITIVE", 10, 0.8)
        ]
        
        with patch("src.api.routes.sentiment_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get(
                "/news_sentiment/topics",
                params={"days": 7, "min_articles": 3}
            )
        
        assert response.status_code == 200
        topics = response.json()
        assert len(topics) == 2
        assert topics[0]["topic"] == "TECHNOLOGY"

    def test_sentiment_database_error(self, client, mock_db):
        """Test sentiment routes database error handling."""
        mock_db.execute_query.side_effect = Exception("Database connection failed")
        
        with patch("src.api.routes.sentiment_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news_sentiment")
        
        assert response.status_code == 500
        assert "Error retrieving sentiment trends" in response.json()["detail"]


# ============================================================================
# EVENT ROUTES TESTS  
# ============================================================================

class TestEventRoutes:
    """Test suite for Event Routes functionality."""
    
    @patch("src.api.routes.event_routes.get_clusterer")
    def test_get_breaking_news_success(self, mock_get_clusterer, client):
        """Test successful breaking news retrieval."""
        mock_clusterer = AsyncMock()
        mock_clusterer.get_breaking_news.return_value = [
            {
                "cluster_id": "cluster-1",
                "cluster_name": "Tech Event",
                "event_type": "breaking",
                "category": "Technology",
                "trending_score": 0.9,
                "impact_score": 0.8,
                "velocity_score": 0.7,
                "cluster_size": 15,
                "first_article_date": "2024-01-01T00:00:00Z",
                "last_article_date": "2024-01-01T12:00:00Z",
                "event_duration_hours": 12.0,
                "source_count": 5,
                "avg_confidence": 0.85
            }
        ]
        mock_get_clusterer.return_value = mock_clusterer
        
        response = client.get("/api/v1/breaking_news")
        
        assert response.status_code == 200
        events = response.json()
        assert len(events) == 1
        assert events[0]["cluster_name"] == "Tech Event"

    @patch("src.api.routes.event_routes.get_redshift_connection_params")
    def test_get_event_clusters_success(self, mock_conn_params, client):
        """Test successful event clusters retrieval."""
        mock_conn_params.return_value = {"host": "test", "port": 5432}
        
        with patch("psycopg2.connect") as mock_connect:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                {
                    "cluster_id": "cluster-1",
                    "cluster_name": "Event Cluster",
                    "event_type": "trending", 
                    "category": "Technology",
                    "cluster_size": 10,
                    "silhouette_score": 0.7,
                    "cohesion_score": 0.8,
                    "separation_score": 0.6,
                    "trending_score": 0.9,
                    "impact_score": 0.8,
                    "velocity_score": 0.7,
                    "first_article_date": datetime(2024, 1, 1),
                    "last_article_date": datetime(2024, 1, 2),
                    "event_duration_hours": 24.0,
                    "primary_sources": '["Source1", "Source2"]',
                    "geographic_focus": '["US", "Europe"]',
                    "key_entities": '["Entity1", "Entity2"]',
                    "status": "active",
                    "created_at": datetime(2024, 1, 1)
                }
            ]
            
            mock_connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            
            response = client.get("/api/v1/events/clusters")
            
            assert response.status_code == 200
            clusters = response.json()
            assert len(clusters) == 1

    def test_event_detection_request_validation(self, client):
        """Test event detection request validation."""
        # Invalid clustering method
        response = client.post("/api/v1/events/detect", json={
            "category": "Technology",
            "days_back": 7,
            "max_articles": 100,
            "clustering_method": "invalid_method",
            "min_cluster_size": 3
        })
        
        assert response.status_code == 422

    def test_event_routes_error_handling(self, client):
        """Test error handling in event routes."""
        with patch("src.api.routes.event_routes.get_clusterer") as mock_get_clusterer:
            mock_clusterer = AsyncMock()
            mock_clusterer.get_breaking_news.side_effect = Exception("Service unavailable")
            mock_get_clusterer.return_value = mock_clusterer
            
            response = client.get("/api/v1/breaking_news")
            
            assert response.status_code == 500
            assert "Error retrieving breaking news" in response.json()["detail"]


# ============================================================================
# ADMIN ROUTES TESTS
# ============================================================================

class TestAdminRoutes:
    """Test suite for Admin Routes functionality."""

    @patch("src.api.routes.admin_routes.require_admin")
    def test_get_system_health_success(self, mock_require_admin, client, mock_db, mock_admin_user):
        """Test successful system health check."""
        mock_require_admin.return_value = mock_admin_user
        mock_db.execute_query.return_value = [(100, 5, 3, datetime.now())]
        
        with patch("src.api.routes.admin_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/admin/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "services" in data
        assert "metrics" in data

    @patch("src.api.routes.admin_routes.require_admin")
    def test_get_user_list(self, mock_require_admin, client, mock_db, mock_admin_user):
        """Test user list retrieval."""
        mock_require_admin.return_value = mock_admin_user
        
        with patch("src.api.routes.admin_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/admin/users", params={"limit": 50})
        
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total_count" in data

    @patch("src.api.routes.admin_routes.require_admin")
    def test_manage_user_success(self, mock_require_admin, client, mock_admin_user):
        """Test successful user management operation."""
        mock_require_admin.return_value = mock_admin_user
        
        response = client.post("/admin/users/manage", json={
            "user_id": "user-123",
            "action": "deactivate",
            "reason": "Policy violation"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "successfully" in data["message"]
        assert data["action"] == "deactivate"

    @patch("src.api.routes.admin_routes.require_admin")
    def test_manage_user_invalid_action(self, mock_require_admin, client, mock_admin_user):
        """Test user management with invalid action."""
        mock_require_admin.return_value = mock_admin_user
        
        response = client.post("/admin/users/manage", json={
            "user_id": "user-123",
            "action": "invalid_action"
        })
        
        assert response.status_code == 400
        assert "Invalid action" in response.json()["detail"]

    @patch("src.api.routes.admin_routes.require_admin")
    def test_get_system_statistics(self, mock_require_admin, client, mock_db, mock_admin_user):
        """Test system statistics retrieval."""
        mock_require_admin.return_value = mock_admin_user
        mock_db.execute_query.side_effect = [
            [(500, 25, 8, 0.6)],  # Article stats
            [("Technology", 100), ("Health", 80)],  # Categories
            [("Source1", 150), ("Source2", 120)]  # Sources
        ]
        
        with patch("src.api.routes.admin_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/admin/system/stats", params={"days_back": 30})
        
        assert response.status_code == 200
        data = response.json()
        assert "article_stats" in data
        assert "top_categories" in data
        assert "top_sources" in data

    @patch("src.api.routes.admin_routes.require_admin")
    def test_update_system_config(self, mock_require_admin, client, mock_admin_user):
        """Test system configuration update."""
        mock_require_admin.return_value = mock_admin_user
        
        response = client.post("/admin/system/config", json={
            "setting_key": "api.rate_limit",
            "setting_value": 2000,
            "category": "api"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "updated successfully" in data["message"]

    @patch("src.api.routes.admin_routes.require_admin")  
    def test_get_system_config(self, mock_require_admin, client, mock_admin_user):
        """Test system configuration retrieval."""
        mock_require_admin.return_value = mock_admin_user
        
        response = client.get("/admin/system/config")
        
        assert response.status_code == 200
        data = response.json()
        assert "configuration" in data

    @patch("src.api.routes.admin_routes.require_admin")
    def test_toggle_maintenance_mode(self, mock_require_admin, client, mock_admin_user):
        """Test maintenance mode toggle."""
        mock_require_admin.return_value = mock_admin_user
        
        response = client.post(
            "/admin/system/maintenance",
            params={"enabled": True, "message": "Scheduled maintenance"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["maintenance_enabled"] == True

    @patch("src.api.routes.admin_routes.require_admin")
    def test_get_system_logs(self, mock_require_admin, client, mock_admin_user):
        """Test system logs retrieval."""
        mock_require_admin.return_value = mock_admin_user
        
        response = client.get(
            "/admin/logs",
            params={"level": "ERROR", "hours": 24, "limit": 100}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "time_range" in data

    def test_admin_authentication_required(self, client):
        """Test that admin endpoints require authentication."""
        response = client.get("/admin/health")
        assert response.status_code in [401, 403]  # Depends on auth implementation


# ============================================================================
# INTEGRATION AND PERFORMANCE TESTS  
# ============================================================================

class TestAPIIntegration:
    """Integration tests across multiple API endpoints."""

    def test_search_to_details_workflow(self, client, mock_db):
        """Test complete workflow from search to article details."""
        # Mock search results
        search_results = [
            ("article1", "AI Article", "url1", datetime.now(), "Source1", "Tech", "snippet...", 0.8, "POSITIVE", 2)
        ]
        # Mock article details
        article_details = [
            ("article1", "AI Article", "url1", datetime.now(), "Source1", "Tech", "Full content...", 0.8, "POSITIVE", ["AI", "Tech"])
        ]
        
        mock_db.execute_query.side_effect = [search_results, [(1,)], article_details]
        
        with patch("src.api.routes.search_routes.SnowflakeAnalyticsConnector", return_value=mock_db), \
             patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            
            # Step 1: Search for articles
            search_response = client.get("/search/articles", params={"q": "AI"})
            assert search_response.status_code == 200
            
            search_data = search_response.json()
            article_id = search_data["results"][0]["id"]
            
            # Step 2: Get detailed article
            detail_response = client.get(f"/news/articles/{article_id}")
            assert detail_response.status_code == 200
            
            detail_data = detail_response.json()
            assert detail_data["content"] == "Full content..."

    def test_sentiment_analysis_workflow(self, client, mock_db):
        """Test sentiment analysis workflow."""
        # Mock sentiment trends and summary data
        mock_db.execute_query.side_effect = [
            # Trends data
            [(datetime.now(), "POSITIVE", 10, 0.8, 0.5, 0.9)],
            # Overall sentiment  
            [("POSITIVE", 10, 0.8, 100.0)],
            # Total count
            [(10,)],
            # Summary data
            [("POSITIVE", 10, 0.8, 0.2)]
        ]
        
        with patch("src.api.routes.sentiment_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            # Get sentiment trends
            trends_response = client.get("/news_sentiment", params={"topic": "AI"})
            assert trends_response.status_code == 200
            
            # Get sentiment summary
            summary_response = client.get("/news_sentiment/summary")
            assert summary_response.status_code == 200


class TestAPIErrorHandling:
    """Test comprehensive error handling across all routes."""

    def test_database_failure_handling(self, client, mock_db):
        """Test handling of database failures across routes."""
        mock_db.execute_query.side_effect = Exception("Database connection lost")
        
        routes_to_test = [
            ("/news/articles", "GET"),
            ("/search/articles?q=test", "GET"),
            ("/news_sentiment", "GET")
        ]
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db), \
             patch("src.api.routes.search_routes.SnowflakeAnalyticsConnector", return_value=mock_db), \
             patch("src.api.routes.sentiment_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            
            for route, method in routes_to_test:
                if method == "GET":
                    response = client.get(route)
                assert response.status_code == 500

    def test_invalid_parameters_handling(self, client, mock_db):
        """Test handling of invalid parameters across routes."""
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            # Invalid limit values
            response = client.get("/news/articles/topic/test", params={"limit": -1})
            assert response.status_code == 422
            
            response = client.get("/news/articles/topic/test", params={"limit": 1001})
            assert response.status_code == 422

    def test_missing_environment_variables(self, client):
        """Test handling of missing environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            response = client.get("/news/articles")
            assert response.status_code == 500
            assert "SNOWFLAKE_ACCOUNT" in response.json()["detail"]


class TestAPIPerformance:
    """Basic performance testing for API endpoints."""

    def test_large_result_set_handling(self, client, mock_db):
        """Test handling of large result sets."""
        # Create large mock dataset
        large_dataset = [
            (f"article{i}", f"Title {i}", f"url{i}", datetime.now(), f"Source{i%5}", 
             f"Category{i%3}", 0.5, "NEUTRAL")
            for i in range(100)
        ]
        
        mock_db.execute_query.return_value = large_dataset
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news/articles/topic/test", params={"limit": 100})
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 100

    def test_concurrent_request_simulation(self, client, mock_db):
        """Simulate handling of concurrent requests."""
        mock_db.execute_query.return_value = [
            ("article1", "Title", "url", datetime.now(), "Source", "Category", 0.5, "NEUTRAL")
        ]
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            # Simulate multiple requests
            responses = []
            for i in range(10):
                response = client.get(f"/news/articles/topic/test{i}")
                responses.append(response)
            
            # All should succeed
            for response in responses:
                assert response.status_code == 200


# ============================================================================
# API CONTRACT AND VALIDATION TESTS
# ============================================================================

class TestAPIContracts:
    """Test API contracts, response schemas, and validation."""

    def test_news_article_response_schema(self, client, mock_db, sample_articles):
        """Test news article response follows expected schema."""
        mock_db.execute_query.return_value = sample_articles
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news/articles/topic/AI")
        
        assert response.status_code == 200
        articles = response.json()
        
        # Validate response structure
        for article in articles:
            required_fields = ["id", "title", "url", "publish_date", "source", "category", "sentiment"]
            for field in required_fields:
                assert field in article
            
            # Validate sentiment structure
            sentiment = article["sentiment"]
            assert "score" in sentiment
            assert "label" in sentiment

    def test_search_response_schema(self, client, mock_db, sample_articles):
        """Test search response follows expected schema."""
        mock_db.execute_query.side_effect = [sample_articles, [(2,)]]
        
        with patch("src.api.routes.search_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/search/articles", params={"q": "test"})
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate top-level structure
        required_fields = ["query", "results", "total_results", "returned_results", "filters"]
        for field in required_fields:
            assert field in data
        
        # Validate results structure
        for result in data["results"]:
            assert "id" in result
            assert "title" in result
            assert "relevance_score" in result

    def test_http_status_codes(self, client, mock_db):
        """Test correct HTTP status codes are returned."""
        # Test successful responses
        mock_db.execute_query.return_value = []
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news/articles")
            assert response.status_code == 200
        
        # Test not found
        mock_db.execute_query.return_value = []
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news/articles/nonexistent")
            assert response.status_code == 404
        
        # Test validation errors
        response = client.get("/news/articles/topic/test", params={"limit": 0})
        assert response.status_code == 422

    def test_content_type_headers(self, client, mock_db):
        """Test correct content type headers."""
        mock_db.execute_query.return_value = []
        
        with patch("src.api.routes.news_routes.SnowflakeAnalyticsConnector", return_value=mock_db):
            response = client.get("/news/articles")
        
        assert response.headers["content-type"] == "application/json"


if __name__ == "__main__":
    # Run tests with coverage
    pytest.main([
        __file__,
        "-v",
        "--cov=src.api.routes",
        "--cov-report=term-missing",
        "--cov-report=html"
    ])