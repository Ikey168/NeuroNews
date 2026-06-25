"""
Tests for the blog / RSS / Atom connector (issue #522).

Covers:
- SubscriptionStore: subscribe, unsubscribe, list, persistence
- Readability: bs4 extraction, noise tag removal, min-char threshold
- BlogConnector: discover (query override + store), fetch, parse
- Document output: source_type="blog", stable IDs, metadata, authors, dates
- Full-text injection via mock full_text_getter
- Watchlist: match_watchlist, run_watchlists, tag filtering
- Pipeline: ingest_feeds with mocked connector + entity extraction path
- Registry: "blog" registered after import
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.connectors.blog.connector import BlogConnector, _stable_id, _strip_html
from src.ingestion.connectors.blog.digest import match_watchlist, run_watchlists
from src.ingestion.connectors.blog.models import DigestMatch, FeedSubscription, WatchlistEntry
from src.ingestion.connectors.blog.subscriptions import SubscriptionStore


# --------------------------------------------------------------------------- #
# Minimal RSS and Atom feed bytes
# --------------------------------------------------------------------------- #

_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    <link>https://example.com</link>
    <item>
      <title>First Post</title>
      <link>https://example.com/first</link>
      <description>Hello &amp; welcome to the &lt;b&gt;blog&lt;/b&gt;.</description>
      <pubDate>Wed, 01 Jan 2025 12:00:00 GMT</pubDate>
      <author>alice@example.com (Alice Smith)</author>
    </item>
    <item>
      <title>Second Post</title>
      <link>https://example.com/second</link>
      <description>Python is great for AI and ML projects.</description>
      <pubDate>Thu, 02 Jan 2025 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Blog</title>
  <entry>
    <title>Atom Entry</title>
    <link href="https://example.com/atom-1"/>
    <id>urn:uuid:atom-1</id>
    <updated>2025-03-15T10:30:00Z</updated>
    <author><name>Bob Jones</name></author>
    <summary>An entry from an Atom feed about machine learning.</summary>
  </entry>
</feed>"""

