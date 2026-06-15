"""Tests for src/scraper/async_pipelines.py (AsyncPipelineProcessor)."""

import json
import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiofiles")

from scraper.async_pipelines import AsyncPipelineProcessor  # noqa: E402


def good_article(**over):
    base = dict(
        title="A clearly valid news headline",
        url="https://bbc.com/news/tech/ai-story",
        content="The technology and software industry " * 30,
        source="bbc",
    )
    base.update(over)
    return base


@pytest.fixture
def proc(monkeypatch):
    # Ensure no S3 client is created
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    p = AsyncPipelineProcessor(max_threads=2)
    yield p
    p.close()


class TestValidateSync:
    def test_valid_article(self, proc):
        a = good_article()
        assert proc.validate_article_sync(a) is True
        assert a["validation_score"] >= 50
        assert a["content_quality"] in ("high", "medium", "low")
        assert a["word_count"] > 0
        assert a["reading_time"] >= 1

    def test_missing_fields(self, proc):
        a = {"title": "", "url": "", "content": "", "source": ""}
        assert proc.validate_article_sync(a) is False
        assert a["validation_score"] == 0

    def test_spam_penalty(self, proc):
        clean = good_article()
        proc.validate_article_sync(clean)
        spam = good_article(title="Click here buy now act fast limited time")
        proc.validate_article_sync(spam)
        assert spam["validation_score"] < clean["validation_score"]


class TestDuplicateSync:
    def test_adds_hashes(self, proc):
        a = good_article()
        assert proc.check_duplicate_sync(a) is False
        assert "url_hash" in a and "content_hash" in a
        assert a["duplicate_check"] == "unique"


class TestEnhance:
    def test_enhance_adds_metadata(self, proc):
        a = good_article()
        out = proc.enhance_article_sync(a)
        assert "category" in out
        assert isinstance(out["keywords"], list)
        assert out["sentiment"] in ("positive", "negative", "neutral")
        assert "processed_date" in out
        assert set(out["entities"]) == {"people", "organizations", "locations", "dates"}


class TestCategory:
    @pytest.mark.parametrize("url,expected", [
        ("https://x.com/technology/a", "Technology"),
        ("https://x.com/politics/b", "Politics"),
        ("https://x.com/sports/c", "Sports"),
    ])
    def test_url_category(self, proc, url, expected):
        assert proc.extract_category({"url": url}) == expected

    def test_content_fallback(self, proc):
        cat = proc.extract_category(
            {"url": "https://x.com/x", "title": "", "content": "research study scientist discovery"}
        )
        assert cat == "Science"

    def test_default_news(self, proc):
        assert proc.extract_category({"url": "https://x.com/x", "content": "zzz"}) == "News"


class TestKeywordsSentimentEntities:
    def test_keywords(self, proc):
        kws = proc.extract_keywords("python python python testing testing code", max_keywords=2)
        assert kws[0] == "python"
        assert len(kws) <= 2

    def test_sentiment_positive(self, proc):
        assert proc.analyze_sentiment("great excellent wonderful success") == "positive"

    def test_sentiment_negative(self, proc):
        assert proc.analyze_sentiment("terrible awful failure crisis") == "negative"

    def test_sentiment_neutral(self, proc):
        assert proc.analyze_sentiment("the cat sat on the mat") == "neutral"

    def test_entities(self, proc):
        ents = proc.extract_entities(
            "John Smith met with Acme Corp on January 5, 2026 in town."
        )
        assert any("John Smith" in p for p in ents["people"])
        assert ents["organizations"]
        assert ents["dates"]


class TestStats:
    def test_distributions(self, proc):
        proc.processed_articles = [
            {"content_quality": "high", "category": "Tech"},
            {"content_quality": "low", "category": "Tech"},
        ]
        qd = proc.get_quality_distribution()
        assert qd["high"] == 1 and qd["low"] == 1
        cd = proc.get_category_distribution()
        assert cd["Tech"] == 2
        stats = proc.get_processing_stats()
        assert stats["total_processed"] == 2
        assert "validation_stats" in stats


class TestAsyncFlow:
    @pytest.mark.asyncio
    async def test_process_articles_async(self, proc):
        articles = [good_article(url=f"https://bbc.com/news/{i}") for i in range(3)]
        result = await proc.process_articles_async(articles)
        assert len(result) == 3
        assert proc.validation_stats["passed"] == 3

    @pytest.mark.asyncio
    async def test_process_filters_invalid(self, proc):
        articles = [good_article(), {"title": "", "url": "", "content": "", "source": ""}]
        result = await proc.process_articles_async(articles)
        assert len(result) == 1
        assert proc.validation_stats["failed"] == 1

    @pytest.mark.asyncio
    async def test_save_processed_articles(self, proc, tmp_path):
        out = tmp_path / "out.json"
        await proc.save_processed_articles([good_article()], str(out))
        assert json.loads(out.read_text())

    @pytest.mark.asyncio
    async def test_upload_no_s3_client(self, proc):
        assert await proc.upload_to_s3_async([good_article()], "bucket", "key") is False
