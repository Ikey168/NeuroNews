"""
Knowledge layer: store claims in the graph and reason over them.

- ``build_claim_graph`` adds extracted claims as ``Claim`` nodes, each asserted
  by its source document via a ``SUPPORTS`` edge with provenance (so every claim
  is cited).
- ``link_claims`` connects claims about the same subject/object across documents
  with ``SUPPORTS`` / ``CONTRADICTS`` edges based on agreement of polarity.
- ``literature_on`` answers "what does the literature say about X" with
  synthesized, cited claims plus corroborating and contradicting evidence.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set

from src.knowledge_graph.claim_extractor import ExtractedClaim
from src.knowledge_graph.foundation import (
    EntityType,
    KnowledgeGraphStore,
    Node,
    Provenance,
    RelationType,
    Triple,
    make_node_id,
)

_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "to", "for", "and", "or", "is", "are",
    "was", "were", "be", "this", "that", "these", "those", "it", "its", "with",
    "as", "by", "at", "from", "their", "our", "we",
}


def _tokens(text: str) -> Set[str]:
    return {
        w for w in re.findall(r"[a-z0-9']+", (text or "").lower())
        if w and w not in _STOPWORDS
    }


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def build_claim_graph(
    store: KnowledgeGraphStore,
    document_id: str,
    claims: Sequence[ExtractedClaim],
    extractor: str = "claim-extractor",
) -> List[Node]:
    """Add claims to the graph, each asserted (SUPPORTS) by its document.

    The document node must already exist (e.g. created by the papers connector).
    Returns the created/merged Claim nodes.
    """
    if store.get_node(document_id) is None:
        raise ValueError(f"Document node {document_id!r} must exist before adding its claims")

    nodes: List[Node] = []
    for claim in claims:
        node = Node(
            type=EntityType.CLAIM,
            name=claim.text,
            node_id=make_node_id(EntityType.CLAIM, claim.text),
            properties={
                "subject": claim.subject,
                "predicate": claim.predicate,
                "object": claim.object,
                "negated": claim.negated,
            },
        )
        store.add_node(node)
        chunk_id = "/".join(claim.chunk_path) if claim.chunk_path else None
        store.add_triple(
            Triple(
                document_id,
                RelationType.SUPPORTS,
                node.node_id,
                provenance=Provenance(
                    source_doc=claim.source_doc or document_id,
                    confidence=claim.confidence,
                    chunk_id=chunk_id,
                    extractor=extractor,
                ),
            )
        )
        nodes.append(node)
    return nodes


def _asserting_docs(store: KnowledgeGraphStore, claim_id: str) -> List[str]:
    """Documents that assert a claim (Document SUPPORTS Claim)."""
    docs = []
    for t in store.triples(predicate=RelationType.SUPPORTS, object=claim_id):
        node = store.get_node(t.subject)
        if node is not None and node.type == EntityType.DOCUMENT:
            docs.append(t.subject)
    return docs


def link_claims(store: KnowledgeGraphStore, similarity_threshold: float = 0.5) -> int:
    """Connect related claims across documents.

    Two claims are related when their subjects and objects overlap. Related
    claims get a ``SUPPORTS`` edge if they share polarity, or ``CONTRADICTS`` if
    one is negated and the other is not. Returns the number of edges added.
    """
    claims = store.nodes_by_type(EntityType.CLAIM)
    profiles = []
    for c in claims:
        profiles.append((
            c,
            _tokens(c.properties.get("subject", "")),
            _tokens(c.properties.get("object", "")),
            bool(c.properties.get("negated", False)),
            _asserting_docs(store, c.node_id),
        ))

    added = 0
    for i in range(len(profiles)):
        ci, subj_i, obj_i, neg_i, docs_i = profiles[i]
        for j in range(i + 1, len(profiles)):
            cj, subj_j, obj_j, neg_j, docs_j = profiles[j]
            subj_sim = _jaccard(subj_i, subj_j)
            obj_sim = _jaccard(obj_i, obj_j)
            if subj_sim < similarity_threshold or obj_sim < similarity_threshold:
                continue

            evidence_doc = (docs_j or docs_i or [cj.node_id])[0]
            relation = RelationType.CONTRADICTS if neg_i != neg_j else RelationType.SUPPORTS
            store.add_triple(
                Triple(
                    ci.node_id,
                    relation,
                    cj.node_id,
                    provenance=Provenance(
                        source_doc=evidence_doc,
                        confidence=round(min(subj_sim, obj_sim), 4),
                        extractor="claim-linker",
                    ),
                    properties={"subject_sim": round(subj_sim, 4), "object_sim": round(obj_sim, 4)},
                )
            )
            added += 1
    return added


def _related_claims(store: KnowledgeGraphStore, claim_id: str, relation: RelationType) -> List[str]:
    """Claim texts linked to ``claim_id`` by ``relation`` (either direction)."""
    out: List[str] = []
    for t in store.neighbors(claim_id):
        if t.predicate != relation:
            continue
        other_id = t.object if t.subject == claim_id else t.subject
        other = store.get_node(other_id)
        if other is not None and other.type == EntityType.CLAIM:
            out.append(other.name)
    return out


def literature_on(
    store: KnowledgeGraphStore,
    topic: str,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return claims about ``topic``, each cited and with supporting/opposing evidence.

    Answers "what does the literature say about X": every matching claim is
    returned with the documents that assert it and any corroborating or
    contradicting claims.
    """
    topic_tokens = _tokens(topic)
    results: List[Dict[str, Any]] = []

    for claim in store.nodes_by_type(EntityType.CLAIM):
        claim_tokens = (
            _tokens(claim.properties.get("subject", ""))
            | _tokens(claim.properties.get("object", ""))
            | _tokens(claim.name)
        )
        if not (topic_tokens & claim_tokens):
            continue

        supported_by = [
            (store.get_node(d).name if store.get_node(d) else d)
            for d in _asserting_docs(store, claim.node_id)
        ]
        results.append({
            "claim": claim.name,
            "subject": claim.properties.get("subject"),
            "predicate": claim.properties.get("predicate"),
            "object": claim.properties.get("object"),
            "negated": claim.properties.get("negated", False),
            "supported_by": supported_by,
            "corroborated_by": _related_claims(store, claim.node_id, RelationType.SUPPORTS),
            "contradicted_by": _related_claims(store, claim.node_id, RelationType.CONTRADICTS),
        })

    # Most-cited claims first.
    results.sort(key=lambda r: len(r["supported_by"]), reverse=True)
    return results[:limit] if limit else results
