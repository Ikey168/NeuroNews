"""High-level pipeline for blog feed ingestion with entity extraction.

``ingest_feeds()`` runs discover → fetch → parse for every subscription and
optionally calls ``BlogConnector.ingest_to_kg()`` on each document so entities
and relationships land in the knowledge graph.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    feeds_fetched: int = 0
    documents_ingested: int = 0
    entities_extracted: int = 0
    relationships_extracted: int = 0
    errors: List[str] = field(default_factory=list)


def ingest_feeds(
    query=None,
    limit_per_feed: int = 20,
    fetch_full_text: bool = True,
    extract_entities: bool = True,
    subs_path=None,
) -> IngestResult:
    """Ingest all subscribed feeds (or ``query`` overrides) and populate the KG.

    Args:
        query: Optional list of URLs/FeedSubscription objects to ingest instead
            of the persisted subscription list.
        limit_per_feed: Max entries per feed.
        fetch_full_text: Whether to follow article URLs for full body extraction.
        extract_entities: Whether to run entity/relationship extraction and
            store results in the knowledge graph.
        subs_path: Override path to subscription JSON store.

    Returns:
        :class:`IngestResult` with counts and any non-fatal error messages.
    """
    from src.ingestion.connectors.blog.connector import BlogConnector

    connector = BlogConnector(
        subs_path=subs_path,
        fetch_full_text=fetch_full_text,
        limit_per_feed=limit_per_feed,
    )
    result = IngestResult()

    refs = list(connector.discover(query))
    result.feeds_fetched = len(refs)

    for ref in refs:
        try:
            raw = connector.fetch(ref)
        except Exception as exc:
            msg = f"fetch failed for {ref.locator}: {exc}"
            logger.warning(msg)
            result.errors.append(msg)
            continue

        try:
            docs = connector.parse(raw)
        except Exception as exc:
            msg = f"parse failed for {ref.locator}: {exc}"
            logger.warning(msg)
            result.errors.append(msg)
            continue

        result.documents_ingested += len(docs)

        if extract_entities:
            for doc in docs:
                try:
                    kg_stats = connector.ingest_to_kg(doc)
                    result.entities_extracted += kg_stats.get("entities", 0)
                    result.relationships_extracted += kg_stats.get("relationships", 0)
                except Exception as exc:
                    logger.debug("entity extraction skipped for %s: %s", doc.document_id, exc)

    return result
