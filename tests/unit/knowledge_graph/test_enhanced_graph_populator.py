"""Tests for src/knowledge_graph/enhanced_graph_populator.py."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import knowledge_graph.enhanced_graph_populator as egp  # noqa: E402

if not getattr(egp, "GRAPH_BUILDER_AVAILABLE", False):
    pytest.skip("GraphBuilder not available", allow_module_level=True)

from knowledge_graph.enhanced_graph_populator import (  # noqa: E402
    EnhancedKnowledgeGraphPopulator,
)


@pytest.fixture
def populator():
    with patch.object(egp, "GraphBuilder", MagicMock()):
        p = EnhancedKnowledgeGraphPopulator(
            neptune_endpoint="wss://fake:8182/gremlin",
            entity_extractor=MagicMock(),
        )
    return p


class TestInit:
    def test_defaults(self, populator):
        assert populator.batch_size == 50
        assert populator.enable_temporal_tracking is True
        assert populator.stats["articles_processed"] == 0
        assert populator.entity_registry == {}

    def test_custom_config(self):
        with patch.object(egp, "GraphBuilder", MagicMock()):
            p = EnhancedKnowledgeGraphPopulator(
                neptune_endpoint="x", batch_size=10,
                enable_temporal_tracking=False, enable_entity_linking=False,
            )
        assert p.batch_size == 10
        assert p.enable_temporal_tracking is False
        assert p.enable_entity_linking is False


class TestNeptuneLabel:
    @pytest.mark.parametrize("etype,label", [
        ("PERSON", "Person"),
        ("ORGANIZATION", "Organization"),
        ("TECHNOLOGY", "Technology"),
        ("POLICY", "Policy"),
        ("LOCATION", "Location"),
        ("MISCELLANEOUS", "Entity"),
        ("UNKNOWN_TYPE", "Entity"),
    ])
    def test_mapping(self, populator, etype, label):
        assert populator._get_neptune_label(etype) == label


class TestStatistics:
    def test_empty_stats(self, populator):
        stats = populator.get_processing_statistics()
        assert stats["articles_processed"] == 0
        assert stats["average_processing_time"] == 0
        assert stats["entities_per_article"] == 0
        assert stats["entity_registry_size"] == 0

    def test_computed_averages(self, populator):
        populator.stats["articles_processed"] = 4
        populator.stats["entities_created"] = 20
        populator.stats["relationships_created"] = 8
        populator.stats["total_processing_time"] = 2.0
        stats = populator.get_processing_statistics()
        assert stats["average_processing_time"] == 0.5
        assert stats["entities_per_article"] == 5.0
        assert stats["relationships_per_article"] == 2.0

    def test_registry_sizes_reflected(self, populator):
        populator.entity_registry = {"a": "v1", "b": "v2"}
        populator.relationship_registry = {("a", "b")}
        stats = populator.get_processing_statistics()
        assert stats["entity_registry_size"] == 2
        assert stats["relationship_registry_size"] == 1


class TestClose:
    @pytest.mark.asyncio
    async def test_close_no_error(self, populator):
        # graph_builder is a MagicMock; close should handle gracefully
        await populator.close()
