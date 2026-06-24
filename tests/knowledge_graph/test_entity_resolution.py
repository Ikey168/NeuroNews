"""
Tests for entity resolution (#516).

Covers the exit criterion ("Geoffrey Hinton" / "Hinton" / "G. Hinton" resolve to
one canonical node) plus organization/concept fuzzy matching, an optional
embedding fallback, guarding against over-merging, and store backfill that
merges duplicate nodes and rewrites triples to canonical ids.
"""

import pytest

from src.knowledge_graph.foundation import (
    EntityResolver,
    EntityType,
    KnowledgeGraphStore,
    Node,
    Provenance,
    RelationType,
    Triple,
    canonicalize_store,
)


# --------------------------------------------------------------------------- #
# People
# --------------------------------------------------------------------------- #


def test_person_variants_resolve_to_one_node():
    r = EntityResolver()
    a = r.resolve(EntityType.PERSON, "Hinton")
    b = r.resolve(EntityType.PERSON, "Geoffrey Hinton")
    c = r.resolve(EntityType.PERSON, "G. Hinton")

    assert a.node_id == b.node_id == c.node_id
    assert r.canonical_count(EntityType.PERSON) == 1
    # The most complete surface form becomes the display name; all are aliases.
    assert b.name == "Geoffrey Hinton"
    assert {"Hinton", "Geoffrey Hinton", "G. Hinton"} <= set(a.aliases)


def test_different_surnames_not_merged():
    r = EntityResolver()
    s1 = r.resolve(EntityType.PERSON, "John Smith")
    s2 = r.resolve(EntityType.PERSON, "Jane Smith")
    assert s1.node_id != s2.node_id
    assert r.canonical_count(EntityType.PERSON) == 2


def test_same_surname_incompatible_given_names_not_merged():
    r = EntityResolver()
    a = r.resolve(EntityType.PERSON, "Geoffrey Hinton")
    b = r.resolve(EntityType.PERSON, "Martin Hinton")
    assert a.node_id != b.node_id


# --------------------------------------------------------------------------- #
# Organizations / concepts (fuzzy + containment + suffix)
# --------------------------------------------------------------------------- #


def test_org_suffix_and_spacing_variants_merge():
    r = EntityResolver()
    a = r.resolve(EntityType.ORGANIZATION, "OpenAI")
    b = r.resolve(EntityType.ORGANIZATION, "OpenAI Inc.")
    c = r.resolve(EntityType.ORGANIZATION, "Open AI")
    assert a.node_id == b.node_id == c.node_id
    assert r.canonical_count(EntityType.ORGANIZATION) == 1


def test_concept_plural_merges_but_distinct_stays_separate():
    r = EntityResolver()
    t1 = r.resolve(EntityType.CONCEPT, "Transformer")
    t2 = r.resolve(EntityType.CONCEPT, "Transformers")
    other = r.resolve(EntityType.CONCEPT, "Recurrent Neural Network")
    assert t1.node_id == t2.node_id
    assert other.node_id != t1.node_id
    assert r.canonical_count(EntityType.CONCEPT) == 2


def test_same_name_different_type_not_merged():
    r = EntityResolver()
    person = r.resolve(EntityType.PERSON, "Apple")  # a person named Apple
    org = r.resolve(EntityType.ORGANIZATION, "Apple")
    assert person.node_id != org.node_id


# --------------------------------------------------------------------------- #
# Embedding fallback
# --------------------------------------------------------------------------- #


def test_embedding_fallback_merges_lexically_distant_names():
    # Lexically these never match; the embedder says they are the same.
    vectors = {
        "New York City": [1.0, 0.0, 0.0],
        "NYC": [0.99, 0.01, 0.0],
        "Los Angeles": [0.0, 1.0, 0.0],
    }
    r = EntityResolver(embedder=lambda name: vectors[name])
    a = r.resolve(EntityType.CONCEPT, "New York City")
    b = r.resolve(EntityType.CONCEPT, "NYC")
    c = r.resolve(EntityType.CONCEPT, "Los Angeles")
    assert a.node_id == b.node_id
    assert c.node_id != a.node_id


# --------------------------------------------------------------------------- #
# Store backfill
# --------------------------------------------------------------------------- #


def test_canonicalize_store_merges_nodes_and_remaps_triples():
    store = KnowledgeGraphStore()
    paper = store.add_node(Node(EntityType.DOCUMENT, "Deep Learning Review"))
    hinton = store.add_node(Node(EntityType.PERSON, "Hinton"))
    geoff = store.add_node(Node(EntityType.PERSON, "Geoffrey Hinton"))
    assert hinton.node_id != geoff.node_id  # two fragments before resolution

    prov = Provenance(source_doc=paper.node_id, confidence=0.9, chunk_id="c1")
    store.add_triple(Triple(paper.node_id, RelationType.AUTHORED_BY, hinton.node_id, provenance=prov))
    store.add_triple(Triple(paper.node_id, RelationType.MENTIONS, geoff.node_id, provenance=prov))

    new_store, id_map = canonicalize_store(store)

    # The two person fragments collapse into one canonical node.
    assert len(new_store.nodes_by_type(EntityType.PERSON)) == 1
    assert id_map[hinton.node_id] == id_map[geoff.node_id]
    # Both triples survive, now pointing at the canonical person.
    canonical_person = id_map[hinton.node_id]
    assert len(new_store.triples(object=canonical_person)) == 2
    assert new_store.node_count == 2  # one document + one person


def test_canonicalize_store_accumulates_provenance_on_merged_facts():
    store = KnowledgeGraphStore()
    a = store.add_node(Node(EntityType.DOCUMENT, "Paper"))
    concept1 = store.add_node(Node(EntityType.CONCEPT, "Transformer"))
    concept2 = store.add_node(Node(EntityType.CONCEPT, "Transformers"))

    store.add_triple(Triple(a.node_id, RelationType.DEFINES, concept1.node_id,
                            provenance=Provenance(source_doc=a.node_id, confidence=0.8, chunk_id="x")))
    store.add_triple(Triple(a.node_id, RelationType.DEFINES, concept2.node_id,
                            provenance=Provenance(source_doc=a.node_id, confidence=0.6, chunk_id="y")))

    new_store, _ = canonicalize_store(store)
    defines = new_store.triples(predicate=RelationType.DEFINES)
    assert len(defines) == 1  # both DEFINES facts collapse to one
    assert len(new_store.provenance_for(defines[0])) == 2  # provenance retained


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
