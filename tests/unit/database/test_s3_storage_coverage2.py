"""Coverage tests for src/database/s3_storage.py.

Uses moto's mock_aws() so the boto3 S3 client created via
src.utils.local_cloud.get_client is intercepted (get_endpoint_url returns None
under pytest, letting moto take over). Targets remaining uncovered branches:
bucket creation/verification errors, S3 key generation edge cases, store/
retrieve/verify/list/batch error handling, statistics, cleanup, export, and the
legacy S3Storage compatibility class plus the module-level ingestion helpers.
"""

import asyncio
import json
import os
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, NoCredentialsError
from moto import mock_aws

from src.database import s3_storage
from src.database.s3_storage import (
    ArticleType,
    S3ArticleStorage,
    S3Storage,
    S3StorageConfig,
    ingest_scraped_articles_to_s3,
    verify_s3_data_consistency,
)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def make_config(bucket="test-bucket"):
    return S3StorageConfig(bucket_name=bucket, region="us-east-1")


def make_storage(bucket="test-bucket", config=None):
    """Create a bucket in moto then a storage bound to it."""
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket)
    return S3ArticleStorage(config or make_config(bucket))


# --------------------------------------------------------------------------
# Initialization / bucket handling
# --------------------------------------------------------------------------

@mock_aws
def test_init_with_explicit_credentials():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="cred-bucket")
    storage = S3ArticleStorage(
        make_config("cred-bucket"),
        aws_access_key_id="AKIAX",
        aws_secret_access_key="secret",
    )
    assert storage.s3_client is not None


@mock_aws
def test_init_missing_bucket_raises_value_error():
    # Bucket not created -> head_bucket 404 -> ValueError
    with pytest.raises(ValueError, match="does not exist"):
        S3ArticleStorage(make_config("no-such-bucket"))


@mock_aws
def test_configure_bucket_disabled_versioning():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="cfg-bucket")
    cfg = S3StorageConfig(bucket_name="cfg-bucket", enable_versioning=False)
    storage = S3ArticleStorage(cfg)
    assert storage.s3_client is not None


def test_init_no_credentials_error(monkeypatch):
    def raise_nocreds(*a, **k):
        raise NoCredentialsError()

    monkeypatch.setattr(s3_storage, "get_client", raise_nocreds)
    storage = S3ArticleStorage(make_config())
    # NoCredentialsError branch -> client set to None (lines 94-96)
    assert storage.s3_client is None


