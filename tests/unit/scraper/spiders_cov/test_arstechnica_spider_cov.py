"""
Coverage tests for ArsTechnicaSpider.

Follows the style of tests/unit/scraper/test_bbc_spider.py and
test_npr_spider.py: builds real ``HtmlResponse`` objects from representative
HTML and asserts on parsed article fields, link extraction, and the
empty / missing-element branches.

NOTE ON A GENUINE SOURCE BUG (documented, not fixed):
The link selector combines two groups where only the second carries
``::attr(href)`` (``'a[href*="/2024/"], a[href*="/2025/"]::attr(href)'``). Links
matched only by the ``/2024/`` group are returned as element-serialization
strings; since those strings do not end with ``/`` they are silently skipped by
the ``if link.endswith("/")`` guard, so ``/2024/`` articles are dropped
entirely. Only ``/2025/`` links flow through the working path.
"""

import pytest

pytest.importorskip("scrapy")

from scrapy.http import HtmlResponse

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from scraper.spiders.arstechnica_spider import ArsTechnicaSpider
from scraper.items import NewsItem


def _response(url, html):
    return HtmlResponse(url=url, body=html.encode("utf-8"))


class TestArsTechnicaSpider:
    """Test suite for ArsTechnicaSpider."""

    @pytest.fixture
    def spider(self):
        return ArsTechnicaSpider()

    def test_spider_initialization(self, spider):
        assert spider.name == "arstechnica"
        assert "arstechnica.com" in spider.allowed_domains
        assert "https://arstechnica.com/" in spider.start_urls

    def test_parse_only_trailing_slash_2025_links(self, spider):
        """Only /2025/ links ending in '/' are requested."""
        html = """
        <html><body>
            <a href="https://arstechnica.com/2025/06/01/story-a/">A slash</a>
            <a href="/2025/06/02/story-b/">B rel slash</a>
            <a href="https://arstechnica.com/2025/06/03/no-slash">C no slash</a>
        </body></html>
        """
        requests = list(spider.parse(_response("https://arstechnica.com/", html)))
        urls = [r.url for r in requests]
        assert "https://arstechnica.com/2025/06/01/story-a/" in urls
        assert "https://arstechnica.com/2025/06/02/story-b/" in urls
        # No trailing slash -> skipped.
        assert not any("no-slash" in u for u in urls)
        for r in requests:
            assert r.callback == spider.parse_article

    def test_parse_2024_link_is_dropped(self, spider):
        """GENUINE BUG: a /2024/-only link is returned as an element string that
        does not end in '/', so it is silently dropped (no requests)."""
        html = """
        <html><body>
            <a href="https://arstechnica.com/2024/06/01/story-a/">2024</a>
        </body></html>
        """
        requests = list(spider.parse(_response("https://arstechnica.com/", html)))
        assert requests == []

    def test_parse_article_full_fields(self, spider):
        html = """
        <html><body>
            <h1 class="post-title">Ars Title</h1>
            <time itemprop="datePublished" datetime="2025-06-01T09:00:00Z">Jun 1</time>
            <span itemprop="author"><a>Bob Ars</a></span>
            <div class="post-content"><p>Ars para one.</p><p>Ars para two.</p></div>
        </body></html>
        """
        url = "https://arstechnica.com/science/2025/06/01/story/"
        items = list(spider.parse_article(_response(url, html)))

        assert len(items) == 1
        item = items[0]
        assert isinstance(item, NewsItem)
        assert item["title"] == "Ars Title"
        assert item["url"] == url
        assert item["source"] == "Ars Technica"
        assert item["author"] == "Bob Ars"
        assert item["published_date"] == "2025-06-01T09:00:00Z"
        assert item["category"] == "Science"
        assert item["content"] == "Ars para one. Ars para two."

    def test_parse_article_itemprop_headline_and_article_content_fallback(self, spider):
        """Title via h1[itemprop=headline]; content via article p fallback."""
        html = """
        <html><body>
            <h1 itemprop="headline">Headline Fallback</h1>
            <article><p>Article body paragraph.</p></article>
        </body></html>
        """
        url = "https://arstechnica.com/2025/06/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["title"] == "Headline Fallback"
        assert item["content"] == "Article body paragraph."

    def test_parse_article_articlebody_content_fallback(self, spider):
        """Content via div[itemprop=articleBody] p fallback."""
        html = """
        <html><body>
            <h1 class="post-title">Body Fallback</h1>
            <div itemprop="articleBody"><p>Structured body paragraph.</p></div>
        </body></html>
        """
        url = "https://arstechnica.com/2025/06/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["content"] == "Structured body paragraph."

    def test_parse_article_default_author_and_section_category(self, spider):
        """No author -> default (note the source typo "Ars Technica Sta");
        an unknown URL category falls back to the .section text."""
        html = """
        <html><body>
            <h1 class="post-title">No Author</h1>
            <div class="post-content"><p>Body.</p></div>
            <div class="post-meta"><span class="section">Culture</span></div>
        </body></html>
        """
        url = "https://arstechnica.com/2025/06/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["author"] == "Ars Technica Sta"
        assert item["category"] == "Culture"

    def test_parse_article_category_defaults_to_technology(self, spider):
        """Unknown URL and no section -> category defaults to "Technology"."""
        html = """
        <html><body>
            <h1 class="post-title">Uncategorised</h1>
            <div class="post-content"><p>Body.</p></div>
        </body></html>
        """
        url = "https://arstechnica.com/2025/06/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["category"] == "Technology"

    def test_parse_article_missing_date_uses_now(self, spider):
        html = """
        <html><body>
            <h1 class="post-title">No Date</h1>
            <div class="post-content"><p>Body.</p></div>
        </body></html>
        """
        url = "https://arstechnica.com/2025/06/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert "T" in item["published_date"]

    def test_parse_article_meta_author_fallback(self, spider):
        html = """
        <html><head><meta name="author" content="Meta Ars"/></head><body>
            <h1 class="post-title">Meta Author</h1>
            <div class="post-content"><p>Body.</p></div>
        </body></html>
        """
        url = "https://arstechnica.com/2025/06/01/story/"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["author"] == "Meta Ars"

    def test_parse_article_empty_content_yields_nothing(self, spider):
        html = "<html><body><h1 class='post-title'>Title Only</h1></body></html>"
        url = "https://arstechnica.com/2025/06/01/story/"
        assert list(spider.parse_article(_response(url, html))) == []

    def test_parse_article_no_title_yields_nothing(self, spider):
        html = """
        <html><body>
            <div class="post-content"><p>Body without a title.</p></div>
        </body></html>
        """
        url = "https://arstechnica.com/2025/06/01/story/"
        assert list(spider.parse_article(_response(url, html))) == []

    def test_extract_category_from_url_variants(self, spider):
        cases = {
            "https://arstechnica.com/tech-policy/2025/01/x/": "Tech Policy",
            "https://arstechnica.com/security/2025/01/x/": "Security",
            "https://arstechnica.com/gadgets/2025/01/x/": "Gadgets",
            "https://arstechnica.com/science/2025/01/x/": "Science",
            "https://arstechnica.com/gaming/2025/01/x/": "Gaming",
            "https://arstechnica.com/cars/2025/01/x/": "Automotive",
            "https://arstechnica.com/space/2025/01/x/": "Space",
        }
        empty = _response("https://arstechnica.com/", "<html><body></body></html>")
        for url, expected in cases.items():
            assert spider._extract_category(url, empty) == expected

    def test_parse_ars_date_direct(self, spider):
        assert spider._parse_ars_date("2025-06-01T09:00:00Z") == "2025-06-01T09:00:00Z"
        assert "T" in spider._parse_ars_date("June 1 2025")
