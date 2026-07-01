"""Coverage tests for src/knowledge_graph/semantic_analyzer.py.

Targets the branches the existing comprehensive suite leaves uncovered:

  * find_semantic_patterns "chain" and "hub" pattern types (lines 211-256 region)
  * frequent-pattern threshold (>= 3) actually firing (line 214-221)
  * get_contextual_relevance: empty entity/context words (line 289) and the
    non-keyword default branch (line 297)
  * _create_entity_clusters: skipping an already-used entity id (line 356)
  * _compute_textual_similarity empty-string short circuit (line 409)
  * _compute_structural_similarity both-empty -> 1.0 (line 426)
  * _determine_relationship_type person/organization, event, default branches
    (lines 441-446)
  * _calculate_cluster_coherence single-entity -> 1.0 (line 451)

Pure-python module; no heavy deps.
"""
from __future__ import annotations

import pytest

pytest.importorskip("src.knowledge_graph.semantic_analyzer")

from src.knowledge_graph.semantic_analyzer import (  # noqa: E402
    RelationshipType,
    SemanticAnalyzer,
    SemanticRelationship,
)


def _rel(source, target, rel_type=RelationshipType.ASSOCIATIVE, strength=0.9):
    return SemanticRelationship(
        source_entity=source,
        target_entity=target,
        relationship_type=rel_type,
        strength=strength,
        confidence=strength,
        context=[],
        properties={},
    )


# ---------------------------------------------------------------------------
# find_semantic_patterns
# ---------------------------------------------------------------------------

class TestFindSemanticPatterns:
    def test_frequent_pattern_fires_at_threshold(self):
        analyzer = SemanticAnalyzer()
        # 3 CAUSAL rels + 1 TEMPORAL -> only CAUSAL crosses the >=3 threshold.
        rels = [
            _rel("a", "b", RelationshipType.CAUSAL),
            _rel("c", "d", RelationshipType.CAUSAL),
            _rel("e", "f", RelationshipType.CAUSAL),
            _rel("g", "h", RelationshipType.TEMPORAL),
        ]
        patterns = analyzer.find_semantic_patterns(rels, pattern_type="frequent")
        assert len(patterns) == 1
        p = patterns[0]
        assert p["pattern_type"] == "frequent_relationship"
        assert p["relationship_type"] == "causal"
        assert p["frequency"] == 3
        assert p["relative_frequency"] == pytest.approx(3 / 4)

    def test_chain_pattern(self):
        analyzer = SemanticAnalyzer()
        # 'hub' entity connects to 3 targets -> a chain of length 3.
        rels = [
            _rel("hub", "t1"),
            _rel("hub", "t2"),
            _rel("hub", "t3"),
            _rel("lonely", "only"),  # single target -> not a chain
        ]
        patterns = analyzer.find_semantic_patterns(rels, pattern_type="chain")
        assert len(patterns) == 1
        chain = patterns[0]
        assert chain["pattern_type"] == "relationship_chain"
        assert chain["source_entity"] == "hub"
        assert chain["chain_length"] == 3
        assert chain["target_entities"] == ["t1", "t2", "t3"]

    def test_hub_pattern(self):
        analyzer = SemanticAnalyzer()
        # 'center' is connected to many peripherals; peripherals have degree 1.
        rels = [
            _rel("center", "p1"),
            _rel("center", "p2"),
            _rel("center", "p3"),
            _rel("center", "p4"),
        ]
        patterns = analyzer.find_semantic_patterns(rels, pattern_type="hub")
        # center degree = 4, others degree = 1; avg is well below center*2 rule.
        hub_entities = {p["entity"] for p in patterns}
        assert "center" in hub_entities
        center = next(p for p in patterns if p["entity"] == "center")
        assert center["pattern_type"] == "hub_entity"
        assert center["degree"] == 4
        assert center["centrality_score"] == pytest.approx(1.0)

    def test_hub_pattern_empty_relationships_returns_empty(self):
        analyzer = SemanticAnalyzer()
        assert analyzer.find_semantic_patterns([], pattern_type="hub") == []


# ---------------------------------------------------------------------------
# get_contextual_relevance
# ---------------------------------------------------------------------------

class TestContextualRelevance:
    def test_no_context_returns_neutral(self):
        analyzer = SemanticAnalyzer()
        assert analyzer.get_contextual_relevance({"name": "x"}, []) == 0.5

    def test_keyword_overlap(self):
        analyzer = SemanticAnalyzer()
        score = analyzer.get_contextual_relevance(
            {"name": "climate policy", "description": "warming"},
            ["climate change and policy"],
        )
        assert 0.0 < score <= 1.0

    def test_empty_entity_words_returns_zero(self):
        analyzer = SemanticAnalyzer()
        # entity has no name/description text -> entity_words empty -> 0.0 (line 289)
        score = analyzer.get_contextual_relevance(
            {"name": "", "description": ""},
            ["some context here"],
        )
        assert score == 0.0

    def test_non_keyword_method_uses_property_count_default(self):
        analyzer = SemanticAnalyzer()
        # relevance_method != keyword_matching -> default branch (line 297)
        entity = {"properties": {"a": 1, "b": 2, "c": 3}}
        score = analyzer.get_contextual_relevance(
            entity, ["ctx"], relevance_method="embedding"
        )
        assert score == pytest.approx(min(1.0, 3 * 0.2))

    def test_non_keyword_method_caps_at_one(self):
        analyzer = SemanticAnalyzer()
        entity = {"properties": {str(i): i for i in range(10)}}
        score = analyzer.get_contextual_relevance(
            entity, ["ctx"], relevance_method="embedding"
        )
        assert score == 1.0


