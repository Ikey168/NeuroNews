"""
Comprehensive integration tests for Database modules.

Tests integration between the data_validation, dynamodb, s3_storage and
snowflake analytics modules using their *current* APIs:

- ``S3Storage`` builds its client through
  ``src.database.s3_storage.get_client`` and ``upload_article`` returns the
  generated S3 key string.
- ``DynamoDBMetadataManager`` builds its resource/client through
  ``get_resource``/``get_client`` and its index/search/health methods are async.
- ``SnowflakeAnalyticsConnector`` is a pure-Python mock connector (no Snowflake
  driver required) exposing ``connect``/``execute_query``/``bulk_insert``/
  ``get_analytics_summary``.
- ``setup.py`` is function-based (no ``DatabaseSetup`` class); configuration is
  read via ``get_db_config``.
"""

import sys
import types
import uuid
from datetime import datetime, timedelta

import pytest
from unittest.mock import MagicMock, patch

# ``src.database.setup`` imports asyncpg at module load time; stub it when the
# optional dependency is absent so collection never crashes.
if "asyncpg" not in sys.modules:
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        _asyncpg_stub = types.ModuleType("asyncpg")
        _asyncpg_stub.Connection = type("Connection", (), {})
        _asyncpg_stub.connect = lambda *a, **k: None
        sys.modules["asyncpg"] = _asyncpg_stub

# boto3 backs the S3 / DynamoDB client factories used by the modules under test.
try:
    import boto3  # noqa: F401
    HAS_BOTO3 = True
except ImportError:  # pragma: no cover - environment dependent
    HAS_BOTO3 = False


# =============================================================================
# In-memory mocks for the cloud client factories
# =============================================================================

