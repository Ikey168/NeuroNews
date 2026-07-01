"""
Line-coverage tests for :mod:`src.scraper.spiders.wired_spider`.

The spider parses the Wired landing page for ``/story/`` links and each
article page for title/content/date/author/category.  These tests build real
``scrapy.http.HtmlResponse`` objects and assert on the parsed output, mirroring
the style of ``tests/unit/scraper/test_bbc_spider.py``.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

# Both Scrapy (used directly) is a hard dependency of the spider; guard it so
# collection degrades gracefully when the optional package is missing.
pytest.importorskip("scrapy")

from scrapy.http import HtmlResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from scraper.items import NewsItem
from scraper.spiders.wired_spider import WiredSpider


def _response(url, html):
    return HtmlResponse(url=url, body=html.encode("utf-8"))


@pytest.fixture
def spider():
    return WiredSpider()


def test_spider_metadata(spider):
    assert spider.name == "wired"
    assert spider.allowed_domains == ["wired.com"]
    assert spider.start_urls == ["https://www.wired.com/"]


def test_parse_extracts_story_links_and_absolutizes(spider):
    html = """
    <html><body>
        <a href="/story/relative-one/">Relative 1</a>
        <a href="/story/relative-two/">Relative 2</a>
        <a href="https://www.wired.com/story/absolute-three/">Absolute 3</a>
        <a href="/gear/not-a-story/">Not a story</a>
        <a href="/science/also-not/">Also not</a>
    </body></html>
    """
    response = _response("https://www.wired.com/", html)

    requests = list(spider.parse(response))

    urls = [r.url for r in requests]
    # Only the three ``/story/`` links are followed; the gear/science links are
    # excluded by the ``a[href*="/story/"]`` selector.
    assert len(requests) == 3
    assert "https://www.wired.com/story/relative-one/" in urls
    assert "https://www.wired.com/story/relative-two/" in urls
    assert "https://www.wired.com/story/absolute-three/" in urls
    assert all("/gear/" not in u for u in urls)

    # Relative links are joined against the response URL to absolute form.
    for r in requests:
        assert r.url.startswith("https://www.wired.com/story/")
        assert r.callback == spider.parse_article


def test_parse_article_primary_selectors(spider):
    html = """
    <html><body>
        <h1 data-testid="ContentHeaderHed">Primary Wired Title</h1>
        <div data-testid="ArticleBodyWrapper">
            <p>First paragraph of the story.</p>
            <p>Second paragraph with detail.</p>
        </div>
        <time data-testid="ContentHeaderPublishDate"
              datetime="2025-01-02T10:00:00Z">Jan 2 2025</time>
        <a data-testid="ContentHeaderAuthorLink">Jane Doe</a>
    </body></html>
    """
    response = _response("https://www.wired.com/story/security/foo", html)

    items = list(spider.parse_article(response))

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, NewsItem)
    assert item["title"] == "Primary Wired Title"
    assert item["url"] == "https://www.wired.com/story/security/foo"
    assert item["source"] == "Wired"
    assert item["content"] == "First paragraph of the story. Second paragraph with detail."
    assert item["published_date"] == "2025-01-02T10:00:00Z"
    assert item["author"] == "Jane Doe"
    # ``/security/`` in the URL maps to the Security category.
    assert item["category"] == "Security"


def test_parse_article_fallback_selectors_and_rubric(spider):
    """Bare ``h1``/``article`` selectors, missing date, byline & rubric."""
    html = """
    <html><body>
        <h1>Fallback Title</h1>
        <article><p>Article-body fallback paragraph.</p></article>
        <a data-testid="ContentHeaderRubric">Gadgets</a>
    </body></html>
    """
    response = _response("https://www.wired.com/story/plain/foo", html)

    item = list(spider.parse_article(response))[0]

    assert item["title"] == "Fallback Title"
    assert item["content"] == "Article-body fallback paragraph."
    # No author element -> default placeholder from the source.
    assert item["author"] == "Wired Sta"
    # No datetime anywhere -> falls back to an ISO ``datetime.now()`` string.
    parsed = datetime.fromisoformat(item["published_date"])
    assert isinstance(parsed, datetime)
    # Category comes from the rubric element when the URL has no known segment.
    assert item["category"] == "Gadgets"


def test_parse_article_default_category(spider):
    html = """
    <html><body>
        <h1>No Category Title</h1>
        <article><p>Some content.</p></article>
    </body></html>
    """
    response = _response("https://www.wired.com/story/misc/foo", html)

    item = list(spider.parse_article(response))[0]
    # No URL match and no rubric -> the "Technology" default.
    assert item["category"] == "Technology"


def test_parse_article_no_content_yields_nothing(spider):
    html = """
    <html><body>
        <h1 data-testid="ContentHeaderHed">Title Only</h1>
    </body></html>
    """
    response = _response("https://www.wired.com/story/empty/foo", html)

    # The guard ``if item["title"] and item["content"]`` suppresses the item
    # when no paragraphs are found.
    assert list(spider.parse_article(response)) == []


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.wired.com/gear/x", "Gear"),
        ("https://www.wired.com/science/x", "Science"),
        ("https://www.wired.com/security/x", "Security"),
        ("https://www.wired.com/business/x", "Business"),
        ("https://www.wired.com/culture/x", "Culture"),
        ("https://www.wired.com/ideas/x", "Ideas"),
        ("https://www.wired.com/backchannel/x", "Backchannel"),
    ],
)
def test_extract_category_from_url(spider, url, expected):
    response = _response(url, "<html><body></body></html>")
    assert spider._extract_category(url, response) == expected
