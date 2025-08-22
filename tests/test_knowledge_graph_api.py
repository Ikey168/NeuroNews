"""
Integration tests for Knowledge Graph API routes

This module tests the FastAPI endpoints for knowledge graph functionality,
including the /related_entities endpoint and other knowledge graph operations.
"""

from unittest.mock import AsyncMock, patch
import os

import pytest
from fastapi.testclient import TestClient

from src.api.app import app  # Fixed import path
from src.knowledge_graph.nlp_populator import KnowledgeGraphPopulator

@pytest.fixture
def client():
    """FastAPI test client with WAF disabled."""
    # Set environment variable to disable WAF for testing
    os.environ["DISABLE_WAF_FOR_TESTS"] = "true"
    test_client = TestClient(app)
    yield test_client
    # Clean up
    if "DISABLE_WAF_FOR_TESTS" in os.environ:
        del os.environ["DISABLE_WAF_FOR_TESTS"]


class TestKnowledgeGraphAPIRoutes:
    """Test cases for knowledge graph API endpoints."""

    @pytest.fixture
    def mock_populator(self):
        """Mock KnowledgeGraphPopulator for testing."""
        populator = AsyncMock(spec=KnowledgeGraphPopulator)
        populator.close = AsyncMock()
        return populator

    def test_get_related_entities_success(self, client):
        """Test successful related entities retrieval."""
        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator.get_related_entities"
        ) as mock_get_related_entities, patch(
            "src.knowledge_graph.nlp_populator.GraphBuilder"
        ) as mock_graph_builder_class:
            # Mock the GraphBuilder to use websocket mode
            mock_graph_builder_instance = AsyncMock()
            mock_graph_builder_class.return_value = mock_graph_builder_instance
            
            # Mock the get_related_entities method directly
            mock_get_related_entities.return_value = [
                {
                    "entity_name": "OpenAI",
                    "entity_type": "ORG",
                    "relationship_type": "works_for",
                    "confidence": 0.9,
                    "mention_count": 5,
                    "first_seen": "2024-01-01T00:00:00",
                    "last_updated": "2024-01-02T00:00:00",
                }
            ]

            response = client.get("/api/v1/related_entities?entity_name=John Doe")

            assert response.status_code == 200
            data = response.json()

            assert data["query_entity"] == "John Doe"
            assert data["total_results"] == 1
            assert data["status"] == "success"
            assert len(data["related_entities"]) == 1
            assert data["related_entities"][0]["entity_name"] == "OpenAI"

    def test_get_related_entities_with_params(self, client):
        """Test related entities with additional parameters."""
        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator.get_related_entities"
        ) as mock_get_related_entities, patch(
            "src.knowledge_graph.nlp_populator.GraphBuilder"
        ) as mock_graph_builder_class:
            # Mock the GraphBuilder to use websocket mode
            mock_graph_builder_instance = AsyncMock()
            mock_graph_builder_class.return_value = mock_graph_builder_instance
            
            mock_get_related_entities.return_value = [
                {
                    "entity_name": "High Confidence Entity",
                    "entity_type": "ORG",
                    "relationship_type": "works_for",
                    "confidence": 0.95,
                    "mention_count": 10,
                    "first_seen": "2024-01-01T00:00:00",
                    "last_updated": "2024-01-02T00:00:00",
                },
                {
                    "entity_name": "Low Confidence Entity",
                    "entity_type": "ORG",
                    "relationship_type": "associated_with",
                    "confidence": 0.5,
                    "mention_count": 2,
                    "first_seen": "2024-01-01T00:00:00",
                    "last_updated": "2024-01-02T00:00:00",
                },
            ]

            response = client.get(
                "/api/v1/related_entities"
                "?entity_name=Test Entity"
                "&max_results=20"
                "&include_confidence=true"
                "&min_confidence=0.8"
            )

            assert response.status_code == 200
            data = response.json()

            assert data["max_results_requested"] == 20
            assert data["min_confidence_threshold"] == 0.8
            # Should filter out low confidence entity
            assert data["total_results"] == 1
            assert data["related_entities"][0]["confidence"] == 0.95

    def test_get_related_entities_no_confidence(self, client):
        """Test related entities without confidence scores."""
        with patch(
            "src.api.routes.knowledge_graph_routes.get_graph_populator"
        ) as mock_get_populator:
            mock_populator = AsyncMock()
            mock_populator.get_related_entities.return_value = [
                {
                    "entity_name": "Test Entity",
                    "entity_type": "ORG",
                    "relationship_type": "works_for",
                    "confidence": 0.9,
                    "mention_count": 5,
                    "first_seen": "2024-01-01T00:00:00",
                    "last_updated": "2024-01-02T00:00:00",
                }
            ]
            mock_populator.close = AsyncMock()
            mock_get_populator.return_value = mock_populator

            response = client.get(
                "/api/v1/related_entities" "?entity_name=Test Entity" "&include_confidence=false"
            )

            assert response.status_code == 200
            data = response.json()

            # Confidence should be removed from results
            assert "confidence" not in data["related_entities"][0]

    def test_get_related_entities_invalid_input(self, client):
        """Test related entities with invalid input."""
        response = client.get("/api/v1/related_entities?entity_name=x")

        assert response.status_code == 400
        data = response.json()
        assert "at least 2 characters" in data["detail"]

    def test_get_related_entities_empty_results(self, client):
        """Test related entities when no results found."""
        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator.get_related_entities"
        ) as mock_get_related_entities, patch(
            "src.knowledge_graph.nlp_populator.GraphBuilder"
        ) as mock_graph_builder_class:
            # Mock the GraphBuilder to use websocket mode
            mock_graph_builder_instance = AsyncMock()
            mock_graph_builder_class.return_value = mock_graph_builder_instance
            
            mock_get_related_entities.return_value = []

            response = client.get("/api/v1/related_entities?entity_name=Nonexistent Entity")

            assert response.status_code == 200
            data = response.json()

            assert data["total_results"] == 0
            assert data["related_entities"] == []
            assert data["status"] == "success"

    def test_get_entity_details_success(self, client):
        """Test successful entity details retrieval."""
        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator._find_entity"
        ) as mock_find_entity, patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator.get_related_entities"
        ) as mock_get_related_entities, patch(
            "src.knowledge_graph.nlp_populator.GraphBuilder"
        ) as mock_graph_builder_class:
            # Mock the GraphBuilder to use websocket mode
            mock_graph_builder_instance = AsyncMock()
            mock_graph_builder_class.return_value = mock_graph_builder_instance
            
            # Mock _find_entity to return entity data
            mock_find_entity.return_value = {
                "id": "entity_123",
                "text": "John Doe",
                "entity_type": "PERSON",
                "normalized_form": "john doe",
                "mention_count": 5,
                "first_seen": "2024-01-01T00:00:00",
                "confidence": 0.95,
                "source_articles": ["article_1", "article_2"],
            }
            
            # Mock get_related_entities
            mock_get_related_entities.return_value = [
                {"entity_name": "OpenAI", "relationship_type": "works_for"}
            ]

            response = client.get("/api/v1/entity_details/entity_123")

            assert response.status_code == 200
            data = response.json()

            assert data["entity_id"] == "entity_123"
            assert data["entity_name"] == "John Doe"
            assert data["entity_type"] == "PERSON"
            assert "relationships" in data
            assert "source_articles" in data

    def test_get_entity_details_not_found(self, client):
        """Test entity details when entity not found."""
        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator._find_entity"
        ) as mock_find_entity, patch(
            "src.knowledge_graph.nlp_populator.GraphBuilder"
        ) as mock_graph_builder_class:
            # Mock the GraphBuilder to use websocket mode
            mock_graph_builder_instance = AsyncMock()
            mock_graph_builder_class.return_value = mock_graph_builder_instance
            
            # Mock _find_entity to return None for entity not found
            mock_find_entity.return_value = None

            response = client.get("/api/v1/entity_details/nonexistent_entity")

            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"]

    def test_populate_article_success(self, client):
        """Test successful article population."""
        article_data = {
            "id": "test_article_123",
            "title": "Test Article",
            "content": "This is test content with John Doe and OpenAI.",
            "published_date": "2024-01-01T00:00:00Z",
        }

        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator.populate_from_article"
        ) as mock_populate_from_article, patch(
            "src.knowledge_graph.nlp_populator.GraphBuilder"
        ) as mock_graph_builder_class:
            # Mock the GraphBuilder to use websocket mode
            mock_graph_builder_instance = AsyncMock()
            mock_graph_builder_class.return_value = mock_graph_builder_instance
            
            # Mock populate_from_article to return expected results
            mock_populate_from_article.return_value = {
                "article_id": "test_article_123",
                "entities_found": 2,
                "entities_added": 2,
                "relationships_found": 1,
                "relationships_added": 1,
                "historical_links": 0,
            }

            response = client.post("/api/v1/populate_article", json=article_data)

            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "success"
            assert "processing_stats" in data
            assert data["processing_stats"]["entities_added"] == 2

    def test_populate_article_missing_fields(self, client):
        """Test article population with missing required fields."""
        incomplete_data = {
            "title": "Test Article",
            "content": "Test content",
            # Missing 'id' field
        }

        response = client.post("/api/v1/populate_article", json=incomplete_data)

        assert response.status_code == 400
        data = response.json()
        assert "Missing required field: id" in data["detail"]

    def test_batch_populate_success(self, client):
        """Test successful batch article population."""
        articles = [
            {
                "id": "article_1",
                "title": "Article 1",
                "content": "Content 1 with John Doe",
            },
            {
                "id": "article_2",
                "title": "Article 2",
                "content": "Content 2 with OpenAI",
            },
        ]

        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator.batch_populate_articles"
        ) as mock_batch_populate_articles, patch(
            "src.knowledge_graph.nlp_populator.GraphBuilder"
        ) as mock_graph_builder_class:
            # Mock the GraphBuilder to use websocket mode
            mock_graph_builder_instance = AsyncMock()
            mock_graph_builder_class.return_value = mock_graph_builder_instance
            
            # Mock batch_populate_articles to return expected results
            mock_batch_populate_articles.return_value = {
                "total_articles": 2,
                "processed_articles": 2,
                "failed_articles": 0,
                "total_entities_added": 4,
                "total_relationships_added": 2,
                "success_rate": 1.0,
            }

            response = client.post("/api/v1/batch_populate", json=articles)

            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "success"
            assert data["batch_stats"]["success_rate"] == 1.0
            assert data["batch_stats"]["total_articles"] == 2

    def test_batch_populate_empty_list(self, client):
        """Test batch population with empty article list."""
        response = client.post("/api/v1/batch_populate", json=[])

        assert response.status_code == 400
        data = response.json()
        assert "No articles provided" in data["detail"]

    def test_batch_populate_too_large(self, client):
        """Test batch population with too many articles."""
        # Create list with 101 articles (exceeds limit of 100)
        articles = [
            {
                "id": "article_{0}".format(i),
                "title": "Title {0}".format(i),
                "content": "Content {0}".format(i),
            }
            for i in range(101)
        ]

        response = client.post("/api/v1/batch_populate", json=articles)

        assert response.status_code == 400
        data = response.json()
        assert "Batch size too large" in data["detail"]

    def test_get_knowledge_graph_stats(self, client):
        """Test knowledge graph statistics endpoint."""
        with patch(
            "src.api.routes.knowledge_graph_routes.get_graph_populator"
        ) as mock_get_populator:
            mock_populator = AsyncMock()
            mock_populator.close = AsyncMock()
            mock_get_populator.return_value = mock_populator

            response = client.get("/api/v1/knowledge_graph_stats")

            assert response.status_code == 200
            data = response.json()

            assert "total_entities" in data
            assert "total_relationships" in data
            assert "total_articles" in data
            assert data["status"] == "success"

    def test_search_entities_success(self, client):
        """Test entity search endpoint."""
        with patch(
            "src.api.routes.knowledge_graph_routes.get_graph_populator"
        ) as mock_get_populator:
            mock_populator = AsyncMock()
            mock_populator.close = AsyncMock()
            mock_get_populator.return_value = mock_populator

            response = client.get("/api/v1/search_entities?query=John Doe")

            assert response.status_code == 200
            data = response.json()

            assert data["query"] == "John Doe"
            assert "results" in data
            assert data["status"] == "success"

    def test_search_entities_short_query(self, client):
        """Test entity search with too short query."""
        response = client.get("/api/v1/search_entities?query=x")

        assert response.status_code == 400
        data = response.json()
        assert "at least 2 characters" in data["detail"]

    def test_error_handling_server_error(self, client):
        """Test API error handling for server errors."""
        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator.get_related_entities"
        ) as mock_get_related_entities, patch(
            "src.knowledge_graph.nlp_populator.GraphBuilder"
        ) as mock_graph_builder_class:
            # Mock the GraphBuilder to use websocket mode
            mock_graph_builder_instance = AsyncMock()
            mock_graph_builder_class.return_value = mock_graph_builder_instance
            
            # Mock get_related_entities to raise an exception
            mock_get_related_entities.side_effect = Exception(
                "Database connection failed"
            )

            response = client.get("/api/v1/related_entities?entity_name=Test Entity")

            assert response.status_code == 500
            data = response.json()
            assert "Failed to retrieve related entities" in data["detail"]


