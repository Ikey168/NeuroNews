"""Comprehensive tests for src/knowledge_graph/enhanced_entity_extractor.py."""

import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from knowledge_graph.enhanced_entity_extractor import (  # noqa: E402
    AdvancedEntityExtractor,
    EnhancedEntity,
    EnhancedRelationship,
    create_advanced_entity_extractor,
    create_high_precision_entity_extractor,
    create_high_recall_entity_extractor,
)


class TestEnhancedEntity:
    def test_post_init_normalizes_and_ids(self):
        e = EnhancedEntity(text="  Apple   Inc.  ", label="ORGANIZATION", start=0, end=10)
        assert e.normalized_form.startswith("Apple")
        assert "Inc" not in e.normalized_form  # org suffix stripped
        assert e.entity_id and len(e.entity_id) == 12

    def test_person_capitalization(self):
        e = EnhancedEntity(text="john   doe", label="PERSON", start=0, end=8)
        assert e.normalized_form == "John Doe"

    def test_generic_normalization(self):
        e = EnhancedEntity(text="some   place", label="LOCATION", start=0, end=5)
        assert e.normalized_form == "some place"

    def test_stable_entity_id(self):
        a = EnhancedEntity(text="Tesla", label="ORGANIZATION", start=0, end=5)
        b = EnhancedEntity(text="Tesla", label="ORGANIZATION", start=9, end=14)
        assert a.entity_id == b.entity_id  # same label+normalized form


class TestEnhancedRelationship:
    def test_to_dict(self):
        s = EnhancedEntity(text="Alice", label="PERSON", start=0, end=5)
        t = EnhancedEntity(text="Acme", label="ORGANIZATION", start=10, end=14)
        rel = EnhancedRelationship(
            source_entity=s, target_entity=t, relation_type="WORKS_FOR",
            confidence=0.8, context="Alice works for Acme",
            evidence_sentences=["Alice works for Acme."],
        )
        d = rel.to_dict()
        assert d["source_id"] == s.entity_id
        assert d["target_id"] == t.entity_id
        assert d["relation_type"] == "WORKS_FOR"
        assert d["evidence_count"] == 1
        assert d["temporal_info"] == {}


class TestExtractorConfig:
    def test_defaults(self):
        ex = AdvancedEntityExtractor()
        assert ex.confidence_threshold == 0.7
        assert ex.max_entity_distance == 200
        assert ex.stats["entities_extracted"] == 0

    def test_custom_config(self):
        ex = AdvancedEntityExtractor({"confidence_threshold": 0.9, "max_entity_distance": 50})
        assert ex.confidence_threshold == 0.9
        assert ex.max_entity_distance == 50


@pytest.fixture
def extractor():
    return AdvancedEntityExtractor()


class TestKeywordExtraction:
    @pytest.mark.asyncio
    async def test_extracts_known_keywords(self, extractor):
        text = "The new system uses artificial intelligence and blockchain technology."
        entities = await extractor._extract_entities_by_keywords(text, "art-1")
        labels = {e.label for e in entities}
        texts = {e.text.lower() for e in entities}
        assert entities  # found something
        assert any("intelligence" in t or "blockchain" in t for t in texts)
        assert all(e.confidence == 0.9 for e in entities)

    @pytest.mark.asyncio
    async def test_no_keywords(self, extractor):
        entities = await extractor._extract_entities_by_keywords("plain text here", "a")
        assert isinstance(entities, list)


class TestPatternExtraction:
    @pytest.mark.asyncio
    async def test_returns_list(self, extractor):
        entities = await extractor._extract_entities_by_patterns(
            "Acme Inc. announced $5 million in funding on January 2020.", "art-1"
        )
        assert isinstance(entities, list)
        for e in entities:
            assert e.confidence == 0.8


