"""
Papers connector: ingest academic papers (arXiv) as documents and into the KG.

Implements the connector interface (`discover` -> `fetch` -> `parse` ->
`Document`) for `source_type="paper"`, and additionally exposes
`ingest_to_kg`, which builds the citation graph (references as `CITES` edges,
authors as `AUTHORED_BY` edges) for a paper.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, List, Optional, Union

from services.ingest.common.document_model import Document
from src.ingestion.connectors.base import Connector, RawDocument, SourceRef
from src.ingestion.connectors.paper.arxiv import ArxivClient, parse_atom
from src.ingestion.connectors.paper.citation_graph import build_citation_graph
from src.ingestion.connectors.paper.models import PaperMetadata
from src.ingestion.connectors.paper.references import ReferencesProvider
from src.ingestion.connectors.registry import register_connector
from src.knowledge_graph.foundation import EntityResolver, KnowledgeGraphStore, Node


def _to_millis(dt) -> Optional[int]:
    return int(dt.timestamp() * 1000) if dt is not None else None


def paper_metadata_to_document(meta: PaperMetadata, ingested_at: int) -> Document:
    """Map paper metadata to a document-ingest-v1 record.

    References are not embedded here (they live in the knowledge graph); only
    lightweight, contract-valid scalars and string arrays go in ``metadata``.
    """
    metadata = {
        "arxiv_id": meta.arxiv_id,
        "doi": meta.doi,
        "primary_category": meta.primary_category,
        "categories": list(meta.categories),
        "reference_count": len(meta.references),
        "reference_ids": [r.document_id for r in meta.references],
    }
    metadata = {k: v for k, v in metadata.items() if v not in (None, [])}

    url = f"https://arxiv.org/abs/{meta.arxiv_id}" if meta.arxiv_id else None
    return Document(
        document_id=meta.document_id,
        source_type="paper",
        language="en",
        ingested_at=ingested_at,
        source_id="arxiv" if meta.arxiv_id else None,
        url=url,
        title=meta.title,
        content=meta.abstract or None,
        content_ref=meta.pdf_url,
        authors=list(meta.authors),
        created_at=_to_millis(meta.published),
        metadata=metadata,
    )


@register_connector
class PaperConnector(Connector):
    """Ingest academic papers from arXiv as documents and citation-graph facts."""

    source_type = "paper"

    def __init__(
        self,
        arxiv_client: Optional[ArxivClient] = None,
        references_provider: Optional[ReferencesProvider] = None,
        http_get=None,
    ):
        self._arxiv = arxiv_client or ArxivClient(http_get=http_get)
        self._references = references_provider

    def discover(self, query: Optional[Union[str, Iterable[str]]] = None) -> Iterable[SourceRef]:
        """Yield a SourceRef per arXiv id. ``query`` is an id or list of ids."""
        if query is None:
            return
        ids = [query] if isinstance(query, str) else list(query)
        for arxiv_id in ids:
            yield SourceRef(locator=arxiv_id, metadata={"arxiv_id": arxiv_id})

    def fetch(self, ref: SourceRef) -> RawDocument:
        return RawDocument(
            ref=ref,
            content=self._arxiv.fetch_by_id(ref.locator),
            content_type="application/atom+xml",
        )

    def parse(self, raw: RawDocument) -> List[Document]:
        content = raw.content
        if isinstance(content, str):
            content = content.encode("utf-8")
        documents = []
        for meta in parse_atom(content):
            if self._references is not None:
                meta.references = self._references.references_for(meta)
            documents.append(paper_metadata_to_document(meta, raw.fetched_at))
        return documents

    # ---- metadata + knowledge graph ------------------------------------ #

    def metadata_for(self, arxiv_id: str) -> PaperMetadata:
        """Fetch full metadata for a paper, including references if a provider is set."""
        meta = self._arxiv.get_metadata(arxiv_id)
        if self._references is not None:
            meta.references = self._references.references_for(meta)
        return meta

    def ingest_to_kg(
        self,
        store: KnowledgeGraphStore,
        arxiv_id: str,
        resolver: Optional[EntityResolver] = None,
    ) -> Node:
        """Ingest a paper by id into the knowledge graph (references -> CITES)."""
        return build_citation_graph(store, self.metadata_for(arxiv_id), resolver=resolver)