class TestAPIParameterValidation:
    """Test API parameter validation and edge cases."""

    def test_related_entities_parameter_bounds(self, client):
        """Test parameter boundary validation for related entities."""
        with patch(
            "src.api.routes.knowledge_graph_routes.get_graph_populator"
        ) as mock_get_populator:
            mock_populator = AsyncMock()
            mock_populator.get_related_entities.return_value = []
            mock_populator.close = AsyncMock()
            mock_get_populator.return_value = mock_populator

            # Test minimum max_results
            response = client.get("/api/v1/related_entities?entity_name=Test&max_results=1")
            assert response.status_code == 200

            # Test maximum max_results
            response = client.get("/api/v1/related_entities?entity_name=Test&max_results=100")
            assert response.status_code == 200

            # Test below minimum
            response = client.get("/api/v1/related_entities?entity_name=Test&max_results=0")
            assert response.status_code == 422  # Validation error

            # Test above maximum
            response = client.get("/api/v1/related_entities?entity_name=Test&max_results=101")
            assert response.status_code == 422  # Validation error

    def test_confidence_parameter_bounds(self, client):
        """Test confidence parameter validation."""
        with patch(
            "src.api.routes.knowledge_graph_routes.get_graph_populator"
        ) as mock_get_populator:
            mock_populator = AsyncMock()
            mock_populator.get_related_entities.return_value = []
            mock_populator.close = AsyncMock()
            mock_get_populator.return_value = mock_populator

            # Valid confidence values
            response = client.get("/api/v1/related_entities?entity_name=Test&min_confidence=0.0")
            assert response.status_code == 200

            response = client.get("/api/v1/related_entities?entity_name=Test&min_confidence=1.0")
            assert response.status_code == 200

            # Invalid confidence values
            response = client.get("/api/v1/related_entities?entity_name=Test&min_confidence=-0.1")
            assert response.status_code == 422

            response = client.get("/api/v1/related_entities?entity_name=Test&min_confidence=1.1")
            assert response.status_code == 422


