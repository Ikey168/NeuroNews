"""
Build the citation graph for a paper in the knowledge graph.

Turns a ``PaperMetadata`` into knowledge-graph facts: a Document node for the
paper, Document nodes for each cited work joined by first-class ``CITES`` edges,
and ``AUTHORED_BY`` edges to resolved Person nodes. Every edge is cited back to
the paper via provenance.
"""

from __future__ import annotations

from typing import Optional

from src.ingestion.connectors.paper.models import PaperMetadata
from src.knowledge_graph.foundation import (
    EntityResolver,
    EntityType,
    KnowledgeGraphStore,
    Node,
    Provenance,
    RelationType,
    Triple,
)

EXTRACTOR = "paper-connector"


def build_citation_graph(
    store: KnowledgeGraphStore,
    meta: PaperMetadata,
    resolver: Optional[EntityResolver] = None,
) -> Node:
    """Add the paper, its authors, and its references to the knowledge graph.

    Returns the paper's Document node. References become ``CITES`` edges
    (Document -> Document); authors become ``AUTHORED_BY`` edges to canonical
    Person nodes.
    """
    resolver = resolver or EntityResolver()

    paper_node = store.add_node(
        Node(EntityType.DOCUMENT, meta.title or meta.document_id, node_id=meta.document_id)
    )
    prov = Provenance(source_doc=meta.document_id, confidence=1.0, extractor=EXTRACTOR)

    for name in meta.authors:
        person = resolver.resolve(EntityType.PERSON, name)
        store.add_node(person)
        store.add_triple(
            Triple(paper_node.node_id, RelationType.AUTHORED_BY, person.node_id, provenance=prov)
        )

    for ref in meta.references:
        if ref.document_id == paper_node.node_id:
            continue  # ignore self-citation
        ref_node = store.add_node(
            Node(EntityType.DOCUMENT, ref.title or ref.document_id, node_id=ref.document_id)
        )
        properties = {"year": ref.year} if ref.year else {}
        store.add_triple(
            Triple(
                paper_node.node_id,
                RelationType.CITES,
                ref_node.node_id,
                provenance=prov,
                properties=properties,
            )
        )

    return paper_node
