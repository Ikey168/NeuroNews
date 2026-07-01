"""
Line-coverage tests for :mod:`src.scraper.spiders.theverge_spider`.

Builds real ``HtmlResponse`` objects and asserts the parsed article fields plus
link extraction, in the style of ``tests/unit/scraper/test_bbc_spider.py``.

NOTE (genuine source bug): the landing-page selector

    'a[href*="/2024/"], a[href*="/2025/"]::attr(href)'

only applies ``::attr(href)`` to the *second* group.  ``a[href*="/2024/"]``
(without ``::attr``) therefore serialises the whole ``<a>`` element instead of
its href, and the resulting raw-HTML "URL" makes ``scrapy.Request`` raise
``ValueError: Missing scheme in request url``.  The tests below exercise the
working ``/2025/`` path and document the broken ``/2024/`` behaviour explicitly.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("scrapy")

from scrapy.http import HtmlResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from scraper.items import NewsItem
from scraper.spiders.theverge_spider import VergeSpider


def _response(url, html):
    return HtmlResponse(url=url, body=html.encode("utf-8"))


@pytest.fixture
def spider():
    return VergeSpider()


def test_spider_metadata(spider):
    assert spider.name == "theverge"
    assert spider.allowed_domains == ["theverge.com"]
    assert spider.start_urls == ["https://www.theverge.com/"]


def test_parse_extracts_2025_links(spider):
    html = """
    <html><body>
        <a href="/2025/2/2/456/bar">Rel 2025</a>
        <a href="https://www.theverge.com/2025/3/3/789/baz">Abs 2025</a>
        <a href="/tech/no-date/">No date link</a>
    </body></html>
    """
    response = _response("https://www.theverge.com/", html)

    requests = list(spider.parse(response))
    urls = [r.url for r in requests]

    assert len(requests) == 2
    assert "https://www.theverge.com/2025/2/2/456/bar" in urls
    assert "https://www.theverge.com/2025/3/3/789/baz" in urls
    for r in requests:
        assert r.url.startswith("https://www.theverge.com/2025/")
        assert r.callback == spider.parse_article


def test_parse_2024_selector_is_broken(spider):
    """Confirm the documented source bug for ``/2024/`` links.

    The first selector lacks ``::attr(href)`` so ``getall()`` returns the raw
    ``<a ...>`` element markup, which is not a valid URL.  ``scrapy.Request``
    rejects it with ``ValueError``.  This asserts the real (buggy) behaviour so
    the failure is captured rather than skipped.
    """
    html = '<html><body><a href="/2024/1/1/1/x">Only 2024</a></body></html>'
    response = _response("https://www.theverge.com/", html)

    raw = response.css(
        'a[href*="/2024/"], a[href*="/2025/"]::attr(href)'
    ).getall()
    # The 2024 match is the serialised element, not its href.
    assert raw == ['<a href="/2024/1/1/1/x">Only 2024</a>']

    with pytest.raises(ValueError):
        list(spider.parse(response))


def test_parse_article_primary_selectors(spider):
    html = """
    <html><body>
        <h1 class="c-page-title">Verge Primary Title</h1>
        <div class="c-entry-content">
            <p>Verge paragraph one.</p>
            <p>Verge paragraph two.</p>
        </div>
        <time datetime="2025-03-03T09:00:00Z">March 3</time>
        <span class="c-byline__author-name">John Verge</span>
    </body></html>
    """
    response = _response("https://www.theverge.com/tech/2025/foo", html)

    items = list(spider.parse_article(response))
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, NewsItem)
    assert item["title"] == "Verge Primary Title"
    assert item["url"] == "https://www.theverge.com/tech/2025/foo"
    assert item["source"] == "The Verge"
    assert item["content"] == "Verge paragraph one. Verge paragraph two."
    assert item["published_date"] == "2025-03-03T09:00:00Z"
    assert item["author"] == "John Verge"
    assert item["category"] == "Technology"


def test_parse_article_fallbacks_and_label_category(spider):
    html = """
    <html><body>
        <h1>Fallback Verge Title</h1>
        <article><p>Article fallback paragraph.</p></article>
        <span class="c-entry-group-labels__item">Reviews</span>
    </body></html>
    """
    response = _response("https://www.theverge.com/misc/foo", html)

    item = list(spider.parse_article(response))[0]
    assert item["title"] == "Fallback Verge Title"
    assert item["content"] == "Article fallback paragraph."
    # No byline element -> placeholder author.
    assert item["author"] == "The Verge Sta"
    # No datetime -> ISO ``now()`` fallback.
    assert isinstance(datetime.fromisoformat(item["published_date"]), datetime)
    # Category label element used because URL has no known segment.
    assert item["category"] == "Reviews"


def test_parse_article_default_category(spider):
    html = """
    <html><body>
        <h1>No Cat Verge</h1>
        <div class="c-entry-content"><p>content</p></div>
    </body></html>
    """
    response = _response("https://www.theverge.com/misc/foo", html)
    item = list(spider.parse_article(response))[0]
    assert item["category"] == "Technology"


def test_parse_article_no_content_yields_nothing(spider):
    html = '<html><body><h1 class="c-page-title">Title Only</h1></body></html>'
    response = _response("https://www.theverge.com/tech/2025/foo", html)
    assert list(spider.parse_article(response)) == []


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.theverge.com/tech/x", "Technology"),
        ("https://www.theverge.com/gaming/x", "Gaming"),
        ("https://www.theverge.com/science/x", "Science"),
        ("https://www.theverge.com/mobile/x", "Mobile"),
        ("https://www.theverge.com/apps/x", "Apps"),
        ("https://www.theverge.com/cars/x", "Transportation"),
        ("https://www.theverge.com/policy/x", "Policy"),
    ],
)
def test_extract_category_from_url(spider, url, expected):
    response = _response(url, "<html><body></body></html>")
    assert spider._extract_category(url, response) == expected