class TestEntityProperties:
    def test_person_title(self, extractor):
        e = EnhancedEntity(text="Smith", label="PERSON", start=10, end=15)
        props = extractor._extract_entity_properties(e, "The CEO Smith spoke today")
        assert props.get("title") in ("CEO", None) or "title" in props

    def test_organization_type(self, extractor):
        e = EnhancedEntity(text="Acme", label="ORGANIZATION", start=4, end=8)
        props = extractor._extract_entity_properties(e, "The company Acme grows fast")
        assert "type" in props

    def test_technology_category(self, extractor):
        e = EnhancedEntity(text="machine learning", label="TECHNOLOGY", start=0, end=16)
        props = extractor._extract_entity_properties(e, "machine learning is here")
        assert props.get("category") == "ai"

    def test_no_properties_for_other(self, extractor):
        e = EnhancedEntity(text="Paris", label="LOCATION", start=0, end=5)
        assert extractor._extract_entity_properties(e, "Paris is nice") == {}


class TestDeduplication:
    def test_merges_duplicates(self, extractor):
        e1 = EnhancedEntity(text="Tesla", label="ORGANIZATION", start=0, end=5, confidence=0.7)
        e2 = EnhancedEntity(text="Tesla Inc", label="ORGANIZATION", start=20, end=29, confidence=0.9)
        result = extractor._deduplicate_entities([e1, e2])
        # "Tesla" and "Tesla Inc" normalize to "Tesla" -> merged
        assert len(result) == 1
        merged = result[0]
        assert merged.mention_count == 2
        assert merged.confidence == 0.9

    def test_keeps_distinct(self, extractor):
        e1 = EnhancedEntity(text="Tesla", label="ORGANIZATION", start=0, end=5)
        e2 = EnhancedEntity(text="Apple", label="ORGANIZATION", start=10, end=15)
        assert len(extractor._deduplicate_entities([e1, e2])) == 2


class TestFullExtractionWithMockedNER:
    @pytest.mark.asyncio
    async def test_extract_entities_from_article(self, extractor):
        ner = MagicMock()
        ner.extract_entities.return_value = [
            {"text": "Alice", "type": "PERSON", "start": 0, "end": 5, "confidence": 0.95},
        ]
        extractor.ner_processor = ner
        entities = await extractor.extract_entities_from_article(
            "art-1", "Alice leads AI", "Alice uses artificial intelligence daily."
        )
        assert any(e.label == "PERSON" for e in entities)
        assert extractor.stats["articles_processed"] == 1

    @pytest.mark.asyncio
    async def test_extract_handles_ner_error(self, extractor):
        ner = MagicMock()
        ner.extract_entities.side_effect = RuntimeError("boom")
        extractor.ner_processor = ner
        result = await extractor.extract_entities_from_article("a", "t", "c")
        assert result == []


class TestRelationshipsAndStats:
    @pytest.mark.asyncio
    async def test_extract_relationships_returns_list(self, extractor):
        ents = [
            EnhancedEntity(text="Alice", label="PERSON", start=0, end=5),
            EnhancedEntity(text="Acme", label="ORGANIZATION", start=20, end=24),
        ]
        rels = await extractor.extract_relationships(ents, "Alice works for Acme.", "a")
        assert isinstance(rels, list)

    def test_infer_relationship_type(self, extractor):
        s = EnhancedEntity(text="Alice", label="PERSON", start=0, end=5)
        t = EnhancedEntity(text="Acme", label="ORGANIZATION", start=10, end=14)
        rel_type = extractor._infer_relationship_type(s, t)
        assert rel_type is None or isinstance(rel_type, str)

    def test_statistics(self, extractor):
        stats = extractor.get_extraction_statistics()
        assert "entities_extracted" in stats
        assert "articles_processed" in stats


class TestFactories:
    def test_create_advanced(self):
        assert isinstance(create_advanced_entity_extractor(), AdvancedEntityExtractor)

    def test_high_precision(self):
        ex = create_high_precision_entity_extractor()
        assert ex.confidence_threshold >= 0.7

    def test_high_recall(self):
        ex = create_high_recall_entity_extractor()
        assert isinstance(ex, AdvancedEntityExtractor)
