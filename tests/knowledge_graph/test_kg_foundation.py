"""
Tests for the knowledge graph foundation (ontology, model, store).

Covers the exit criteria: facts are stored as cited triples, and the ontology
validates entity and relation types (including subtype-aware domain/range
constraints, provenance on every triple, and reified edge properties).
"""

import pytest

from src.knowledge_graph.foundation import (
    EntityType,
    KnowledgeGraphStore,
    Node,
    OntologyViolation,
    Provenance,
    RelationType,
    Triple,
    is_subtype,
    is_valid_relation,
    make_node_id,
    validate_relation,
)


# --------------------------------------------------------------------------- #
# Ontology
# --------------------------------------------------------------------------- #


def test_is_subtype_hierarchy():
    assert is_subtype(EntityType.PERSON, EntityType.ENTITY)
    assert is_subtype(EntityType.METHOD, EntityType.CONCEPT)
    assert is_subtype(EntityType.METHOD, EntityType.ENTITY)  # transitive
    assert is_subtype(EntityType.CONCEPT, EntityType.CONCEPT)  # reflexive
    assert not is_subtype(EntityType.PERSON, EntityType.ORGANIZATION)
    assert not is_subtype(EntityType.ENTITY, EntityType.PERSON)


@pytest.mark.parametrize(
    "relation,subj,obj",
    [
        (RelationType.AUTHORED_BY, EntityType.DOCUMENT, EntityType.PERSON),
        (RelationType.AUTHORED_BY, EntityType.DOCUMENT, EntityType.ORGANIZATION),
        (RelationType.CITES, EntityType.DOCUMENT, EntityType.DOCUMENT),
        (RelationType.DEFINES, EntityType.DOCUMENT, EntityType.CONCEPT),
        (RelationType.MENTIONS, EntityType.DOCUMENT, EntityType.PERSON),  # subtype of Entity
        (RelationType.INSTANCE_OF, EntityType.PERSON, EntityType.CONCEPT),
        (RelationType.INSTANCE_OF, EntityType.METHOD, EntityType.CONCEPT),
        (RelationType.SUPPORTS, EntityType.CLAIM, EntityType.CLAIM),
        (RelationType.CONTRADICTS, EntityType.DOCUMENT, EntityType.CLAIM),
        (RelationType.PART_OF, EntityType.CONCEPT, EntityType.CONCEPT),
    ],
)
def test_valid_relations(relation, subj, obj):
    assert is_valid_relation(relation, subj, obj)


@pytest.mark.parametrize(
    "relation,subj,obj",
    [
        (RelationType.CITES, EntityType.PERSON, EntityType.DOCUMENT),
        (RelationType.AUTHORED_BY, EntityType.DOCUMENT, EntityType.DOCUMENT),
        (RelationType.DEFINES, EntityType.PERSON, EntityType.CONCEPT),
        (RelationType.SUPPORTS, EntityType.PERSON, EntityType.CLAIM),
        (RelationType.PART_OF, EntityType.CONCEPT, EntityType.DOCUMENT),
    ],
)
def test_invalid_relations_raise(relation, subj, obj):
    assert not is_valid_relation(relation, subj, obj)
    with pytest.raises(OntologyViolation):
        validate_relation(relation, subj, obj)


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


def test_node_id_is_deterministic_and_type_aware():
    a = Node(type=EntityType.CONCEPT, name="Knowledge Graph")
    b = Node(type=EntityType.CONCEPT, name="  knowledge   graph ")
    assert a.node_id == b.node_id == make_node_id(EntityType.CONCEPT, "knowledge graph")
    # Same name, different type -> different node.
    assert Node(type=EntityType.PERSON, name="Knowledge Graph").node_id != a.node_id


def test_provenance_requires_source_and_valid_confidence():
    with pytest.raises(ValueError):
        Provenance(source_doc="")
    with pytest.raises(ValueError):
        Provenance(source_doc="doc-1", confidence=1.5)
    p = Provenance(source_doc="doc-1", confidence=0.9, chunk_id="c3", extractor="rules")
    assert p.to_dict()["chunk_id"] == "c3"


