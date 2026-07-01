"""
Coverage tests for TechCrunchSpider.

Follows the style of tests/unit/scraper/test_bbc_spider.py and
test_npr_spider.py: builds real ``HtmlResponse`` objects from representative
HTML and asserts on parsed article fields, link extraction, and the
empty / missing-element branches.

NOTE ON A GENUINE SOURCE BUG (documented, not fixed):
The link selectors combine two groups where only the second carries
``::attr(href)`` (e.g.
``'a[href*="techcrunch.com/2024/"], a[href*="techcrunch.com/2025/"]::attr(href)'``).
Links matched only by the first ``/2024/`` group are returned as element
serialization strings; ``parse`` then joins them onto the base URL producing a
mangled, percent-encoded URL. Only ``/2025/`` links flow through the working
path. The tests exercise the working ``/2025/`` path and document the mangled
output for the ``/2024/`` case.
"""

import pytest

pytest.importorskip("scrapy")

from scrapy.http import HtmlResponse

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from scraper.spiders.techcrunch_spider import TechCrunchSpider
from scraper.items import NewsItem


def _response(url, html):
    return HtmlResponse(url=url, body=html.encode("utf-8"))


class TestTechCrunchSpider:
    """Test suite for TechCrunchSpider."""

    @pytest.fixture
    def spider(self):
        return TechCrunchSpider()

    def test_spider_initialization(self, spider):
        assert spider.name == "techcrunch"
        assert "techcrunch.com" in spider.allowed_domains
        assert "https://techcrunch.com/" in spider.start_urls

    def test_parse_absolute_2025_links(self, spider):
        """Absolute /2025/ links are requested unchanged with parse_article."""
        html = """
        <html><body>
            <a href="https://techcrunch.com/2025/05/01/story-a/">A</a>
            <a href="https://techcrunch.com/2025/05/02/story-b/">B</a>
        </body></html>
        """
        requests = list(spider.parse(_response("https://techcrunch.com/", html)))
        urls = [r.url for r in requests]
        assert "https://techcrunch.com/2025/05/01/story-a/" in urls
        assert "https://techcrunch.com/2025/05/02/story-b/" in urls
        for r in requests:
            assert r.callback == spider.parse_article

    def test_parse_relative_2025_link_made_absolute(self, spider):
        """A relative /2025/ link is resolved against the response URL."""
        html = """
        <html><body>
            <a href="/2025/05/03/story-c/">C relative</a>
        </body></html>
        """
        requests = list(spider.parse(_response("https://techcrunch.com/", html)))
        urls = [r.url for r in requests]
        assert "https://techcrunch.com/2025/05/03/story-c/" in urls

    def test_parse_2024_link_is_mangled(self, spider):
        """GENUINE BUG: a /2024/-only link is returned as an element string and
        gets urljoined into a percent-encoded, non-article URL."""
        html = """
        <html><body>
            <a href="https://techcrunch.com/2024/12/31/old-story/">Old</a>
        </body></html>
        """
        requests = list(spider.parse(_response("https://techcrunch.com/", html)))
        urls = [r.url for r in requests]
        # The mangled request contains the percent-encoded '<a href=' fragment
        # rather than a clean article URL.
        assert any("%3Ca" in u for u in urls)
        assert "https://techcrunch.com/2024/12/31/old-story/" not in urls

    def test_parse_article_full_fields(self, spider):
        html = """
        <html><body>
            <h1 class="article__title">TC Title</h1>
            <time class="full-date-time" datetime="2025-05-01T09:00:00Z">May 1</time>
            <div class="byline"><a rel="author">Alice TC</a></div>
            <div class="article-content"><p>TC para one.</p><p>TC para two.</p></div>
        </body></html>
        """
        url = "https://techcrunch.com/2025/05/01/ai/story/"
        items = list(spider.parse_article(_response(url, html)))

        assert len(items) == 1
        item = items[0]
        assert isinstance(item, NewsItem)
        assert item["title"] == "TC Title"
        assert item["url"] == url
        assert item["source"] == "TechCrunch"
        assert item["author"] == "Alice TC"
        # ISO datetime is passed through unchanged.
        assert item["published_date"] == "2025-05-01T09:00:00Z"
        # /ai/ in the URL -> the Artificial Intelligence category.
        assert item["category"] == "Artificial Intelligence"
        assert item["content"] == "TC para one. TC para two."

    def test_parse_article_entry_content_and_h1_fallbacks(self, spider):
        """Title falls back to a bare <h1>; content to .entry-content p."""
        html = """
        <html><body>
            <h1>Plain Title</h1>
            <div class="entry-content"><p>Entry body paragraph.</p></div>
        </body></html>
        """
        url = "https://techcrunch.com/2025/05/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["title"] == "Plain Title"
        assert item["content"] == "Entry body paragraph."

    def test_parse_article_default_author_and_tag_category(self, spider):
        """No byline -> default author (note the source typo "TechCrunch Sta");
        an unknown URL category falls back to the first tag link text."""
        html = """
        <html><body>
            <h1 class="article__title">No Byline</h1>
            <div class="article-content"><p>Body.</p></div>
            <div class="tags"><a>Fintech</a><a>More</a></div>
        </body></html>
        """
        url = "https://techcrunch.com/2025/05/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["author"] == "TechCrunch Sta"
        assert item["category"] == "Fintech"

    def test_parse_article_category_defaults_to_technology(self, spider):
        """Unknown URL and no tags -> category defaults to "Technology"."""
        html = """
        <html><body>
            <h1 class="article__title">Uncategorised</h1>
            <div class="article-content"><p>Body.</p></div>
        </body></html>
        """
        url = "https://techcrunch.com/2025/05/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["category"] == "Technology"

    def test_parse_article_missing_date_uses_now(self, spider):
        html = """
        <html><body>
            <h1 class="article__title">No Date</h1>
            <div class="article-content"><p>Body.</p></div>
        </body></html>
        """
        url = "https://techcrunch.com/2025/05/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert "T" in item["published_date"]

    def test_parse_article_meta_author_fallback(self, spider):
        """Author falls back to the meta[name=author] tag when no byline link."""
        html = """
        <html><head><meta name="author" content="Meta Writer"/></head><body>
            <h1 class="article__title">Meta Author</h1>
            <div class="article-content"><p>Body.</p></div>
        </body></html>
        """
        url = "https://techcrunch.com/2025/05/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["author"] == "Meta Writer"

    def test_parse_article_empty_content_yields_nothing(self, spider):
        html = "<html><body><h1 class='article__title'>Title Only</h1></body></html>"
        url = "https://techcrunch.com/2025/05/01/story/"
        assert list(spider.parse_article(_response(url, html))) == []

    def test_parse_article_no_title_yields_nothing(self, spider):
        html = """
        <html><body>
            <div class="article-content"><p>Body with no title.</p></div>
        </body></html>
        """
        url = "https://techcrunch.com/2025/05/01/story/"
        assert list(spider.parse_article(_response(url, html))) == []

    def test_extract_category_from_url_variants(self, spider):
        cases = {
            "https://techcrunch.com/2025/01/01/startups/x": "Startups",
            "https://techcrunch.com/2025/01/01/apps/x": "Apps",
            "https://techcrunch.com/2025/01/01/gadgets/x": "Gadgets",
            "https://techcrunch.com/2025/01/01/venture/x": "Venture Capital",
            "https://techcrunch.com/2025/01/01/security/x": "Security",
            "https://techcrunch.com/2025/01/01/mobile/x": "Mobile",
            "https://techcrunch.com/2025/01/01/ai/x": "Artificial Intelligence",
        }
        empty = _response("https://techcrunch.com/", "<html><body></body></html>")
        for url, expected in cases.items():
            assert spider._extract_category(url, empty) == expected

    def test_parse_techcrunch_date_direct(self, spider):
        # ISO datetime is returned unchanged.
        assert spider._parse_techcrunch_date("2025-05-01T09:00:00Z") == "2025-05-01T09:00:00Z"
        # Non-ISO -> ISO now (contains a 'T').
        assert "T" in spider._parse_techcrunch_date("May 1 2025")
