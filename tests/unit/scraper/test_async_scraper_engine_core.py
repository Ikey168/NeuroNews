"""Tests for pure logic of src/scraper/async_scraper_engine.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiohttp")
pytest.importorskip("bs4")

from scraper.async_scraper_engine import (  # noqa: E402
    Article,
    AsyncNewsScraperEngine,
    NewsSource,
    PerformanceMonitor,
)


def article(**over):
    base = dict(
        title="A reasonably long headline here", url="https://x.com/a",
        content="word " * 50, author="Alice", published_date="2026-01-01",
        source="x", scraped_date="2026-01-02", content_length=250,
    )
    base.update(over)
    return Article(**base)


@pytest.fixture
def engine():
    return AsyncNewsScraperEngine(enable_monitoring=False)


class TestPerformanceMonitor:
    def test_record_and_stats(self):
        mon = PerformanceMonitor()
        try:
            mon.record_article("bbc")
            mon.record_success(0.5)
            mon.record_error("cnn")
            stats = mon.get_stats()
            assert stats["total_articles"] == 1
            assert stats["successful_requests"] == 1
            assert stats["failed_requests"] == 1
            assert 0 <= stats["success_rate"] <= 100
            assert stats["source_stats"]["bbc"]["articles"] == 1
            assert stats["source_stats"]["cnn"]["errors"] == 1
        finally:
            mon.stop()


class TestDataclasses:
    def test_article_defaults(self):
        a = article()
        assert a.language == "en"
        assert a.content_quality == "unknown"

    def test_news_source(self):
        s = NewsSource(name="BBC", base_url="https://bbc.com",
                       article_selectors={}, link_patterns=["/news/"])
        assert s.requires_js is False
        assert s.rate_limit == 1.0


class TestCategoryExtraction:
    @pytest.mark.parametrize("url,cat", [
        ("https://x.com/technology/ai", "Technology"),
        ("https://x.com/politics/election", "Politics"),
        ("https://x.com/business/market", "Business"),
        ("https://x.com/sports/football", "Sports"),
        ("https://x.com/health/covid", "Health"),
        ("https://x.com/science/study", "Science"),
        ("https://x.com/random/page", "News"),
    ])
    def test_category(self, engine, url, cat):
        assert engine.extract_category_from_url(url) == cat


class TestValidateArticle:
    def test_valid(self, engine):
        assert engine.validate_article(article()) == 100

    def test_missing_title(self, engine):
        assert engine.validate_article(article(title="")) == 65  # -25 -10 (len<10)

    def test_missing_content(self, engine):
        assert engine.validate_article(article(content="", content_length=0)) == 50  # -30 -20

    def test_missing_author(self, engine):
        assert engine.validate_article(article(author="")) == 90

    def test_short_content(self, engine):
        assert engine.validate_article(article(content_length=50)) == 80

    def test_score_floor(self, engine):
        score = engine.validate_article(
            Article(title="", url="", content="", author="", published_date="",
                    source="", scraped_date="", content_length=0)
        )
        assert score >= 0


class TestQualityLabel:
    @pytest.mark.parametrize("score,label", [(90, "high"), (70, "medium"), (40, "low")])
    def test_labels(self, engine, score, label):
        assert engine.get_quality_label(score) == label


class TestHtmlExtraction:
    def test_extract_text_by_selector(self, engine):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div><h1 class='t'>Hello</h1></div>", "html.parser")
        assert engine.extract_text_by_selector(soup, "h1.t") == "Hello"

    def test_extract_text_missing(self, engine):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div></div>", "html.parser")
        assert engine.extract_text_by_selector(soup, "h1.missing") == ""


class TestSaveArticles:
    @pytest.mark.asyncio
    async def test_save_articles(self, engine, tmp_path):
        import json
        out = tmp_path / "articles.json"
        await engine.save_articles([article()], str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert len(data) == 1
