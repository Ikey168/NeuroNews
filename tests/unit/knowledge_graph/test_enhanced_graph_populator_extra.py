"""Extra tests for src/knowledge_graph/enhanced_graph_populator.py.

These tests target the async orchestration / node+edge construction logic that
the existing test_enhanced_graph_populator.py does not cover. The GraphBuilder
and entity extractor are mocked (AsyncMock for async graph calls) so everything
runs offline without a live Neptune/Gremlin database.
"""

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import knowledge_graph.enhanced_graph_populator as mod  # noqa: E402

if not getattr(mod, "GRAPH_BUILDER_AVAILABLE", False):
    pytest.skip("GraphBuilder not available", allow_module_level=True)

EnhancedEntity = pytest.importorskip(
    "knowledge_graph.enhanced_entity_extractor"
).EnhancedEntity
EnhancedRelationship = pytest.importorskip(
    "knowledge_graph.enhanced_entity_extractor"
).EnhancedRelationship

from knowledge_graph.enhanced_graph_populator import (  # noqa: E402
    EnhancedKnowledgeGraphPopulator,
    create_enhanced_knowledge_graph_populator,
    create_high_performance_graph_populator,
)


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #
def make_entity(text, label, **kw):
    """Build a real EnhancedEntity (handy because of __post_init__ id logic)."""
    return EnhancedEntity(
        text=text,
        label=label,
        start=kw.pop("start", 0),
        end=kw.pop("end", len(text)),
        confidence=kw.pop("confidence", 0.9),
        source_article_id=kw.pop("source_article_id", "art-1"),
        **kw,
    )


def make_graph_builder():
    """A GraphBuilder mock with AsyncMock async methods and a chainable g."""
    gb = MagicMock()
    gb.connect = AsyncMock()
    gb.add_vertex = AsyncMock(return_value={"id": "vtx-generated"})
    gb.add_relationship = AsyncMock(return_value={"id": "edge-1"})
    gb.get_vertex_by_id = AsyncMock(return_value=None)
    gb._execute_traversal = AsyncMock(return_value=[])
    # g is a chainable mock: any attribute access / call returns itself.
    gb.g = MagicMock()
    gb.client = None
    return gb


@pytest.fixture
def populator():
    gb = make_graph_builder()
    with patch.object(mod, "GraphBuilder", return_value=gb):
        p = EnhancedKnowledgeGraphPopulator(
            neptune_endpoint="wss://fake:8182/gremlin",
            entity_extractor=MagicMock(),
        )
    # make graph_builder the controllable mock
    p.graph_builder = gb
    return p


# --------------------------------------------------------------------------- #
# _add_article_vertex
# --------------------------------------------------------------------------- #
class TestAddArticleVertex:
    @pytest.mark.asyncio
    async def test_basic_properties_and_truncation(self, populator):
        long_content = "x" * 2000
        vid = await populator._add_article_vertex(
            "art-1", "Title", long_content, None, None
        )
        assert vid == "vtx-generated"
        label, props = populator.graph_builder.add_vertex.call_args[0]
        assert label == "Article"
        assert props["id"] == "art-1"
        assert props["title"] == "Title"
        # content truncated to 1000 chars, but content_length keeps full length
        assert len(props["content"]) == 1000
        assert props["content_length"] == 2000
        assert props["source"] == "enhanced_nlp_populator"

    @pytest.mark.asyncio
    async def test_published_date_and_metadata_selected(self, populator):
        pub = datetime(2025, 1, 2, 3, 4, 5)
        meta = {
            "source_url": "http://x",
            "author": "Jane",
            "category": "Tech",
            "tags": ["a"],
            "ignored_field": "nope",
        }
        await populator._add_article_vertex("a", "t", "c", pub, meta)
        _, props = populator.graph_builder.add_vertex.call_args[0]
        assert props["published_date"] == pub.isoformat()
        assert props["author"] == "Jane"
        assert props["category"] == "Tech"
        assert props["source_url"] == "http://x"
        assert props["tags"] == ["a"]
        assert "ignored_field" not in props

    @pytest.mark.asyncio
    async def test_falls_back_to_article_id_when_no_result(self, populator):
        populator.graph_builder.add_vertex = AsyncMock(return_value=None)
        vid = await populator._add_article_vertex("art-9", "t", "c", None, None)
        assert vid == "art-9"