def test_triple_requires_provenance_and_carries_properties():
    with pytest.raises(TypeError):
        Triple("a", RelationType.CITES, "b", provenance={"source_doc": "x"})
    t = Triple(
        "doc:1",
        RelationType.CITES,
        "doc:2",
        provenance=Provenance(source_doc="doc:1", confidence=1.0),
        properties={"year": 2023, "context": "as shown in"},
    )
    assert t.key == ("doc:1", "CITES", "doc:2")
    assert t.properties["year"] == 2023


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #


@pytest.fixture
def store():
    return KnowledgeGraphStore()


def _doc(store, name):
    return store.add_node(Node(type=EntityType.DOCUMENT, name=name))


def test_store_rejects_triple_with_unknown_nodes(store):
    paper = _doc(store, "Paper A")
    t = Triple(
        paper.node_id,
        RelationType.CITES,
        "doc:missing",
        provenance=Provenance(source_doc=paper.node_id),
    )
    with pytest.raises(OntologyViolation):
        store.add_triple(t)


def test_store_enforces_ontology_on_write(store):
    paper = _doc(store, "Paper A")
    person = store.add_node(Node(type=EntityType.PERSON, name="Ada Lovelace"))
    # Document CITES Person is not permitted.
    bad = Triple(
        paper.node_id,
        RelationType.CITES,
        person.node_id,
        provenance=Provenance(source_doc=paper.node_id),
    )
    with pytest.raises(OntologyViolation):
        store.add_triple(bad)


def test_store_stores_cited_triples_and_accumulates_provenance(store):
    a = _doc(store, "Paper A")
    b = _doc(store, "Paper B")
    t1 = Triple(a.node_id, RelationType.CITES, b.node_id,
                provenance=Provenance(source_doc=a.node_id, confidence=0.7, chunk_id="c1"))
    store.add_triple(t1)
    # Re-assert the same fact from another location with higher confidence.
    t2 = Triple(a.node_id, RelationType.CITES, b.node_id,
                provenance=Provenance(source_doc=a.node_id, confidence=0.95, chunk_id="c2"),
                properties={"year": 2024})
    stored = store.add_triple(t2)

    assert store.triple_count == 1  # same fact, not duplicated
    assert len(store.provenance_for(stored)) == 2  # both citations retained
    assert stored.provenance.confidence == 0.95  # representative = highest confidence
    assert stored.properties["year"] == 2024  # reified edge property merged


def test_store_recenters_on_concepts_and_claims(store):
    """Documents are anchors; concepts/claims are the knowledge, all cited."""
    paper = _doc(store, "Attention Is All You Need")
    concept = store.add_node(Node(type=EntityType.CONCEPT, name="Transformer"))
    claim = store.add_node(Node(type=EntityType.CLAIM, name="Attention outperforms recurrence"))

    prov = Provenance(source_doc=paper.node_id, confidence=0.9, chunk_id="abstract")
    store.add_triple(Triple(paper.node_id, RelationType.DEFINES, concept.node_id, provenance=prov))
    store.add_triple(Triple(paper.node_id, RelationType.SUPPORTS, claim.node_id, provenance=prov))
    store.add_triple(Triple(paper.node_id, RelationType.MENTIONS, concept.node_id, provenance=prov))

    assert store.node_count == 3
    assert store.triple_count == 3
    # Every fact about the concept is cited back to a document anchor.
    for t in store.neighbors(concept.node_id):
        assert t.provenance.source_doc == paper.node_id
    assert len(store.triples(predicate=RelationType.DEFINES)) == 1
    assert len(store.nodes_by_type(EntityType.CLAIM)) == 1


def test_store_add_node_merges_aliases_not_type(store):
    store.add_node(Node(type=EntityType.PERSON, name="Hinton", aliases=["G. Hinton"]))
    merged = store.add_node(Node(type=EntityType.PERSON, name="Hinton", aliases=["Geoffrey Hinton"]))
    assert set(merged.aliases) == {"G. Hinton", "Geoffrey Hinton"}
    # Same id but conflicting type is rejected.
    bad = Node(type=EntityType.ORGANIZATION, name="Hinton")
    bad.node_id = merged.node_id
    with pytest.raises(OntologyViolation):
        store.add_node(bad)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
