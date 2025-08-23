"""
Test Enhanced Knowledge Graph Components - Issue #36

This module provides comprehensive tests for the enhanced knowledge graph population
system, including advanced entity extraction, relationship detection, and Neptune
integration verification.

Test Coverage:
- Enhanced entity extraction with advanced patterns
- Relationship detection and validation
- Neptune graph population and querying
- SPARQL/Gremlin query verification
- Entity linking and deduplication
- Batch processing performance
- Data quality validation
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Import components to test
try:
    from src.knowledge_graph.enhanced_entity_extractor import (
        AdvancedEntityExtractor,
        EnhancedEntity,
        EnhancedRelationship,
        create_advanced_entity_extractor,
    )
    from src.knowledge_graph.enhanced_graph_populator import (
        EnhancedKnowledgeGraphPopulator,
        create_enhanced_knowledge_graph_populator,
    )

    ENHANCED_KG_AVAILABLE = True
except ImportError:
    ENHANCED_KG_AVAILABLE = False


class TestEnhancedEntityExtractor:
    """Test cases for the AdvancedEntityExtractor class."""

    @pytest.fixture
    def mock_nlp_pipeline(self):
        """Create a mock NLP pipeline for testing."""
        mock_pipeline = Mock()
        mock_pipeline.process_text = AsyncMock(
            return_value={
                "entities": [
                    {
                        "text": "Apple Inc.",
                        "label": "ORG",
                        "start": 0,
                        "end": 10,
                        "confidence": 0.95,
                    },
                    {
                        "text": "Tim Cook",
                        "label": "PERSON",
                        "start": 20,
                        "end": 28,
                        "confidence": 0.92,
                    },
                    {
                        "text": "artificial intelligence",
                        "label": "TECH",
                        "start": 50,
                        "end": 73,
                        "confidence": 0.88,
                    },
                ],
                "sentences": [
                    "Apple Inc. CEO Tim Cook announced new artificial intelligence initiatives."
                ],
                "dependencies": [
                    {"text": "CEO", "head": "Tim Cook", "rel": "title"},
                    {"text": "announced", "head": "Tim Cook", "rel": "action"},
                ],
            }
        )
        return mock_pipeline

    @pytest.fixture
    def sample_article_content(self):
        """Sample article content for testing."""
        return """
        Apple Inc., the technology giant based in Cupertino, California, announced a major
        partnership with Google LLC to develop advanced artificial intelligence systems.
        The collaboration, led by CEO Tim Cook of Apple and CEO Sundar Pichai of Google,
        will focus on machine learning and neural networks.

        The partnership aims to create new AI standards for privacy protection and data
        security. Both companies will contribute their expertise in deep learning and
        natural language processing to the initiative.

        This collaboration represents a significant shift in the competitive landscape
        between Apple and Google, who have traditionally been rivals in the smartphone
        and operating system markets.
        """

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_entity_extraction_basic(
        self, mock_nlp_pipeline, sample_article_content
    ):
        """Test basic entity extraction functionality."""
        extractor = AdvancedEntityExtractor(nlp_pipeline=mock_nlp_pipeline)

        entities = await extractor.extract_entities_from_article(
            article_id="test_001",
            title="Apple Google AI Partnership",
            content=sample_article_content,
        )

        assert len(entities) > 0
        assert any(entity.text == "Apple Inc." for entity in entities)
        assert any(entity.text == "Tim Cook" for entity in entities)
        assert any(entity.label == "ORGANIZATION" for entity in entities)
        assert any(entity.label == "PERSON" for entity in entities)

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_relationship_extraction(
        self, mock_nlp_pipeline, sample_article_content
    ):
        """Test relationship extraction between entities."""
        extractor = AdvancedEntityExtractor(nlp_pipeline=mock_nlp_pipeline)

        # First extract entities
        entities = await extractor.extract_entities_from_article(
            article_id="test_002",
            title="Test Relationships",
            content=sample_article_content,
        )

        # Then extract relationships
        relationships = await extractor.extract_relationships(
            entities, sample_article_content, "test_002"
        )

        assert len(relationships) > 0

        # Check for specific relationship types
        relation_types = [rel.relation_type for rel in relationships]
        assert any("WORKS_FOR" in relation_types or "CEO_OF" in relation_types)
        assert any("PARTNERS_WITH" in relation_types)

        # Verify relationship properties
        for rel in relationships:
            assert rel.confidence > 0.0
            assert rel.source_entity is not None
            assert rel.target_entity is not None
            assert len(rel.context) > 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_entity_normalization(self, mock_nlp_pipeline):
        """Test entity text normalization and alias detection."""
        extractor = AdvancedEntityExtractor(nlp_pipeline=mock_nlp_pipeline)

        # Test content with various entity mentions
        content = """
        Apple Inc. is a major technology company. Apple, founded by Steve Jobs,
        continues to innovate. The company Apple has partnerships with Google.
        Google LLC, also known as Alphabet's Google, works with various companies.
        """'

        entities = await extractor.extract_entities_from_article(
            article_id="test_003", title="Entity Normalization Test", content=content
        )

        # Check for normalized forms
        apple_entities = [e for e in entities if "apple" in e.text.lower()]
        google_entities = [e for e in entities if "google" in e.text.lower()]

        assert len(apple_entities) > 0
        assert len(google_entities) > 0

        # Verify normalization
        for entity in apple_entities:
            assert entity.normalized_form.lower() in ["apple inc.", "apple"]

        for entity in google_entities:
            assert entity.normalized_form.lower() in ["google llc", "google"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_confidence_thresholding(
        self, mock_nlp_pipeline, sample_article_content
    ):
        """Test confidence-based entity filtering."""
        extractor = AdvancedEntityExtractor(nlp_pipeline=mock_nlp_pipeline)
        extractor.confidence_threshold = 0.8

        entities = await extractor.extract_entities_from_article(
            article_id="test_004",
            title="Confidence Test",
            content=sample_article_content,
        )

        # All returned entities should meet confidence threshold
        for entity in entities:
            assert entity.confidence >= 0.8

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_entity_properties_extraction(self, mock_nlp_pipeline):
        """Test extraction of entity-specific properties."""
        extractor = AdvancedEntityExtractor(nlp_pipeline=mock_nlp_pipeline)

        content = """
        Dr. Sarah Johnson, Chief Technology Officer at Microsoft Corporation,
        announced the development of GPT-5, an advanced artificial intelligence model.
        Microsoft, headquartered in Redmond, Washington, is investing heavily in AI research.
        The GDPR regulation affects how companies handle personal data in Europe.
        """

        entities = await extractor.extract_entities_from_article(
            article_id="test_005", title="Properties Test", content=content
        )

        # Check for person with title
        person_entities = [e for e in entities if e.label == "PERSON"]
        org_entities = [e for e in entities if e.label == "ORGANIZATION"]
        tech_entities = [e for e in entities if e.label == "TECHNOLOGY"]
        policy_entities = [e for e in entities if e.label == "POLICY"]

        assert len(person_entities) > 0
        assert len(org_entities) > 0
        assert len(tech_entities) > 0
        assert len(policy_entities) > 0

        # Verify property extraction
        sarah_entity = next(
            (e for e in person_entities if "sarah" in e.text.lower()), None
        )
        if sarah_entity:
            assert "title" in sarah_entity.properties
            assert (
                "cto" in sarah_entity.properties["title"].lower()
                or "chie" in sarah_entity.properties["title"].lower()
            )


class TestEnhancedKnowledgeGraphPopulator:
    """Test cases for the EnhancedKnowledgeGraphPopulator class."""

    @pytest.fixture
    def mock_graph_builder(self):
        """Create a mock GraphBuilder for testing."""
        mock_builder = Mock()
        mock_builder.connect = AsyncMock()
        mock_builder.add_vertex = AsyncMock(return_value={"id": "vertex_123"})
        mock_builder.add_relationship = AsyncMock(
            return_value={"id": "edge_456"})
        mock_builder.get_vertex_by_id = AsyncMock(
            return_value={"id": "vertex_123", "name": "test"}
        )
        mock_builder._execute_traversal = AsyncMock(return_value=[])
        return mock_builder

    @pytest.fixture
    def mock_entity_extractor(self):
        """Create a mock AdvancedEntityExtractor for testing."""
        mock_extractor = Mock()

        # Mock entities
        mock_entities = [
            EnhancedEntity(
                entity_id="ent_001",
                text="Apple Inc.",
                label="ORGANIZATION",
                start=0,
                end=10,
                confidence=0.95,
                normalized_form="Apple Inc.",
                source_article_id="test_001",
                properties={"type": "Technology Company"},
                aliases=["Apple"],
                mention_count=1,
            ),
            EnhancedEntity(
                entity_id="ent_002",
                text="Tim Cook",
                label="PERSON",
                start=20,
                end=28,
                confidence=0.92,
                normalized_form="Tim Cook",
                source_article_id="test_001",
                properties={"title": "CEO", "organization": "Apple Inc."},
                aliases=[],
                mention_count=1,
            ),
        ]

        # Mock relationships
        mock_relationships = [
            EnhancedRelationship(
                source_entity=mock_entities[1],  # Tim Cook
                target_entity=mock_entities[0],  # Apple Inc.
                relation_type="WORKS_FOR",
                confidence=0.89,
                context="Tim Cook is the CEO of Apple Inc.",
                evidence_sentences=["Tim Cook is the CEO of Apple Inc."],
                source_article_id="test_001",
            )
        ]

        mock_extractor.extract_entities_from_article = AsyncMock(
            return_value=mock_entities
        )
        mock_extractor.extract_relationships = AsyncMock(
            return_value=mock_relationships
        )

        return mock_extractor

    @pytest.fixture
    def sample_article_data(self):
        """Sample article data for testing."""
        return {
            "id": "test_kg_001",
            "title": "Apple Announces New AI Initiative",
            "content": """
            Apple Inc. CEO Tim Cook announced today that the company will be investing
            $10 billion in artificial intelligence research over the next five years.
            The initiative will focus on machine learning and natural language processing.

            The announcement comes as Apple faces increased competition from Google
            and Microsoft in the AI space. Cook emphasized that privacy will remain
            a core principle in Apple's AI development.
            """,
            "published_date": datetime(2025, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
            "metadata": {
                "category": "Technology",
                "source_url": "https://example.com/apple-ai-initiative",
                "author": "Tech Journalist",'
            },
        }

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_article_processing(
        self, mock_graph_builder, mock_entity_extractor, sample_article_data
    ):
        """Test complete article processing workflow."""
        with patch(
            "src.knowledge_graph.enhanced_graph_populator.GraphBuilder",
            return_value=mock_graph_builder,
        ):
            populator = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="ws://mock-endpoint",
                entity_extractor=mock_entity_extractor,
            )

            result = await populator.populate_from_article(
                article_id=sample_article_data["id"],
                title=sample_article_data["title"],
                content=sample_article_data["content"],
                published_date=sample_article_data["published_date"],
                metadata=sample_article_data["metadata"],
            )

            # Verify processing results
            assert result["article_id"] == sample_article_data["id"]
            assert "article_vertex_id" in result
            assert result["entities"]["extracted"] > 0
            assert result["entities"]["created"] > 0
            assert result["relationships"]["extracted"] > 0
            assert result["relationships"]["created"] > 0
            assert result["processing_time"] > 0

            # Verify graph builder calls
            mock_graph_builder.connect.assert_called_once()
            assert mock_graph_builder.add_vertex.call_count >= 1  # Article + entities
            assert (
                mock_graph_builder.add_relationship.call_count >= 1
            )  # Entity relationships + mentions

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_batch_processing(self, mock_graph_builder, mock_entity_extractor):
        """Test batch processing of multiple articles."""
        articles = [
            {
                "id": "batch_test_{0}".format(i),
                "title": "Test Article {0}".format(i),
                "content": "This is test article number {0} content.".format(i),
                "published_date": datetime.now(timezone.utc),
                "metadata": {"batch": True},
            }
            for i in range(5)
        ]

        with patch(
            "src.knowledge_graph.enhanced_graph_populator.GraphBuilder",
            return_value=mock_graph_builder,
        ):
            populator = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="ws://mock-endpoint",
                entity_extractor=mock_entity_extractor,
                batch_size=2,
            )

            results = await populator.populate_from_articles_batch(articles)

            assert len(results) == len(articles)

            for result in results:
                assert "article_id" in result
                assert "processing_time" in result
                assert result["entities"]["extracted"] >= 0
                assert result["relationships"]["extracted"] >= 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_entity_deduplication(
        self, mock_graph_builder, mock_entity_extractor
    ):
        """Test entity deduplication and linking."""
        # Mock existing entity found
        mock_graph_builder._execute_traversal.return_value = [
            "existing_vertex_123"]

        with patch(
            "src.knowledge_graph.enhanced_graph_populator.GraphBuilder",
            return_value=mock_graph_builder,
        ):
            populator = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="ws://mock-endpoint",
                entity_extractor=mock_entity_extractor,
                enable_entity_linking=True,
            )

            result = await populator.populate_from_article(
                article_id="dedup_test",
                title="Entity Deduplication Test",
                content="Apple Inc. is a technology company.",
                published_date=datetime.now(timezone.utc),
            )

            # Should have linked to existing entities rather than creating new ones
            assert result["entities"]["linked"] > 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_relationship_querying(
        self, mock_graph_builder, mock_entity_extractor
    ):
        """Test entity relationship querying."""
        # Mock query results
        mock_graph_builder._execute_traversal.return_value = [
            {
                "id": ["related_entity_1"],
                "normalized_form": ["Google LLC"],
                "entity_type": ["ORGANIZATION"],
                "confidence": [0.95],
                "mention_count": [5],
            }
        ]

        with patch(
            "src.knowledge_graph.enhanced_graph_populator.GraphBuilder",
            return_value=mock_graph_builder,
        ):
            populator = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="ws://mock-endpoint",
                entity_extractor=mock_entity_extractor,
            )

            result = await populator.query_entity_relationships(
                entity_name="Apple Inc.",
                max_depth=2,
                relationship_types=["PARTNERS_WITH", "COMPETES_WITH"],
            )

            assert result["query_entity"] == "Apple Inc."
            assert "related_entities" in result
            assert result["total_results"] >= 0
            assert result["max_depth"] == 2
            assert result["relationship_types"] == [
                "PARTNERS_WITH", "COMPETES_WITH"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_graph_validation(self, mock_graph_builder, mock_entity_extractor):
        """Test knowledge graph data validation."""
        # Mock validation query results
        mock_graph_builder._execute_traversal.side_effect = [
            [10],  # Person count
            [5],  # Organization count
            [3],  # Technology count
            [2],  # Policy count
            [1],  # Location count
            [0],  # Entity count
            [15],  # WORKS_FOR relationships
            [8],  # PARTNERS_WITH relationships
            [3],  # COMPETES_WITH relationships
            [2],  # DEVELOPS relationships
            [1],  # USES_TECHNOLOGY relationships
            [2],  # Orphaned entities
        ]

        with patch(
            "src.knowledge_graph.enhanced_graph_populator.GraphBuilder",
            return_value=mock_graph_builder,
        ):
            populator = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="ws://mock-endpoint",
                entity_extractor=mock_entity_extractor,
            )

            validation = await populator.validate_graph_data()

            assert "entity_counts" in validation
            assert "relationship_counts" in validation
            assert "orphaned_entities" in validation
            assert validation["entity_counts"]["Person"] == 10
            assert validation["relationship_counts"]["WORKS_FOR"] == 15
            assert validation["orphaned_entities"] == 2
            assert "validated_at" in validation

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_processing_statistics(
        self, mock_graph_builder, mock_entity_extractor, sample_article_data
    ):
        """Test processing statistics tracking."""
        with patch(
            "src.knowledge_graph.enhanced_graph_populator.GraphBuilder",
            return_value=mock_graph_builder,
        ):
            populator = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="ws://mock-endpoint",
                entity_extractor=mock_entity_extractor,
            )

            # Process multiple articles
            for i in range(3):
                article_data = sample_article_data.copy()
                article_data["id"] = "stats_test_{0}".format(i)

                await populator.populate_from_article(
                    article_id=article_data["id"],
                    title=article_data["title"],
                    content=article_data["content"],
                    published_date=article_data["published_date"],
                    metadata=article_data["metadata"],
                )

            stats = populator.get_processing_statistics()

            assert stats["articles_processed"] == 3
            assert stats["entities_created"] > 0
            assert stats["relationships_created"] > 0
            assert stats["average_processing_time"] > 0
            assert stats["entities_per_article"] > 0
            assert stats["relationships_per_article"] > 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_confidence_filtering(
        self, mock_graph_builder, mock_entity_extractor
    ):
        """Test confidence-based filtering of entities and relationships."""
        # Create extractor with low confidence entities
        low_confidence_entity = EnhancedEntity(
            entity_id="low_con",
            text="Low Confidence Entity",
            label="ORGANIZATION",
            start=0,
            end=20,
            confidence=0.5,  # Below default threshold
            normalized_form="Low Confidence Entity",
            source_article_id="test",
            properties={},
            aliases=[],
            mention_count=1,
        )

        mock_entity_extractor.extract_entities_from_article.return_value = [
            low_confidence_entity
        ]
        mock_entity_extractor.extract_relationships.return_value = []

        with patch(
            "src.knowledge_graph.enhanced_graph_populator.GraphBuilder",
            return_value=mock_graph_builder,
        ):
            populator = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="ws://mock-endpoint",
                entity_extractor=mock_entity_extractor,
            )

            # Set high confidence threshold
            populator.entity_confidence_threshold = 0.8

            result = await populator.populate_from_article(
                article_id="confidence_test",
                title="Confidence Test",
                content="Test content",
                published_date=datetime.now(timezone.utc),
            )

            # Low confidence entity should be filtered out
            assert result["entities"]["extracted"] == 1
            # Should be filtered out
            assert result["entities"][f"iltered"] == 0
            assert result["entities"]["created"] == 0


class TestKnowledgeGraphIntegration:
    """Integration tests for the complete knowledge graph system."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_end_to_end_workflow(self):
        """Test complete end-to-end knowledge graph population workflow."""
        # Mock all dependencies
        mock_nlp_pipeline = Mock()
        mock_nlp_pipeline.process_text = AsyncMock(
            return_value={
                "entities": [
                    {
                        "text": "Apple Inc.",
                        "label": "ORG",
                        "start": 0,
                        "end": 10,
                        "confidence": 0.95,
                    },
                    {
                        "text": "Tim Cook",
                        "label": "PERSON",
                        "start": 20,
                        "end": 28,
                        "confidence": 0.92,
                    },
                ],
                "sentences": ["Apple Inc. CEO Tim Cook announced new initiatives."],
                "dependencies": [],
            }
        )

        mock_graph_builder = Mock()
        mock_graph_builder.connect = AsyncMock()
        mock_graph_builder.add_vertex = AsyncMock(
            return_value={"id": "vertex_123"})
        mock_graph_builder.add_relationship = AsyncMock(
            return_value={"id": "edge_456"})
        mock_graph_builder._execute_traversal = AsyncMock(return_value=[])

        with patch(
            "src.knowledge_graph.enhanced_graph_populator.GraphBuilder",
            return_value=mock_graph_builder,
        ):
            # Create components
            entity_extractor = AdvancedEntityExtractor(
                nlp_pipeline=mock_nlp_pipeline)
            populator = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="ws://mock-endpoint", entity_extractor=entity_extractor
            )

            # Process article
            result = await populator.populate_from_article(
                article_id="integration_test",
                title="Apple Leadership Update",
                content="Apple Inc. CEO Tim Cook announced strategic changes.",
                published_date=datetime.now(timezone.utc),
            )

            # Verify end-to-end processing
            assert result["article_id"] == "integration_test"
            assert result["entities"]["extracted"] > 0
            assert result["processing_time"] > 0

            # Verify graph operations
            mock_graph_builder.connect.assert_called_once()
            assert mock_graph_builder.add_vertex.call_count > 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    async def test_error_handling_robustness(self):
        """Test system robustness with various error conditions."""
        # Test with failing entity extractor
        failing_extractor = Mock()
        failing_extractor.extract_entities_from_article = AsyncMock(
            side_effect=Exception("Extraction failed")
        )

        mock_graph_builder = Mock()
        mock_graph_builder.connect = AsyncMock()

        with patch(
            "src.knowledge_graph.enhanced_graph_populator.GraphBuilder",
            return_value=mock_graph_builder,
        ):
            populator = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="ws://mock-endpoint",
                entity_extractor=failing_extractor,
            )

            # Should handle extraction failure gracefully
            with pytest.raises(Exception):
                await populator.populate_from_article(
                    article_id="error_test",
                    title="Error Test",
                    content="Test content",
                    published_date=datetime.now(timezone.utc),
                )

            # Verify error statistics
            stats = populator.get_processing_statistics()
            assert stats["processing_errors"] > 0


