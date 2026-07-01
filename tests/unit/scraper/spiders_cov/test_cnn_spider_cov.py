"""
Coverage tests for CNNSpider.

Follows the style of tests/unit/scraper/test_bbc_spider.py and
test_npr_spider.py: builds real ``HtmlResponse`` objects from representative
HTML and asserts on the parsed article fields, start URLs / link extraction, and
the empty / missing-element branches.

NOTE ON A GENUINE SOURCE BUG (not fixed here, only documented by the tests):
The combined link selector in ``CNNSpider.parse`` is
``'a[href*="/2024/"], a[href*="/2025/"]::attr(href)'``. The ``::attr(href)``
pseudo-element only applies to the *second* group, so links matched only by the
``/2024/`` group are returned as full element-serialization strings
(``'<a href="...">...</a>'``) rather than hrefs. Because such a string does not
start with ``/`` it is never passed through ``response.urljoin`` and
``scrapy.Request`` then raises ``ValueError: Missing scheme in request url``.
Only ``/2025/`` links flow through the working ``::attr(href)`` path. The tests
below exercise the working ``/2025/`` path and assert the raise on ``/2024/``.
"""

import pytest

# Guard the optional Scrapy dependency so collection never crashes when it is
# absent.
pytest.importorskip("scrapy")

from scrapy.http import HtmlResponse

# Import with proper path handling
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from scraper.spiders.cnn_spider import CNNSpider
from scraper.items import NewsItem


def _response(url, html):
    return HtmlResponse(url=url, body=html.encode("utf-8"))