def test_init_generic_exception(monkeypatch):
    def raise_generic(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(s3_storage, "get_client", raise_generic)
    storage = S3ArticleStorage(make_config())
    # Generic Exception branch -> client None (lines 100-102)
    assert storage.s3_client is None


def _client_error(code):
    return ClientError({"Error": {"Code": str(code), "Message": "err"}}, "Op")


@mock_aws
def test_ensure_bucket_access_denied():
    # head_bucket returns 403 -> ValueError "Access denied"
    storage = make_storage()
    bad = MagicMock()
    bad.head_bucket.side_effect = _client_error(403)
    storage.s3_client = bad
    with pytest.raises(ValueError, match="Access denied"):
        storage._ensure_bucket_exists()


@mock_aws
def test_ensure_bucket_other_client_error_reraised():
    storage = make_storage()
    bad = MagicMock()
    bad.head_bucket.side_effect = _client_error(500)
    storage.s3_client = bad
    with pytest.raises(ClientError):
        storage._ensure_bucket_exists()


@mock_aws
def test_ensure_and_configure_bucket_no_client():
    storage = make_storage()
    storage.s3_client = None
    # both early-return without error (lines 107, 130)
    assert storage._ensure_bucket_exists() is None
    assert storage._configure_bucket() is None


@mock_aws
def test_configure_bucket_client_error_logged():
    storage = make_storage()
    bad = MagicMock()
    bad.put_bucket_versioning.side_effect = _client_error(500)
    storage.s3_client = bad
    # ClientError caught + logged, no raise (lines 160-161)
    assert storage._configure_bucket() is None


# --------------------------------------------------------------------------
# S3 key generation
# --------------------------------------------------------------------------

@mock_aws
def test_generate_s3_key_uses_current_date_when_missing():
    storage = make_storage()
    key = storage._generate_s3_key({"url": "u", "title": "t"}, ArticleType.RAW)
    assert key.startswith("raw_articles/")
    assert key.endswith(".json")


@mock_aws
def test_generate_s3_key_invalid_date_falls_back_to_uuid():
    storage = make_storage()
    # published_date with wrong number of parts -> ValueError -> uuid fallback
    key = storage._generate_s3_key(
        {"published_date": "2024/01", "url": "u", "title": "t"}, ArticleType.RAW
    )
    assert key.startswith("raw_articles/")


@mock_aws
def test_generate_s3_key_date_override():
    storage = make_storage()
    key = storage._generate_s3_key(
        {"id": "abc", "url": "u", "title": "t"},
        ArticleType.PROCESSED,
        date_override="2023-05-06",
    )
    assert key == "processed_articles/2023/05/06/abc.json"


# --------------------------------------------------------------------------
# store / retrieve
# --------------------------------------------------------------------------

@mock_aws
def test_store_raw_article_missing_fields():
    storage = make_storage()
    with pytest.raises(ValueError, match="Missing required fields"):
        run(storage.store_raw_article({"title": "t"}))


@mock_aws
def test_store_raw_article_no_client():
    storage = make_storage()
    storage.s3_client = None
    with pytest.raises(ValueError, match="S3 client not available"):
        run(storage.store_raw_article({"title": "t", "content": "c", "url": "u"}))


@mock_aws
def test_store_and_retrieve_roundtrip():
    storage = make_storage()
    article = {
        "title": "Hello",
        "content": "World body",
        "url": "http://x/1",
        "source": "src",
        "published_date": "2024-03-04",
    }
    meta = run(storage.store_raw_article(article))
    assert meta.processing_status == "stored"
    fetched = run(storage.retrieve_article(meta.s3_key))
    assert fetched["title"] == "Hello"
    assert fetched["storage_type"] == "raw"


@mock_aws
def test_store_raw_article_too_large():
    cfg = S3StorageConfig(bucket_name="big-bucket", max_file_size_mb=0)
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="big-bucket")
    storage = S3ArticleStorage(cfg)
    with pytest.raises(ValueError, match="too large"):
        run(
            storage.store_raw_article(
                {"title": "t", "content": "some content", "url": "u"}
            )
        )


@mock_aws
def test_store_raw_article_non_standard_storage_class():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="sc-bucket")
    cfg = S3StorageConfig(bucket_name="sc-bucket", storage_class="STANDARD_IA")
    storage = S3ArticleStorage(cfg)
    meta = run(
        storage.store_raw_article(
            {"title": "T", "content": "body", "url": "http://x/sc"}
        )
    )
    # StorageClass extra arg path exercised (line 284)
    assert meta.processing_status == "stored"


@mock_aws
def test_store_processed_article_and_storage_class():
    cfg = S3StorageConfig(bucket_name="proc-bucket", storage_class="STANDARD_IA")
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="proc-bucket")
    storage = S3ArticleStorage(cfg)
    meta = run(
        storage.store_processed_article(
            {"id": "p1", "title": "T", "url": "u", "source": "s"},
            processing_metadata={"pipeline": "v1"},
        )
    )
    assert meta.article_type == ArticleType.PROCESSED
    assert meta.processing_status == "processed"


@mock_aws
def test_store_processed_article_no_client():
    storage = make_storage()
    storage.s3_client = None
    with pytest.raises(ValueError, match="S3 client not available"):
        run(storage.store_processed_article({"id": "p"}))


@mock_aws
def test_retrieve_article_not_found():
    storage = make_storage()
    with pytest.raises(ValueError, match="Article not found"):
        run(storage.retrieve_article("raw_articles/2024/01/01/missing.json"))


@mock_aws
def test_retrieve_article_no_client():
    storage = make_storage()
    storage.s3_client = None
    with pytest.raises(ValueError, match="S3 client not available"):
        run(storage.retrieve_article("k"))


# --------------------------------------------------------------------------
# integrity verification
# --------------------------------------------------------------------------

@mock_aws
def test_verify_integrity_true():
    storage = make_storage()
    article = {
        "title": "T",
        "content": "consistent body",
        "url": "http://x/9",
    }
    meta = run(storage.store_raw_article(article))
    assert run(storage.verify_article_integrity(meta.s3_key)) is True


@mock_aws
def test_verify_integrity_missing_hash():
    storage = make_storage()
    # Put an object with no content_hash
    storage.s3_client.put_object(
        Bucket=storage.bucket_name,
        Key="raw_articles/2024/01/01/nohash.json",
        Body=json.dumps({"content": "x"}),
    )
    assert (
        run(storage.verify_article_integrity("raw_articles/2024/01/01/nohash.json"))
        is False
    )