class MockS3Client:
    """Minimal in-memory S3 client mirroring the surface S3Storage uses."""

    def __init__(self):
        self.objects = {}

    def head_bucket(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_bucket_versioning(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_bucket_lifecycle_configuration(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_bucket_encryption(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[f"{Bucket}/{Key}"] = Body
        return {"ETag": f'"{uuid.uuid4()}"'}

    def get_object(self, Bucket, Key):
        return {"Body": MagicMock(read=lambda: self.objects[f"{Bucket}/{Key}"])}

    def list_objects_v2(self, Bucket, Prefix="", **kwargs):
        contents = [
            {"Key": key.split("/", 1)[1], "Size": len(str(body))}
            for key, body in self.objects.items()
            if key.startswith(f"{Bucket}/")
        ]
        return {"Contents": contents, "KeyCount": len(contents)}


class MockDynamoDBTable:
    """In-memory DynamoDB table mirroring the boto3 resource Table surface."""

    def __init__(self, table_name="test-table"):
        self.table_name = table_name
        self.items = {}
        # The manager calls describe_table on init to decide whether to create
        # the table; returning a value makes it treat the table as existing.
        self.meta = MagicMock()
        self.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

    def put_item(self, Item, **kwargs):
        item_id = Item.get("article_id") or str(uuid.uuid4())
        self.items[item_id] = Item
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_item(self, Key, **kwargs):
        key_value = list(Key.values())[0]
        item = self.items.get(key_value)
        return {"Item": item} if item else {}

    def query(self, **kwargs):
        items = list(self.items.values())
        return {"Items": items[:10], "Count": len(items)}

    def scan(self, **kwargs):
        items = list(self.items.values())
        return {"Items": items, "Count": len(items)}

    def delete_item(self, Key, **kwargs):
        key_value = list(Key.values())[0]
        self.items.pop(key_value, None)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def batch_writer(self, **kwargs):
        return _MockBatchWriter(self)


class _MockBatchWriter:
    def __init__(self, table):
        self.table = table

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def put_item(self, Item, **kwargs):
        self.table.put_item(Item=Item)


def _reputation_config():
    from src.database.data_validation_pipeline import SourceReputationConfig

    return SourceReputationConfig(
        trusted_domains=["integration-test.com", "trusted.com", "workflow-test.com"],
        questionable_domains=[],
        banned_domains=[],
        reputation_thresholds={
            "trusted": 0.9,
            "reliable": 0.7,
            "questionable": 0.4,
            "unreliable": 0.2,
        },
    )


# Distinct, non-fuzzy-similar titles so the duplicate detector does not reject
# later articles in multi-article tests as near-duplicates of earlier ones.
DISTINCT_TITLES = [
    "Breaking technology news today worldwide",
    "Economic policy shifts across the markets",
    "Sports championship final delivers results",
    "Health research breakthrough was announced",
    "Climate summit reaches a broad agreement",
]


def _article_body(index):
    """Content with enough words to clear the validator's word-count threshold.

    The leading distinct phrase keeps each article's content hash unique so the
    duplicate detector does not reject later articles in a batch.
    """
    return (
        f"{DISTINCT_TITLES[index % len(DISTINCT_TITLES)]}. Detailed coverage "
        f"number {index} about the subject with enough words to clear the "
        "validation threshold for word count and length requirements set by the "
        "validator system."
    )


def _snowflake_config():
    from src.database.snowflake_analytics_connector import SnowflakeConfig

    return SnowflakeConfig(
        account="analytics-account",
        user="analytics_user",
        password="analytics_password",
        warehouse="analytics_wh",
        database="ANALYTICS_DB",
        schema="PUBLIC",
    )


@pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed")
class TestDatabaseModuleIntegration:
    """Tests for integration between the current database modules."""

    @pytest.fixture(autouse=True)
    def setup_integration_mocking(self):
        """Patch the S3 / DynamoDB client factories with in-memory mocks."""
        self.mock_s3_client = MockS3Client()
        self.mock_dynamodb_table = MockDynamoDBTable("integration-test-table")
        mock_resource = MagicMock()
        mock_resource.Table.return_value = self.mock_dynamodb_table

        with patch(
            "src.database.s3_storage.get_client", return_value=self.mock_s3_client
        ), patch(
            "src.database.dynamodb_metadata_manager.get_resource",
            return_value=mock_resource,
        ), patch(
            "src.database.dynamodb_metadata_manager.get_client",
            return_value=MagicMock(),
        ):
            yield

    @pytest.mark.asyncio
    async def test_data_validation_to_storage_pipeline(self):
        """Validate articles, then store them in S3 and index in DynamoDB."""
        from src.database.data_validation_pipeline import DataValidationPipeline
        from src.database.s3_storage import S3Storage
        from src.database.dynamodb_metadata_manager import (
            DynamoDBMetadataManager,
            ArticleMetadataIndex,
        )

        validator = DataValidationPipeline(_reputation_config())
        s3_storage = S3Storage(bucket_name="integration-test-bucket")
        dynamodb_manager = DynamoDBMetadataManager("integration-test-table")

        raw_articles = [
            {
                "id": f"integration_test_{i}",
                "title": DISTINCT_TITLES[i],
                "content": _article_body(i),
                "source": "integration-test.com",
                "url": f"https://integration-test.com/article{i}",
                "published_date": "2024-01-15T10:30:00Z",
                "category": "technology",
            }
            for i in range(2)
        ]

        for article in raw_articles:
            result = validator.validate_article(article)
            assert result.is_valid

            s3_key = s3_storage.upload_article(result.cleaned_data)
            assert isinstance(s3_key, str)

            index = await dynamodb_manager.index_article_metadata(article)
            assert isinstance(index, ArticleMetadataIndex)

        # Both storage backends actually received the data.
        assert len(self.mock_s3_client.objects) == 2
        assert len(self.mock_dynamodb_table.items) == 2

    @pytest.mark.asyncio
    async def test_storage_to_analytics_pipeline(self):
        """Store articles in S3, then run them through Snowflake analytics."""
        from src.database.s3_storage import S3Storage
        from src.database.snowflake_analytics_connector import (
            SnowflakeAnalyticsConnector,
        )

        s3_storage = S3Storage(bucket_name="analytics-test-bucket")
        connector = SnowflakeAnalyticsConnector(_snowflake_config())

        test_articles = [
            {
                "id": f"analytics_test_{i}",
                "title": f"Analytics Test Article {i}",
                "content": _article_body(i),
                "source": "trusted.com",
                "url": f"https://trusted.com/analytics{i}",
                "published_date": "2024-01-15T10:30:00Z",
                "category": "technology",
            }
            for i in range(2)
        ]

        for article in test_articles:
            s3_key = s3_storage.upload_article(article)
            assert isinstance(s3_key, str)

        assert connector.connect() is True
        inserted = connector.bulk_insert("articles", test_articles)
        assert inserted == len(test_articles)

        rows = connector.execute_query("SELECT COUNT(*) FROM articles")
        assert isinstance(rows, list)

        assert len(self.mock_s3_client.objects) == 2

    @pytest.mark.asyncio
    async def test_complete_article_processing_workflow(self):
        """Full chain: validate -> S3 -> DynamoDB index -> Snowflake load."""
        from src.database.data_validation_pipeline import DataValidationPipeline
        from src.database.s3_storage import S3Storage
        from src.database.dynamodb_metadata_manager import (
            DynamoDBMetadataManager,
            ArticleMetadataIndex,
        )
        from src.database.snowflake_analytics_connector import (
            SnowflakeAnalyticsConnector,
        )

        article = {
            "id": f"workflow_test_{uuid.uuid4().hex[:8]}",
            "title": "Complete Workflow Test Article",
            "content": _article_body(1),
            "source": "workflow-test.com",
            "url": "https://workflow-test.com/complete-test",
            "published_date": "2024-01-15T10:30:00Z",
            "category": "technology",
            "author": "Workflow Tester",
        }

        # Step 1: Validation
        validator = DataValidationPipeline(_reputation_config())
        result = validator.validate_article(article)
        assert result.is_valid

        # Step 2: S3 storage
        s3_storage = S3Storage(bucket_name="workflow-test-bucket")
        s3_key = s3_storage.upload_article(result.cleaned_data)
        assert isinstance(s3_key, str)

        # Step 3: DynamoDB metadata index
        dynamodb_manager = DynamoDBMetadataManager("integration-test-table")
        index = await dynamodb_manager.index_article_metadata(article)
        assert isinstance(index, ArticleMetadataIndex)
        assert index.article_id == article["id"]

        # Step 4: Snowflake analytics load
        connector = SnowflakeAnalyticsConnector(_snowflake_config())
        connector.connect()
        inserted = connector.bulk_insert("articles", [article])
        assert inserted == 1

        # Verify the complete workflow touched every backend.
        assert len(self.mock_s3_client.objects) == 1
        assert article["id"] in self.mock_dynamodb_table.items

    @pytest.mark.asyncio
    async def test_cross_module_error_handling(self):
        """An S3 failure is surfaced while DynamoDB indexing still succeeds."""
        from src.database.s3_storage import S3Storage
        from src.database.dynamodb_metadata_manager import (
            DynamoDBMetadataManager,
            ArticleMetadataIndex,
        )

        s3_storage = S3Storage(bucket_name="error-test-bucket")
        dynamodb_manager = DynamoDBMetadataManager("integration-test-table")

        # Force the S3 put to fail.
        self.mock_s3_client.put_object = MagicMock(side_effect=Exception("S3 Error"))

        article = {
            "id": "error_test_1",
            "title": "Error Test Article",
            "content": _article_body(1),
            "source": "trusted.com",
            "url": "https://trusted.com/error-test",
            "published_date": "2024-01-15T10:30:00Z",
        }

        with pytest.raises(Exception):
            s3_storage.upload_article(article)

        # DynamoDB indexing is independent and still works.
        index = await dynamodb_manager.index_article_metadata(article)
        assert isinstance(index, ArticleMetadataIndex)
        assert "error_test_1" in self.mock_dynamodb_table.items

    def test_database_setup_integration(self, monkeypatch):
        """Database setup config integrates with the analytics connector.

        The legacy class-based ``DatabaseSetup``/``DatabaseSetupConfig`` API no
        longer exists; setup.py is function-based, so this exercises
        ``get_db_config`` instead.
        """
        from src.database.setup import get_db_config
        from src.database.snowflake_analytics_connector import (
            SnowflakeAnalyticsConnector,
        )

        monkeypatch.delenv("TESTING", raising=False)

        # Function-based setup configuration.
        prod_config = get_db_config(testing=False)
        assert prod_config["database"] == "neuronews_dev"
        test_config = get_db_config(testing=True)
        assert test_config["database"] == "neuronews_test"

        # Analytics connector integrates on top of the configured database.
        connector = SnowflakeAnalyticsConnector(_snowflake_config())
        assert connector.connect() is True
        summary = connector.get_analytics_summary()
        assert summary["connection_status"] == "connected"

    @pytest.mark.asyncio
    async def test_batch_processing_integration(self):
        """Batch validate, batch-store and batch-index a set of articles."""
        from src.database.data_validation_pipeline import DataValidationPipeline
        from src.database.s3_storage import S3Storage
        from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager
        from src.database.snowflake_analytics_connector import (
            SnowflakeAnalyticsConnector,
        )

        validator = DataValidationPipeline(_reputation_config())
        s3_storage = S3Storage(bucket_name="batch-test-bucket")
        dynamodb_manager = DynamoDBMetadataManager("integration-test-table")

        # Distinct vocabulary per article so the duplicate detector does not
        # reject later items in the batch.
        vocab = [
            f"{a}{b}{c}{d}"
            for a in "bcdfghjk"
            for b in "aeiou"
            for c in "mnprs"
            for d in "tkl"
        ]
        articles = []
        for i in range(5):
            words = vocab[i * 6:(i + 1) * 6]
            articles.append(
                {
                    "id": f"batch_integration_{i}",
                    "title": " ".join(w.capitalize() for w in words[:5]),
                    "content": " ".join(words * 6) + " completed.",
                    "source": "trusted.com",
                    "url": f"https://trusted.com/batch-{i}",
                    "published_date": "2024-01-15T10:30:00Z",
                }
            )

        validation_results = validator.batch_validate_articles(articles)
        assert len(validation_results) == 5
        assert all(r.is_valid for r in validation_results)

        for result in validation_results:
            s3_storage.upload_article(result.cleaned_data)

        batch_result = await dynamodb_manager.batch_index_articles(articles)
        assert batch_result["indexed_count"] == 5

        connector = SnowflakeAnalyticsConnector(_snowflake_config())
        connector.connect()
        assert connector.bulk_insert("articles", articles) == 5

        assert len(self.mock_s3_client.objects) == 5
        assert len(self.mock_dynamodb_table.items) == 5

    @pytest.mark.asyncio
    async def test_real_time_processing_integration(self):
        """Real-time path: index in DynamoDB and store in S3 per article."""
        from src.database.s3_storage import S3Storage
        from src.database.dynamodb_metadata_manager import (
            DynamoDBMetadataManager,
            ArticleMetadataIndex,
        )

        s3_storage = S3Storage(bucket_name="realtime-test-bucket")
        dynamodb_manager = DynamoDBMetadataManager("integration-test-table")

        article = {
            "id": f"realtime_{datetime.now().microsecond}",
            "title": "Real-time Processing Test",
            "content": _article_body(1),
            "source": "trusted.com",
            "url": "https://trusted.com/realtime",
            "published_date": "2024-01-15T10:30:00Z",
        }

        index = await dynamodb_manager.index_article_metadata(article)
        assert isinstance(index, ArticleMetadataIndex)

        s3_key = s3_storage.upload_article(article)
        assert isinstance(s3_key, str)

        assert article["id"] in self.mock_dynamodb_table.items
        assert len(self.mock_s3_client.objects) == 1

    @pytest.mark.asyncio
    async def test_monitoring_and_health_checks(self):
        """Health/monitoring surfaces across S3, DynamoDB and Snowflake."""
        from src.database.s3_storage import S3Storage
        from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager
        from src.database.snowflake_analytics_connector import (
            SnowflakeAnalyticsConnector,
        )

        s3_storage = S3Storage(bucket_name="health-check-bucket")
        dynamodb_manager = DynamoDBMetadataManager("integration-test-table")
        connector = SnowflakeAnalyticsConnector(_snowflake_config())

        # S3: storage statistics (async) returns a dict.
        s3_stats = await s3_storage.get_storage_statistics()
        assert isinstance(s3_stats, dict)

        # DynamoDB: health_check (async) reports a status.
        dynamo_health = await dynamodb_manager.health_check()
        assert isinstance(dynamo_health, dict)
        assert "status" in dynamo_health

        # Snowflake: analytics summary reflects the connection state.
        connector.connect()
        summary = connector.get_analytics_summary()
        assert summary["connection_status"] == "connected"

    @pytest.mark.asyncio
    async def test_performance_optimization_integration(self):
        """Bulk operations across Snowflake and S3 for a larger dataset."""
        from src.database.s3_storage import S3Storage
        from src.database.snowflake_analytics_connector import (
            SnowflakeAnalyticsConnector,
        )

        s3_storage = S3Storage(bucket_name="performance-test-bucket")
        connector = SnowflakeAnalyticsConnector(_snowflake_config())
        connector.connect()

        test_data = [
            {
                "id": f"perf_test_{i}",
                "title": f"Performance Test {i}",
                "content": _article_body(i),
                "source": "trusted.com",
                "url": f"https://trusted.com/perf-{i}",
                "published_date": "2024-01-15T10:30:00Z",
            }
            for i in range(20)
        ]

        # Bulk insert into Snowflake.
        inserted = connector.bulk_insert("articles", test_data)
        assert inserted == 20

        # Per-article S3 upload.
        for article in test_data:
            s3_storage.upload_article(article)
        assert len(self.mock_s3_client.objects) == 20