# ---------------------------------------------------------------------------
# similarity helpers
# ---------------------------------------------------------------------------

class TestSimilarityHelpers:
    def test_textual_similarity_empty_short_circuit(self):
        analyzer = SemanticAnalyzer()
        assert analyzer._compute_textual_similarity("", "anything") == 0.0
        assert analyzer._compute_textual_similarity("anything", "") == 0.0

    def test_structural_similarity_both_empty_is_one(self):
        analyzer = SemanticAnalyzer()
        # Two dicts with zero keys -> both prop sets empty -> 1.0 (line 426).
        assert analyzer._compute_structural_similarity({}, {}) == 1.0

    def test_structural_similarity_partial_overlap(self):
        analyzer = SemanticAnalyzer()
        sim = analyzer._compute_structural_similarity(
            {"a": 1, "b": 2}, {"b": 3, "c": 4}
        )
        # intersection {b}=1, union {a,b,c}=3
        assert sim == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# _determine_relationship_type branches
# ---------------------------------------------------------------------------

class TestDetermineRelationshipType:
    def test_same_type_is_similarity(self):
        analyzer = SemanticAnalyzer()
        rt = analyzer._determine_relationship_type(
            {"type": "Person"}, {"type": "person"}
        )
        assert rt == RelationshipType.SIMILARITY

    def test_person_organization_is_associative(self):
        analyzer = SemanticAnalyzer()
        rt = analyzer._determine_relationship_type(
            {"type": "Person"}, {"type": "Organization"}
        )
        assert rt == RelationshipType.ASSOCIATIVE

    def test_event_involved_is_temporal(self):
        analyzer = SemanticAnalyzer()
        rt = analyzer._determine_relationship_type(
            {"type": "Location"}, {"type": "Event"}
        )
        assert rt == RelationshipType.TEMPORAL

    def test_default_branch_is_associative(self):
        analyzer = SemanticAnalyzer()
        rt = analyzer._determine_relationship_type(
            {"type": "Location"}, {"type": "Technology"}
        )
        assert rt == RelationshipType.ASSOCIATIVE


# ---------------------------------------------------------------------------
# clustering internals
# ---------------------------------------------------------------------------

class TestClustering:
    def test_cluster_coherence_single_entity_is_one(self):
        analyzer = SemanticAnalyzer()
        assert analyzer._calculate_cluster_coherence([{"name": "solo"}]) == 1.0

    def test_create_clusters_skips_used_entities(self):
        # Force everything similar so the first pass consumes the later entities,
        # exercising the "already used" continue branch (line 356) on the outer
        # loop when it reaches an entity that was folded into an earlier cluster.
        analyzer = SemanticAnalyzer(similarity_threshold=0.0)
        entities = [
            {"id": "e1", "name": "alpha shared token", "type": "concept"},
            {"id": "e2", "name": "beta shared token", "type": "concept"},
            {"id": "e3", "name": "gamma shared token", "type": "concept"},
        ]
        clusters = analyzer._create_entity_clusters(entities)
        # All three collapse into a single cluster centered on e1.
        assert len(clusters) == 1
        assert clusters[0].centroid_entity == "e1"
        assert set(clusters[0].entities) >= {"e1", "e2"}

    def test_compute_similarity_dispatch_methods(self):
        analyzer = SemanticAnalyzer()
        e1 = {"name": "Apple Inc", "type": "Organization"}
        e2 = {"name": "Apple Inc", "type": "Organization"}
        # "textual" branch (line 182)
        textual = analyzer.compute_entity_similarity(e1, e2, similarity_method="textual")
        assert textual == pytest.approx(1.0)
        # "structural" branch (line 184) -- identical key sets -> 1.0
        structural = analyzer.compute_entity_similarity(
            e1, e2, similarity_method="structural"
        )
        assert structural == pytest.approx(1.0)
        # default "combined" averages the two
        combined = analyzer.compute_entity_similarity(e1, e2)
        assert combined == pytest.approx((textual + structural) / 2.0)

    def test_metrics_with_no_relationships_or_clusters(self):
        analyzer = SemanticAnalyzer(similarity_threshold=0.99)
        # Dissimilar single-token entities -> no relationships, no clusters, so
        # the zero-branches for avg strength (line 393) and coherence (402) run.
        entities = [
            {"id": "e1", "name": "orange", "type": "fruit"},
            {"id": "e2", "name": "hammer", "type": "tool"},
        ]
        result = analyzer.analyze_entity_relationships(entities)
        assert result.relationship_count == 0
        assert result.semantic_metrics["avg_relationship_strength"] == 0.0
        assert result.semantic_metrics["semantic_coherence"] == 0.0

    def test_analyze_relationships_updates_stats(self):
        analyzer = SemanticAnalyzer(similarity_threshold=0.0)
        entities = [
            {"id": "e1", "name": "shared token here", "type": "concept"},
            {"id": "e2", "name": "shared token also", "type": "concept"},
        ]
        result = analyzer.analyze_entity_relationships(
            entities, include_weak_relationships=True
        )
        assert result.entity_count == 2
        assert result.relationship_count >= 1
        stats = analyzer.get_analysis_statistics()
        assert stats["total_analyses"] == 1
        assert stats["total_relationships_found"] == result.relationship_count
