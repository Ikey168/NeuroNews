"""
In-memory knowledge graph store.

Stores typed nodes and reified, provenance-bearing triples, enforcing the
ontology on every write (entity/relation types must exist; relations must be
permitted between the subject's and object's types). The interface is backend
agnostic so a Gremlin/Neptune-backed implementation can follow without changing
callers.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from src.knowledge_graph.foundation.model import Node, Provenance, Triple
from src.knowledge_graph.foundation.ontology import (
    EntityType,
    OntologyViolation,
    RelationType,
    validate_relation,
)


class KnowledgeGraphStore:
    """A typed, provenance-enforcing knowledge graph held in memory."""

    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        # Triples keyed by fact identity; repeated assertions accumulate provenance.
        self._triples: Dict[tuple, Triple] = {}
        self._provenance: Dict[tuple, List[Provenance]] = {}

    # ---- nodes ---------------------------------------------------------- #

    def add_node(self, node: Node) -> Node:
        """Add or merge a node. Re-adding the same id merges aliases/properties."""
        existing = self._nodes.get(node.node_id)
        if existing is None:
            self._nodes[node.node_id] = node
            return node
        if existing.type != node.type:
            raise OntologyViolation(
                f"Node {node.node_id} already exists as {existing.type.value}, "
                f"cannot redefine as {node.type.value}"
            )
        for alias in node.aliases:
            if alias not in existing.aliases:
                existing.aliases.append(alias)
        existing.properties.update(node.properties)
        return existing

    def get_node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def nodes_by_type(self, entity_type: EntityType) -> List[Node]:
        return [n for n in self._nodes.values() if n.type == entity_type]

    # ---- triples -------------------------------------------------------- #

    def add_triple(self, triple: Triple) -> Triple:
        """Validate against the ontology and store the triple as a cited fact.

        Both endpoints must already exist as nodes, and the relation must be
        permitted between their types. Re-asserting the same fact appends its
        provenance to the existing triple rather than duplicating it.
        """
        subject = self._nodes.get(triple.subject)
        obj = self._nodes.get(triple.object)
        if subject is None:
            raise OntologyViolation(f"Unknown subject node {triple.subject!r}; add it first")
        if obj is None:
            raise OntologyViolation(f"Unknown object node {triple.object!r}; add it first")

        validate_relation(triple.predicate, subject.type, obj.type)

        key = triple.key
        if key in self._triples:
            self._provenance[key].append(triple.provenance)
            # Keep the highest-confidence provenance as the representative one.
            best = max(self._provenance[key], key=lambda p: p.confidence)
            self._triples[key].provenance = best
            self._triples[key].properties.update(triple.properties)
            return self._triples[key]

        self._triples[key] = triple
        self._provenance[key] = [triple.provenance]
        return triple

    def provenance_for(self, triple: Triple) -> List[Provenance]:
        """All provenance records backing a fact (one per assertion)."""
        return list(self._provenance.get(triple.key, []))

    def triples(
        self,
        subject: Optional[str] = None,
        predicate: Optional[RelationType] = None,
        object: Optional[str] = None,
    ) -> List[Triple]:
        """Query stored facts, optionally filtered by any of subject/predicate/object."""
        results: Iterable[Triple] = self._triples.values()
        if subject is not None:
            results = [t for t in results if t.subject == subject]
        if predicate is not None:
            results = [t for t in results if t.predicate == predicate]
        if object is not None:
            results = [t for t in results if t.object == object]
        return list(results)

    def neighbors(self, node_id: str) -> List[Triple]:
        """All facts with ``node_id`` as subject or object."""
        return [t for t in self._triples.values() if node_id in (t.subject, t.object)]

    # ---- stats ---------------------------------------------------------- #

    def __len__(self) -> int:
        return len(self._triples)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def triple_count(self) -> int:
        return len(self._triples)
