"""Blog / RSS / Atom ingestion connector."""

from src.ingestion.connectors.blog.connector import BlogConnector
from src.ingestion.connectors.blog.digest import match_watchlist, run_watchlists
from src.ingestion.connectors.blog.models import DigestMatch, FeedSubscription, WatchlistEntry
from src.ingestion.connectors.blog.pipeline import IngestResult, ingest_feeds
from src.ingestion.connectors.blog.subscriptions import SubscriptionStore

__all__ = [
    "BlogConnector",
    "DigestMatch",
    "FeedSubscription",
    "IngestResult",
    "SubscriptionStore",
    "WatchlistEntry",
    "ingest_feeds",
    "match_watchlist",
    "run_watchlists",
]
