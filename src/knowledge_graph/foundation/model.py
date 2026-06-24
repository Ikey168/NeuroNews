"""
Knowledge graph data model: nodes, provenance, and reified triples.

The graph is a set of typed nodes connected by reified triples. Every triple
carries provenance ``(source_doc, chunk_id, confidence, extractor)`` so the
graph is a database of *cited* facts rather than anonymous edges, and may carry
arbitrary edge properties (e.g. ``CITES`` with a ``year``).

Re-centering note: ``DOCUMENT`` nodes are anchors (where a fact was asserted);
``CONCEPT`` and ``CLAIM`` nodes are the knowledge the graph is built around.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.knowledge_graph.foundation.ontology import EntityType, RelationType


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def make_node_id(entity_type: EntityType, name: str) -> str:
    """Deterministic node id from type + normalized name.

    This is a stable surrogate key, not entity resolution (tracked separately);
    it simply keeps repeated mentions of the same surface form collapsed.
    """
    digest = hashlib.md5(f"{entity_type.value}:{_normalize(name)}".encode()).hexdigest()
    return f"{entity_type.value.lower()}:{digest[:12]}"


@dataclass
class Node:
    """A typed entity in the knowledge graph."""

    type: EntityType
    name: str
    node_id: str = ""
    aliases: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.type, EntityType):
            self.type = EntityType(self.type)
        if not self.node_id:
            self.node_id = make_node_id(self.type, self.name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "type": self.type.value,
            "name": self.name,
            "aliases": list(self.aliases),
            "properties": dict(self.properties),
        }


@dataclass
class Provenance:
    """Where a fact came from and how confident we are in it."""

    source_doc: str
    confidence: float = 1.0
    chunk_id: Optional[str] = None
    extractor: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.source_doc:
            raise ValueError("Provenance.source_doc is required (a fact must be cited)")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(f"Provenance.confidence must be in [0, 1], got {self.confidence}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_doc": self.source_doc,
            "confidence": self.confidence,
            "chunk_id": self.chunk_id,
            "extractor": self.extractor,
        }


@dataclass
class Triple:
    """A reified, provenance-bearing edge: subject --predicate--> object.

    ``subject`` and ``object`` are node ids. ``properties`` holds reified edge
    attributes (e.g. ``{"year": 2023, "context": "..."}`` on a ``CITES`` edge).
    Ontology validity is enforced by the store, which knows the node types.
    """

    subject: str
    predicate: RelationType
    object: str
    provenance: Provenance
    properties: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.predicate, RelationType):
            self.predicate = RelationType(self.predicate)
        if not self.subject or not self.object:
            raise ValueError("Triple requires non-empty subject and object node ids")
        if not isinstance(self.provenance, Provenance):
            raise TypeError("Triple.provenance must be a Provenance instance")

    @property
    def key(self) -> tuple:
        """Identity of the asserted fact, independent of provenance/properties."""
        return (self.subject, self.predicate.value, self.object)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate.value,
            "object": self.object,
            "provenance": self.provenance.to_dict(),
            "properties": dict(self.properties),
        }
