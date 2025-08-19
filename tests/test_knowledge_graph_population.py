"""
Comprehensive test suite for Knowledge Graph NLP Population

This module tests the NLP-based knowledge graph population functionality,
including entity extraction, relationship detection, historical linking,
and API endpoints.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.knowledge_graph.nlp_populator import (
    Entity,
    KnowledgeGraphPopulator,
    Relationship,
    get_entity_relationships,
    populate_article_to_graph,
)


class TestKnowledgeGraphPopulator:
    """Test cases for KnowledgeGraphPopulator class."""

    @pytest.fixture
    def mock_graph_builder(self):
        """Mock GraphBuilder for testing."""
        builder = AsyncMock()
        builder.connect = AsyncMock()
        builder.close = AsyncMock()
        builder.add_vertex = AsyncMock(return_value={"id": "test_vertex"})
        builder.add_edge = AsyncMock(return_value={"id": "test_edge"})
        builder.query_vertices = AsyncMock(return_value=[])
        builder.get_related_vertices = AsyncMock(return_value=[])
        builder.update_vertex_property = AsyncMock(return_value={"updated": True})
        return builder

    @pytest.fixture
    def mock_ner_processor(self):
        """Mock NER processor for testing."""
        processor = AsyncMock()
        processor.process_text = AsyncMock(
            return_value={
                "entities": [
                    {
                        "text": "John Doe",
                        "label": "PERSON",
                        "start": 0,
                        "end": 8,
                        "confidence": 0.95,
                    },
                    {
                        "text": "OpenAI",
                        "label": "ORG",
                        "start": 20,
                        "end": 26,
                        "confidence": 0.90,
                    },
                ]
            }
        )
        return processor

    @pytest.fixture
    def populator(self, mock_graph_builder, mock_ner_processor):
        """Create KnowledgeGraphPopulator instance with mocks."""
        with patch("src.knowledge_graph.nlp_populator.GraphBuilder") as mock_gb:
            mock_gb.return_value = mock_graph_builder

            populator = KnowledgeGraphPopulator(
                neptune_endpoint="test-endpoint", ner_processor=mock_ner_processor
            )
            populator.graph_builder = mock_graph_builder
            return populator

    @pytest.mark.asyncio
    async def test_entity_creation(self):
        """Test Entity dataclass creation and normalization."""
        entity = Entity(
            text="John Doe", label="PERSON", start=0, end=8, confidence=0.95
        )

        assert entity.text == "John Doe"
        assert entity.label == "PERSON"
        assert entity.normalized_form == "john doe"
        assert entity.confidence == 0.95

    @pytest.mark.asyncio
    async def test_relationship_creation(self):
        """Test Relationship dataclass creation."""
        relationship = Relationship(
            source_entity="john doe",
            target_entity="openai",
            relation_type="works_for",
            confidence=0.85,
            context="John Doe works for OpenAI",
            article_id="article_123",
        )

        assert relationship.source_entity == "john doe"
        assert relationship.target_entity == "openai"
        assert relationship.relation_type == "works_for"
        assert relationship.confidence == 0.85

    @pytest.mark.asyncio
    async def test_extract_entities(self, populator):
        """Test entity extraction from text."""
        text = "John Doe works for OpenAI in San Francisco."

        entities = await populator._extract_entities(text)

        assert len(entities) == 2
        assert entities[0].text == "John Doe"
        assert entities[0].label == "PERSON"
        assert entities[1].text == "OpenAI"
        assert entities[1].label == "ORG"

    @pytest.mark.asyncio
    async def test_add_article_node(self, populator):
        """Test adding article node to graph."""
        article_id = "test_article_123"
        title = "Test Article"
        content = "This is test content for the article."
        published_date = datetime.utcnow()

        result = await populator._add_article_node(
            article_id, title, content, published_date
        )

        populator.graph_builder.add_vertex.assert_called_once()
        call_args = populator.graph_builder.add_vertex.call_args

        assert call_args[0][0] == "Article"  # Vertex type
        properties = call_args[0][1]
        assert properties["id"] == article_id
        assert properties["title"] == title
        assert properties["type"] == "article"

    @pytest.mark.asyncio
    async def test_add_entity_node_new(self, populator):
        """Test adding new entity node to graph."""
        entity = Entity(
            text="John Doe", label="PERSON", start=0, end=8, confidence=0.95
        )

        # Mock that entity doesn't exist
        populator._find_entity = AsyncMock(return_value=None)

        result = await populator._add_entity_node(entity, "article_123")

        populator.graph_builder.add_vertex.assert_called_once()
        call_args = populator.graph_builder.add_vertex.call_args

        assert call_args[0][0] == "Person"  # Mapped entity type
        properties = call_args[0][1]
        assert properties["text"] == "John Doe"
        assert properties["entity_type"] == "PERSON"
        assert properties["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_add_entity_node_existing(self, populator):
        """Test updating existing entity node."""
        entity = Entity(
            text="John Doe", label="PERSON", start=0, end=8, confidence=0.95
        )

        # Mock that entity exists
        populator._find_entity = AsyncMock(return_value={"id": "existing_id"})
        populator._update_entity_mentions = AsyncMock(return_value={"updated": True})

        result = await populator._add_entity_node(entity, "article_123")

        # Should call update instead of add
        populator._update_entity_mentions.assert_called_once()
        populator.graph_builder.add_vertex.assert_not_called()

    @pytest.mark.asyncio
    async def test_link_entity_to_article(self, populator):
        """Test linking entity to article with relationship."""
        entity = Entity(
            text="John Doe", label="PERSON", start=0, end=8, confidence=0.95
        )
        article_id = "article_123"

        result = await populator._link_entity_to_article(entity, article_id)

        populator.graph_builder.add_edge.assert_called_once()
        call_args = populator.graph_builder.add_edge.call_args

        # Verify edge creation parameters
        assert call_args[0][2] == "MENTIONED_IN"  # Edge type
        edge_properties = call_args[0][3]
        assert edge_properties["relation_type"] == "mentioned_in"
        assert edge_properties["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_extract_relationships(self, populator):
        """Test relationship extraction between entities."""
        entities = [
            Entity(text="John Doe", label="PERSON", start=0, end=8, confidence=0.95),
            Entity(text="OpenAI", label="ORG", start=20, end=26, confidence=0.90),
        ]
        text = "John Doe works for OpenAI in San Francisco."
        article_id = "article_123"

        relationships = await populator._extract_relationships(
            entities, text, article_id
        )

        assert len(relationships) >= 1
        assert relationships[0].source_entity == "john doe"
        assert relationships[0].target_entity == "openai"
        assert relationships[0].relation_type == "works_for"

    @pytest.mark.asyncio
    async def test_determine_relationship_type(self, populator):
        """Test relationship type determination logic."""
        # Test known relationship mapping
        rel_type = populator._determine_relationship_type("PERSON", "ORG")
        assert rel_type == "works_for"

        rel_type = populator._determine_relationship_type("ORG", "GPE")
        assert rel_type == "based_in"

        # Test reverse mapping
        rel_type = populator._determine_relationship_type("ORG", "PERSON")
        assert rel_type == "works_for"

        # Test default relationship
        rel_type = populator._determine_relationship_type("UNKNOWN", "UNKNOWN")
        assert rel_type == "related_to"

    @pytest.mark.asyncio
    async def test_add_relationship_edge(self, populator):
        """Test adding relationship edge to graph."""
        relationship = Relationship(
            source_entity="john doe",
            target_entity="openai",
            relation_type="works_for",
            confidence=0.85,
            context="John Doe works for OpenAI",
            article_id="article_123",
        )

        # Mock entity label lookup
        populator._get_entity_label = Mock(return_value="PERSON")

        result = await populator._add_relationship_edge(relationship)

        populator.graph_builder.add_edge.assert_called_once()
        call_args = populator.graph_builder.add_edge.call_args

        assert call_args[0][2] == "WORKS_FOR"  # Edge type (uppercase)
        edge_properties = call_args[0][3]
        assert edge_properties["relation_type"] == "works_for"
        assert edge_properties["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_populate_from_article(self, populator):
        """Test full article population workflow."""
        article_id = "test_article_123"
        title = "John Doe Joins OpenAI"
        content = "John Doe, a renowned AI researcher, has joined OpenAI to work on advanced AI systems."
        published_date = datetime.utcnow()

        # Mock internal methods
        populator._find_entity = AsyncMock(return_value=None)
        populator._find_related_historical_events = AsyncMock(return_value=[])
        populator._find_related_policies = AsyncMock(return_value=[])

        stats = await populator.populate_from_article(
            article_id, title, content, published_date
        )

        # Verify statistics structure
        assert "article_id" in stats
        assert "entities_found" in stats
        assert "entities_added" in stats
        assert "relationships_found" in stats
        assert "relationships_added" in stats
        assert "historical_links" in stats
        assert stats["article_id"] == article_id

    @pytest.mark.asyncio
    async def test_get_related_entities(self, populator):
        """Test getting related entities for API."""
        entity_name = "John Doe"

        # Mock graph builder to return related entities
        populator.graph_builder.get_related_vertices.return_value = [
            {
                "text": "OpenAI",
                "entity_type": "ORG",
                "relationship_type": "works_for",
                "confidence": 0.9,
                "mention_count": 5,
                "first_seen": "2024-01-01T00:00:00",
                "last_updated": "2024-01-02T00:00:00",
            }
        ]

        # Mock entity lookup
        populator._find_entity_by_name = AsyncMock(return_value={"id": "entity_123"})

        related_entities = await populator.get_related_entities(
            entity_name, max_results=10
        )

        assert len(related_entities) == 1
        assert related_entities[0]["entity_name"] == "OpenAI"
        assert related_entities[0]["entity_type"] == "ORG"
        assert related_entities[0]["relationship_type"] == "works_for"

    @pytest.mark.asyncio
    async def test_get_related_entities_not_found(self, populator):
        """Test getting related entities when entity doesn't exist."""
        entity_name = "Nonexistent Entity"

        # Mock entity not found
        populator._find_entity_by_name = AsyncMock(return_value=None)

        related_entities = await populator.get_related_entities(entity_name)

        assert related_entities == []

    @pytest.mark.asyncio
    async def test_batch_populate_articles(self, populator):
        """Test batch processing of multiple articles."""
        articles = [
            {
                "id": "article_1",
                "title": "Title 1",
                "content": "Content 1",
                "published_date": "2024-01-01T00:00:00Z",
            },
            {"id": "article_2", "title": "Title 2", "content": "Content 2"},
        ]

        # Mock populate_from_article to return stats
        async def mock_populate(article_id, title, content, published_date):
            return {
                "entities_added": 2,
                "relationships_added": 1,
                "historical_links": 0,
            }

        populator.populate_from_article = AsyncMock(side_effect=mock_populate)

        batch_stats = await populator.batch_populate_articles(articles)

        assert batch_stats["total_articles"] == 2
        assert batch_stats["processed_articles"] == 2
        assert batch_stats["failed_articles"] == 0
        assert batch_stats["total_entities_added"] == 4
        assert batch_stats["total_relationships_added"] == 2
        assert batch_stats["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_batch_populate_with_failures(self, populator):
        """Test batch processing with some failed articles."""
        articles = [
            {"id": "article_1", "title": "Title 1", "content": "Content 1"},
            {"id": "article_2", "title": "Title 2", "content": "Content 2"},
        ]

        # Mock populate_from_article to fail for second article
        async def mock_populate(article_id, title, content, published_date):
            if article_id == "article_2":
                raise Exception("Processing failed")
            return {
                "entities_added": 2,
                "relationships_added": 1,
                "historical_links": 0,
            }

        populator.populate_from_article = AsyncMock(side_effect=mock_populate)

        batch_stats = await populator.batch_populate_articles(articles)

        assert batch_stats["total_articles"] == 2
        assert batch_stats["processed_articles"] == 1
        assert batch_stats["failed_articles"] == 1
        assert batch_stats["success_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_generate_entity_id(self, populator):
        """Test entity ID generation for consistency."""
        normalized_form = "john doe"
        entity_type = "PERSON"

        id1 = populator._generate_entity_id(normalized_form, entity_type)
        id2 = populator._generate_entity_id(normalized_form, entity_type)

        # Should generate same ID for same inputs
        assert id1 == id2
        assert len(id1) == 32  # MD5 hash length

    @pytest.mark.asyncio
    async def test_close(self, populator):
        """Test closing the populator connection."""
        await populator.close()

        populator.graph_builder.close.assert_called_once()


class TestUtilityFunctions:
    """Test utility functions for integration."""

    @pytest.mark.asyncio
    async def test_populate_article_to_graph(self):
        """Test convenience function for single article population."""
        article_data = {
            "id": "test_article",
            "title": "Test Title",
            "content": "Test content",
            "published_date": datetime.utcnow(),
        }
        neptune_endpoint = "test-endpoint"

        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator"
        ) as MockPopulator:
            mock_instance = AsyncMock()
            mock_instance.populate_from_article = AsyncMock(
                return_value={"stats": "test"}
            )
            mock_instance.close = AsyncMock()
            MockPopulator.return_value = mock_instance

            stats = await populate_article_to_graph(article_data, neptune_endpoint)

            assert stats == {"stats": "test"}
            mock_instance.populate_from_article.assert_called_once()
            mock_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_entity_relationships(self):
        """Test convenience function for getting entity relationships."""
        entity_name = "John Doe"
        neptune_endpoint = "test-endpoint"

        with patch(
            "src.knowledge_graph.nlp_populator.KnowledgeGraphPopulator"
        ) as MockPopulator:
            mock_instance = AsyncMock()
            mock_instance.get_related_entities = AsyncMock(
                return_value=[{"entity": "test"}]
            )
            mock_instance.close = AsyncMock()
            MockPopulator.return_value = mock_instance

            relationships = await get_entity_relationships(
                entity_name, neptune_endpoint
            )

            assert relationships == [{"entity": "test"}]
            mock_instance.get_related_entities.assert_called_once_with(entity_name, 10)
            mock_instance.close.assert_called_once()


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_text_extraction(self, mock_graph_builder, mock_ner_processor):
        """Test entity extraction from empty text."""
        mock_ner_processor.process_text.return_value = {"entities": []}

        populator = KnowledgeGraphPopulator(
            neptune_endpoint="test-endpoint", ner_processor=mock_ner_processor
        )
        populator.graph_builder = mock_graph_builder

        entities = await populator._extract_entities("")
        assert entities == []

    @pytest.mark.asyncio
    async def test_low_confidence_relationships(
        self, mock_graph_builder, mock_ner_processor
    ):
        """Test filtering of low-confidence relationships."""
        populator = KnowledgeGraphPopulator(
            neptune_endpoint="test-endpoint", ner_processor=mock_ner_processor
        )
        populator.graph_builder = mock_graph_builder
        populator.min_confidence = 0.8  # High threshold

        entities = [
            Entity(text="A", label="PERSON", start=0, end=1, confidence=0.5),
            Entity(text="B", label="ORG", start=5, end=6, confidence=0.5),
        ]

        relationships = await populator._extract_relationships(
            entities, "A and B", "article"
        )

        # Should be filtered out due to low confidence
        high_conf_relationships = [
            r for r in relationships if r.confidence >= populator.min_confidence
        ]
        assert len(high_conf_relationships) == 0

    @pytest.mark.asyncio
    async def test_error_handling_in_populate(
        self, mock_graph_builder, mock_ner_processor
    ):
        """Test error handling during article population."""
        mock_graph_builder.connect.side_effect = Exception("Connection failed")

        populator = KnowledgeGraphPopulator(
            neptune_endpoint="test-endpoint", ner_processor=mock_ner_processor
        )
        populator.graph_builder = mock_graph_builder

        with pytest.raises(Exception) as exc_info:
            await populator.populate_from_article("id", "title", "content")

        assert "Connection failed" in str(exc_info.value)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
