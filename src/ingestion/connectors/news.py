"""
News connector: the existing RSS/Atom news ingest, expressed as a connector.

This wraps the pure fetch/parse helpers already in
``src.ingestion.scrapy_integration`` (the live news ingester) behind the generic
connector interface, producing ``Document`` records with ``source_type="news"``.
The legacy warehouse path in ``scrapy_integration`` is left untouched; this is
the generalized entry point on top of the same fetch/parse logic.

Sentiment, which the legacy ingester computes inline, is an enrichment under the
document model and is therefore exposed separately via :meth:`enrichments_for`
rather than baked into the core ``Document``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from services.ingest.common.document_model import Document
from src.ingestion.connectors.base import Connector, RawDocument, SourceRef
from src.ingestion.connectors.registry import register_connector


def _to_millis(dt: datetime) -> int:
    """Convert a (naive, UTC) datetime to milliseconds since epoch."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


@register_connector
class NewsConnector(Connector):
    """Ingest news articles from RSS/Atom feeds as document-ingest-v1 records."""

    source_type = "news"

    def __init__(
        self,
        feeds: Optional[Sequence[Any]] = None,
        limit_per_feed: int = 25,
        http_get=None,
    ):
        # Imported lazily so the framework stays importable without the news deps.
        from src.ingestion import scrapy_integration as si

        self._si = si
        self._feeds = list(feeds) if feeds is not None else list(si.DEFAULT_FEEDS)
        self._limit_per_feed = limit_per_feed
        self._http_get = http_get or si._http_get

    def discover(self, query: Optional[Any] = None) -> Iterable[SourceRef]:
        """Yield one SourceRef per configured feed.

        ``query`` may be a sequence of ``Feed`` objects to override the default
        feed list for this run.
        """
        feeds = list(query) if query else self._feeds
        for feed in feeds:
            yield SourceRef(
                locator=feed.url,
                title=feed.name,
                metadata={"feed_name": feed.name, "category": feed.category},
            )

    def fetch(self, ref: SourceRef) -> RawDocument:
        return RawDocument(
            ref=ref,
            content=self._http_get(ref.locator),
            content_type="application/xml",
        )

    def parse(self, raw: RawDocument) -> List[Document]:
        feed = self._si.Feed(
            name=raw.ref.metadata.get("feed_name", raw.ref.title or raw.ref.locator),
            url=raw.ref.locator,
            category=raw.ref.metadata.get("category", "World"),
        )
        content = raw.content
        if isinstance(content, str):
            content = content.encode("utf-8")

        ingested_at = raw.fetched_at
        documents: List[Document] = []
        for article in self._si.parse_feed(content, feed, limit=self._limit_per_feed):
            documents.append(self._article_to_document(article, ingested_at))
        return documents

    @staticmethod
    def _article_to_document(article: Any, ingested_at: int) -> Document:
        return Document(
            document_id=article.id,
            source_type="news",
            language="en",
            ingested_at=ingested_at,
            source_id=article.source,
            url=article.url,
            title=article.title,
            content=article.content,
            created_at=_to_millis(article.publish_date),
            metadata={"category": article.category},
        )

    @staticmethod
    def enrichments_for(article: Any) -> Dict[str, Any]:
        """Enrichments the legacy ingester computes inline (kept out of the core record)."""
        return {
            "sentiment": {
                "score": article.sentiment_score,
                "label": article.sentiment_label,
            }
        }
