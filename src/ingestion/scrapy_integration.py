"""
News ingestion into the local analytics warehouse.

Fetches real articles from public RSS/Atom news feeds, scores their sentiment,
and writes them into the DuckDB ``news_articles`` table that the API serves.
This replaces the seeded sample data with live headlines.

Usage:

    # stop the API server first (DuckDB allows a single writer), then:
    python -m src.ingestion.scrapy_integration            # append latest news
    python -m src.ingestion.scrapy_integration --replace  # wipe + reload
    python -m src.ingestion.scrapy_integration --limit 40 # per-feed cap

The module has no Scrapy/AWS dependencies; it uses the standard library for
HTTP + XML parsing and NLTK's VADER for sentiment (with a built-in fallback so
it still works offline-of-NLTK).
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional, Sequence, Tuple
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from src.database.local_analytics_connector import get_shared_connection
from src.database.local_warehouse_seed import ensure_schema

logger = logging.getLogger(__name__)

USER_AGENT = "NeuroNewsBot/1.0 (+https://github.com/Ikey168/NeuroNews)"
HTTP_TIMEOUT = 15
_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class Feed:
    """A news source RSS/Atom feed and the category to file its articles under."""

    name: str
    url: str
    category: str


# Reliable, public feeds. Several outlets are included per category so the same
# real-world story is covered by multiple sources, which lets the clusterer
# group cross-outlet coverage into multi-source event clusters.
DEFAULT_FEEDS: List[Feed] = [
    # --- World / top news (big stories show up across all of these) ---
    Feed("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "World"),
    Feed("Guardian World", "https://www.theguardian.com/world/rss", "World"),
    Feed("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "World"),
    Feed("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "World"),
    Feed("NPR News", "https://feeds.npr.org/1001/rss.xml", "World"),
    # --- Economy / business ---
    Feed("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "Economy"),
    Feed("Guardian Business", "https://www.theguardian.com/business/rss", "Economy"),
    Feed("NYT Business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "Economy"),
    # --- Technology ---
    Feed("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "Technology"),
    Feed("Guardian Technology", "https://www.theguardian.com/technology/rss", "Technology"),
    Feed("NYT Technology", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "Technology"),
    Feed("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "Technology"),
    # --- Policy / politics ---
    Feed("BBC Politics", "https://feeds.bbci.co.uk/news/politics/rss.xml", "Policy"),
    Feed("Guardian Politics", "https://www.theguardian.com/politics/rss", "Policy"),
    Feed("NYT Politics", "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml", "Policy"),
    # --- Health ---
    Feed("BBC Health", "https://feeds.bbci.co.uk/news/health/rss.xml", "Health"),
    Feed("Guardian Society", "https://www.theguardian.com/society/rss", "Health"),
    Feed("NYT Health", "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml", "Health"),
    # --- Energy / environment ---
    Feed("Guardian Environment", "https://www.theguardian.com/environment/rss", "Energy"),
    Feed("NYT Climate", "https://rss.nytimes.com/services/xml/rss/nyt/Climate.xml", "Energy"),
    Feed("EIA Today in Energy", "https://www.eia.gov/rss/todayinenergy.xml", "Energy"),
    # --- Science ---
    Feed("BBC Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "Science"),
    Feed("Guardian Science", "https://www.theguardian.com/science/rss", "Science"),
    Feed("NYT Science", "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml", "Science"),
]


@dataclass
class Article:
    """A normalized article ready to be stored in the warehouse."""

    id: str
    title: str
    url: str
    content: str
    publish_date: datetime
    source: str
    category: str
    sentiment_score: float
    sentiment_label: str

    def as_row(self) -> tuple:
        return (
            self.id,
            self.title,
            self.url,
            self.content,
            self.publish_date,
            self.source,
            self.category,
            self.sentiment_score,
            self.sentiment_label,
        )


# --------------------------------------------------------------------------- #
# Sentiment
# --------------------------------------------------------------------------- #

_VADER = None
_VADER_TRIED = False

# Tiny fallback lexicon used only when NLTK/VADER is unavailable.
_POS_WORDS = {
    "gain", "gains", "grow", "growth", "surge", "boost", "win", "wins", "record",
    "breakthrough", "soar", "soars", "rally", "rallies", "up", "rise", "rises",
    "strong", "success", "approve", "approved", "recovery", "optimistic", "beat",
}
_NEG_WORDS = {
    "loss", "losses", "fall", "falls", "drop", "drops", "plunge", "crash", "slump",
    "down", "decline", "declines", "weak", "fear", "fears", "crisis", "cut", "cuts",
    "warn", "warns", "risk", "risks", "fail", "fails", "recession", "ban", "probe",
}


def _get_vader():
    global _VADER, _VADER_TRIED
    if _VADER is not None or _VADER_TRIED:
        return _VADER
    _VADER_TRIED = True
    try:
        import nltk
        from nltk.sentiment.vader import SentimentIntensityAnalyzer

        try:
            _VADER = SentimentIntensityAnalyzer()
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
            _VADER = SentimentIntensityAnalyzer()
    except Exception as exc:  # nltk missing or download failed
        logger.warning("VADER unavailable (%s); using fallback sentiment", exc)
        _VADER = None
    return _VADER


def score_sentiment(text: str) -> Tuple[float, str]:
    """Return (compound_score in [-1, 1], label) for the given text."""
    text = (text or "").strip()
    if not text:
        return 0.0, "neutral"

    analyzer = _get_vader()
    if analyzer is not None:
        score = float(analyzer.polarity_scores(text)["compound"])
    else:
        words = re.findall(r"[a-z']+", text.lower())
        pos = sum(w in _POS_WORDS for w in words)
        neg = sum(w in _NEG_WORDS for w in words)
        score = (pos - neg) / (pos + neg + 2.0)

    score = round(max(-1.0, min(1.0, score)), 4)
    label = "positive" if score > 0.05 else "negative" if score < -0.05 else "neutral"
    return score, label


# --------------------------------------------------------------------------- #
# Fetching + parsing
# --------------------------------------------------------------------------- #


def _http_get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read()


def _strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_date(raw: Optional[str]) -> datetime:
    if raw:
        raw = raw.strip()
        # RFC-822 (RSS)
        try:
            dt = parsedate_to_datetime(raw)
            if dt is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError):
            pass
        # ISO-8601 (Atom)
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.now()


def _make_id(url: str) -> str:
    return "rss-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def parse_feed(xml_bytes: bytes, feed: Feed, limit: int = 25) -> List[Article]:
    """Parse RSS 2.0 or Atom bytes into Article objects."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.warning("Could not parse feed %s: %s", feed.name, exc)
        return []

    articles: List[Article] = []

    # RSS 2.0: <rss><channel><item>...   Atom: <feed><entry>...
    channel = root.find("channel")
    if channel is not None:
        items = channel.findall("item")
        for item in items[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = item.findtext("description") or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            pub = item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date")
            article = _build_article(title, link, desc, pub, feed)
            if article:
                articles.append(article)
    else:
        # Atom
        entries = root.findall("{0}entry".format(_ATOM))
        for entry in entries[:limit]:
            title = (entry.findtext("{0}title".format(_ATOM)) or "").strip()
            link = ""
            link_el = entry.find("{0}link".format(_ATOM))
            if link_el is not None:
                link = (link_el.get("href") or link_el.text or "").strip()
            desc = entry.findtext("{0}summary".format(_ATOM)) or entry.findtext("{0}content".format(_ATOM))
            pub = entry.findtext("{0}published".format(_ATOM)) or entry.findtext("{0}updated".format(_ATOM))
            article = _build_article(title, link, desc, pub, feed)
            if article:
                articles.append(article)

    return articles


def _build_article(
    title: str, link: str, desc: Optional[str], pub: Optional[str], feed: Feed
) -> Optional[Article]:
    if not title or not link:
        return None
    content = _strip_html(desc)
    score, label = score_sentiment("{0}. {1}".format(title, content))
    return Article(
        id=_make_id(link),
        title=title,
        url=link,
        content=content,
        publish_date=_parse_date(pub),
        source=feed.name,
        category=feed.category,
        sentiment_score=score,
        sentiment_label=label,
    )


def fetch_articles(
    feeds: Optional[Sequence[Feed]] = None, limit_per_feed: int = 25
) -> List[Article]:
    """Fetch and parse all feeds, skipping any that fail."""
    feeds = list(feeds) if feeds is not None else DEFAULT_FEEDS
    articles: List[Article] = []
    for feed in feeds:
        try:
            logger.info("Fetching %s (%s)", feed.name, feed.url)
            raw = _http_get(feed.url)
            parsed = parse_feed(raw, feed, limit=limit_per_feed)
            logger.info("  %d articles from %s", len(parsed), feed.name)
            articles.extend(parsed)
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", feed.name, exc)
    return articles


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #


def store_articles(articles: Sequence[Article], replace: bool = False) -> int:
    """Write articles into the warehouse, returning the number of new rows.

    With ``replace`` the whole table is cleared first; otherwise the synthetic
    sample seed (ids ``art-*``) is dropped and only previously unseen URLs are
    inserted, so re-running is idempotent.
    """
    conn = get_shared_connection()
    ensure_schema(conn)

    if replace:
        conn.execute("DELETE FROM news_articles")
    else:
        # Remove the synthetic sample seed so real news isn't mixed with it.
        conn.execute("DELETE FROM news_articles WHERE id LIKE 'art-%'")

    existing = {row[0] for row in conn.execute("SELECT id FROM news_articles").fetchall()}
    new_rows = [a.as_row() for a in articles if a.id not in existing]
    if new_rows:
        conn.executemany(
            """
            INSERT INTO news_articles
                (id, title, url, content, publish_date, source, category,
                 sentiment_score, sentiment_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            new_rows,
        )
    return len(new_rows)


def ingest(
    feeds: Optional[Sequence[Feed]] = None,
    limit_per_feed: int = 25,
    replace: bool = False,
) -> dict:
    """Fetch real news and store it. Returns summary stats."""
    articles = fetch_articles(feeds, limit_per_feed=limit_per_feed)
    inserted = store_articles(articles, replace=replace)
    total = get_shared_connection().execute(
        "SELECT COUNT(*) FROM news_articles"
    ).fetchone()[0]
    return {"fetched": len(articles), "inserted": inserted, "total_in_warehouse": total}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest real news into the local warehouse")
    parser.add_argument("--limit", type=int, default=25, help="Max articles per feed")
    parser.add_argument(
        "--replace", action="store_true", help="Wipe the table before inserting"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        stats = ingest(limit_per_feed=args.limit, replace=args.replace)
    except Exception as exc:  # most commonly the DuckDB single-writer lock
        logger.error("Ingestion failed: %s", exc)
        logger.error(
            "If the API server is running, stop it first — DuckDB allows a "
            "single writer process."
        )
        return 1

    logger.info(
        "Ingest complete: fetched=%(fetched)d inserted=%(inserted)d total=%(total_in_warehouse)d",
        stats,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