@mock_aws
def test_verify_integrity_error_returns_false():
    storage = make_storage()
    # Non-existent key -> retrieve raises -> verify returns False
    assert run(storage.verify_article_integrity("missing/key.json")) is False


# --------------------------------------------------------------------------
# listing
# --------------------------------------------------------------------------

@mock_aws
def test_list_by_date_invalid_format_returns_empty():
    storage = make_storage()
    assert run(storage.list_articles_by_date("2024/01", ArticleType.RAW)) == []


@mock_aws
def test_list_by_date_and_prefix():
    storage = make_storage()
    run(
        storage.store_raw_article(
            {
                "title": "A",
                "content": "b",
                "url": "http://x/a",
                "published_date": "2024-07-08",
            }
        )
    )
    keys = run(storage.list_articles_by_date("2024-07-08", ArticleType.RAW))
    assert len(keys) == 1
    # limit path
    limited = run(storage.list_articles_by_prefix("raw_articles/", limit=1))
    assert len(limited) == 1


@mock_aws
def test_list_prefix_no_client_returns_empty():
    storage = make_storage()
    storage.s3_client = None
    assert run(storage.list_articles_by_prefix("raw_articles/")) == []
    assert run(storage.list_articles_by_date("2024-01-01", ArticleType.RAW)) == []


# --------------------------------------------------------------------------
# batch storage
# --------------------------------------------------------------------------

@mock_aws
def test_batch_store_mixed_success_and_error():
    storage = make_storage()
    articles = [
        {"title": "Good", "content": "body", "url": "http://x/good"},
        {"title": "Bad"},  # missing content/url -> error metadata
    ]
    results = run(storage.batch_store_raw_articles(articles))
    statuses = [r.processing_status for r in results]
    assert "stored" in statuses
    assert "error" in statuses
    err = next(r for r in results if r.processing_status == "error")
    assert err.error_message


@mock_aws
def test_batch_store_no_client():
    storage = make_storage()
    storage.s3_client = None
    with pytest.raises(ValueError, match="S3 client not available"):
        run(storage.batch_store_raw_articles([{"title": "t"}]))


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------

@mock_aws
def test_storage_statistics():
    storage = make_storage()
    run(
        storage.store_raw_article(
            {"title": "A", "content": "b", "url": "http://x/a"}
        )
    )
    run(
        storage.store_processed_article({"id": "p", "title": "P", "url": "u"})
    )
    stats = run(storage.get_storage_statistics())
    assert stats["total_count"] == 2
    assert stats["raw_articles"]["count"] == 1
    assert stats["processed_articles"]["count"] == 1


@mock_aws
def test_storage_statistics_no_client():
    storage = make_storage()
    storage.s3_client = None
    stats = run(storage.get_storage_statistics())
    assert stats == {"error": "S3 client not available"}


# --------------------------------------------------------------------------
# cleanup
# --------------------------------------------------------------------------

@mock_aws
def test_cleanup_old_articles_none_recent():
    storage = make_storage()
    run(
        storage.store_raw_article(
            {"title": "A", "content": "b", "url": "http://x/a"}
        )
    )
    # Just-stored article is newer than cutoff -> nothing deleted
    deleted = run(storage.cleanup_old_articles(days=365))
    assert deleted == 0


@mock_aws
def test_cleanup_deletes_old_articles():
    storage = make_storage()
    run(
        storage.store_raw_article(
            {"title": "A", "content": "b", "url": "http://x/a"}
        )
    )
    # Cutoff in the future (negative days) -> the object is "older" than cutoff
    deleted = run(storage.cleanup_old_articles(days=-1))
    assert deleted == 1


@mock_aws
def test_cleanup_no_client():
    storage = make_storage()
    storage.s3_client = None
    assert run(storage.cleanup_old_articles()) == 0


# --------------------------------------------------------------------------
# delete
# --------------------------------------------------------------------------

@mock_aws
def test_delete_article():
    storage = make_storage()
    meta = run(
        storage.store_raw_article(
            {"title": "A", "content": "b", "url": "http://x/a"}
        )
    )
    storage.delete_article(meta.s3_key)
    with pytest.raises(ValueError, match="Article not found"):
        run(storage.retrieve_article(meta.s3_key))


