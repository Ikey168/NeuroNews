"""
Tests for the ingestion connector framework (registry + news connector).

Verifies that:
1. The registry registers, resolves, and lists connectors.
2. The news connector wraps the existing RSS ingest, producing valid
   document-ingest-v1 records with source_type=news.
3. harvest() chains discover -> fetch -> parse and is resilient to bad sources.
"""

import pytest

from services.ingest.common.document_contracts import DocumentIngestValidator
from src.ingestion.connectors import (
    Connector,
    RawDocument,
    SourceRef,
    available_source_types,
    get_connector,
    is_registered,
    register_connector,
)
from src.ingestion.connectors.news import NewsConnector
from src.ingestion.scrapy_integration import Feed

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Test Feed</title>
  <item>
    <title>Markets surge on strong earnings</title>
    <link>https://example.com/a</link>
    <description>Some &lt;b&gt;great&lt;/b&gt; news about record gains</description>
    <pubDate>Wed, 02 Oct 2024 13:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Second headline</title>
    <link>https://example.com/b</link>
    <description>More coverage</description>
    <pubDate>Wed, 02 Oct 2024 14:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


@pytest.fixture(scope="module")
def validator():
    return DocumentIngestValidator()


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_news_connector_is_registered():
    assert is_registered("news")
    assert "news" in available_source_types()
    assert isinstance(get_connector("news"), NewsConnector)


def test_get_connector_unknown_raises():
    with pytest.raises(KeyError):
        get_connector("does-not-exist")


def test_register_requires_source_type():
    with pytest.raises(ValueError):

        @register_connector
        class _Bad(Connector):  # no source_type
            def discover(self, query=None):
                return []

            def fetch(self, ref):
                return RawDocument(ref=ref, content=b"")

            def parse(self, raw):
                return []


def test_register_and_resolve_custom_connector():
    @register_connector
    class DummyConnector(Connector):
        source_type = "note"

        def discover(self, query=None):
            yield SourceRef(locator="note-1")

        def fetch(self, ref):
            return RawDocument(ref=ref, content="hello")

        def parse(self, raw):
            return []

    assert is_registered("note")
    assert isinstance(get_connector("note"), DummyConnector)


# --------------------------------------------------------------------------- #
# News connector
# --------------------------------------------------------------------------- #


def _news_connector(http_get=None, feeds=None):
    feeds = feeds or [Feed("Test Feed", "https://example.com/feed", "Business")]
    return NewsConnector(feeds=feeds, http_get=http_get or (lambda url: SAMPLE_RSS))


def test_news_discover_yields_one_ref_per_feed():
    conn = _news_connector()
    refs = list(conn.discover())
    assert len(refs) == 1
    assert refs[0].locator == "https://example.com/feed"
    assert refs[0].metadata["category"] == "Business"


def test_news_parse_produces_valid_documents(validator):
    conn = _news_connector()
    raw = conn.fetch(next(iter(conn.discover())))
    docs = conn.parse(raw)

    assert len(docs) == 2
    for doc in docs:
        payload = doc.to_dict()
        validator.validate_document(payload)  # must satisfy document-ingest-v1
        assert payload["source_type"] == "news"
        assert payload["metadata"]["category"] == "Business"
        assert payload["url"].startswith("https://example.com/")
        # Enrichments must not be part of the core record.
        assert "sentiment_score" not in payload
        assert "sentiment" not in payload


def test_news_harvest_chains_pipeline(validator):
    conn = _news_connector()
    docs = list(conn.harvest())
    assert len(docs) == 2
    titles = {d.title for d in docs}
    assert "Markets surge on strong earnings" in titles


def test_news_harvest_skips_unreachable_feeds():
    def flaky_get(url):
        if "bad" in url:
            raise OSError("boom")
        return SAMPLE_RSS

    feeds = [
        Feed("Good", "https://example.com/good", "World"),
        Feed("Bad", "https://example.com/bad", "World"),
    ]
    conn = NewsConnector(feeds=feeds, http_get=flaky_get)
    docs = list(conn.harvest())
    # Only the good feed contributes; the bad one is skipped, not fatal.
    assert len(docs) == 2


def test_news_enrichments_separated_from_core():
    conn = _news_connector()
    raw = conn.fetch(next(iter(conn.discover())))
    articles = conn._si.parse_feed(SAMPLE_RSS, conn._feeds[0], limit=25)
    enr = NewsConnector.enrichments_for(articles[0])
    assert "sentiment" in enr
    assert -1.0 <= enr["sentiment"]["score"] <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
