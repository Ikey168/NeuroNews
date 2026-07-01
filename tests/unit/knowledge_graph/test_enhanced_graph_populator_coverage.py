"""Coverage tests for src/knowledge_graph/enhanced_graph_populator.py.

Targets the remaining reachable lines not hit by the existing populator unit
tests:

  * _add_entity_vertex Technology / Policy / Location property blocks (408, 416, 424)
  * _process_relationships_batch per-relationship exception handling (507-510)
  * _merge_entity_data exception handling (565-566)
  * _link_entity_to_article exception handling (600-601)
  * _link_to_historical_entities exception handling / continue (644-650)
  * execute_sparql_query error branch (773-775)
  * _update_vertex_properties exception handling (801-802)
  * create_high_quality_graph_populator factory (936-939)

The GraphBuilder is fully mocked (AsyncMock for async calls), so nothing talks
to a live Neptune/Gremlin server. We drive coroutines with asyncio.run.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.knowledge_graph.enhanced_graph_populator as egp  # noqa: E402

if not getattr(egp, "GRAPH_BUILDER_AVAILABLE", False):
    pytest.skip("GraphBuilder not available", allow_module_level=True)

from src.knowledge_graph.enhanced_entity_extractor import (  # noqa: E402
    EnhancedEntity,
    EnhancedRelationship,
)
from src.knowledge_graph.enhanced_graph_populator import (  # noqa: E402
    EnhancedKnowledgeGraphPopulator,
    create_high_quality_graph_populator,
)


def _run(coro):
    return asyncio.run(coro)


def _entity(text, label, **kw):
    return EnhancedEntity(
        text=text,
        label=label,
        start=kw.pop("start", 0),
        end=kw.pop("end", len(text)),
        confidence=kw.pop("confidence", 0.9),
        source_article_id=kw.pop("source_article_id", "art-1"),
        **kw,
    )


def _graph_builder():
    gb = MagicMock()
    gb.connect = AsyncMock()
    gb.add_vertex = AsyncMock(return_value={"id": "vtx-generated"})
    gb.add_relationship = AsyncMock(return_value={"id": "edge-1"})
    gb.get_vertex_by_id = AsyncMock(return_value=None)
    gb._execute_traversal = AsyncMock(return_value=[])
    gb.g = MagicMock()
    gb.client = None
    return gb


@pytest.fixture
def populator():
    gb = _graph_builder()
    with patch.object(egp, "GraphBuilder", return_value=gb):
        p = EnhancedKnowledgeGraphPopulator(
            neptune_endpoint="wss://fake:8182/gremlin",
            entity_extractor=MagicMock(),
        )
    p.graph_builder = gb
    return p


# ---------------------------------------------------------------------------
# _add_entity_vertex -- per-type property blocks
# ---------------------------------------------------------------------------

class TestAddEntityVertexTypes:
    def _props_for(self, populator, entity):
        vid = _run(populator._add_entity_vertex(entity))
        assert vid == "vtx-generated"
        label, props = populator.graph_builder.add_vertex.call_args[0]
        return label, props

    def test_technology_properties(self, populator):
        ent = _entity("TensorFlow", "TECHNOLOGY")
        ent.properties = {"category": "ai", "description": "ML lib"}
        label, props = self._props_for(populator, ent)
        assert label == "Technology"
        assert props["techName"] == ent.normalized_form
        assert props["category"] == "ai"
        assert props["description"] == "ML lib"

    def test_policy_properties(self, populator):
        ent = _entity("GDPR", "POLICY")
        ent.properties = {"type": "privacy", "jurisdiction": "EU"}
        label, props = self._props_for(populator, ent)
        assert label == "Policy"
        assert props["policyName"] == ent.normalized_form
        assert props["type"] == "privacy"
        assert props["jurisdiction"] == "EU"

    def test_location_properties(self, populator):
        ent = _entity("Silicon Valley", "LOCATION")
        ent.properties = {"type": "region", "country": "USA"}
        label, props = self._props_for(populator, ent)
        assert label == "Location"
        assert props["locationName"] == ent.normalized_form
        assert props["country"] == "USA"

    def test_add_entity_vertex_returns_none_on_error(self, populator):
        # add_vertex raising -> the except branch returns None.
        populator.graph_builder.add_vertex = AsyncMock(side_effect=RuntimeError("neptune down"))
        ent = _entity("Alice", "PERSON")
        assert _run(populator._add_entity_vertex(ent)) is None


# ---------------------------------------------------------------------------
# _process_relationships_batch -- per-relationship exception (507-510)
# ---------------------------------------------------------------------------

class TestProcessRelationshipsErrors:
    def _rel(self, src, tgt):
        return EnhancedRelationship(
            source_entity=src,
            target_entity=tgt,
            relation_type="WORKS_FOR",
            confidence=0.9,
            context="ctx",
            article_id="art-1",
        )

    def test_exception_moves_relationship_to_skipped(self, populator):
        src = _entity("Alice", "PERSON")
        tgt = _entity("Acme", "ORGANIZATION")
        # Register vertex ids so the code reaches add_relationship.
        populator.entity_registry[src.entity_id] = "v-src"
        populator.entity_registry[tgt.entity_id] = "v-tgt"
        populator.graph_builder.add_relationship = AsyncMock(
            side_effect=RuntimeError("edge failed")
        )
        rel = self._rel(src, tgt)
        result = _run(populator._process_relationships_batch([rel], "art-1"))
        assert result["created"] == []
        assert len(result["skipped"]) == 1

    def test_missing_vertex_registry_skips(self, populator):
        src = _entity("Alice", "PERSON")
        tgt = _entity("Acme", "ORGANIZATION")
        # No registry entries -> source/target vertex ids are None -> skipped.
        rel = self._rel(src, tgt)
        result = _run(populator._process_relationships_batch([rel], "art-1"))
        assert result["created"] == []
        assert len(result["skipped"]) == 1

    def test_created_relationship_records_registry(self, populator):
        src = _entity("Alice", "PERSON")
        tgt = _entity("Acme", "ORGANIZATION")
        populator.entity_registry[src.entity_id] = "v-src"
        populator.entity_registry[tgt.entity_id] = "v-tgt"
        rel = self._rel(src, tgt)
        result = _run(populator._process_relationships_batch([rel], "art-1"))
        assert len(result["created"]) == 1
        key = "v-src:WORKS_FOR:v-tgt"
        assert key in populator.relationship_registry


# ---------------------------------------------------------------------------
# _merge_entity_data exception (565-566)
# ---------------------------------------------------------------------------

class TestMergeEntityDataError:
    def test_merge_error_is_swallowed(self, populator):
        ent = _entity("Acme", "ORGANIZATION", aliases=["Acme Corp"])
        # get_vertex_by_id raises -> the merge except branch logs & returns.
        populator.graph_builder.get_vertex_by_id = AsyncMock(
            side_effect=RuntimeError("lookup failed")
        )
        # Should not raise.
        _run(populator._merge_entity_data("v-existing", ent))

    def test_merge_updates_properties_on_success(self, populator):
        ent = _entity("Acme", "ORGANIZATION", aliases=["Acme Corp"])
        populator.graph_builder.get_vertex_by_id = AsyncMock(
            return_value={"aliases": '["Old Alias"]'}
        )
        with patch.object(populator, "_update_vertex_properties", new=AsyncMock()) as upd:
            _run(populator._merge_entity_data("v-existing", ent))
        upd.assert_awaited_once()
        _, props = upd.await_args[0]
        # New + existing aliases merged.
        assert "Acme Corp" in props["aliases"]
        assert "Old Alias" in props["aliases"]


# ---------------------------------------------------------------------------
# _link_entity_to_article exception (600-601)
# ---------------------------------------------------------------------------

class TestLinkEntityToArticleError:
    def test_link_error_is_swallowed(self, populator):
        ent = _entity("Alice", "PERSON")
        populator.graph_builder.add_relationship = AsyncMock(
            side_effect=RuntimeError("edge failed")
        )
        _run(populator._link_entity_to_article(ent, "art-vtx", "ent-vtx"))

    def test_link_uses_type_specific_relation(self, populator):
        ent = _entity("TensorFlow", "TECHNOLOGY")
        _run(populator._link_entity_to_article(ent, "art-vtx", "ent-vtx"))
        args = populator.graph_builder.add_relationship.call_args[0]
        # article_vtx, entity_vtx, relation_type, props
        assert args[2] == "MENTIONS_TECH"

    def test_link_unknown_type_defaults(self, populator):
        ent = _entity("Thing", "MISCELLANEOUS")
        _run(populator._link_entity_to_article(ent, "art-vtx", "ent-vtx"))
        args = populator.graph_builder.add_relationship.call_args[0]
        assert args[2] == "MENTIONS_ENTITY"


# ---------------------------------------------------------------------------
# _link_to_historical_entities exception / continue (644-650)
# ---------------------------------------------------------------------------

class TestHistoricalLinkErrors:
    def test_error_during_similar_lookup_is_skipped(self, populator):
        ent = _entity("Alice", "PERSON")
        with patch.object(
            populator,
            "_find_similar_entities",
            new=AsyncMock(side_effect=RuntimeError("query failed")),
        ):
            links = _run(populator._link_to_historical_entities([ent], "art-1"))
        # Exception caught, continue -> no links produced.
        assert links == []

    def test_creates_link_when_similar_found(self, populator):
        ent = _entity("Alice", "PERSON")
        populator.entity_registry[ent.entity_id] = "v-alice"
        with patch.object(
            populator,
            "_find_similar_entities",
            new=AsyncMock(return_value=["hist-vtx-1"]),
        ):
            links = _run(populator._link_to_historical_entities([ent], "art-1"))
        assert len(links) == 1
        assert links[0]["linked_to"] == "hist-vtx-1"


# ---------------------------------------------------------------------------
# execute_sparql_query error branch (773-775)
# ---------------------------------------------------------------------------

class TestSparqlQuery:
    def test_placeholder_response(self, populator):
        res = _run(populator.execute_sparql_query("SELECT * WHERE {}"))
        assert res["results"] == []
        assert "not yet implemented" in res["message"]

    def test_error_branch(self, populator):
        # Make str(sparql_query) blow up? Instead patch logger.warning to raise so
        # the except path (773-775) executes and returns an error dict.
        with patch.object(egp.logger, "warning", side_effect=RuntimeError("boom")):
            res = _run(populator.execute_sparql_query("SELECT * WHERE {}"))
        assert "error" in res
        assert res["query"] == "SELECT * WHERE {}"


# ---------------------------------------------------------------------------
# _update_vertex_properties exception (801-802)
# ---------------------------------------------------------------------------

class TestUpdateVertexPropertiesError:
    def test_update_error_is_swallowed(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(
            side_effect=RuntimeError("update failed")
        )
        # Should not raise.
        _run(populator._update_vertex_properties("v-1", {"confidence": 0.9}))

    def test_update_success_calls_traversal(self, populator):
        _run(populator._update_vertex_properties("v-1", {"a": 1, "b": 2}))
        populator.graph_builder._execute_traversal.assert_awaited_once()


# ---------------------------------------------------------------------------
# create_high_quality_graph_populator factory (936-939)
# ---------------------------------------------------------------------------

class TestHighQualityFactory:
    def test_factory_builds_configured_populator(self):
        gb = _graph_builder()
        with patch.object(egp, "GraphBuilder", return_value=gb):
            p = create_high_quality_graph_populator("wss://fake:8182/gremlin")
        assert isinstance(p, EnhancedKnowledgeGraphPopulator)
        assert p.batch_size == 25
        assert p.enable_temporal_tracking is True
        assert p.enable_entity_linking is True
        # The injected extractor had its confidence threshold bumped.
        assert p.entity_extractor.confidence_threshold == 0.85