@mock_aws
def test_delete_article_no_client():
    storage = make_storage()
    storage.s3_client = None
    with pytest.raises(ValueError, match="S3 client not available"):
        storage.delete_article("k")


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------

@mock_aws
def test_export_articles_to_local(tmp_path):
    storage = make_storage()
    run(
        storage.store_raw_article(
            {
                "title": "A",
                "content": "b",
                "url": "http://x/a",
                "published_date": "2024-02-03",
            }
        )
    )
    count = run(
        storage.export_articles_to_local(
            str(tmp_path / "out"),
            date_filter="2024-02-03",
            article_type=ArticleType.RAW,
        )
    )
    assert count == 1
    files = os.listdir(str(tmp_path / "out"))
    assert len(files) == 1


@mock_aws
def test_export_all_types(tmp_path):
    storage = make_storage()
    run(storage.store_raw_article({"title": "A", "content": "b", "url": "http://x/a"}))
    run(storage.store_processed_article({"id": "p", "title": "P", "url": "u"}))
    count = run(storage.export_articles_to_local(str(tmp_path / "all")))
    assert count == 2


@mock_aws
def test_export_no_client():
    storage = make_storage()
    storage.s3_client = None
    assert run(storage.export_articles_to_local("/tmp/whatever")) == 0


# --------------------------------------------------------------------------
# Legacy S3Storage class
# --------------------------------------------------------------------------

@mock_aws
def test_legacy_upload_and_get_article():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="legacy-bucket")
    storage = S3Storage(bucket_name="legacy-bucket", prefix="news_articles")
    key = storage.upload_article(
        {"title": "Legacy", "content": "body", "source": "My Source"}
    )
    assert key.startswith("news_articles/")
    got = storage.get_article(key)
    assert got["title"] == "Legacy"
    assert got["storage_type"] == "raw"


@mock_aws
def test_legacy_upload_missing_fields():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="legacy2")
    storage = S3Storage(bucket_name="legacy2")
    with pytest.raises(ValueError, match="Missing required fields"):
        storage.upload_article({"title": "x"})


@mock_aws
def test_legacy_generate_s3_key_invalid_date():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="legacy3")
    storage = S3Storage(bucket_name="legacy3")
    key = storage._generate_s3_key(
        {"published_date": "bad", "title": "t", "content": "c", "url": "u", "source": "s"}
    )
    # falls back to current date structure; still under prefix
    assert key.startswith("news_articles/")


@mock_aws
def test_legacy_list_and_delete_and_file_ops(tmp_path):
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="legacy4")
    storage = S3Storage(bucket_name="legacy4")
    key = storage.upload_article(
        {"title": "L", "content": "b", "source": "s"}
    )
    listed = storage.list_articles()
    assert key in listed

    # upload_file / download_file roundtrip
    local = tmp_path / "f.txt"
    local.write_text("hello")
    storage.upload_file(str(local), "uploads/f.txt")
    out = tmp_path / "back.txt"
    storage.download_file("uploads/f.txt", str(out))
    assert out.read_text() == "hello"

    storage.delete_article(key)
    assert key not in storage.list_articles()


@mock_aws
def test_legacy_file_ops_no_client():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="legacy5")
    storage = S3Storage(bucket_name="legacy5")
    storage.s3_client = None
    with pytest.raises(ValueError):
        storage.upload_file("/x", "y")
    with pytest.raises(ValueError):
        storage.download_file("y", "/x")
    with pytest.raises(ValueError):
        storage.delete_article("k")


# --------------------------------------------------------------------------
# Error-handling paths driven by a mocked failing client
# --------------------------------------------------------------------------

@mock_aws
def test_store_raw_article_put_error_reraised():
    storage = make_storage()
    storage.s3_client.put_object = MagicMock(side_effect=RuntimeError("put fail"))
    with pytest.raises(RuntimeError, match="put fail"):
        run(storage.store_raw_article({"title": "t", "content": "c", "url": "u"}))


@mock_aws
def test_store_processed_article_put_error_reraised():
    storage = make_storage()
    storage.s3_client.put_object = MagicMock(side_effect=RuntimeError("put fail"))
    with pytest.raises(RuntimeError, match="put fail"):
        run(storage.store_processed_article({"id": "p", "title": "t"}))


@mock_aws
def test_retrieve_article_other_client_error_reraised():
    storage = make_storage()
    storage.s3_client.get_object = MagicMock(side_effect=_client_error("AccessDenied"))
    with pytest.raises(ClientError):
        run(storage.retrieve_article("some/key.json"))


