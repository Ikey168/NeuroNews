"""Tests for src/ingestion/scrapy_integration.py (RSS -> warehouse ingestion)."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("duckdb")

from ingestion.scrapy_integration import (  # noqa: E402
    Feed,
    parse_feed,
    score_sentiment,
    _parse_date,
    _make_id,
    _strip_html,
)

SAMPLE_RSS = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Sample</title>
    <item>
      <title>Markets surge to record high on strong growth</title>
      <link>https://example.com/a</link>
      <description>&lt;p&gt;Stocks rallied as gains accelerated.&lt;/p&gt;</description>
      <pubDate>Wed, 18 Jun 2025 09:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Energy crisis deepens as prices plunge and fears grow</title>
      <link>https://example.com/b</link>
      <description>Losses mount.</description>
      <pubDate>Wed, 18 Jun 2025 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Sample</title>
  <entry>
    <title>New breakthrough boosts recovery</title>
    <link href="https://example.com/atom1"/>
    <summary>A strong success story.</summary>
    <published>2025-06-18T08:00:00Z</published>
  </entry>
</feed>
"""

FEED = Feed("Test Feed", "https://example.com/rss", "Economy")


class TestParseFeed:
    def test_parses_rss_items(self):
        articles = parse_feed(SAMPLE_RSS, FEED)
        assert len(articles) == 2
        first = articles[0]
        assert first.title.startswith("Markets surge")
        assert first.url == "https://example.com/a"
        assert first.source == "Test Feed"
        assert first.category == "Economy"
        # HTML stripped from description
        assert "<p>" not in first.content

    def test_parses_atom_entries(self):
        articles = parse_feed(SAMPLE_ATOM, FEED)
        assert len(articles) == 1
        assert articles[0].url == "https://example.com/atom1"
        assert articles[0].title.startswith("New breakthrough")

    def test_limit_is_respected(self):
        articles = parse_feed(SAMPLE_RSS, FEED, limit=1)
        assert len(articles) == 1

    def test_bad_xml_returns_empty(self):
        assert parse_feed(b"not xml at all", FEED) == []

    def test_item_without_title_or_link_skipped(self):
        rss = b"""<?xml version="1.0"?><rss><channel>
            <item><description>no title or link</description></item>
        </channel></rss>"""
        assert parse_feed(rss, FEED) == []


class TestSentiment:
    def test_positive(self):
        score, label = score_sentiment(
            "Markets surge to record high on strong growth and wins"
        )
        assert label == "positive"
        assert score > 0

    def test_negative(self):
        score, label = score_sentiment(
            "Crisis deepens as prices crash and losses mount amid fears"
        )
        assert label == "negative"
        assert score < 0

    def test_neutral_empty(self):
        assert score_sentiment("") == (0.0, "neutral")

    def test_score_bounded(self):
        score, _ = score_sentiment("win " * 50)
        assert -1.0 <= score <= 1.0


class TestHelpers:
    def test_make_id_stable_and_prefixed(self):
        a = _make_id("https://example.com/x")
        b = _make_id("https://example.com/x")
        assert a == b
        assert a.startswith("rss-")

    def test_strip_html(self):
        assert _strip_html("<p>Hello   <b>world</b></p>") == "Hello world"

    def test_parse_date_rfc822(self):
        dt = _parse_date("Wed, 18 Jun 2025 09:30:00 GMT")
        assert dt.year == 2025 and dt.month == 6 and dt.day == 18

    def test_parse_date_iso(self):
        dt = _parse_date("2025-06-18T08:00:00Z")
        assert dt.year == 2025 and dt.hour == 8
