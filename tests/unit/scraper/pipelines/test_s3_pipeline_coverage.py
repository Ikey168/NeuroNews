"""Coverage-focused tests for src/scraper/pipelines/s3_pipeline.py.

Exercises the full item lifecycle of ``S3StoragePipeline``:

* ``from_crawler`` settings resolution
* ``open_spider`` bucket-exists / 404 / 403 / other ClientError branches
* ``process_item`` key generation, metadata truncation, put_object success,
  the uninitialized-client guard, and the upload-failure branch.

Uses moto's ``mock_aws`` to back S3 with an in-memory implementation. boto3 and
moto are guarded with ``importorskip`` so the file skips cleanly when absent.
"""

import json
import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto")
pytest.importorskip("scrapy")
from botocore.exceptions import ClientError  # noqa: E402
from moto import mock_aws  # noqa: E402
from scrapy.exceptions import DropItem  # noqa: E402

from scraper.pipelines.s3_pipeline import S3StoragePipeline  # noqa: E402


class FakeLogger:
    def __init__(self):
        self.info_messages = []
        self.error_messages = []

    def info(self, msg):
        self.info_messages.append(msg)

    def error(self, msg):
        self.error_messages.append(msg)


class FakeSpider:
    def __init__(self):
        self.logger = FakeLogger()


def _item(**over):
    base = {
        "title": "Breaking! News: Something Happened?? at 100mph",
        "url": "https://news.example.com/story/1",
        "source": "news.example.com",
        "published_date": "2026-01-02",
        "author": "Jane Doe",
        "category": "World",
        "content": "body text",
    }
    base.update(over)
    return base


class TestFromCrawler:
    def test_uses_settings(self):
        crawler = type("C", (), {})()
        crawler.settings = type(
            "S",
            (),
            {"get": staticmethod(lambda key, default=None: {
                "LOCAL_BUCKET_NAME": "my-bucket",
                "S3_PREFIX": "prefixed",
            }.get(key, default))},
        )()
        pipeline = S3StoragePipeline.from_crawler(crawler)
        assert pipeline.s3_bucket == "my-bucket"
        assert pipeline.s3_prefix == "prefixed"

    def test_defaults_when_absent(self):
        crawler = type("C", (), {})()
        crawler.settings = type(
            "S", (), {"get": staticmethod(lambda key, default=None: default)}
        )()
        pipeline = S3StoragePipeline.from_crawler(crawler)
        assert pipeline.s3_bucket == "neuronews-local"
        assert pipeline.s3_prefix == "news_articles"


class TestOpenSpider:
    def test_bucket_exists(self):
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket="present-bucket")
            pipeline = S3StoragePipeline(s3_bucket="present-bucket")
            spider = FakeSpider()
            pipeline.open_spider(spider)
            assert pipeline.s3_client is not None
            assert spider.logger.error_messages == []

    def test_missing_bucket_raises_dropitem_404(self):
        with mock_aws():
            pipeline = S3StoragePipeline(s3_bucket="never-created-bucket")
            spider = FakeSpider()
            with pytest.raises(DropItem):
                pipeline.open_spider(spider)
            assert any(
                "does not exist" in m for m in spider.logger.error_messages
            )

    def test_forbidden_bucket_403(self, monkeypatch):
        pipeline = S3StoragePipeline(s3_bucket="forbidden")
        spider = FakeSpider()

        class FakeClient:
            def head_bucket(self, Bucket):
                raise ClientError(
                    {"Error": {"Code": "403", "Message": "Forbidden"}},
                    "HeadBucket",
                )

        monkeypatch.setattr(
            "scraper.pipelines.s3_pipeline.get_client", lambda svc: FakeClient()
        )
        with pytest.raises(DropItem):
            pipeline.open_spider(spider)
        assert any("forbidden" in m for m in spider.logger.error_messages)

    def test_other_client_error(self, monkeypatch):
        pipeline = S3StoragePipeline(s3_bucket="weird")
        spider = FakeSpider()

        class FakeClient:
            def head_bucket(self, Bucket):
                raise ClientError(
                    {"Error": {"Code": "500", "Message": "Boom"}},
                    "HeadBucket",
                )

        monkeypatch.setattr(
            "scraper.pipelines.s3_pipeline.get_client", lambda svc: FakeClient()
        )
        with pytest.raises(DropItem):
            pipeline.open_spider(spider)
        assert any("Error accessing" in m for m in spider.logger.error_messages)


class TestProcessItem:
    def test_uninitialized_client_guard(self):
        pipeline = S3StoragePipeline(s3_bucket="b")
        # s3_client is None because open_spider was never called
        with pytest.raises(DropItem):
            pipeline.process_item(_item(), FakeSpider())

    def test_successful_upload_and_key_format(self):
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket="store-bucket")
            pipeline = S3StoragePipeline(s3_bucket="store-bucket", s3_prefix="arts")
            spider = FakeSpider()
            pipeline.open_spider(spider)

            returned = pipeline.process_item(_item(), spider)
            assert returned["title"].startswith("Breaking")

            # Exactly one object was written; verify key structure + slug cleaning.
            listing = client.list_objects_v2(Bucket="store-bucket")
            keys = [obj["Key"] for obj in listing.get("Contents", [])]
            assert len(keys) == 1
            key = keys[0]
            assert key.startswith("arts/news-example-com/")
            assert key.endswith(".json")
            # Special chars removed, spaces -> hyphens, lowercased slug.
            slug = key.rsplit("_", 1)[1][:-5]
            assert slug == "breaking-news-something-happened-at-100mph"

            # Body is the JSON-serialized item.
            body = client.get_object(Bucket="store-bucket", Key=key)["Body"].read()
            stored = json.loads(body)
            assert stored["url"] == "https://news.example.com/story/1"

            assert any("Stored article in S3" in m for m in spider.logger.info_messages)

    def test_missing_fields_use_defaults(self):
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket="defaults-bucket")
            pipeline = S3StoragePipeline(s3_bucket="defaults-bucket")
            spider = FakeSpider()
            pipeline.open_spider(spider)

            pipeline.process_item({"content": "x"}, spider)
            listing = client.list_objects_v2(Bucket="defaults-bucket")
            key = listing["Contents"][0]["Key"]
            # source default "unknown", title default "untitled"
            assert "/unknown/" in key
            head = client.head_object(Bucket="defaults-bucket", Key=key)
            assert head["Metadata"]["title"] == "Untitled"
            assert head["Metadata"]["source"] == "Unknown"

    def test_metadata_truncated_to_255(self):
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket="trunc-bucket")
            pipeline = S3StoragePipeline(s3_bucket="trunc-bucket")
            spider = FakeSpider()
            pipeline.open_spider(spider)

            long_url = "https://x.example.com/" + ("a" * 400)
            pipeline.process_item(_item(url=long_url), spider)
            listing = client.list_objects_v2(Bucket="trunc-bucket")
            key = listing["Contents"][0]["Key"]
            head = client.head_object(Bucket="trunc-bucket", Key=key)
            assert len(head["Metadata"]["url"]) == 255

    def test_upload_failure_raises_dropitem(self, monkeypatch):
        pipeline = S3StoragePipeline(s3_bucket="b")
        spider = FakeSpider()

        class FailingClient:
            def put_object(self, **kwargs):
                raise ClientError(
                    {"Error": {"Code": "500", "Message": "upload failed"}},
                    "PutObject",
                )

        pipeline.s3_client = FailingClient()
        with pytest.raises(DropItem):
            pipeline.process_item(_item(), spider)
        assert any("Failed to upload" in m for m in spider.logger.error_messages)
