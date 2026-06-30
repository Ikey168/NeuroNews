"""Extra moto-backed tests for src/database/dynamodb_pipeline_integration.py.

These target the gaps left by
tests/unit/database/modules/dynamodb/test_dynamodb_pipeline_integration.py
(which exercises a non-existent class) and
tests/unit/database/test_dynamodb_pipeline_integration.py (which covers init /
config / a couple of sync stubs). Here we exercise the real async flows:

* DynamoDBMetadataPipeline.spider_opened / spider_closed / process_item
* S3MetadataSync.sync_multiple_s3_articles (enabled + disabled)
* RedshiftMetadataSync.sync_redshift_load_event / sync_batch_redshift_loads
* DataValidationMetadataSync.sync_validation_results
* MetadataIntegrationOrchestrator.initialize / process_scraped_article /
  get_integration_statistics
* sync_existing_s3_articles + from_crawler with credentials

Real assertions verify DynamoDB round-trips through a moto-backed manager.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from database.dynamodb_pipeline_integration import (  # noqa: E402
    DataValidationMetadataSync,
    DynamoDBMetadataPipeline,
    MetadataIntegrationOrchestrator,
    RedshiftMetadataSync,
    S3MetadataSync,
    sync_existing_s3_articles,
)
from database.dynamodb_metadata_manager import (  # noqa: E402
    DynamoDBMetadataConfig,
    DynamoDBMetadataManager,
)


@pytest.fixture(autouse=True)
def aws_creds(monkeypatch):
    for k in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SECURITY_TOKEN",
        "AWS_SESSION_TOKEN",
    ):
        monkeypatch.setenv(k, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def _config(table_name):
    return DynamoDBMetadataConfig(
        table_name=table_name,
        region="us-east-1",
        endpoint_url=None,
        enable_point_in_time_recovery=False,  # moto lacks update_continuous_backups
    )


@pytest.fixture
def manager():
    with mock_aws():
        yield DynamoDBMetadataManager(_config("extra-pipeline-metadata"))


def _spider(name="cnn"):
    spider = MagicMock()
    spider.name = name
    spider.version = "3.0"
    return spider


def _article(article_id, **overrides):
    """Article data with all GSI-key attributes (source, published_date,
    category) non-empty so the moto-backed table accepts the item."""
    data = {
        "id": article_id,
        "url": f"https://example.com/{article_id}",
        "title": f"Title {article_id}",
        "source": "example-source",
        "published_date": "2026-06-01",
        "category": "news",
        "content": "body content",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# DynamoDBMetadataPipeline lifecycle + process_item
# ---------------------------------------------------------------------------
class TestPipelineProcessItem:
    @pytest.mark.asyncio
    async def test_spider_opened_initializes_manager_and_start_time(self):
        with mock_aws():
            pipeline = DynamoDBMetadataPipeline(_config("lifecycle-table"))
            assert pipeline.manager is None
            await pipeline.spider_opened(_spider())
            assert isinstance(pipeline.manager, DynamoDBMetadataManager)
            assert pipeline.stats["start_time"] is not None

    @pytest.mark.asyncio
    async def test_spider_closed_runs_without_division_error(self):
        # indexed_articles is 0 -> exercises the max(1, ...) guard.
        pipeline = DynamoDBMetadataPipeline()
        pipeline.stats["start_time"] = None
        await pipeline.spider_closed(_spider())  # must not raise

    @pytest.mark.asyncio
    async def test_process_item_without_manager_returns_item_unchanged(self):
        pipeline = DynamoDBMetadataPipeline()
        item = {"id": "x1", "url": "https://x/1", "title": "t"}
        result = await pipeline.process_item(item, _spider())
        assert result is item
        assert "dynamodb_metadata" not in item
        assert pipeline.stats["indexed_articles"] == 0

    @pytest.mark.asyncio
    async def test_process_item_success_indexes_and_annotates_item(self):
        with mock_aws():
            pipeline = DynamoDBMetadataPipeline(_config("process-item-table"))
            await pipeline.spider_opened(_spider("bbc"))

            item = {
                "id": "art-100",
                "title": "Quantum computing leap",
                "url": "https://bbc.com/news/100",
                "content": "Body content here",
                "published_date": "2026-03-01",
                "tags": ["science"],
            }
            result = await pipeline.process_item(item, _spider("bbc"))

            # Item annotated with DynamoDB metadata for downstream pipelines.
            assert result["dynamodb_metadata"]["article_id"] == "art-100"
            assert "content_hash" in result["dynamodb_metadata"]
            assert "indexed_date" in result["dynamodb_metadata"]

            # Stats updated and processing time recorded.
            assert pipeline.stats["indexed_articles"] == 1
            assert pipeline.stats["failed_articles"] == 0
            assert pipeline.stats["total_processing_time"] > 0

            # Article actually persisted in DynamoDB.
            fetched = await pipeline.manager.get_article_by_id("art-100")
            assert fetched is not None
            assert fetched.title == "Quantum computing leap"

    @pytest.mark.asyncio
    async def test_process_item_failure_increments_failed_and_keeps_item(self):
        pipeline = DynamoDBMetadataPipeline()
        # Manager set but its index call raises -> error branch (item not dropped).
        pipeline.manager = MagicMock()
        pipeline.manager.index_article_metadata = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        item = {"id": "err-1", "url": "https://x/err", "title": "t"}
        result = await pipeline.process_item(item, _spider())
        assert result is item
        assert "dynamodb_metadata" not in item
        assert pipeline.stats["failed_articles"] == 1
        assert pipeline.stats["indexed_articles"] == 0

    def test_from_crawler_builds_config_and_connects_signals(self):
        crawler = MagicMock()
        settings = MagicMock()

        def _get(key, default=None):
            values = {
                "DYNAMODB_METADATA_TABLE": "crawler-table",
                "AWS_REGION": "eu-west-1",
            }
            return values.get(key, default)

        settings.get.side_effect = _get
        settings.getint.side_effect = lambda k, d=None: d
        settings.getbool.side_effect = lambda k, d=None: d
        crawler.settings = settings

        pipeline = DynamoDBMetadataPipeline.from_crawler(crawler)
        # from_crawler builds config from settings and passes None credentials.
        assert pipeline.config.table_name == "crawler-table"
        assert pipeline.config.region == "eu-west-1"
        assert pipeline.aws_credentials is None
        # Both spider lifecycle signals are wired up.
        assert crawler.signals.connect.call_count == 2


# ---------------------------------------------------------------------------
# S3MetadataSync.sync_multiple_s3_articles
# ---------------------------------------------------------------------------
class TestS3MultiSync:
    @pytest.mark.asyncio
    async def test_sync_multiple_disabled(self):
        sync = S3MetadataSync(MagicMock(), auto_sync=False)
        result = await sync.sync_multiple_s3_articles([{"article_id": "a"}])
        assert result == {"status": "disabled", "synced": 0, "failed": 0}

    @pytest.mark.asyncio
    async def test_sync_multiple_success(self):
        # Use a mocked manager: the real batch_index_articles path keys items
        # off GSI attributes, but this test focuses on the converter +
        # result-aggregation logic of sync_multiple_s3_articles itself.
        mgr = MagicMock()
        mgr.batch_index_articles = AsyncMock(
            return_value={
                "indexed_count": 3,
                "failed_count": 0,
                "failed_articles": [],
            }
        )
        sync = S3MetadataSync(mgr, auto_sync=True)
        s3_list = [
            {
                "article_id": f"s3-{i}",
                "title": f"S3 Article {i}",
                "source": "s3-source",
                "published_date": "2026-04-0{0}".format(i + 1),
                "url": f"https://s3/{i}",
                "s3_key": f"raw/{i}.json",
                "content_hash": f"hash-{i}",
            }
            for i in range(3)
        ]
        result = await sync.sync_multiple_s3_articles(s3_list)
        assert result["status"] == "completed"
        assert result["total_items"] == 3
        assert result["synced_count"] == 3
        assert result["failed_count"] == 0
        assert "sync_time_ms" in result

        # Verify the S3->article_data converter mapped fields correctly and
        # stamped the stored_s3 processing status for the downstream manager.
        called_with = mgr.batch_index_articles.call_args.args[0]
        assert len(called_with) == 3
        assert called_with[0]["id"] == "s3-0"
        assert called_with[0]["s3_key"] == "raw/0.json"
        assert called_with[0]["content_hash"] == "hash-0"
        assert all(a["processing_status"] == "stored_s3" for a in called_with)

    @pytest.mark.asyncio
    async def test_sync_multiple_handles_batch_exception(self):
        mgr = MagicMock()
        mgr.batch_index_articles = AsyncMock(side_effect=RuntimeError("batch down"))
        sync = S3MetadataSync(mgr, auto_sync=True)
        result = await sync.sync_multiple_s3_articles(
            [{"article_id": "a"}, {"article_id": "b"}]
        )
        assert result["status"] == "completed"
        assert result["failed_count"] == 2
        assert result["failed_items"] == [{"error": "batch down"}]


# ---------------------------------------------------------------------------
# RedshiftMetadataSync
# ---------------------------------------------------------------------------
class TestRedshiftSync:
    @pytest.mark.asyncio
    async def test_load_event_disabled(self):
        sync = RedshiftMetadataSync(MagicMock(), auto_update=False)
        assert await sync.sync_redshift_load_event({"article_id": "x"}) is False

    @pytest.mark.asyncio
    async def test_load_event_success_marks_loaded(self, manager):
        await manager.index_article_metadata(_article("rs-1"))
        sync = RedshiftMetadataSync(manager, auto_update=True)
        ok = await sync.sync_redshift_load_event({"article_id": "rs-1"})
        assert ok is True
        updated = await manager.get_article_by_id("rs-1")
        assert updated.redshift_loaded is True
        assert updated.processing_status == "processed"

    @pytest.mark.asyncio
    async def test_load_event_missing_article_id_returns_false(self, manager):
        sync = RedshiftMetadataSync(manager, auto_update=True)
        # integrate_with_redshift_etl returns False when no article_id present.
        assert await sync.sync_redshift_load_event({}) is False

    @pytest.mark.asyncio
    async def test_batch_disabled(self):
        sync = RedshiftMetadataSync(MagicMock(), auto_update=False)
        result = await sync.sync_batch_redshift_loads([{"article_id": "a"}])
        assert result == {"status": "disabled", "updated": 0, "failed": 0}

    @pytest.mark.asyncio
    async def test_batch_mixed_results(self, manager):
        # One existing article (will update ok) + one missing id (update "fails").
        await manager.index_article_metadata(_article("rs-ok"))
        sync = RedshiftMetadataSync(manager, auto_update=True)
        result = await sync.sync_batch_redshift_loads(
            [{"article_id": "rs-ok"}, {"no_id": True}]
        )
        assert result["status"] == "completed"
        assert result["total_records"] == 2
        assert result["updated_count"] == 1
        assert result["failed_count"] == 1
        assert result["failed_items"][0]["error"] == "Update failed"


# ---------------------------------------------------------------------------
# DataValidationMetadataSync
# ---------------------------------------------------------------------------
class TestValidationSync:
    @pytest.mark.asyncio
    async def test_disabled_returns_false(self):
        sync = DataValidationMetadataSync(MagicMock(), include_validation_metrics=False)
        assert await sync.sync_validation_results("a", {"quality_score": 9}) is False

    @pytest.mark.asyncio
    async def test_success_writes_validation_fields(self, manager):
        await manager.index_article_metadata(_article("v-1"))
        sync = DataValidationMetadataSync(manager, include_validation_metrics=True)
        ok = await sync.sync_validation_results(
            "v-1",
            {
                "quality_score": 88,
                "content_quality": "high",
                "is_duplicate": False,
                "source_reputation": "trusted",
            },
        )
        assert ok is True
        updated = await manager.get_article_by_id("v-1")
        assert updated.validation_score == 88
        assert updated.content_quality == "high"

    @pytest.mark.asyncio
    async def test_error_returns_false(self):
        mgr = MagicMock()
        mgr.update_article_metadata = AsyncMock(side_effect=RuntimeError("nope"))
        sync = DataValidationMetadataSync(mgr, include_validation_metrics=True)
        assert await sync.sync_validation_results("a", {"quality_score": 1}) is False


# ---------------------------------------------------------------------------
# MetadataIntegrationOrchestrator
# ---------------------------------------------------------------------------
class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_initialize_healthy(self):
        with mock_aws():
            orch = MetadataIntegrationOrchestrator(_config("orch-init"))
            await orch.initialize()  # health_check passes against moto -> no raise

    @pytest.mark.asyncio
    async def test_initialize_unhealthy_raises(self):
        with mock_aws():
            orch = MetadataIntegrationOrchestrator(_config("orch-unhealthy"))
            orch.dynamodb_manager.health_check = AsyncMock(
                return_value={"status": "unhealthy", "error": "x"}
            )
            with pytest.raises(RuntimeError):
                await orch.initialize()

    @pytest.mark.asyncio
    async def test_process_scraped_article_full_flow(self):
        with mock_aws():
            orch = MetadataIntegrationOrchestrator(_config("orch-process"))
            article_data = _article(
                "full-1",
                title="Full pipeline article",
                s3_key="raw/full-1.json",
                validation_result={
                    "quality_score": 77,
                    "content_quality": "good",
                },
            )
            results = await orch.process_scraped_article(article_data)
            assert results["article_id"] == "full-1"
            assert results["dynamodb_indexed"] is True
            assert results["s3_synced"] is True
            assert results["validation_synced"] is True
            assert results["errors"] == []
            assert "processing_time_ms" in results

    @pytest.mark.asyncio
    async def test_process_scraped_article_minimal_skips_optional_syncs(self):
        with mock_aws():
            orch = MetadataIntegrationOrchestrator(_config("orch-min"))
            results = await orch.process_scraped_article(_article("min-1"))
            assert results["dynamodb_indexed"] is True
            assert results["s3_synced"] is False
            assert results["validation_synced"] is False

    @pytest.mark.asyncio
    async def test_process_scraped_article_records_errors(self):
        with mock_aws():
            orch = MetadataIntegrationOrchestrator(_config("orch-err"))
            orch.dynamodb_manager.index_article_metadata = AsyncMock(
                side_effect=RuntimeError("index failed")
            )
            results = await orch.process_scraped_article({"id": "e-1"})
            assert results["dynamodb_indexed"] is False
            assert len(results["errors"]) == 1
            assert "index failed" in results["errors"][0]

    @pytest.mark.asyncio
    async def test_get_integration_statistics_real(self):
        with mock_aws():
            orch = MetadataIntegrationOrchestrator(_config("orch-real-stats"))
            await orch.dynamodb_manager.index_article_metadata(
                _article("st-1", source="bbc")
            )
            stats = await orch.get_integration_statistics()
            assert stats["dynamodb_stats"]["total_articles"] == 1
            assert stats["health_status"]["status"] == "healthy"
            assert stats["integration_status"]["s3_sync"] is True
            assert "timestamp" in stats

    @pytest.mark.asyncio
    async def test_get_integration_statistics_error(self):
        with mock_aws():
            orch = MetadataIntegrationOrchestrator(_config("orch-stats-err"))
            orch.dynamodb_manager.get_metadata_statistics = AsyncMock(
                side_effect=RuntimeError("stats down")
            )
            stats = await orch.get_integration_statistics()
            assert "error" in stats
            assert "stats down" in stats["error"]


# ---------------------------------------------------------------------------
# sync_existing_s3_articles utility
# ---------------------------------------------------------------------------
class TestSyncExisting:
    @pytest.mark.asyncio
    async def test_returns_placeholder(self, manager):
        result = await sync_existing_s3_articles(MagicMock(), manager)
        assert result["status"] == "completed"
        assert result["synced_count"] == 0