@mock_aws
def test_retrieve_article_generic_error_reraised():
    storage = make_storage()
    storage.s3_client.get_object = MagicMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        run(storage.retrieve_article("some/key.json"))


@mock_aws
def test_verify_integrity_hash_mismatch():
    storage = make_storage()
    # Store object whose stored content_hash does not match its content
    storage.s3_client.put_object(
        Bucket=storage.bucket_name,
        Key="raw_articles/2024/01/01/mm.json",
        Body=json.dumps({"content": "real content", "content_hash": "deadbeef"}),
    )
    result = run(storage.verify_article_integrity("raw_articles/2024/01/01/mm.json"))
    assert result is False


@mock_aws
def test_list_prefix_paginator_error_returns_empty():
    storage = make_storage()
    storage.s3_client.get_paginator = MagicMock(side_effect=RuntimeError("no pager"))
    assert run(storage.list_articles_by_prefix("raw_articles/")) == []


@mock_aws
def test_statistics_head_object_error_swallowed():
    storage = make_storage()
    run(storage.store_raw_article({"title": "A", "content": "b", "url": "http://x/a"}))
    # head_object raising is swallowed inside the sample loop (632-633)
    storage.s3_client.head_object = MagicMock(side_effect=RuntimeError("head fail"))
    stats = run(storage.get_storage_statistics())
    assert stats["total_count"] == 1


@mock_aws
def test_statistics_outer_error_returns_error_dict():
    storage = make_storage()
    storage.s3_client.get_paginator = MagicMock(side_effect=RuntimeError("pager"))
    # list returns [] on error; force a deeper failure via head_object list? Instead
    # patch list_articles_by_prefix to raise to hit outer except (648-650).
    orig = storage.list_articles_by_prefix

    async def boom(*a, **k):
        raise RuntimeError("stat outer")

    storage.list_articles_by_prefix = boom
    stats = run(storage.get_storage_statistics())
    assert "error" in stats


@mock_aws
def test_cleanup_head_object_error_swallowed():
    storage = make_storage()
    run(storage.store_raw_article({"title": "A", "content": "b", "url": "http://x/a"}))
    storage.s3_client.head_object = MagicMock(side_effect=RuntimeError("head fail"))
    # per-key error logged, loop continues, deleted stays 0 (687-688)
    assert run(storage.cleanup_old_articles(days=-1)) == 0


@mock_aws
def test_cleanup_outer_error_returns_zero():
    storage = make_storage()

    async def boom(*a, **k):
        raise RuntimeError("cleanup outer")

    storage.list_articles_by_prefix = boom
    assert run(storage.cleanup_old_articles(days=30)) == 0


@mock_aws
def test_delete_article_error_reraised():
    storage = make_storage()
    storage.s3_client.delete_object = MagicMock(side_effect=RuntimeError("del fail"))
    with pytest.raises(RuntimeError, match="del fail"):
        storage.delete_article("k")


@mock_aws
def test_export_download_error_swallowed(tmp_path):
    storage = make_storage()
    run(
        storage.store_raw_article(
            {"title": "A", "content": "b", "url": "http://x/a"}
        )
    )
    storage.s3_client.download_file = MagicMock(side_effect=RuntimeError("dl fail"))
    # per-key download error swallowed -> exported 0 (757-758)
    count = run(
        storage.export_articles_to_local(
            str(tmp_path / "e"), article_type=ArticleType.RAW
        )
    )
    assert count == 0


@mock_aws
def test_export_outer_error_returns_zero(tmp_path):
    storage = make_storage()

    async def boom(*a, **k):
        raise RuntimeError("export outer")

    storage.list_articles_by_prefix = boom
    count = run(
        storage.export_articles_to_local(
            str(tmp_path / "e2"), article_type=ArticleType.RAW
        )
    )
    assert count == 0


@mock_aws
def test_legacy_upload_no_client():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="legacy-nc")
    storage = S3Storage(bucket_name="legacy-nc")
    storage.s3_client = None
    with pytest.raises(ValueError, match="S3 client not available"):
        storage.upload_article({"title": "t", "content": "c", "source": "s"})


@mock_aws
def test_legacy_upload_put_error_reraised():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="legacy-pe")
    storage = S3Storage(bucket_name="legacy-pe")
    storage.s3_client.put_object = MagicMock(side_effect=RuntimeError("put fail"))
    with pytest.raises(RuntimeError, match="put fail"):
        storage.upload_article({"title": "t", "content": "c", "source": "s"})


