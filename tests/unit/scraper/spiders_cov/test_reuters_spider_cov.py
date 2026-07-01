"""
Line-coverage tests for :mod:`src.scraper.spiders.reuters_spider`.

Builds real ``HtmlResponse`` objects and asserts parsed article fields plus
``/article/`` link extraction, mirroring ``tests/unit/scraper/test_bbc_spider.py``.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("scrapy")

from scrapy.http import HtmlResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from scraper.items import NewsItem
from scraper.spiders.reuters_spider import ReutersSpider


def _response(url, html):
    return HtmlResponse(url=url, body=html.encode("utf-8"))


@pytest.fixture
def spider():
    return ReutersSpider()


def test_spider_metadata(spider):
    assert spider.name == "reuters"
    assert spider.allowed_domains == ["reuters.com"]
    assert spider.start_urls == ["https://www.reuters.com/"]


def test_parse_extracts_article_links(spider):
    html = """
    <html><body>
        <a href="/article/foo-idUSKBN">Rel article</a>
        <a href="https://www.reuters.com/article/bar-idUSXYZ">Abs article</a>
        <a href="/markets/other/">Not an article</a>
    </body></html>
    """
    response = _response("https://www.reuters.com/", html)

    requests = list(spider.parse(response))
    urls = [r.url for r in requests]

    assert len(requests) == 2
    assert "https://www.reuters.com/article/foo-idUSKBN" in urls
    assert "https://www.reuters.com/article/bar-idUSXYZ" in urls
    for r in requests:
        assert "/article/" in r.url
        assert r.url.startswith("https://www.reuters.com/")
        assert r.callback == spider.parse_article


def test_parse_article_primary_selectors(spider):
    html = """
    <html><body>
        <h1 data-testid="Heading">Reuters Primary Title</h1>
        <div data-testid="paragraph">
            <p>Reuters paragraph one.</p>
            <p>Reuters paragraph two.</p>
        </div>
        <time datetime="2025-04-04T08:00:00Z">April 4</time>
        <div data-testid="BylineBar"><a>Reuters Author</a></div>
    </body></html>
    """
    response = _response("https://www.reuters.com/business/article/foo", html)

    items = list(spider.parse_article(response))
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, NewsItem)
    assert item["title"] == "Reuters Primary Title"
    assert item["url"] == "https://www.reuters.com/business/article/foo"
    assert item["source"] == "Reuters"
    assert item["content"] == "Reuters paragraph one. Reuters paragraph two."
    assert item["published_date"] == "2025-04-04T08:00:00Z"
    assert item["author"] == "Reuters Author"
    assert item["category"] == "Business"


def test_parse_article_fallbacks_and_default_author(spider):
    html = """
    <html><body>
        <h1>Fallback Reuters Title</h1>
        <article><p>Article fallback paragraph.</p></article>
    </body></html>
    """
    response = _response("https://www.reuters.com/misc/foo", html)

    item = list(spider.parse_article(response))[0]
    assert item["title"] == "Fallback Reuters Title"
    assert item["content"] == "Article fallback paragraph."
    # No byline element -> placeholder author.
    assert item["author"] == "Reuters Sta"
    # No datetime anywhere -> ISO ``now()`` fallback.
    assert isinstance(datetime.fromisoformat(item["published_date"]), datetime)
    # No URL segment and no breadcrumb -> "News" default.
    assert item["category"] == "News"


def test_parse_article_breadcrumb_category(spider):
    html = """
    <html><body>
        <h1 data-testid="Heading">Breadcrumb Title</h1>
        <div data-testid="paragraph"><p>content here</p></div>
        <nav aria-label="breadcrumb">
            <a>Home</a><a>Special Section</a><a>Article</a>
        </nav>
    </body></html>
    """
    response = _response("https://www.reuters.com/foo/bar", html)

    item = list(spider.parse_article(response))[0]
    # Uses the second-to-last breadcrumb entry when the URL has no known segment.
    assert item["category"] == "Special Section"


def test_parse_article_no_content_yields_nothing(spider):
    html = '<html><body><h1 data-testid="Heading">Title Only</h1></body></html>'
    response = _response("https://www.reuters.com/business/article/foo", html)
    assert list(spider.parse_article(response)) == []


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.reuters.com/business/x", "Business"),
        ("https://www.reuters.com/technology/x", "Technology"),
        ("https://www.reuters.com/world/x", "World"),
        ("https://www.reuters.com/markets/x", "Markets"),
        ("https://www.reuters.com/sports/x", "Sports"),
        ("https://www.reuters.com/politics/x", "Politics"),
    ],
)
def test_extract_category_from_url(spider, url, expected):
    response = _response(url, "<html><body></body></html>")
    assert spider._extract_category(url, response) == expected
