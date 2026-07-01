"""Coverage tests for src/knowledge_graph/nlp_populator.py.

``GraphBuilder`` is patched on the module so no Neptune/Gremlin connection is
attempted, and a mock ``ner_processor`` is always injected so the real
transformer-loading ``NERProcessor`` is never constructed. All async graph
operations are AsyncMocks; assertions target the real entity/relationship
shaping and statistics logic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.knowledge_graph.nlp_populator as mod
from src.knowledge_graph.nlp_populator import (
    Entity,
    KnowledgeGraphPopulator,
    Relationship,
)


@pytest.fixture(autouse=True)
def patch_graph_builder(monkeypatch):
    """Replace GraphBuilder with a mock whose async methods are AsyncMocks."""
    def make_builder(endpoint, force_websocket_mode=False):
        gb = MagicMock()
        gb.endpoint = endpoint
        gb.connection = None
        gb.connect = AsyncMock()
        gb.close = AsyncMock()
        gb.add_vertex = AsyncMock(return_value={"id": "v1"})
        gb.add_edge = AsyncMock(return_value={"id": "e1"})
        gb.query_vertices = AsyncMock(return_value=[])
        gb.update_vertex_property = AsyncMock(return_value={"updated": True})
        gb.get_related_vertices = AsyncMock(return_value=[])
        return gb

    monkeypatch.setattr(mod, "GraphBuilder", make_builder)
    yield


def _ner_mock(entities):
    ner = MagicMock()
    ner.process_text = AsyncMock(return_value={"entities": entities})
    return ner


def _populator(entities=None):
    ner = _ner_mock(entities or [])
    return KnowledgeGraphPopulator("neptune://test", ner_processor=ner)


# ===========================================================================
# Dataclasses
# ===========================================================================

def test_entity_post_init_normalizes():
    ent = Entity(text="  Apple Inc  ", label="ORG", start=0, end=9, confidence=0.9)
    assert ent.normalized_form == "apple inc"


def test_entity_preserves_explicit_normalized_form():
    ent = Entity(text="X", label="ORG", start=0, end=1, normalized_form="custom")
    assert ent.normalized_form == "custom"


def test_relationship_defaults():
    rel = Relationship(source_entity="a", target_entity="b", relation_type="works_for", confidence=0.9)
    assert rel.context == ""
    assert rel.article_id is None


# ===========================================================================
# __init__
# ===========================================================================

def test_init_sets_mappings_and_threshold():
    pop = _populator()
    assert pop.entity_type_mapping["PERSON"] == "Person"
    assert pop.entity_type_mapping["LAW"] == "Policy"
    assert pop.min_confidence == 0.6
    assert pop.graph_builder.endpoint == "neptune://test"


# ===========================================================================
# _extract_entities
# ===========================================================================

@pytest.mark.asyncio
async def test_extract_entities_maps_fields():
    pop = _populator([
        {"text": "Alice", "label": "PERSON", "start": 0, "end": 5, "confidence": 0.95},
    ])
    ents = await pop._extract_entities("Alice works here")
    assert len(ents) == 1
    assert ents[0].text == "Alice"
    assert ents[0].label == "PERSON"
    assert ents[0].confidence == 0.95


@pytest.mark.asyncio
async def test_extract_entities_error_returns_empty():
    pop = _populator()
    pop.ner_processor.process_text = AsyncMock(side_effect=RuntimeError("ner down"))
    assert await pop._extract_entities("text") == []


# ===========================================================================
# _generate_entity_id / _get_entity_label / _determine_relationship_type
# ===========================================================================

def test_generate_entity_id_is_deterministic():
    pop = _populator()
    a = pop._generate_entity_id("apple inc", "ORG")
    b = pop._generate_entity_id("apple inc", "ORG")
    c = pop._generate_entity_id("apple inc", "PERSON")
    assert a == b
    assert a != c
    assert len(a) == 32  # md5 hexdigest


def test_get_entity_label_placeholder():
    pop = _populator()
    assert pop._get_entity_label("anything") == "ENTITY"


def test_determine_relationship_type_forward_and_reverse():
    pop = _populator()
    assert pop._determine_relationship_type("PERSON", "ORG") == "works_for"
    # reverse direction resolves to the same rule
    assert pop._determine_relationship_type("ORG", "PERSON") == "works_for"
    assert pop._determine_relationship_type("LAW", "GPE") == "applies_to"


def test_determine_relationship_type_default():
    pop = _populator()
    assert pop._determine_relationship_type("MONEY", "DATE") == "related_to"


# ===========================================================================
# _add_article_node
# ===========================================================================

@pytest.mark.asyncio
async def test_add_article_node_with_published_date():
    pop = _populator()
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result = await pop._add_article_node("art1", "Title", "Body content", dt)
    assert result == {"id": "v1"}
    call = pop.graph_builder.add_vertex.await_args
    label, props = call.args
    assert label == "Article"
    assert props["id"] == "art1"
    assert props["published_date"] == dt.isoformat()
    assert "content_hash" in props


@pytest.mark.asyncio
async def test_add_article_node_error_returns_none():
    pop = _populator()
    pop.graph_builder.add_vertex = AsyncMock(side_effect=RuntimeError("db"))
    result = await pop._add_article_node("art", "t", "c", None)
    assert result is None


# ===========================================================================
# _add_entity_node
# ===========================================================================

@pytest.mark.asyncio
async def test_add_entity_node_new():
    pop = _populator()
    pop._find_entity = AsyncMock(return_value=None)  # not existing -> add_vertex
    ent = Entity(text="Apple", label="ORG", start=0, end=5, confidence=0.9)
    result = await pop._add_entity_node(ent, "art1")
    assert result == {"id": "v1"}
    label, props = pop.graph_builder.add_vertex.await_args.args
    assert label == "Organization"
    assert props["entity_type"] == "ORG"


@pytest.mark.asyncio
async def test_add_entity_node_existing_updates():
    pop = _populator()
    pop._find_entity = AsyncMock(return_value={"id": "existing"})
    pop._update_entity_mentions = AsyncMock(return_value={"updated": True})
    ent = Entity(text="Apple", label="ORG", start=0, end=5, confidence=0.9)
    result = await pop._add_entity_node(ent, "art1")
    assert result == {"updated": True}
    pop._update_entity_mentions.assert_awaited_once()
    pop.graph_builder.add_vertex.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_entity_node_unknown_label_defaults_to_entity():
    pop = _populator()
    pop._find_entity = AsyncMock(return_value=None)
    ent = Entity(text="thing", label="WEIRD", start=0, end=5, confidence=0.5)
    await pop._add_entity_node(ent, "art1")
    label, _ = pop.graph_builder.add_vertex.await_args.args
    assert label == "Entity"


@pytest.mark.asyncio
async def test_add_entity_node_error_returns_none():
    pop = _populator()
    pop._find_entity = AsyncMock(side_effect=RuntimeError("boom"))
    ent = Entity(text="x", label="ORG", start=0, end=1, confidence=0.5)
    assert await pop._add_entity_node(ent, "a") is None


# ===========================================================================
# _link_entity_to_article
# ===========================================================================

@pytest.mark.asyncio
async def test_link_entity_to_article():
    pop = _populator()
    ent = Entity(text="Apple", label="ORG", start=3, end=8, confidence=0.9)
    result = await pop._link_entity_to_article(ent, "art1")
    assert result == {"id": "e1"}
    args = pop.graph_builder.add_edge.await_args.args
    # (source_id, target_id, "MENTIONED_IN", props)
    assert args[1] == "art1"
    assert args[2] == "MENTIONED_IN"
    assert args[3]["start_position"] == 3


@pytest.mark.asyncio
async def test_link_entity_to_article_error_returns_none():
    pop = _populator()
    pop.graph_builder.add_edge = AsyncMock(side_effect=RuntimeError("edge fail"))
    ent = Entity(text="x", label="ORG", start=0, end=1, confidence=0.5)
    assert await pop._link_entity_to_article(ent, "a") is None


# ===========================================================================
# _extract_relationships
# ===========================================================================

@pytest.mark.asyncio
async def test_extract_relationships_close_entities():
    pop = _populator()
    e1 = Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9)
    e2 = Entity(text="Acme", label="ORG", start=20, end=24, confidence=0.8)
    text = "Alice works at Acme corporation in the city."
    rels = await pop._extract_relationships([e1, e2], text, "art1")
    assert len(rels) == 1
    assert rels[0].relation_type == "works_for"
    assert 0 < rels[0].confidence <= 0.8
    assert rels[0].article_id == "art1"


@pytest.mark.asyncio
async def test_extract_relationships_far_apart_skipped():
    pop = _populator()
    e1 = Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9)
    e2 = Entity(text="Acme", label="ORG", start=500, end=504, confidence=0.8)
    rels = await pop._extract_relationships([e1, e2], "x" * 600, "art1")
    assert rels == []


@pytest.mark.asyncio
async def test_extract_relationships_same_entity_skipped():
    pop = _populator()
    e1 = Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9)
    e2 = Entity(text="Alice", label="PERSON", start=10, end=15, confidence=0.9)
    # Same normalized_form -> skipped.
    rels = await pop._extract_relationships([e1, e2], "Alice and Alice", "art1")
    assert rels == []


# ===========================================================================
# _add_relationship_edge
# ===========================================================================

@pytest.mark.asyncio
async def test_add_relationship_edge():
    pop = _populator()
    rel = Relationship(
        source_entity="alice", target_entity="acme",
        relation_type="works_for", confidence=0.8, context="Alice works at Acme",
        article_id="art1",
    )
    result = await pop._add_relationship_edge(rel)
    assert result == {"id": "e1"}
    args = pop.graph_builder.add_edge.await_args.args
    assert args[2] == "WORKS_FOR"  # relation_type uppercased


@pytest.mark.asyncio
async def test_add_relationship_edge_error_returns_none():
    pop = _populator()
    pop.graph_builder.add_edge = AsyncMock(side_effect=RuntimeError("edge"))
    rel = Relationship(source_entity="a", target_entity="b", relation_type="related_to", confidence=0.9)
    assert await pop._add_relationship_edge(rel) is None


# ===========================================================================
# historical / policy linking
# ===========================================================================

@pytest.mark.asyncio
async def test_link_to_historical_data():
    pop = _populator()
    pop._find_related_historical_events = AsyncMock(return_value=[{"id": "ev1"}])
    pop._find_related_policies = AsyncMock(return_value=[{"id": "pol1"}])
    pop._create_historical_link = AsyncMock(return_value={"id": "link"})
    ents = [
        Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9),
        Entity(text="GDPR", label="LAW", start=10, end=14, confidence=0.9),
    ]
    links = await pop._link_to_historical_data(ents, "art1")
    # PERSON -> event + policy (PERSON is in both lists); LAW -> policy.
    assert len(links) == 3


@pytest.mark.asyncio
async def test_link_to_historical_data_error_returns_empty():
    pop = _populator()
    pop._find_related_historical_events = AsyncMock(side_effect=RuntimeError("q"))
    ents = [Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9)]
    assert await pop._link_to_historical_data(ents, "art1") == []


@pytest.mark.asyncio
async def test_find_related_historical_events():
    pop = _populator()
    pop.graph_builder.query_vertices = AsyncMock(return_value=[{"id": "ev"}])
    ent = Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9)
    result = await pop._find_related_historical_events(ent)
    assert result == [{"id": "ev"}]


@pytest.mark.asyncio
async def test_find_related_historical_events_error():
    pop = _populator()
    pop.graph_builder.query_vertices = AsyncMock(side_effect=RuntimeError("db"))
    ent = Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9)
    assert await pop._find_related_historical_events(ent) == []


@pytest.mark.asyncio
async def test_find_related_policies():
    pop = _populator()
    pop.graph_builder.query_vertices = AsyncMock(return_value=[{"id": "pol"}])
    ent = Entity(text="GDPR", label="LAW", start=0, end=4, confidence=0.9)
    assert await pop._find_related_policies(ent) == [{"id": "pol"}]


@pytest.mark.asyncio
async def test_find_related_policies_error():
    pop = _populator()
    pop.graph_builder.query_vertices = AsyncMock(side_effect=RuntimeError("db"))
    ent = Entity(text="GDPR", label="LAW", start=0, end=4, confidence=0.9)
    assert await pop._find_related_policies(ent) == []


@pytest.mark.asyncio
async def test_create_historical_link():
    pop = _populator()
    ent = Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9)
    result = await pop._create_historical_link(ent, {"id": "ev1"}, "art1", "historical_reference")
    assert result == {"id": "e1"}
    args = pop.graph_builder.add_edge.await_args.args
    assert args[1] == "ev1"
    assert args[2] == "HISTORICAL_REFERENCE"


@pytest.mark.asyncio
async def test_create_historical_link_no_id_returns_none():
    pop = _populator()
    ent = Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9)
    # historical item without an 'id' -> None (no edge created).
    result = await pop._create_historical_link(ent, {}, "art1", "policy_reference")
    assert result is None


@pytest.mark.asyncio
async def test_create_historical_link_error_returns_none():
    pop = _populator()
    pop.graph_builder.add_edge = AsyncMock(side_effect=RuntimeError("edge"))
    ent = Entity(text="Alice", label="PERSON", start=0, end=5, confidence=0.9)
    assert await pop._create_historical_link(ent, {"id": "x"}, "art1", "t") is None


# ===========================================================================
# _find_entity / _update_entity_mentions / _find_entity_by_name
# ===========================================================================

@pytest.mark.asyncio
async def test_find_entity_found_and_missing():
    pop = _populator()
    pop.graph_builder.query_vertices = AsyncMock(return_value=[{"id": "x"}])
    assert await pop._find_entity("x") == {"id": "x"}
    pop.graph_builder.query_vertices = AsyncMock(return_value=[])
    assert await pop._find_entity("x") is None


@pytest.mark.asyncio
async def test_find_entity_error_returns_none():
    pop = _populator()
    pop.graph_builder.query_vertices = AsyncMock(side_effect=RuntimeError("db"))
    assert await pop._find_entity("x") is None


@pytest.mark.asyncio
async def test_update_entity_mentions():
    pop = _populator()
    assert await pop._update_entity_mentions("eid", "art1") == {"updated": True}


@pytest.mark.asyncio
async def test_update_entity_mentions_error():
    pop = _populator()
    pop.graph_builder.update_vertex_property = AsyncMock(side_effect=RuntimeError("db"))
    assert await pop._update_entity_mentions("eid", "art1") is None


@pytest.mark.asyncio
async def test_find_entity_by_name():
    pop = _populator()
    pop.graph_builder.query_vertices = AsyncMock(return_value=[{"id": "n"}])
    assert await pop._find_entity_by_name("alice") == {"id": "n"}


@pytest.mark.asyncio
async def test_find_entity_by_name_error():
    pop = _populator()
    pop.graph_builder.query_vertices = AsyncMock(side_effect=RuntimeError("db"))
    assert await pop._find_entity_by_name("alice") is None


# ===========================================================================
# get_related_entities
# ===========================================================================

@pytest.mark.asyncio
async def test_get_related_entities_success():
    pop = _populator()
    pop._find_entity_by_name = AsyncMock(return_value={"id": "eid"})
    pop.graph_builder.get_related_vertices = AsyncMock(return_value=[
        {"text": "Acme", "entity_type": "ORG", "relationship_type": "works_for",
         "confidence": 0.8, "mention_count": 3},
    ])
    result = await pop.get_related_entities("Alice", max_results=5)
    assert len(result) == 1
    assert result[0]["entity_name"] == "Acme"
    assert result[0]["relationship_type"] == "works_for"
    assert result[0]["mention_count"] == 3


@pytest.mark.asyncio
async def test_get_related_entities_not_found():
    pop = _populator()
    pop._find_entity_by_name = AsyncMock(return_value=None)
    assert await pop.get_related_entities("Ghost") == []


@pytest.mark.asyncio
async def test_get_related_entities_error_returns_empty():
    pop = _populator()
    pop._find_entity_by_name = AsyncMock(side_effect=RuntimeError("db"))
    assert await pop.get_related_entities("Alice") == []


# ===========================================================================
# populate_from_article (integration of the pieces)
# ===========================================================================

@pytest.mark.asyncio
async def test_populate_from_article_full():
    pop = _populator([
        {"text": "Alice", "label": "PERSON", "start": 0, "end": 5, "confidence": 0.9},
        {"text": "Acme", "label": "ORG", "start": 20, "end": 24, "confidence": 0.85},
    ])
    pop._find_entity = AsyncMock(return_value=None)
    stats = await pop.populate_from_article("art1", "Alice at Acme", "Alice works at Acme corp.")
    assert stats["article_id"] == "art1"
    assert stats["entities_found"] == 2
    assert stats["entities_added"] == 2
    # PERSON+ORG close together -> a works_for relationship above threshold.
    assert stats["relationships_found"] >= 1
    assert "processing_timestamp" in stats
    pop.graph_builder.connect.assert_awaited()


@pytest.mark.asyncio
async def test_populate_from_article_reraises_on_error():
    pop = _populator()
    pop.graph_builder.connect = AsyncMock(side_effect=RuntimeError("no neptune"))
    with pytest.raises(RuntimeError):
        await pop.populate_from_article("art1", "t", "c")


# ===========================================================================
# batch_populate_articles
# ===========================================================================

@pytest.mark.asyncio
async def test_batch_populate_articles_mixed_success_failure():
    pop = _populator()
    good = {"entities_added": 2, "relationships_added": 1, "historical_links": 0}

    async def fake_populate(article_id, title, content, published_date):
        if article_id == "bad":
            raise RuntimeError("boom")
        return good

    pop.populate_from_article = fake_populate
    articles = [
        {"id": "a1", "title": "T", "content": "C", "published_date": "2024-01-01T00:00:00Z"},
        {"id": "bad", "title": "T", "content": "C"},
    ]
    stats = await pop.batch_populate_articles(articles)
    assert stats["total_articles"] == 2
    assert stats["processed_articles"] == 1
    assert stats["failed_articles"] == 1
    assert stats["total_entities_added"] == 2
    assert stats["success_rate"] == 0.5


@pytest.mark.asyncio
async def test_batch_populate_articles_empty():
    pop = _populator()
    stats = await pop.batch_populate_articles([])
    assert stats["total_articles"] == 0
    assert stats["success_rate"] == 0


# ===========================================================================
# close
# ===========================================================================

@pytest.mark.asyncio
async def test_close_with_connection():
    pop = _populator()
    pop.graph_builder.connection = object()
    await pop.close()
    pop.graph_builder.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_no_connection():
    pop = _populator()
    pop.graph_builder.connection = None
    await pop.close()
    pop.graph_builder.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_swallows_error():
    pop = _populator()
    pop.graph_builder.connection = object()
    pop.graph_builder.close = AsyncMock(side_effect=RuntimeError("close fail"))
    # Should not raise.
    await pop.close()


# ===========================================================================
# Module-level convenience functions
# ===========================================================================

@pytest.mark.asyncio
async def test_populate_article_to_graph(monkeypatch):
    captured = {}

    class FakePopulator:
        def __init__(self, endpoint):
            captured["endpoint"] = endpoint

        async def populate_from_article(self, aid, title, content, pub):
            captured["aid"] = aid
            return {"article_id": aid, "entities_added": 1}

        async def close(self):
            captured["closed"] = True

    monkeypatch.setattr(mod, "KnowledgeGraphPopulator", FakePopulator)
    result = await mod.populate_article_to_graph(
        {"id": "a1", "title": "T", "content": "C"}, "neptune://x"
    )
    assert result["article_id"] == "a1"
    assert captured["endpoint"] == "neptune://x"
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_get_entity_relationships(monkeypatch):
    captured = {}

    class FakePopulator:
        def __init__(self, endpoint):
            captured["endpoint"] = endpoint

        async def get_related_entities(self, name, max_results):
            captured["name"] = name
            captured["max"] = max_results
            return [{"entity_name": "Acme"}]

        async def close(self):
            captured["closed"] = True

    monkeypatch.setattr(mod, "KnowledgeGraphPopulator", FakePopulator)
    result = await mod.get_entity_relationships("Alice", "neptune://x", max_results=7)
    assert result == [{"entity_name": "Acme"}]
    assert captured["max"] == 7
    assert captured["closed"] is True