# --------------------------------------------------------------------------
# Module-level ingestion helpers
# --------------------------------------------------------------------------

@mock_aws
def test_ingest_empty_list():
    result = run(ingest_scraped_articles_to_s3([], make_config()))
    assert result["status"] == "success"
    assert result["total_articles"] == 0


@mock_aws
def test_ingest_articles_success():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="ingest-bucket")
    cfg = make_config("ingest-bucket")
    articles = [
        {"title": "A", "content": "body a", "url": "http://x/a"},
        {"title": "B", "content": "body b", "url": "http://x/b"},
    ]
    result = run(
        ingest_scraped_articles_to_s3(
            articles,
            cfg,
            aws_credentials={
                "aws_access_key_id": "k",
                "aws_secret_access_key": "s",
            },
        )
    )
    assert result["status"] == "success"
    assert result["stored_articles"] == 2
    assert len(result["stored_keys"]) == 2


@mock_aws
def test_ingest_articles_partial_success():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="ingest2")
    cfg = make_config("ingest2")
    articles = [
        {"title": "Good", "content": "body", "url": "http://x/g"},
        {"title": "Bad"},  # missing fields -> error
    ]
    result = run(ingest_scraped_articles_to_s3(articles, cfg))
    assert result["status"] == "partial_success"
    assert result["failed_articles"] == 1


@mock_aws
def test_ingest_critical_error(monkeypatch):
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="ingest-crit")
    cfg = make_config("ingest-crit")

    async def boom(self, *a, **k):
        raise RuntimeError("critical batch failure")

    monkeypatch.setattr(S3ArticleStorage, "batch_store_raw_articles", boom)
    result = run(
        ingest_scraped_articles_to_s3(
            [{"title": "A", "content": "b", "url": "http://x/a"}], cfg
        )
    )
    assert result["status"] == "error"
    assert result["errors"]


@mock_aws
def test_verify_consistency_invalid_article():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="verify-inv")
    cfg = make_config("verify-inv")
    storage = S3ArticleStorage(cfg)
    # Store an object with a wrong content_hash so integrity check fails
    storage.s3_client.put_object(
        Bucket="verify-inv",
        Key="raw_articles/2024/01/01/bad.json",
        Body=json.dumps({"content": "body", "content_hash": "wrong"}),
    )
    result = run(verify_s3_data_consistency(cfg, sample_size=10))
    assert result["status"] == "warning"
    assert result["invalid_articles"] == 1
    assert result["errors"]


@mock_aws
def test_verify_consistency_integrity_check_raises(monkeypatch):
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="verify-raise")
    cfg = make_config("verify-raise")
    storage = S3ArticleStorage(cfg)
    run(storage.store_raw_article({"title": "A", "content": "b", "url": "http://x/a"}))

    async def raising(self, key):
        raise RuntimeError("integrity boom")

    # verify_article_integrity itself raising hits the per-key except (1025-1027)
    monkeypatch.setattr(S3ArticleStorage, "verify_article_integrity", raising)
    result = run(verify_s3_data_consistency(cfg, sample_size=10))
    assert result["invalid_articles"] == 1
    assert any("Error verifying" in e for e in result["errors"])


@mock_aws
def test_verify_consistency_outer_error(monkeypatch):
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="verify-err")
    cfg = make_config("verify-err")

    async def boom(self, *a, **k):
        raise RuntimeError("verify outer failure")

    monkeypatch.setattr(S3ArticleStorage, "list_articles_by_prefix", boom)
    result = run(verify_s3_data_consistency(cfg))
    assert result["status"] == "error"
    assert result["errors"]


@mock_aws
def test_verify_consistency_no_articles():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="verify-empty")
    result = run(verify_s3_data_consistency(make_config("verify-empty")))
    assert result["status"] == "success"
    assert result["total_checked"] == 0


@mock_aws
def test_verify_consistency_with_valid_articles():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="verify-full")
    cfg = make_config("verify-full")
    storage = S3ArticleStorage(cfg)
    run(storage.store_raw_article({"title": "A", "content": "b", "url": "http://x/a"}))
    result = run(verify_s3_data_consistency(cfg, sample_size=10))
    assert result["total_checked"] == 1
    assert result["valid_articles"] == 1
    assert result["integrity_rate"] == 100.0
