"""Tests for async methods of S3ArticleStorage in src/database/s3_storage.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from database.s3_storage import (  # noqa: E402
    ArticleType,
    S3ArticleStorage,
    S3StorageConfig,
)


@pytest.fixture(autouse=True)
def aws_creds(monkeypatch):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
              "AWS_SECURITY_TOKEN", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(k, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def storage():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        cfg = S3StorageConfig(bucket_name="test-bucket", enable_encryption=True)
        yield S3ArticleStorage(cfg)


def raw_article(**over):
    base = dict(title="Headline", content="Body content here", url="https://x.com/a",
                source="bbc", published_date="2026-01-15")
    base.update(over)
    return base


class TestStoreRaw:
    @pytest.mark.asyncio
    async def test_store_raw(self, storage):
        meta = await storage.store_raw_article(raw_article())
        assert meta.article_type == ArticleType.RAW
        assert meta.processing_status == "stored"
        assert meta.s3_key.endswith(".json")
        assert meta.file_size > 0

    @pytest.mark.asyncio
    async def test_store_raw_missing_fields(self, storage):
        with pytest.raises(ValueError, match="Missing required fields"):
            await storage.store_raw_article({"title": "only title"})

    @pytest.mark.asyncio
    async def test_store_raw_no_client(self, storage):
        storage.s3_client = None
        with pytest.raises(ValueError, match="S3 client not available"):
            await storage.store_raw_article(raw_article())


class TestStoreProcessed:
    @pytest.mark.asyncio
    async def test_store_processed(self, storage):
        meta = await storage.store_processed_article(raw_article(id="abc"))
        assert meta.article_type == ArticleType.PROCESSED
        assert meta.processing_status == "processed"


class TestRetrieveAndIntegrity:
    @pytest.mark.asyncio
    async def test_roundtrip(self, storage):
        meta = await storage.store_raw_article(raw_article())
        got = await storage.retrieve_article(meta.s3_key)
        assert got["url"] == "https://x.com/a"

    @pytest.mark.asyncio
    async def test_retrieve_missing(self, storage):
        with pytest.raises(ValueError, match="not found"):
            await storage.retrieve_article("raw_articles/nope.json")

    @pytest.mark.asyncio
    async def test_integrity_true(self, storage):
        meta = await storage.store_raw_article(raw_article())
        assert await storage.verify_article_integrity(meta.s3_key) is True

    @pytest.mark.asyncio
    async def test_integrity_missing_key_false(self, storage):
        assert await storage.verify_article_integrity("raw_articles/nope.json") is False


class TestListing:
    @pytest.mark.asyncio
    async def test_list_by_prefix(self, storage):
        await storage.store_raw_article(raw_article())
        keys = await storage.list_articles_by_prefix(ArticleType.RAW.value)
        assert len(keys) == 1

    @pytest.mark.asyncio
    async def test_list_by_prefix_limit(self, storage):
        for i in range(3):
            await storage.store_raw_article(raw_article(url=f"https://x.com/{i}",
                                                        content=f"body {i}"))
        keys = await storage.list_articles_by_prefix(ArticleType.RAW.value, limit=2)
        assert len(keys) == 2

    @pytest.mark.asyncio
    async def test_list_by_date(self, storage):
        await storage.store_raw_article(raw_article())
        # scraped_date drives the key; just assert it returns a list without error
        keys = await storage.list_articles_by_date(
            "2026-01-15", ArticleType.RAW
        )
        assert isinstance(keys, list)

    @pytest.mark.asyncio
    async def test_list_by_date_bad_format(self, storage):
        assert await storage.list_articles_by_date("badformat", ArticleType.RAW) == []


class TestBatch:
    @pytest.mark.asyncio
    async def test_batch_store(self, storage):
        articles = [raw_article(url=f"https://x.com/{i}", content=f"b{i}") for i in range(3)]
        results = await storage.batch_store_raw_articles(articles)
        assert len(results) == 3
        assert all(r.processing_status == "stored" for r in results)

    @pytest.mark.asyncio
    async def test_batch_with_errors(self, storage):
        articles = [raw_article(), {"title": "bad"}]  # second is invalid
        results = await storage.batch_store_raw_articles(articles)
        assert len(results) == 2
        assert any(r.processing_status == "error" for r in results)


class TestStatsAndCleanup:
    @pytest.mark.asyncio
    async def test_statistics(self, storage):
        await storage.store_raw_article(raw_article())
        await storage.store_processed_article(raw_article(id="p1"))
        stats = await storage.get_storage_statistics()
        assert stats["raw_articles"]["count"] == 1
        assert stats["processed_articles"]["count"] == 1
        assert stats["total_count"] == 2

    @pytest.mark.asyncio
    async def test_cleanup_keeps_recent(self, storage):
        await storage.store_raw_article(raw_article())
        # Recent article -> not deleted with a large retention window
        assert await storage.cleanup_old_articles(days=365) == 0

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old(self, storage):
        await storage.store_raw_article(raw_article())
        # negative retention -> cutoff in the future -> everything is "old"
        assert await storage.cleanup_old_articles(days=-1) == 1


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete(self, storage):
        meta = await storage.store_raw_article(raw_article())
        storage.delete_article(meta.s3_key)
        with pytest.raises(ValueError):
            await storage.retrieve_article(meta.s3_key)