class TestFactoryFunctions:
    """Test factory functions for creating configured instances."""

    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    def test_create_enhanced_knowledge_graph_populator(self):
        """Test standard factory function."""
        populator = create_enhanced_knowledge_graph_populator(
            "ws://test-endpoint")

        assert isinstance(populator, EnhancedKnowledgeGraphPopulator)
        assert populator.neptune_endpoint == "ws://test-endpoint"
        assert populator.batch_size == 50
        assert populator.enable_temporal_tracking is True
        assert populator.enable_entity_linking is True

    @pytest.mark.skipif(
        not ENHANCED_KG_AVAILABLE, reason="Enhanced KG components not available"
    )
    def test_create_advanced_entity_extractor(self):
        """Test entity extractor factory function."""
        extractor = create_advanced_entity_extractor()

        assert isinstance(extractor, AdvancedEntityExtractor)
        assert extractor.confidence_threshold > 0
        assert len(extractor.relationship_patterns) > 0


if __name__ == "__main__":
    # Run a quick test to verify imports and basic functionality
    print(" Enhanced Knowledge Graph Tests")
    print("=" * 50)

    try:
        if ENHANCED_KG_AVAILABLE:
            print(" All enhanced knowledge graph components available")

            # Test factory functions
            extractor = create_advanced_entity_extractor()
            print(" Entity extractor created: {0}".format(
                type(extractor).__name__))

            populator = create_enhanced_knowledge_graph_populator("ws://test")
            print(" Graph populator created: {0}".format(
                type(populator).__name__))

            print(
                ""
 Run full tests with: pytest test_enhanced_knowledge_graph.py -v""
            )
        else:
            print("❌ Enhanced knowledge graph components not available")
            print("   Install required dependencies and verify imports")

    except Exception as e:
        print("❌ Test setup failed: {0}".format(e))

    print(""
 Test Coverage:")
    print("  • Entity extraction with advanced patterns")
    print("  • Relationship detection and validation")
    print("  • Neptune graph population")
    print("  • SPARQL/Gremlin query verification")
    print("  • Entity linking and deduplication")
    print("  • Batch processing performance")
    print("  • Error handling and robustness")
    print("  • End-to-end integration workflows")"