# --------------------------------------------------------------------------- #
# _add_entity_vertex
# --------------------------------------------------------------------------- #
class TestAddEntityVertex:
    @pytest.mark.asyncio
    async def test_person_label_and_typed_properties(self, populator):
        ent = make_entity("Tim Cook", "PERSON")
        ent.properties = {"title": "CEO", "organization": "Apple"}
        ent.aliases = ["Timothy Cook"]
        vid = await populator._add_entity_vertex(ent)
        assert vid == "vtx-generated"
        label, props = populator.graph_builder.add_vertex.call_args[0]
        assert label == "Person"
        assert props["entity_type"] == "PERSON"
        assert props["name"] == ent.normalized_form
        assert props["title"] == "CEO"
        assert props["organization"] == "Apple"
        # aliases serialized as JSON
        assert "Timothy Cook" in props["aliases"]

    @pytest.mark.asyncio
    async def test_organization_label_mapping(self, populator):
        ent = make_entity("Apple Inc.", "ORGANIZATION")
        ent.properties = {"type": "public", "industry": "tech"}
        await populator._add_entity_vertex(ent)
        label, props = populator.graph_builder.add_vertex.call_args[0]
        assert label == "Organization"
        assert props["orgName"] == ent.normalized_form
        assert props["industry"] == "tech"

    @pytest.mark.asyncio
    async def test_unknown_label_defaults_to_entity(self, populator):
        ent = make_entity("Something", "WEIRD")
        await populator._add_entity_vertex(ent)
        label, _ = populator.graph_builder.add_vertex.call_args[0]
        assert label == "Entity"

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, populator):
        populator.graph_builder.add_vertex = AsyncMock(side_effect=RuntimeError("boom"))
        ent = make_entity("X", "PERSON")
        assert await populator._add_entity_vertex(ent) is None


# --------------------------------------------------------------------------- #
# _process_entities_batch
# --------------------------------------------------------------------------- #
class TestProcessEntitiesBatch:
    @pytest.mark.asyncio
    async def test_creates_new_entity_and_links_to_article(self, populator):
        populator._find_existing_entity = AsyncMock(return_value=None)
        ent = make_entity("Apple", "ORGANIZATION")
        result = await populator._process_entities_batch([ent], "art-1", "art-vtx")
        assert result["created"] == ["vtx-generated"]
        assert result["linked"] == []
        # registry now records mapping
        assert populator.entity_registry[ent.entity_id] == "vtx-generated"
        # relationship from article to entity was created
        assert populator.graph_builder.add_relationship.await_count == 1

    @pytest.mark.asyncio
    async def test_existing_entity_is_linked_and_merged(self, populator):
        populator._find_existing_entity = AsyncMock(return_value="existing-vtx")
        populator._merge_entity_data = AsyncMock()
        ent = make_entity("Apple", "ORGANIZATION")
        result = await populator._process_entities_batch([ent], "art-1", "art-vtx")
        assert result["linked"] == ["existing-vtx"]
        assert result["merged"] == ["existing-vtx"]
        assert result["created"] == []
        populator._merge_entity_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_entity_without_linking_not_merged(self, populator):
        populator.enable_entity_linking = False
        populator._find_existing_entity = AsyncMock(return_value="existing-vtx")
        populator._merge_entity_data = AsyncMock()
        ent = make_entity("Apple", "ORGANIZATION")
        result = await populator._process_entities_batch([ent], "art-1", "art-vtx")
        assert result["linked"] == ["existing-vtx"]
        assert result["merged"] == []
        populator._merge_entity_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_in_one_entity_does_not_abort_batch(self, populator):
        populator._find_existing_entity = AsyncMock(
            side_effect=[RuntimeError("x"), None]
        )
        ents = [make_entity("Bad", "PERSON"), make_entity("Good", "ORGANIZATION")]
        result = await populator._process_entities_batch(ents, "art-1", "av")
        # second entity still created despite first raising
        assert result["created"] == ["vtx-generated"]


