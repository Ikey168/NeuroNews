"""Comprehensive tests for src/database/dynamodb_metadata_manager.py."""

import sys
import os

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from database.dynamodb_metadata_manager import (  # noqa: E402
    ArticleMetadataIndex,
    DynamoDBMetadataConfig,
    DynamoDBMetadataManager,
    IndexType,
    QueryResult,
    SearchMode,
    SearchQuery,
)


def sample_index(**over):
    base = dict(
        article_id="a1",
        content_hash="h1",
        title="Breaking Technology News Today",
        source="reuters",
        published_date="2026-01-15",
        tags=["tech", "ai"],
        category="technology",
    )
    base.update(over)
    return ArticleMetadataIndex(**base)


class TestEnums:
    def test_index_type_values(self):
        assert IndexType.SOURCE_DATE.value == "source-date-index"
        assert IndexType.FULLTEXT.value == "fulltext-index"

    def test_search_mode_values(self):
        assert SearchMode.EXACT.value == "exact"
        assert SearchMode.FUZZY.value == "fuzzy"


class TestArticleMetadataIndex:
    def test_post_init_sets_dates_and_tokens(self):
        idx = sample_index()
        assert idx.indexed_date  # auto-populated
        assert idx.last_updated == idx.indexed_date
        # title tokens generated, lowercased, deduped, >2 chars
        assert "breaking" in idx.title_tokens
        assert "technology" in idx.title_tokens
        assert all(len(t) > 2 for t in idx.title_tokens)

    def test_explicit_dates_preserved(self):
        idx = sample_index(indexed_date="2020-01-01T00:00:00", last_updated="2020-02-02")
        assert idx.indexed_date == "2020-01-01T00:00:00"
        assert idx.last_updated == "2020-02-02"

    def test_tokenize_strips_punctuation(self):
        idx = sample_index()
        tokens = idx._tokenize_text("Hello, World! AI-driven.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "ai" not in tokens  # 2 chars, filtered

    def test_to_dynamodb_item_computed_fields(self):
        idx = sample_index()
        item = idx.to_dynamodb_item()
        assert item["source_date"] == "reuters#2026-01-15"
        assert item["date_source"] == "2026-01-15#reuters"
        assert item["category_date"] == "technology#2026-01-15"
        assert item["year_month"] == "2026-01"
        assert item["tags_string"] == "ai#tech"  # sorted

    def test_to_dynamodb_item_empty_tags_and_short_date(self):
        idx = sample_index(tags=[], published_date="20")
        item = idx.to_dynamodb_item()
        assert item["tags_string"] == ""
        assert item["year_month"] == ""

    def test_roundtrip_from_dynamodb_item(self):
        item = sample_index().to_dynamodb_item()
        restored = ArticleMetadataIndex.from_dynamodb_item(item)
        assert restored.article_id == "a1"
        assert restored.source == "reuters"
        assert restored.tags == ["tech", "ai"]

    def test_from_dynamodb_item_defaults(self):
        restored = ArticleMetadataIndex.from_dynamodb_item({})
        assert restored.article_id == ""
        assert restored.language == "en"
        assert restored.processing_status == "indexed"


class TestDataclasses:
    def test_config_defaults(self):
        cfg = DynamoDBMetadataConfig()
        assert cfg.table_name == "neuronews-article-metadata"
        assert cfg.region == "us-east-1"

    def test_search_query_defaults(self):
        q = SearchQuery(query_text="ai")
        assert q.fields == ["title", "content_summary"]
        assert q.search_mode == SearchMode.CONTAINS
        assert q.limit == 50

    def test_query_result(self):
        r = QueryResult(items=[sample_index()], count=1)
        assert r.count == 1
        assert r.total_count is None


@pytest.fixture
def manager():
    """A manager backed by a real moto-mocked DynamoDB table."""
    with mock_aws():
        mgr = DynamoDBMetadataManager(
            DynamoDBMetadataConfig(table_name="test-meta", region="us-east-1")
        )
        yield mgr


class TestManagerLogic:
    """Pure-logic methods that need no live AWS calls."""

    def test_create_metadata_generates_ids(self, manager):
        meta = manager._create_metadata_from_article(
            {"title": "T", "url": "http://x", "content": "body text"}
        )
        assert meta.article_id  # md5 of url+title
        assert meta.content_hash  # sha256 of content
        assert meta.title == "T"

    def test_create_metadata_uses_provided_id(self, manager):
        meta = manager._create_metadata_from_article(
            {"id": "explicit", "title": "T", "content_hash": "given"}
        )
        assert meta.article_id == "explicit"
        assert meta.content_hash == "given"

    def test_create_metadata_tags_from_category(self, manager):
        meta = manager._create_metadata_from_article(
            {"title": "T", "category": "sports"}
        )
        assert meta.tags == ["sports"]

    def test_create_metadata_scalar_tag_wrapped(self, manager):
        meta = manager._create_metadata_from_article({"title": "T", "tags": "single"})
        assert meta.tags == ["single"]

    def test_tokenize_search_query_removes_stopwords(self, manager):
        tokens = manager._tokenize_search_query("the AI and the future of Tech")
        assert "the" not in tokens
        assert "and" not in tokens
        assert "ai" in tokens
        assert "future" in tokens

    def test_relevance_score_weights_title_higher(self, manager):
        item = sample_index(title="quantum computing", content_summary="quantum")
        title_score = manager._calculate_relevance_score(
            item, ["quantum"], ["title"]
        )
        summary_score = manager._calculate_relevance_score(
            item, ["quantum"], ["content_summary"]
        )
        assert title_score > summary_score

    def test_relevance_score_list_field(self, manager):
        item = sample_index(tags=["ai", "ml"])
        score = manager._calculate_relevance_score(item, ["ai"], ["tags"])
        assert score > 0

    def test_score_and_sort_orders_by_relevance(self, manager):
        a = sample_index(article_id="a", title="machine learning deep")
        b = sample_index(article_id="b", title="cooking recipes")
        q = SearchQuery(query_text="machine", fields=["title"])
        ordered = manager._score_and_sort_results([b, a], ["machine"], q)
        assert ordered[0].article_id == "a"

    def test_build_search_filter_none_for_empty(self, manager):
        q = SearchQuery(query_text="")
        assert manager._build_search_filter([], q) is None

    def test_build_search_filter_contains(self, manager):
        q = SearchQuery(query_text="ai", fields=["title"], search_mode=SearchMode.CONTAINS)
        assert manager._build_search_filter(["ai"], q) is not None

    def test_build_additional_filters_scalar_and_list(self, manager):
        assert manager._build_additional_filters({"source": "bbc"}) is not None
        assert manager._build_additional_filters({"source": ["bbc", "cnn"]}) is not None

    def test_build_date_range_filter(self, manager):
        assert manager._build_date_range_filter({"start": "2026-01-01"}) is not None
        assert manager._build_date_range_filter(
            {"start": "2026-01-01", "end": "2026-02-01"}
        ) is not None
        assert manager._build_date_range_filter({}) is None


class TestManagerAWSFlows:
    """End-to-end flows against the moto-mocked table."""

    @pytest.mark.asyncio
    async def test_index_and_get(self, manager):
        result = await manager.index_article_metadata(
            {"id": "x1", "title": "Hello World News", "source": "reuters",
             "published_date": "2026-01-10", "category": "tech", "content": "the body"}
        )
        assert result.article_id == "x1"
        got = await manager.get_article_by_id("x1")
        assert got is not None
        assert got.article_id == "x1"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, manager):
        assert await manager.get_article_by_id("nope") is None

    @pytest.mark.asyncio
    async def test_batch_index(self, manager):
        articles = [
            {"id": f"b{i}", "title": f"Article {i} headline", "source": "src",
             "published_date": "2026-01-1{0}".format(i), "category": "news", "content": f"body {i}"}
            for i in range(3)
        ]
        result = await manager.batch_index_articles(articles)
        assert result["indexed_count"] == 3

    @pytest.mark.asyncio
    async def test_delete(self, manager):
        await manager.index_article_metadata(
            {"id": "d1", "title": "To Delete Soon", "source": "s",
             "published_date": "2026-01-10", "category": "tech"}
        )
        assert await manager.delete_article_metadata("d1") is True
        assert await manager.get_article_by_id("d1") is None

    @pytest.mark.asyncio
    async def test_get_by_source(self, manager):
        await manager.index_article_metadata(
            {"id": "s1", "title": "Source One News", "source": "reuters",
             "published_date": "2026-01-10", "category": "tech"}
        )
        res = await manager.get_articles_by_source("reuters")
        assert isinstance(res, QueryResult)
        assert res.count >= 1

    @pytest.mark.asyncio
    async def test_statistics(self, manager):
        await manager.index_article_metadata(
            {"id": "st1", "title": "Stats Article Here", "source": "reuters",
             "published_date": "2026-01-10", "category": "tech"}
        )
        stats = await manager.get_metadata_statistics()
        assert stats["total_articles"] >= 1

    @pytest.mark.asyncio
    async def test_health_check(self, manager):
        health = await manager.health_check()
        assert health["status"] in ("healthy", "unhealthy")