_HTML_ARTICLE = b"""<!DOCTYPE html>
<html>
  <head><title>Full Article</title></head>
  <body>
    <nav>Nav stuff here</nav>
    <article>
      <h1>The Real Content</h1>
      <p>This is the full article body with enough text to meet the minimum
      character threshold for readability extraction. It contains substantial
      content about topics that are interesting to readers of the blog.</p>
      <p>More paragraphs follow here to ensure we hit the minimum length.</p>
    </article>
    <footer>Footer boilerplate</footer>
    <script>alert('noise')</script>
  </body>
</html>"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_connector(tmp_path, feed_bytes=_RSS, full_text="", fetch_full_text=True):
    http_get = MagicMock(return_value=feed_bytes)
    ft_getter = MagicMock(return_value=full_text)
    connector = BlogConnector(
        subs_path=tmp_path / "subs.json",
        fetch_full_text=fetch_full_text,
        http_get=http_get,
        full_text_getter=ft_getter,
    )
    return connector, http_get, ft_getter


# --------------------------------------------------------------------------- #
# SubscriptionStore
# --------------------------------------------------------------------------- #

class TestSubscriptionStore:
    def test_empty_store_returns_empty_list(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        assert store.list() == []

    def test_subscribe_creates_entry(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        sub = store.subscribe("https://example.com/rss", name="Example", tags=["tech"])
        assert sub.url == "https://example.com/rss"
        assert sub.name == "Example"
        assert sub.tags == ["tech"]
        assert sub.added_at > 0

    def test_subscribe_persists_across_instances(self, tmp_path):
        p = tmp_path / "subs.json"
        SubscriptionStore(p).subscribe("https://a.com/rss", name="A")
        loaded = SubscriptionStore(p).list()
        assert len(loaded) == 1
        assert loaded[0].url == "https://a.com/rss"

    def test_subscribe_upserts_existing(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        store.subscribe("https://a.com/rss", name="A")
        store.subscribe("https://a.com/rss", name="A Updated", tags=["new"])
        subs = store.list()
        assert len(subs) == 1
        assert subs[0].name == "A Updated"
        assert subs[0].tags == ["new"]

    def test_unsubscribe_removes_entry(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        store.subscribe("https://a.com/rss")
        store.subscribe("https://b.com/rss")
        removed = store.unsubscribe("https://a.com/rss")
        assert removed is True
        remaining = store.list()
        assert len(remaining) == 1
        assert remaining[0].url == "https://b.com/rss"

    def test_unsubscribe_missing_returns_false(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        assert store.unsubscribe("https://nothere.com/rss") is False

    def test_get_returns_subscription(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        store.subscribe("https://a.com/rss", name="A")
        sub = store.get("https://a.com/rss")
        assert sub is not None
        assert sub.name == "A"

    def test_get_missing_returns_none(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        assert store.get("https://nothere.com") is None

    def test_multiple_subscriptions(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        for i in range(5):
            store.subscribe(f"https://feed{i}.com/rss", name=f"Feed {i}")
        assert len(store.list()) == 5

    def test_missing_file_returns_empty(self, tmp_path):
        store = SubscriptionStore(tmp_path / "nonexistent" / "subs.json")
        assert store.list() == []


# --------------------------------------------------------------------------- #
# Readability
# --------------------------------------------------------------------------- #

class TestReadability:
    def test_bs4_extracts_article_content(self):
        from src.ingestion.connectors.blog.readability import _bs4_extract
        text = _bs4_extract(_HTML_ARTICLE)
        assert "The Real Content" in text
        assert "full article body" in text

    def test_bs4_removes_nav_footer_script(self):
        from src.ingestion.connectors.blog.readability import _bs4_extract
        text = _bs4_extract(_HTML_ARTICLE)
        assert "Nav stuff" not in text
        assert "Footer boilerplate" not in text
        assert "alert" not in text

    def test_bs4_returns_empty_for_short_content(self):
        from src.ingestion.connectors.blog.readability import _bs4_extract
        html = b"<html><body><article>Short.</article></body></html>"
        text = _bs4_extract(html)
        assert text == ""

    def test_fetch_full_text_network_error_returns_empty(self):
        from src.ingestion.connectors.blog.readability import fetch_full_text
        text = fetch_full_text("https://definitely-not-real-domain.invalid/")
        assert text == ""

    def test_fetch_full_text_calls_http_get(self):
        from src.ingestion.connectors.blog.readability import fetch_full_text
        getter = MagicMock(return_value=_HTML_ARTICLE)
        text = fetch_full_text("https://example.com/article", _http_get=getter)
        getter.assert_called_once_with("https://example.com/article")
        assert "The Real Content" in text

    def test_fetch_full_text_empty_response_returns_empty(self):
        from src.ingestion.connectors.blog.readability import fetch_full_text
        getter = MagicMock(return_value=b"")
        text = fetch_full_text("https://example.com", _http_get=getter)
        assert text == ""


# --------------------------------------------------------------------------- #
# BlogConnector — discover
# --------------------------------------------------------------------------- #

class TestBlogConnectorDiscover:
    def test_discover_reads_from_store(self, tmp_path):
        connector, _, _ = _make_connector(tmp_path)
        connector.subscribe("https://a.com/rss", name="A")
        connector.subscribe("https://b.com/rss", name="B")
        refs = list(connector.discover())
        urls = [r.locator for r in refs]
        assert "https://a.com/rss" in urls
        assert "https://b.com/rss" in urls

    def test_discover_query_url_strings(self, tmp_path):
        connector, _, _ = _make_connector(tmp_path)
        refs = list(connector.discover(["https://x.com/rss", "https://y.com/rss"]))
        assert len(refs) == 2
        assert refs[0].locator == "https://x.com/rss"

    def test_discover_query_subscription_objects(self, tmp_path):
        connector, _, _ = _make_connector(tmp_path)
        subs = [FeedSubscription(url="https://z.com/rss", name="Z", tags=["ai"])]
        refs = list(connector.discover(subs))
        assert refs[0].locator == "https://z.com/rss"
        assert refs[0].metadata["tags"] == ["ai"]

    def test_discover_query_dicts(self, tmp_path):
        connector, _, _ = _make_connector(tmp_path)
        refs = list(connector.discover([{"url": "https://q.com/rss", "name": "Q", "tags": ["news"]}]))
        assert refs[0].locator == "https://q.com/rss"
        assert refs[0].title == "Q"

    def test_discover_empty_store_yields_nothing(self, tmp_path):
        connector, _, _ = _make_connector(tmp_path)
        assert list(connector.discover()) == []


# --------------------------------------------------------------------------- #
# BlogConnector — fetch
# --------------------------------------------------------------------------- #

class TestBlogConnectorFetch:
    def test_fetch_calls_http_get(self, tmp_path):
        connector, http_get, _ = _make_connector(tmp_path)
        from src.ingestion.connectors.base import SourceRef
        ref = SourceRef(locator="https://example.com/rss", metadata={"name": "X", "tags": []})
        raw = connector.fetch(ref)
        http_get.assert_called_once_with("https://example.com/rss")
        assert raw.content == _RSS
        assert raw.content_type == "application/xml"

    def test_fetch_stores_ref(self, tmp_path):
        connector, _, _ = _make_connector(tmp_path)
        from src.ingestion.connectors.base import SourceRef
        ref = SourceRef(locator="https://example.com/rss", metadata={"name": "X", "tags": []})
        raw = connector.fetch(ref)
        assert raw.ref is ref


# --------------------------------------------------------------------------- #
# BlogConnector — parse (RSS)
# --------------------------------------------------------------------------- #

class TestBlogConnectorParseRSS:
    def _parse_rss(self, tmp_path, full_text="", fetch_full_text=True):
        connector, http_get, _ = _make_connector(tmp_path, _RSS, full_text, fetch_full_text)
        from src.ingestion.connectors.base import RawDocument, SourceRef
        ref = SourceRef(locator="https://example.com/rss", metadata={"name": "Test Blog", "tags": ["tech"]})
        raw = RawDocument(ref=ref, content=_RSS, content_type="application/xml")
        return connector.parse(raw)

    def test_parse_returns_two_documents(self, tmp_path):
        docs = self._parse_rss(tmp_path)
        assert len(docs) == 2

    def test_document_source_type(self, tmp_path):
        docs = self._parse_rss(tmp_path)
        assert all(d.source_type == "blog" for d in docs)

    def test_document_titles(self, tmp_path):
        docs = self._parse_rss(tmp_path)
        titles = {d.title for d in docs}
        assert "First Post" in titles
        assert "Second Post" in titles

    def test_document_urls(self, tmp_path):
        docs = self._parse_rss(tmp_path)
        urls = {d.url for d in docs}
        assert "https://example.com/first" in urls

    def test_document_html_stripped_from_summary(self, tmp_path):
        docs = self._parse_rss(tmp_path)
        first = next(d for d in docs if d.title == "First Post")
        assert "<b>" not in (first.content or "")
        assert "Hello" in (first.content or "")
        assert "welcome" in (first.content or "")

    def test_document_stable_id(self, tmp_path):
        docs = self._parse_rss(tmp_path)
        for d in docs:
            assert d.document_id.startswith("blog-")
            assert len(d.document_id) == len("blog-") + 16

    def test_document_source_id_is_feed_name(self, tmp_path):
        docs = self._parse_rss(tmp_path)
        assert all(d.source_id == "Test Blog" for d in docs)

    def test_document_tags_from_ref_metadata(self, tmp_path):
        docs = self._parse_rss(tmp_path)
        assert all("tech" in (d.metadata or {}).get("tags", []) for d in docs)

    def test_document_created_at_populated(self, tmp_path):
        docs = self._parse_rss(tmp_path)
        first = next(d for d in docs if d.title == "First Post")
        assert first.created_at is not None
        assert first.created_at > 0

    def test_full_text_used_when_longer(self, tmp_path):
        long_full_text = "x" * 500
        docs = self._parse_rss(tmp_path, full_text=long_full_text)
        first = next(d for d in docs if d.title == "First Post")
        assert first.content == long_full_text
        assert first.metadata.get("has_full_text") is True

    def test_summary_used_when_full_text_shorter(self, tmp_path):
        docs = self._parse_rss(tmp_path, full_text="tiny")
        first = next(d for d in docs if d.title == "First Post")
        assert first.content != "tiny"

    def test_full_text_not_fetched_when_disabled(self, tmp_path):
        _, _, ft_getter = _make_connector(tmp_path, _RSS, "", fetch_full_text=False)
        # Re-build with disabled flag
        connector = BlogConnector(
            subs_path=tmp_path / "subs.json",
            fetch_full_text=False,
            http_get=MagicMock(return_value=_RSS),
            full_text_getter=ft_getter,
        )
        from src.ingestion.connectors.base import RawDocument, SourceRef
        ref = SourceRef(locator="https://example.com/rss", metadata={"name": "T", "tags": []})
        raw = RawDocument(ref=ref, content=_RSS)
        connector.parse(raw)
        ft_getter.assert_not_called()

    def test_limit_per_feed_respected(self, tmp_path):
        connector = BlogConnector(
            subs_path=tmp_path / "subs.json",
            limit_per_feed=1,
            http_get=MagicMock(return_value=_RSS),
            full_text_getter=MagicMock(return_value=""),
        )
        from src.ingestion.connectors.base import RawDocument, SourceRef
        ref = SourceRef(locator="https://example.com/rss", metadata={"name": "T", "tags": []})
        raw = RawDocument(ref=ref, content=_RSS)
        docs = connector.parse(raw)
        assert len(docs) == 1


# --------------------------------------------------------------------------- #
# BlogConnector — parse (Atom)
# --------------------------------------------------------------------------- #

class TestBlogConnectorParseAtom:
    def test_atom_feed_parsed(self, tmp_path):
        connector, _, _ = _make_connector(tmp_path, _ATOM, "")
        from src.ingestion.connectors.base import RawDocument, SourceRef
        ref = SourceRef(locator="https://example.com/atom", metadata={"name": "Atom Blog", "tags": []})
        raw = RawDocument(ref=ref, content=_ATOM)
        docs = connector.parse(raw)
        assert len(docs) == 1
        assert docs[0].title == "Atom Entry"
        assert docs[0].source_type == "blog"
        assert "machine learning" in (docs[0].content or "")

    def test_atom_author_populated(self, tmp_path):
        connector, _, _ = _make_connector(tmp_path, _ATOM, "")
        from src.ingestion.connectors.base import RawDocument, SourceRef
        ref = SourceRef(locator="https://example.com/atom", metadata={"name": "Atom Blog", "tags": []})
        raw = RawDocument(ref=ref, content=_ATOM)
        docs = connector.parse(raw)
        assert "Bob Jones" in docs[0].authors


# --------------------------------------------------------------------------- #
# BlogConnector — harvest (integration)
# --------------------------------------------------------------------------- #

class TestBlogConnectorHarvest:
    def test_harvest_yields_documents(self, tmp_path):
        connector, _, _ = _make_connector(tmp_path)
        connector.subscribe("https://example.com/rss", name="Test")
        docs = list(connector.harvest())
        assert len(docs) == 2
        assert all(d.source_type == "blog" for d in docs)

    def test_harvest_skips_failed_fetch(self, tmp_path):
        connector, http_get, _ = _make_connector(tmp_path)
        connector.subscribe("https://good.com/rss", name="Good")
        connector.subscribe("https://bad.com/rss", name="Bad")
        http_get.side_effect = lambda url: _RSS if "good" in url else (_ for _ in ()).throw(OSError("fail"))
        docs = list(connector.harvest())
        assert len(docs) == 2  # only from good feed


# --------------------------------------------------------------------------- #
# Watchlist / digest
# --------------------------------------------------------------------------- #

class TestWatchlist:
    def _make_docs(self):
        from services.ingest.common.document_model import Document
        now = int(time.time() * 1000)
        return [
            Document(
                document_id="blog-001",
                source_type="blog",
                language="en",
                ingested_at=now,
                title="Python and AI are booming",
                content="Many developers use Python for machine learning projects.",
                url="https://example.com/1",
                metadata={"tags": ["tech"]},
            ),
            Document(
                document_id="blog-002",
                source_type="blog",
                language="en",
                ingested_at=now,
                title="Climate change research",
                content="Scientists publish new findings on global warming effects.",
                url="https://example.com/2",
                metadata={"tags": ["science"]},
            ),
            Document(
                document_id="blog-003",
                source_type="blog",
                language="en",
                ingested_at=now,
                title="Stock market drops",
                content="Markets fell sharply on inflation concerns.",
                url="https://example.com/3",
                metadata={"tags": ["finance"]},
            ),
        ]

    def test_match_by_content_keyword(self):
        docs = self._make_docs()
        matches = match_watchlist(docs, ["machine learning"], "ai-watch")
        assert len(matches) == 1
        assert matches[0].document_id == "blog-001"
        assert "machine learning" in matches[0].matched_keywords

    def test_match_by_title_keyword(self):
        docs = self._make_docs()
        matches = match_watchlist(docs, ["climate"], "env-watch")
        assert len(matches) == 1
        assert matches[0].document_id == "blog-002"

    def test_no_match_returns_empty(self):
        docs = self._make_docs()
        matches = match_watchlist(docs, ["blockchain"], "crypto-watch")
        assert matches == []

    def test_multiple_keywords_match(self):
        docs = self._make_docs()
        matches = match_watchlist(docs, ["python", "warming"], "wide-watch")
        assert len(matches) == 2

    def test_case_insensitive_matching(self):
        docs = self._make_docs()
        matches = match_watchlist(docs, ["PYTHON"], "case-watch")
        assert len(matches) == 1

    def test_tag_filter_narrows_results(self):
        docs = self._make_docs()
        matches = match_watchlist(docs, ["python", "warming"], "filtered", tag_filter=["tech"])
        assert len(matches) == 1
        assert matches[0].document_id == "blog-001"

    def test_run_watchlists_returns_dict(self):
        docs = self._make_docs()
        watchlists = [
            WatchlistEntry(name="ai", keywords=["python", "machine learning"]),
            WatchlistEntry(name="climate", keywords=["warming", "climate"]),
        ]
        result = run_watchlists(docs, watchlists)
        assert "ai" in result
        assert "climate" in result
        assert len(result["ai"]) == 1
        assert len(result["climate"]) == 1

    def test_digest_match_fields(self):
        docs = self._make_docs()
        matches = match_watchlist(docs, ["python"], "test-watch")
        m = matches[0]
        assert isinstance(m, DigestMatch)
        assert m.watchlist_name == "test-watch"
        assert m.title == "Python and AI are booming"
        assert m.url == "https://example.com/1"


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #

class TestIngestFeeds:
    def test_ingest_feeds_returns_result(self, tmp_path):
        from src.ingestion.connectors.blog.pipeline import ingest_feeds

        connector_mock = MagicMock()
        from src.ingestion.connectors.base import SourceRef, RawDocument
        from services.ingest.common.document_model import Document

        ref = SourceRef(locator="https://x.com/rss", metadata={"name": "X", "tags": []})
        doc = Document(
            document_id="blog-aaa",
            source_type="blog",
            language="en",
            ingested_at=int(time.time() * 1000),
            title="Test",
            content="Content",
        )
        connector_mock.discover.return_value = [ref]
        connector_mock.fetch.return_value = RawDocument(ref=ref, content=b"")
        connector_mock.parse.return_value = [doc]
        connector_mock.ingest_to_kg.return_value = {"entities": 3, "relationships": 1}

        with patch("src.ingestion.connectors.blog.connector.BlogConnector", return_value=connector_mock):
            result = ingest_feeds(
                query=["https://x.com/rss"],
                extract_entities=True,
                subs_path=tmp_path / "subs.json",
            )

        assert result.feeds_fetched == 1
        assert result.documents_ingested == 1
        assert result.entities_extracted == 3
        assert result.relationships_extracted == 1
        assert result.errors == []

    def test_ingest_feeds_fetch_error_recorded(self, tmp_path):
        from src.ingestion.connectors.blog.pipeline import ingest_feeds

        connector_mock = MagicMock()
        from src.ingestion.connectors.base import SourceRef

        ref = SourceRef(locator="https://bad.com/rss", metadata={"name": "Bad", "tags": []})
        connector_mock.discover.return_value = [ref]
        connector_mock.fetch.side_effect = OSError("timeout")

        with patch("src.ingestion.connectors.blog.connector.BlogConnector", return_value=connector_mock):
            result = ingest_feeds(extract_entities=False, subs_path=tmp_path / "subs.json")

        assert result.documents_ingested == 0
        assert len(result.errors) == 1
        assert "fetch failed" in result.errors[0]

    def test_ingest_feeds_no_entity_extraction(self, tmp_path):
        from src.ingestion.connectors.blog.pipeline import ingest_feeds

        connector_mock = MagicMock()
        from src.ingestion.connectors.base import SourceRef, RawDocument
        from services.ingest.common.document_model import Document

        ref = SourceRef(locator="https://x.com/rss", metadata={"name": "X", "tags": []})
        doc = Document(document_id="blog-bbb", source_type="blog", language="en", ingested_at=int(time.time() * 1000), title="T", content="C")
        connector_mock.discover.return_value = [ref]
        connector_mock.fetch.return_value = RawDocument(ref=ref, content=b"")
        connector_mock.parse.return_value = [doc]

        with patch("src.ingestion.connectors.blog.connector.BlogConnector", return_value=connector_mock):
            result = ingest_feeds(extract_entities=False, subs_path=tmp_path / "subs.json")

        connector_mock.ingest_to_kg.assert_not_called()
        assert result.entities_extracted == 0


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

class TestRegistry:
    def test_blog_registered(self):
        from src.ingestion.connectors.registry import is_registered
        import src.ingestion.connectors.blog  # noqa: F401
        assert is_registered("blog")

    def test_stable_id_deterministic(self):
        id1 = _stable_id("https://example.com/post")
        id2 = _stable_id("https://example.com/post")
        assert id1 == id2
        assert id1.startswith("blog-")

    def test_stable_id_distinct_urls(self):
        assert _stable_id("https://a.com/1") != _stable_id("https://b.com/2")

    def test_strip_html(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"
        assert _strip_html("") == ""
        assert _strip_html(None) == ""