class TestCNNSpider:
    """Test suite for CNNSpider."""

    @pytest.fixture
    def spider(self):
        return CNNSpider()

    def test_spider_initialization(self, spider):
        assert spider.name == "cnn"
        assert "cnn.com" in spider.allowed_domains
        assert "https://www.cnn.com/" in spider.start_urls

    def test_parse_extracts_category_filtered_links(self, spider):
        """Only /2025/ links whose path matches a category filter are followed."""
        html = """
        <html><body>
            <a href="https://www.cnn.com/2025/02/20/tech/gadget">Tech (kept)</a>
            <a href="https://www.cnn.com/2025/03/01/politics/thing">Politics (kept)</a>
            <a href="https://www.cnn.com/2025/03/01/business/thing">Business (kept)</a>
            <a href="https://www.cnn.com/2025/03/01/weather/thing">Weather (filtered out)</a>
        </body></html>
        """
        requests = list(spider.parse(_response("https://www.cnn.com/", html)))

        urls = [r.url for r in requests]
        # tech / politics / business match the category filter.
        assert any("/tech/gadget" in u for u in urls)
        assert any("/politics/thing" in u for u in urls)
        assert any("/business/thing" in u for u in urls)
        # weather matches no category filter and lacks /index.html -> dropped.
        assert not any("/weather/" in u for u in urls)

        for r in requests:
            assert r.callback == spider.parse_article

    def test_parse_index_html_links_always_kept(self, spider):
        """Any /2025/ link containing /index.html passes the filter."""
        html = """
        <html><body>
            <a href="https://www.cnn.com/2025/04/01/misc/story/index.html">Misc index</a>
        </body></html>
        """
        requests = list(spider.parse(_response("https://www.cnn.com/", html)))
        assert len(requests) == 1
        assert requests[0].url.endswith("/index.html")

    def test_parse_relative_2025_link_is_made_absolute(self, spider):
        """Relative /2025/ links are resolved against the response URL."""
        html = """
        <html><body>
            <a href="/2025/05/05/tech/rel/index.html">Relative</a>
        </body></html>
        """
        requests = list(spider.parse(_response("https://www.cnn.com/", html)))
        assert len(requests) == 1
        assert requests[0].url == "https://www.cnn.com/2025/05/05/tech/rel/index.html"

    def test_parse_follows_pagination(self, spider):
        """A pagination-arrow-right link yields a follow request back to parse."""
        html = """
        <html><body>
            <a class="pagination-arrow-right" href="/page/2">Next</a>
        </body></html>
        """
        requests = list(spider.parse(_response("https://www.cnn.com/", html)))
        assert len(requests) == 1
        assert requests[0].url == "https://www.cnn.com/page/2"
        assert requests[0].callback == spider.parse

    def test_parse_2024_link_raises_missing_scheme(self, spider):
        """GENUINE BUG: a /2024/-only link is returned as an element string and
        makes scrapy.Request raise ValueError (missing scheme)."""
        html = """
        <html><body>
            <a href="/2024/01/15/politics/story/index.html">2024 link</a>
        </body></html>
        """
        with pytest.raises(ValueError):
            list(spider.parse(_response("https://www.cnn.com/", html)))

    def test_parse_article_full_fields(self, spider):
        html = """
        <html><head>
            <meta property="article:published_time" content="2025-02-20T12:00:00Z"/>
        </head><body>
            <h1 class="headline__text">CNN Headline Text</h1>
            <div class="timestamp">Updated 1200 GMT (2000 HKT) February 20, 2025</div>
            <span class="byline__name">Jane CNN</span>
            <div class="zn-body__paragraph">First CNN paragraph.</div>
            <div class="zn-body__paragraph">Second CNN paragraph.</div>
        </body></html>
        """
        url = "https://www.cnn.com/2025/02/20/politics/story/index.html"
        items = list(spider.parse_article(_response(url, html)))

        assert len(items) == 1
        item = items[0]
        assert isinstance(item, NewsItem)
        assert item["title"] == "CNN Headline Text"
        assert item["url"] == url
        assert item["source"] == "CNN"
        assert item["author"] == "Jane CNN"
        assert item["category"] == "Politics"
        # "February 20, 2025" -> midnight ISO.
        assert item["published_date"] == "2025-02-20T00:00:00"
        assert item["content"] == "First CNN paragraph. Second CNN paragraph."

    def test_parse_article_title_fallback_to_document_title(self, spider):
        """With no h1, the <title> tag is used as the title fallback."""
        html = """
        <html><head><title>Doc Title</title></head><body>
            <div class="zn-body__paragraph">Some content.</div>
        </body></html>
        """
        url = "https://www.cnn.com/2025/01/01/misc/a/index.html"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["title"] == "Doc Title"

    def test_parse_article_articlebody_content_fallback(self, spider):
        """When zn-body paragraphs are absent, the ArticleBody selector is used."""
        html = """
        <html><body>
            <h1 class="headline__text">Body Fallback</h1>
            <div data-component-name="ArticleBody"><p>Body paragraph one.</p></div>
        </body></html>
        """
        url = "https://www.cnn.com/2025/01/01/misc/a/index.html"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["content"] == "Body paragraph one."

    def test_parse_article_default_author_and_breadcrumb_category(self, spider):
        """No byline -> default author (note the source typo "CNN Sta");
        an unknown URL category falls back to the breadcrumb text."""
        html = """
        <html><body>
            <h1 class="headline__text">No Byline</h1>
            <div class="zn-body__paragraph">Body.</div>
            <span class="breadcrumb__item">World</span>
        </body></html>
        """
        url = "https://www.cnn.com/2025/01/01/misc/a/index.html"
        item = list(spider.parse_article(_response(url, html)))[0]
        # Documents the genuine "Staff" -> "Sta" typo in the source default.
        assert item["author"] == "CNN Sta"
        assert item["category"] == "World"

    def test_parse_article_category_defaults_to_news(self, spider):
        """Unknown URL and no breadcrumb -> category defaults to "News"."""
        html = """
        <html><body>
            <h1 class="headline__text">Uncategorised</h1>
            <div class="zn-body__paragraph">Body.</div>
        </body></html>
        """
        url = "https://www.cnn.com/2025/01/01/misc/a/index.html"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert item["category"] == "News"

    def test_parse_article_bad_date_falls_back_to_now(self, spider):
        """An unparseable timestamp falls back to an ISO 'now' value."""
        html = """
        <html><body>
            <h1 class="headline__text">Bad Date</h1>
            <div class="zn-body__paragraph">Body.</div>
            <div class="timestamp">no recognisable date here</div>
        </body></html>
        """
        url = "https://www.cnn.com/2025/01/01/misc/a/index.html"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert "T" in item["published_date"]

    def test_parse_article_missing_date_uses_now(self, spider):
        """No date element at all -> ISO 'now' value."""
        html = """
        <html><body>
            <h1 class="headline__text">No Date</h1>
            <div class="zn-body__paragraph">Body.</div>
        </body></html>
        """
        url = "https://www.cnn.com/2025/01/01/misc/a/index.html"
        item = list(spider.parse_article(_response(url, html)))[0]
        assert "T" in item["published_date"]

    def test_parse_article_empty_content_yields_nothing(self, spider):
        """Title present but no content -> the yield guard drops the item."""
        html = "<html><body><h1 class='headline__text'>Title Only</h1></body></html>"
        url = "https://www.cnn.com/2025/01/01/misc/a/index.html"
        assert list(spider.parse_article(_response(url, html))) == []

    def test_parse_article_no_title_yields_nothing(self, spider):
        """Content present but no title -> the yield guard drops the item."""
        html = """
        <html><body>
            <div class="zn-body__paragraph">Body without a title.</div>
        </body></html>
        """
        url = "https://www.cnn.com/2025/01/01/misc/a/index.html"
        assert list(spider.parse_article(_response(url, html))) == []

    def test_extract_category_from_url_variants(self, spider):
        """All URL-based category mappings are exercised directly."""
        cases = {
            "https://www.cnn.com/2025/01/01/politics/x": "Politics",
            "https://www.cnn.com/2025/01/01/business/x": "Business",
            "https://www.cnn.com/2025/01/01/tech/x": "Technology",
            "https://www.cnn.com/2025/01/01/health/x": "Health",
            "https://www.cnn.com/2025/01/01/sport/x": "Sports",
            "https://www.cnn.com/2025/01/01/entertainment/x": "Entertainment",
        }
        empty = _response("https://www.cnn.com/", "<html><body></body></html>")
        for url, expected in cases.items():
            assert spider._extract_category(url, empty) == expected

    def test_parse_cnn_date_direct(self, spider):
        assert spider._parse_cnn_date("January 1, 2024") == "2024-01-01T00:00:00"
        # Unparseable -> ISO now (contains a 'T').
        assert "T" in spider._parse_cnn_date("not a date")
