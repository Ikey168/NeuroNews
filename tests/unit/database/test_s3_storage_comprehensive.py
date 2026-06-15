"""Comprehensive tests for src/database/s3_storage.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from database.s3_storage import (  # noqa: E402
    ArticleMetadata,
    ArticleType,
    S3ArticleStorage,
    S3Storage,
    S3StorageConfig,
)

BUCKET = "neuronews-test-bucket"


def article(**over):
    base = {
        "title": "Major Tech News Today",
        "content": "This is the article body content with several words.",
        "url": "https://example.com/news/1",
        "source": "example.com",
        "published_date": "2026-01-15",
    }
    base.update(over)
    return base


@pytest.fixture
def storage():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield S3ArticleStorage(S3StorageConfig(bucket_name=BUCKET, region="us-east-1"))


class TestDataclasses:
    def test_article_type(self):
        assert ArticleType.RAW.value == "raw_articles"
        assert ArticleType.PROCESSED.value == "processed_articles"

    def test_config_defaults(self):
        cfg = S3StorageConfig(bucket_name="b")
        assert cfg.region == "us-east-1"
        assert cfg.enable_versioning is True
        assert cfg.lifecycle_days == 365

    def test_article_metadata(self):
        m = ArticleMetadata(
            article_id="a", source="s", url="u", title="t",
            published_date="2026-01-01", scraped_date="2026-01-02",
            content_hash="h", file_size=10, s3_key="k", article_type=ArticleType.RAW,
        )
        assert m.processing_status == "pending"
        assert m.error_message is None


class TestKeyGeneration:
    def test_article_id_stable(self, storage):
        a = article()
        assert storage._generate_article_id(a) == storage._generate_article_id(a)

    def test_content_hash(self, storage):
        h = storage._calculate_content_hash("hello")
        assert len(h) == 64  # sha256 hex

    def test_s3_key_structure(self, storage):
        key = storage._generate_s3_key(article(), ArticleType.RAW)
        assert key.startswith("raw_articles/2026/01/15/")
        assert key.endswith(".json")

    def test_s3_key_date_override(self, storage):
        key = storage._generate_s3_key(article(), ArticleType.PROCESSED, date_override="2025-06-30")
        assert key.startswith("processed_articles/2025/06/30/")

    def test_s3_key_explicit_id(self, storage):
        key = storage._generate_s3_key(article(id="custom-id"), ArticleType.RAW)
        assert key.endswith("custom-id.json")

    def test_s3_key_invalid_date_fallback(self, storage):
        key = storage._generate_s3_key(article(published_date="bad"), ArticleType.RAW)
        assert key.startswith("raw_articles/")
        assert key.endswith(".json")

    def test_s3_key_no_date_uses_now(self, storage):
        a = article()
        del a["published_date"]
        key = storage._generate_s3_key(a, ArticleType.RAW)
        assert key.startswith("raw_articles/")


class TestBucketInit:
    def test_missing_bucket_raises(self):
        with mock_aws():
            # bucket NOT created -> head_bucket 404 -> ValueError
            with pytest.raises(ValueError):
                S3ArticleStorage(S3StorageConfig(bucket_name="does-not-exist"))


class TestStoreRetrieve:
    @pytest.mark.asyncio
    async def test_store_raw_article(self, storage):
        meta = await storage.store_raw_article(article())
        assert isinstance(meta, ArticleMetadata)
        assert meta.article_type == ArticleType.RAW
        assert meta.s3_key.startswith("raw_articles/")
        assert meta.file_size > 0

    @pytest.mark.asyncio
    async def test_store_raw_missing_fields(self, storage):
        with pytest.raises(ValueError):
            await storage.store_raw_article({"title": "only title"})

    @pytest.mark.asyncio
    async def test_store_no_client_raises(self, storage):
        storage.s3_client = None
        with pytest.raises(ValueError):
            await storage.store_raw_article(article())

    @pytest.mark.asyncio
    async def test_store_processed_article(self, storage):
        meta = await storage.store_processed_article(article(nlp_sentiment="positive"))
        assert meta.article_type == ArticleType.PROCESSED
        assert meta.s3_key.startswith("processed_articles/")

    @pytest.mark.asyncio
    async def test_store_then_retrieve(self, storage):
        meta = await storage.store_raw_article(article())
        retrieved = await storage.retrieve_article(meta.s3_key)
        assert retrieved["title"] == "Major Tech News Today"

    @pytest.mark.asyncio
    async def test_verify_integrity(self, storage):
        meta = await storage.store_raw_article(article())
        assert await storage.verify_article_integrity(meta.s3_key) is True

    @pytest.mark.asyncio
    async def test_batch_store(self, storage):
        arts = [article(url=f"https://example.com/{i}", title=f"Article {i} News") for i in range(3)]
        result = await storage.batch_store_raw_articles(arts)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_by_prefix(self, storage):
        await storage.store_raw_article(article())
        keys = await storage.list_articles_by_prefix("raw_articles/")
        assert len(keys) >= 1

    @pytest.mark.asyncio
    async def test_list_by_date(self, storage):
        await storage.store_raw_article(article())
        keys = await storage.list_articles_by_date("2026-01-15", ArticleType.RAW)
        assert isinstance(keys, list)

    @pytest.mark.asyncio
    async def test_statistics(self, storage):
        await storage.store_raw_article(article())
        stats = await storage.get_storage_statistics()
        assert stats["total_count"] >= 1

    @pytest.mark.asyncio
    async def test_delete_article(self, storage):
        meta = await storage.store_raw_article(article())
        storage.delete_article(meta.s3_key)
        assert await storage.verify_article_integrity(meta.s3_key) is False


class TestS3StorageSubclass:
    @pytest.fixture
    def s3(self):
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
            yield S3Storage(bucket_name=BUCKET, aws_region="us-east-1")

    def test_upload_and_get(self, s3):
        key = s3.upload_article(article())
        assert key
        got = s3.get_article(key)
        assert got["title"] == "Major Tech News Today"

    def test_list_articles(self, s3):
        s3.upload_article(article())
        listed = s3.list_articles()
        assert isinstance(listed, list)

    def test_upload_download_file(self, s3, tmp_path):
        local = tmp_path / "f.txt"
        local.write_text("hello file")
        s3.upload_file(str(local), "files/f.txt")
        out = tmp_path / "out.txt"
        s3.download_file("files/f.txt", str(out))
        assert out.read_text() == "hello file"

    def test_delete(self, s3):
        key = s3.upload_article(article())
        s3.delete_article(key)
