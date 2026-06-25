"""Data models for the blog/RSS/Atom connector."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class FeedSubscription:
    """A subscribed RSS/Atom feed URL with optional name and topic tags."""

    url: str
    name: str = ""
    tags: List[str] = field(default_factory=list)
    added_at: int = 0  # epoch-ms


@dataclass
class WatchlistEntry:
    """A named set of keywords to monitor across ingested blog posts."""

    name: str
    keywords: List[str]
    tags: List[str] = field(default_factory=list)  # scope to specific feed tags


@dataclass
class DigestMatch:
    """A document that matched a watchlist entry."""

    document_id: str
    title: str
    url: str
    matched_keywords: List[str]
    watchlist_name: str
