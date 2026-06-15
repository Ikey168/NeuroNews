"""Async (moto-backed) tests for DynamoDBMetadataManager query/CRUD methods."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from database.dynamodb_metadata_manager import (  # noqa: E402
    DynamoDBMetadataConfig,
    DynamoDBMetadataManager,
    SearchQuery,
)


@pytest.fixture(autouse=True)
def aws_creds(monkeypatch):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
              "AWS_SECURITY_TOKEN", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(k, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def manager():
    with mock_aws():
        cfg = DynamoDBMetadataConfig(
            table_name="test-article-metadata",
            region="us-east-1",
            enable_point_in_time_recovery=False,  # not supported by moto
        )
        yield DynamoDBMetadataManager(cfg)


def article(**over):
    base = dict(
        id="art-1",
        url="https://bbc.com/news/1",
        title="Breaking technology news today",
        content_hash="hash1",
        source="bbc",
        published_date="2026-01-15",
        category="Technology",
        tags=["ai", "tech"],
        author="Alice",
    )
    base.update(over)
    return base


class TestIndexing:
    @pytest.mark.asyncio
    async def test_index_single(self, manager):
        meta = await manager.index_article_metadata(article())
        assert meta.article_id == "art-1"
        fetched = await manager.get_article_by_id("art-1")
        assert fetched is not None
        assert fetched.title == "Breaking technology news today"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, manager):
        assert await manager.get_article_by_id("nope") is None

    @pytest.mark.asyncio
    async def test_batch_index(self, manager):
        articles = [article(id=f"a{i}", url=f"https://x/{i}", content_hash=f"h{i}")
                    for i in range(5)]
        result = await manager.batch_index_articles(articles)
        assert result["indexed_count"] == 5
        assert result["failed_count"] == 0
        assert result["total_articles"] == 5


class TestQueries:
    @pytest.mark.asyncio
    async def test_by_source(self, manager):
        await manager.index_article_metadata(article(id="a1", source="bbc"))
        await manager.index_article_metadata(
            article(id="a2", source="cnn", content_hash="h2", url="https://cnn/2")
        )
        result = await manager.get_articles_by_source("bbc")
        assert result.count == 1
        assert result.items[0].source == "bbc"

    @pytest.mark.asyncio
    async def test_by_source_with_date_filter(self, manager):
        await manager.index_article_metadata(article(id="a1", published_date="2026-01-15"))
        result = await manager.get_articles_by_source(
            "bbc", start_date="2026-01-01", end_date="2026-01-31"
        )
        assert result.count == 1

    @pytest.mark.asyncio
    async def test_by_date_range(self, manager):
        await manager.index_article_metadata(article(id="a1", published_date="2026-01-15"))
        await manager.index_article_metadata(
            article(id="a2", published_date="2026-06-15", content_hash="h2",
                    url="https://x/2")
        )
        result = await manager.get_articles_by_date_range("2026-01-01", "2026-02-01")
        assert result.count == 1

    @pytest.mark.asyncio
    async def test_by_tags_any(self, manager):
        await manager.index_article_metadata(article(id="a1", tags=["ai"]))
        await manager.index_article_metadata(
            article(id="a2", tags=["sports"], content_hash="h2", url="https://x/2")
        )
        result = await manager.get_articles_by_tags(["ai"], match_all=False)
        assert result.count == 1

    @pytest.mark.asyncio
    async def test_by_tags_all(self, manager):
        await manager.index_article_metadata(article(id="a1", tags=["ai", "tech"]))
        result = await manager.get_articles_by_tags(["ai", "tech"], match_all=True)
        assert result.count == 1
        result2 = await manager.get_articles_by_tags(["ai", "missing"], match_all=True)
        assert result2.count == 0

    @pytest.mark.asyncio
    async def test_by_category(self, manager):
        await manager.index_article_metadata(article(id="a1", category="Technology"))
        result = await manager.get_articles_by_category("Technology")
        assert result.count == 1

    @pytest.mark.asyncio
    async def test_search_articles(self, manager):
        await manager.index_article_metadata(article(id="a1", title="technology breakthrough"))
        result = await manager.search_articles(SearchQuery(query_text="technology"))
        assert result.count >= 1

    @pytest.mark.asyncio
    async def test_search_empty_query(self, manager):
        result = await manager.search_articles(SearchQuery(query_text="   "))
        assert result.count == 0


class TestStatsAndCrud:
    @pytest.mark.asyncio
    async def test_statistics(self, manager):
        await manager.index_article_metadata(article(id="a1", source="bbc", category="Technology"))
        await manager.index_article_metadata(
            article(id="a2", source="bbc", category="Sports", content_hash="h2",
                    url="https://x/2")
        )
        stats = await manager.get_metadata_statistics()
        assert stats["total_articles"] == 2
        assert stats["source_distribution"]["bbc"] == 2

    @pytest.mark.asyncio
    async def test_update(self, manager):
        await manager.index_article_metadata(article(id="a1", category="Technology"))
        ok = await manager.update_article_metadata("a1", {"category": "Science"})
        assert ok is True
        updated = await manager.get_article_by_id("a1")
        assert updated.category == "Science"

    @pytest.mark.asyncio
    async def test_delete(self, manager):
        await manager.index_article_metadata(article(id="a1"))
        ok = await manager.delete_article_metadata("a1")
        assert ok is True
        assert await manager.get_article_by_id("a1") is None

    @pytest.mark.asyncio
    async def test_health_check(self, manager):
        health = await manager.health_check()
        assert health["status"] == "healthy"
        assert health["table_name"] == "test-article-metadata"
