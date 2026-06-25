"""Watchlist matching and digest building for blog posts.

A watchlist is a named set of keywords; any ingested post whose title or
content contains one of those keywords surfaces in the digest.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from src.ingestion.connectors.blog.models import DigestMatch, WatchlistEntry


def match_watchlist(
    documents: list,
    keywords: List[str],
    watchlist_name: str = "default",
    tag_filter: Optional[List[str]] = None,
) -> List[DigestMatch]:
    """Return one :class:`DigestMatch` per document that contains any keyword.

    ``tag_filter`` narrows the search to documents whose metadata ``tags``
    overlap with the filter list (ignored if empty or None).
    """
    lower_kws = [kw.lower() for kw in keywords if kw.strip()]
    matches: List[DigestMatch] = []
    for doc in documents:
        if not _tag_ok(doc, tag_filter):
            continue
        title = (getattr(doc, "title", None) or doc.get("title", "") if isinstance(doc, dict) else doc.title or "")
        content = (getattr(doc, "content", None) or doc.get("content", "") if isinstance(doc, dict) else doc.content or "")
        url = (getattr(doc, "url", None) or doc.get("url", "") if isinstance(doc, dict) else doc.url or "")
        doc_id = (getattr(doc, "document_id", None) or doc.get("document_id", "") if isinstance(doc, dict) else doc.document_id or "")
        haystack = (title + " " + content).lower()
        matched = [kw for kw in lower_kws if kw in haystack]
        if matched:
            matches.append(DigestMatch(
                document_id=doc_id,
                title=title,
                url=url,
                matched_keywords=matched,
                watchlist_name=watchlist_name,
            ))
    return matches


def run_watchlists(
    documents: list,
    watchlists: List[WatchlistEntry],
) -> Dict[str, List[DigestMatch]]:
    """Run every watchlist against ``documents``; return matches keyed by name."""
    return {
        w.name: match_watchlist(documents, w.keywords, w.name, w.tags or None)
        for w in watchlists
    }


def _tag_ok(doc, tag_filter: Optional[List[str]]) -> bool:
    if not tag_filter:
        return True
    meta = getattr(doc, "metadata", None) or (doc.get("metadata") if isinstance(doc, dict) else {}) or {}
    doc_tags = meta.get("tags", [])
    return bool(set(doc_tags) & set(tag_filter))