class TestAPIIntegration:
    """Integration tests for API workflows."""

    def test_full_workflow_populate_and_query(self, client):
        """Test full workflow: populate article then query related entities."""
        # First populate an article
        article_data = {
            "id": "workflow_test_article",
            "title": "John Doe Joins OpenAI",
            "content": "John Doe, a renowned researcher, has joined OpenAI to work on AI safety.",
        }

        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator.populate_from_article"
        ) as mock_populate_from_article, patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator.get_related_entities"
        ) as mock_get_related_entities, patch(
            "src.knowledge_graph.nlp_populator.GraphBuilder"
        ) as mock_graph_builder_class:
            # Mock the GraphBuilder to use websocket mode
            mock_graph_builder_instance = AsyncMock()
            mock_graph_builder_class.return_value = mock_graph_builder_instance

            # Mock population response
            mock_populate_from_article.return_value = {
                "article_id": "workflow_test_article",
                "entities_found": 2,
                "entities_added": 2,
                "relationships_found": 1,
                "relationships_added": 1,
            }

            # Mock related entities response
            mock_get_related_entities.return_value = [
                {
                    "entity_name": "OpenAI",
                    "entity_type": "ORG",
                    "relationship_type": "works_for",
                    "confidence": 0.9,
                }
            ]

            # Step 1: Populate article
            populate_response = client.post("/api/v1/populate_article", json=article_data)
            assert populate_response.status_code == 200

            # Step 2: Query related entities
            query_response = client.get("/api/v1/related_entities?entity_name=John Doe")
            assert query_response.status_code == 200

            query_data = query_response.json()
            assert len(query_data["related_entities"]) == 1
            assert query_data["related_entities"][0]["entity_name"] == "OpenAI"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