# --------------------------------------------------------------------------- #
# _process_relationships_batch
# --------------------------------------------------------------------------- #
def make_rel(src, tgt, rel_type="WORKS_FOR", confidence=0.9, temporal=None):
    return EnhancedRelationship(
        source_entity=src,
        target_entity=tgt,
        relation_type=rel_type,
        confidence=confidence,
        context="some context " * 100,  # long, to exercise truncation
        article_id="art-1",
        evidence_sentences=["s1", "s2"],
        temporal_info=temporal,
    )


class TestProcessRelationshipsBatch:
    @pytest.mark.asyncio
    async def test_created_when_both_vertices_known(self, populator):
        src = make_entity("Tim Cook", "PERSON")
        tgt = make_entity("Apple", "ORGANIZATION")
        populator.entity_registry = {src.entity_id: "v-src", tgt.entity_id: "v-tgt"}
        rel = make_rel(src, tgt)
        result = await populator._process_relationships_batch([rel], "art-1")
        assert len(result["created"]) == 1
        assert result["skipped"] == []
        s, t, rtype, props = populator.graph_builder.add_relationship.call_args[0]
        assert (s, t, rtype) == ("v-src", "v-tgt", "WORKS_FOR")
        assert len(props["context"]) <= 500
        assert props["evidence_count"] == 2
        # relationship key recorded
        assert "v-src:WORKS_FOR:v-tgt" in populator.relationship_registry

    @pytest.mark.asyncio
    async def test_skipped_when_vertex_missing(self, populator):
        src = make_entity("Tim Cook", "PERSON")
        tgt = make_entity("Apple", "ORGANIZATION")
        populator.entity_registry = {src.entity_id: "v-src"}  # tgt missing
        rel = make_rel(src, tgt)
        result = await populator._process_relationships_batch([rel], "art-1")
        assert result["created"] == []
        assert len(result["skipped"]) == 1
        populator.graph_builder.add_relationship.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_duplicate_relationship_skipped(self, populator):
        src = make_entity("Tim Cook", "PERSON")
        tgt = make_entity("Apple", "ORGANIZATION")
        populator.entity_registry = {src.entity_id: "v-src", tgt.entity_id: "v-tgt"}
        populator.relationship_registry.add("v-src:WORKS_FOR:v-tgt")
        rel = make_rel(src, tgt)
        result = await populator._process_relationships_batch([rel], "art-1")
        assert result["created"] == []
        assert len(result["skipped"]) == 1

    @pytest.mark.asyncio
    async def test_temporal_info_merged_when_enabled(self, populator):
        src = make_entity("Tim Cook", "PERSON")
        tgt = make_entity("Apple", "ORGANIZATION")
        populator.entity_registry = {src.entity_id: "v-src", tgt.entity_id: "v-tgt"}
        populator.enable_temporal_tracking = True
        rel = make_rel(src, tgt, temporal={"year": "2025"})
        await populator._process_relationships_batch([rel], "art-1")
        _, _, _, props = populator.graph_builder.add_relationship.call_args[0]
        assert props["year"] == "2025"

    @pytest.mark.asyncio
    async def test_skipped_when_add_relationship_returns_falsy(self, populator):
        src = make_entity("Tim Cook", "PERSON")
        tgt = make_entity("Apple", "ORGANIZATION")
        populator.entity_registry = {src.entity_id: "v-src", tgt.entity_id: "v-tgt"}
        populator.graph_builder.add_relationship = AsyncMock(return_value=None)
        rel = make_rel(src, tgt)
        result = await populator._process_relationships_batch([rel], "art-1")
        assert result["created"] == []
        assert len(result["skipped"]) == 1


