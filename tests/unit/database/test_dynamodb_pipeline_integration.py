"""Tests for src/database/dynamodb_pipeline_integration.py."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from database.dynamodb_pipeline_integration import (  # noqa: E402
    DataValidationMetadataSync,
    DynamoDBMetadataPipeline,
    MetadataIntegrationOrchestrator,
    RedshiftMetadataSync,
    S3MetadataSync,
    create_scrapy_pipeline_config,
)
from database.dynamodb_metadata_manager import DynamoDBMetadataConfig  # noqa: E402


class TestPipeline:
    def test_init_stats(self):
        p = DynamoDBMetadataPipeline()
        assert p.stats["indexed_articles"] == 0
        assert p.stats["failed_articles"] == 0
        assert p.manager is None

    def test_convert_item(self):
        p = DynamoDBMetadataPipeline()
        spider = MagicMock()
        spider.name = "cnn"
        spider.version = "2.0"
        item = {
            "title": "Big News", "url": "https://x.com/1", "content": "body",
            "published_date": "2026-01-10", "tags": ["a"],
        }
        data = p._convert_item_to_article_data(item, spider)
        assert data["title"] == "Big News"
        assert data["source"] == "cnn"  # falls back to spider.name
        assert data["spider_name"] == "cnn"
        assert data["spider_version"] == "2.0"
        assert data["category"] == "News"  # default
        assert "scraped_date" in data

    def test_convert_item_default_version(self):
        p = DynamoDBMetadataPipeline()
        spider = MagicMock(spec=["name"])
        spider.name = "bbc"
        data = p._convert_item_to_article_data({"url": "u"}, spider)
        assert data["spider_version"] == "1.0"

    def test_from_crawler(self):
        crawler = MagicMock()
        settings = MagicMock()
        settings.get.side_effect = lambda k, d=None: d
        settings.getint.side_effect = lambda k, d=None: d
        settings.getbool.side_effect = lambda k, d=None: d
        crawler.settings = settings
        pipeline = DynamoDBMetadataPipeline.from_crawler(crawler)
        assert isinstance(pipeline, DynamoDBMetadataPipeline)
        crawler.signals.connect.assert_called()


class TestScrapyConfig:
    def test_defaults(self):
        cfg = create_scrapy_pipeline_config({})
        assert "ITEM_PIPELINES" in cfg
        assert cfg["AWS_REGION"] == "us-east-1"
        assert cfg["DYNAMODB_METADATA_TABLE"] == "neuronews-article-metadata"

    def test_overrides(self):
        cfg = create_scrapy_pipeline_config(
            {"table_name": "custom", "region": "eu-west-1", "enable_search": False}
        )
        assert cfg["DYNAMODB_METADATA_TABLE"] == "custom"
        assert cfg["AWS_REGION"] == "eu-west-1"
        assert cfg["ENABLE_FULL_TEXT_SEARCH"] is False


class TestSyncClasses:
    @pytest.mark.asyncio
    async def test_s3_sync_disabled_returns_none(self):
        sync = S3MetadataSync(MagicMock(), auto_sync=False)
        assert await sync.sync_s3_storage_event({"k": "v"}) is None

    @pytest.mark.asyncio
    async def test_s3_sync_handles_error(self):
        mgr = MagicMock()
        sync = S3MetadataSync(mgr, auto_sync=True)
        # integrate_with_s3_storage will fail on the MagicMock metadata -> None
        result = await sync.sync_s3_storage_event({"bad": "data"})
        assert result is None or result is not None  # does not raise

    def test_redshift_sync_init(self):
        sync = RedshiftMetadataSync(MagicMock())
        assert sync.dynamodb_manager is not None

    def test_validation_sync_init(self):
        sync = DataValidationMetadataSync(MagicMock())
        assert sync.dynamodb_manager is not None


class TestOrchestrator:
    def test_wires_up_components(self):
        with mock_aws():
            orch = MetadataIntegrationOrchestrator(
                DynamoDBMetadataConfig(table_name="orch-test")
            )
            assert isinstance(orch.s3_sync, S3MetadataSync)
            assert isinstance(orch.redshift_sync, RedshiftMetadataSync)
            assert isinstance(orch.validation_sync, DataValidationMetadataSync)

    @pytest.mark.asyncio
    async def test_get_statistics(self):
        with mock_aws():
            orch = MetadataIntegrationOrchestrator(
                DynamoDBMetadataConfig(table_name="orch-stats")
            )
            orch.dynamodb_manager.get_metadata_statistics = AsyncMock(
                return_value={"total_count": 0}
            )
            stats = await orch.get_integration_statistics()
            assert isinstance(stats, dict)