# --------------------------------------------------------------------------- #
# _link_entity_to_article + mention type mapping
# --------------------------------------------------------------------------- #
class TestLinkEntityToArticle:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "label,rel_type",
        [
            ("PERSON", "MENTIONS_PERSON"),
            ("ORGANIZATION", "MENTIONS_ORG"),
            ("TECHNOLOGY", "MENTIONS_TECH"),
            ("POLICY", "MENTIONS_POLICY"),
            ("LOCATION", "MENTIONS_LOCATION"),
            ("WEIRD", "MENTIONS_ENTITY"),
        ],
    )
    async def test_relation_type_mapping(self, populator, label, rel_type):
        ent = make_entity("X", label)
        await populator._link_entity_to_article(ent, "art-vtx", "ent-vtx")
        a, b, rtype, props = populator.graph_builder.add_relationship.call_args[0]
        assert (a, b, rtype) == ("art-vtx", "ent-vtx", rel_type)
        assert props["mention_confidence"] == ent.confidence


# --------------------------------------------------------------------------- #
# _find_existing_entity / _find_similar_entities
# --------------------------------------------------------------------------- #
class TestFindExisting:
    @pytest.mark.asyncio
    async def test_returns_first_result(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(
            return_value=["found-id", "other"]
        )
        ent = make_entity("Apple", "ORGANIZATION")
        assert await populator._find_existing_entity(ent) == "found-id"

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(return_value=[])
        ent = make_entity("Apple", "ORGANIZATION")
        assert await populator._find_existing_entity(ent) is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(
            side_effect=RuntimeError("db down")
        )
        ent = make_entity("Apple", "ORGANIZATION")
        assert await populator._find_existing_entity(ent) is None

    @pytest.mark.asyncio
    async def test_find_similar_entities_returns_list(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(
            return_value=["s1", "s2"]
        )
        ent = make_entity("Apple", "ORGANIZATION")
        assert await populator._find_similar_entities(ent) == ["s1", "s2"]

    @pytest.mark.asyncio
    async def test_find_similar_entities_empty_on_error(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(
            side_effect=RuntimeError("x")
        )
        ent = make_entity("Apple", "ORGANIZATION")
        assert await populator._find_similar_entities(ent) == []


# --------------------------------------------------------------------------- #
# _merge_entity_data + _update_vertex_properties
# --------------------------------------------------------------------------- #
class TestMergeEntityData:
    @pytest.mark.asyncio
    async def test_merges_aliases_with_existing(self, populator):
        populator.graph_builder.get_vertex_by_id = AsyncMock(
            return_value={"aliases": '["old"]'}
        )
        populator._update_vertex_properties = AsyncMock()
        ent = make_entity("Apple", "ORGANIZATION")
        ent.aliases = ["new"]
        await populator._merge_entity_data("vtx-1", ent)
        props = populator._update_vertex_properties.call_args[0][1]
        import json

        merged = set(json.loads(props["aliases"]))
        assert merged == {"old", "new"}

    @pytest.mark.asyncio
    async def test_no_aliases_skips_alias_update(self, populator):
        populator._update_vertex_properties = AsyncMock()
        ent = make_entity("Apple", "ORGANIZATION")
        ent.aliases = []
        await populator._merge_entity_data("vtx-1", ent)
        props = populator._update_vertex_properties.call_args[0][1]
        assert "aliases" not in props
        assert props["mention_count"] == ent.mention_count

    @pytest.mark.asyncio
    async def test_update_vertex_properties_chains_traversal(self, populator):
        await populator._update_vertex_properties("vtx-1", {"a": 1, "b": 2})
        populator.graph_builder._execute_traversal.assert_awaited_once()


# --------------------------------------------------------------------------- #
# _link_to_historical_entities
# --------------------------------------------------------------------------- #
class TestLinkToHistorical:
    @pytest.mark.asyncio
    async def test_creates_similar_to_edges(self, populator):
        ent = make_entity("Apple", "ORGANIZATION")
        populator.entity_registry = {ent.entity_id: "ent-vtx"}
        populator._find_similar_entities = AsyncMock(return_value=["sim-1", "sim-2"])
        links = await populator._link_to_historical_entities([ent], "art-1")
        assert len(links) == 2
        assert populator.graph_builder.add_relationship.await_count == 2
        # uses SIMILAR_TO relation
        _, _, rtype, _ = populator.graph_builder.add_relationship.call_args[0]
        assert rtype == "SIMILAR_TO"

    @pytest.mark.asyncio
    async def test_skips_when_entity_not_in_registry(self, populator):
        ent = make_entity("Apple", "ORGANIZATION")
        populator.entity_registry = {}  # not registered
        populator._find_similar_entities = AsyncMock(return_value=["sim-1"])
        links = await populator._link_to_historical_entities([ent], "art-1")
        assert links == []
        populator.graph_builder.add_relationship.assert_not_awaited()


# --------------------------------------------------------------------------- #
# populate_from_article (full orchestration) + batch
# --------------------------------------------------------------------------- #
class TestPopulateFromArticle:
    @pytest.mark.asyncio
    async def test_full_flow_filters_by_confidence_and_updates_stats(self, populator):
        high = make_entity("Apple", "ORGANIZATION", confidence=0.95)
        low = make_entity("Maybe", "PERSON", confidence=0.1)  # below 0.7 threshold
        populator.entity_extractor.extract_entities_from_article = AsyncMock(
            return_value=[high, low]
        )
        rel = make_rel(high, high, confidence=0.9)
        populator.entity_extractor.extract_relationships = AsyncMock(
            return_value=[rel]
        )
        populator._find_existing_entity = AsyncMock(return_value=None)
        populator._link_to_historical_entities = AsyncMock(return_value=[])

        result = await populator.populate_from_article(
            "art-1", "Title", "Content body", datetime(2025, 1, 1)
        )

        assert result["article_id"] == "art-1"
        assert result["entities"]["extracted"] == 2
        assert result["entities"]["filtered"] == 1  # low-conf dropped
        assert result["entities"]["created"] == 1
        assert populator.stats["articles_processed"] == 1
        assert populator.stats["entities_created"] == 1
        # extractor was given title and content
        populator.entity_extractor.extract_entities_from_article.assert_awaited_once_with(
            "art-1", "Title", "Content body"
        )

    @pytest.mark.asyncio
    async def test_entity_linking_disabled_skips_historical(self, populator):
        populator.enable_entity_linking = False
        ent = make_entity("Apple", "ORGANIZATION", confidence=0.95)
        populator.entity_extractor.extract_entities_from_article = AsyncMock(
            return_value=[ent]
        )
        populator.entity_extractor.extract_relationships = AsyncMock(return_value=[])
        populator._find_existing_entity = AsyncMock(return_value=None)
        populator._link_to_historical_entities = AsyncMock(return_value=[])
        result = await populator.populate_from_article("art-1", "t", "c")
        assert result["historical_links"] == 0
        populator._link_to_historical_entities.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_increments_error_stat_and_raises(self, populator):
        populator.entity_extractor.extract_entities_from_article = AsyncMock(
            side_effect=RuntimeError("extractor failed")
        )
        with pytest.raises(RuntimeError):
            await populator.populate_from_article("art-1", "t", "c")
        assert populator.stats["processing_errors"] == 1


class TestPopulateBatch:
    @pytest.mark.asyncio
    async def test_aggregates_results_and_handles_exceptions(self, populator):
        async def fake_populate(aid, title, content, pub=None, meta=None):
            if aid == "bad":
                raise RuntimeError("nope")
            return {"article_id": aid}

        populator.populate_from_article = AsyncMock(side_effect=fake_populate)
        articles = [
            {"id": "a1", "title": "t", "content": "c"},
            {"id": "bad", "title": "t", "content": "c"},
            {"id": "a2", "title": "t", "content": "c"},
        ]
        results = await populator.populate_from_articles_batch(articles)
        ids = {r["article_id"] for r in results}
        assert ids == {"a1", "a2"}
        assert populator.stats["processing_errors"] == 1


# --------------------------------------------------------------------------- #
# query_entity_relationships + execute_sparql_query + validate_graph_data
# --------------------------------------------------------------------------- #
class TestQueries:
    @pytest.mark.asyncio
    async def test_query_entity_relationships_formats_results(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(
            return_value=[
                {
                    "id": ["v1"],
                    "normalized_form": ["Apple"],
                    "entity_type": ["ORGANIZATION"],
                    "confidence": [0.9],
                    "mention_count": [3],
                }
            ]
        )
        res = await populator.query_entity_relationships("Apple", max_depth=2)
        assert res["query_entity"] == "Apple"
        assert res["total_results"] == 1
        assert res["related_entities"][0]["name"] == "Apple"
        assert res["related_entities"][0]["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_query_with_relationship_types_filter(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(return_value=[])
        res = await populator.query_entity_relationships(
            "Apple", max_depth=1, relationship_types=["WORKS_FOR"]
        )
        assert res["relationship_types"] == ["WORKS_FOR"]
        assert res["related_entities"] == []

    @pytest.mark.asyncio
    async def test_query_returns_error_dict_on_exception(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        res = await populator.query_entity_relationships("Apple")
        assert res["related_entities"] == []
        assert "error" in res

    @pytest.mark.asyncio
    async def test_execute_sparql_query_placeholder(self, populator):
        res = await populator.execute_sparql_query("SELECT ?s WHERE {}")
        assert res["query"] == "SELECT ?s WHERE {}"
        assert res["results"] == []
        assert "message" in res

    @pytest.mark.asyncio
    async def test_validate_graph_data_counts(self, populator):
        # _execute_traversal called many times; return count list each time
        populator.graph_builder._execute_traversal = AsyncMock(return_value=[7])
        res = await populator.validate_graph_data()
        assert res["entity_counts"]["Person"] == 7
        assert res["relationship_counts"]["WORKS_FOR"] == 7
        assert res["orphaned_entities"] == 7
        assert "validated_at" in res

    @pytest.mark.asyncio
    async def test_validate_graph_data_error_path(self, populator):
        populator.graph_builder._execute_traversal = AsyncMock(
            side_effect=RuntimeError("db gone")
        )
        res = await populator.validate_graph_data()
        assert "error" in res


# --------------------------------------------------------------------------- #
# close + factory functions
# --------------------------------------------------------------------------- #
class TestCloseAndFactories:
    @pytest.mark.asyncio
    async def test_close_closes_client(self, populator):
        client = MagicMock()
        client.close = AsyncMock()
        populator.graph_builder.client = client
        await populator.close()
        client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_swallows_errors(self, populator):
        client = MagicMock()
        client.close = AsyncMock(side_effect=RuntimeError("x"))
        populator.graph_builder.client = client
        # should not raise
        await populator.close()

    def test_create_enhanced_populator(self):
        with patch.object(mod, "GraphBuilder", return_value=make_graph_builder()), \
                patch.object(mod, "create_advanced_entity_extractor", MagicMock()):
            p = create_enhanced_knowledge_graph_populator("wss://x")
        assert p.batch_size == 50
        assert p.enable_temporal_tracking is True
        assert p.enable_entity_linking is True

    def test_create_high_performance_populator(self):
        with patch.object(mod, "GraphBuilder", return_value=make_graph_builder()), \
                patch.object(mod, "create_advanced_entity_extractor", MagicMock()):
            p = create_high_performance_graph_populator("wss://x")
        assert p.batch_size == 100
        assert p.enable_temporal_tracking is False
        assert p.enable_entity_linking is False


# --------------------------------------------------------------------------- #
# init guard
# --------------------------------------------------------------------------- #
class TestInitGuard:
    def test_raises_when_graph_builder_unavailable(self):
        with patch.object(mod, "GRAPH_BUILDER_AVAILABLE", False):
            with pytest.raises(ImportError):
                EnhancedKnowledgeGraphPopulator("wss://x", entity_extractor=MagicMock())
