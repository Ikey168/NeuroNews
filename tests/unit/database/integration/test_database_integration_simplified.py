"""
Comprehensive Database Integration Tests for Issue #417 - Simplified Version

This module provides complete test coverage for all database modules in
src/database/ to achieve solid test coverage for the database layer.

This simplified version focuses on testing the *current* database module APIs
and covering a broad set of functional paths.
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from typing import Any, Dict, List, Optional

import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ``src.database.setup`` does ``import asyncpg`` at module load time. asyncpg is
# an optional dependency that may be absent in the test environment, so provide a
# lightweight stub before that module is imported. This keeps collection and the
# setup tests running (the connection is patched per-test) without weakening any
# assertion.
if "asyncpg" not in sys.modules:
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        _asyncpg_stub = types.ModuleType("asyncpg")
        _asyncpg_stub.Connection = type("Connection", (), {})
        _asyncpg_stub.connect = lambda *a, **k: None
        sys.modules["asyncpg"] = _asyncpg_stub

# Guard the remaining optional cloud dependencies so collection never crashes
# when they are absent.
try:  # boto3 backs the S3 / DynamoDB client factories
    import boto3  # noqa: F401
    HAS_BOTO3 = True
except ImportError:  # pragma: no cover - environment dependent
    HAS_BOTO3 = False

# Reputation thresholds the current SourceReputationConfig analyzer expects. It
# reads the "trusted"/"reliable"/"questionable"/"unreliable" keys.
REPUTATION_THRESHOLDS = {
    "trusted": 0.9,
    "reliable": 0.7,
    "questionable": 0.4,
    "unreliable": 0.2,
}


# =============================================================================
# Mock Classes for External Dependencies
# =============================================================================

class MockPostgresConnection:
    """Mock PostgreSQL connection for testing."""

    def __init__(self, config=None):
        self.config = config or {}
        self.closed = False

    def cursor(self, cursor_factory=None):
        return MockCursor()

    def commit(self):
        return True

    def rollback(self):
        return True

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class MockCursor:
    """Mock database cursor for testing."""

    def __init__(self):
        self.results = [{"id": 1, "title": "Test Article"}]
        self.current_query = None

    def execute(self, query, params=None):
        self.current_query = query
        if "information_schema.tables" in query:
            # setup_test_database selects table_name and reads row[0]; the
            # default psycopg2 cursor yields plain tuples, not dict rows.
            self.results = [("articles",), ("api_keys",)]
        elif "INSERT" in query.upper() and "RETURNING" in query.upper():
            self.results = [{"id": 1}]

    def fetchone(self):
        return self.results[0] if self.results else None

    def fetchall(self):
        return self.results

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockS3Client:
    """Mock S3 client for testing."""

    def __init__(self):
        self.buckets = {"test-bucket": True}
        self.objects = {}

    def head_bucket(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_bucket_versioning(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_bucket_lifecycle_configuration(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_bucket_encryption(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def create_bucket(self, Bucket, **kwargs):
        self.buckets[Bucket] = True
        return {"Location": f"/{Bucket}"}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[f"{Bucket}/{Key}"] = Body
        return {"ETag": f'"{uuid.uuid4()}"'}

    def get_object(self, Bucket, Key):
        key_path = f"{Bucket}/{Key}"
        if key_path not in self.objects:
            raise Exception("Object not found")
        return {"Body": MockS3Object(self.objects[key_path])}

    def delete_object(self, Bucket, Key):
        key_path = f"{Bucket}/{Key}"
        if key_path in self.objects:
            del self.objects[key_path]
        return {"DeleteMarker": False}


class MockS3Object:
    """Mock S3 object body."""

    def __init__(self, content):
        self.content = content if isinstance(content, bytes) else str(content).encode("utf-8")

    def read(self):
        return self.content


class MockDynamoDBTable:
    """Mock DynamoDB table mirroring the boto3 resource Table surface."""

    def __init__(self, table_name):
        self.table_name = table_name
        self.items = {}
        # The manager calls self.table.meta.client.describe_table(...) on init to
        # detect whether the table already exists; returning a value (rather than
        # raising) makes it treat the table as existing and skip creation.
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
        return {"Items": list(self.items.values())[:10], "Count": len(self.items)}

    def scan(self, **kwargs):
        return {"Items": list(self.items.values()), "Count": len(self.items)}

    def delete_item(self, Key, **kwargs):
        key_value = list(Key.values())[0]
        if key_value in self.items:
            del self.items[key_value]
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


# =============================================================================
# Test Classes for Database Setup Module
# =============================================================================

class TestDatabaseSetup:
    """Test database setup and connection management."""

    def test_get_db_config_production(self, monkeypatch):
        """Test production database configuration."""
        from src.database.setup import get_db_config

        # The test conftest sets TESTING=true globally; clear it so the
        # production (non-testing) branch is exercised.
        monkeypatch.delenv("TESTING", raising=False)

        config = get_db_config(testing=False)

        assert isinstance(config, dict)
        assert "host" in config
        assert "port" in config
        assert "database" in config
        assert "user" in config
        assert "password" in config
        assert config["database"] == "neuronews_dev"

    def test_get_db_config_testing(self):
        """Test testing database configuration."""
        from src.database.setup import get_db_config

        config = get_db_config(testing=True)

        assert isinstance(config, dict)
        assert config["database"] == "neuronews_test"
        assert config["host"] == "test-postgres"

    def test_get_sync_connection_success(self):
        """Test successful synchronous connection."""
        from src.database.setup import get_sync_connection

        with patch("src.database.setup.psycopg2") as mock_psycopg2:
            mock_psycopg2.connect.return_value = MockPostgresConnection()

            conn = get_sync_connection(testing=True)

            assert conn is not None
            mock_psycopg2.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_async_connection_success(self):
        """Test successful asynchronous connection."""
        from src.database.setup import get_async_connection

        with patch("src.database.setup.asyncpg") as mock_asyncpg:
            mock_asyncpg.connect = AsyncMock(return_value=MockPostgresConnection())

            conn = await get_async_connection(testing=True)

            assert conn is not None
            mock_asyncpg.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_setup_test_database(self):
        """Test test database setup."""
        from src.database.setup import setup_test_database

        with patch("src.database.setup.psycopg2") as mock_psycopg2:
            mock_psycopg2.OperationalError = Exception
            # The readiness probe closes its connection, then a fresh connection
            # is used for the real work, so yield a new connection per call.
            mock_psycopg2.connect.side_effect = (
                lambda *a, **k: MockPostgresConnection()
            )

            with patch("asyncio.sleep"):  # speed up retry logic
                await setup_test_database()

            assert mock_psycopg2.connect.called

    @pytest.mark.asyncio
    async def test_cleanup_test_database(self):
        """Test test database cleanup."""
        from src.database.setup import cleanup_test_database

        with patch("src.database.setup.psycopg2") as mock_psycopg2:
            mock_psycopg2.connect.return_value = MockPostgresConnection()

            await cleanup_test_database()

            assert mock_psycopg2.connect.called

    def test_create_test_articles(self):
        """Test test article creation."""
        from src.database.setup import create_test_articles

        with patch("src.database.setup.psycopg2") as mock_psycopg2:
            mock_psycopg2.connect.return_value = MockPostgresConnection()

            article_ids = create_test_articles(count=5)

            assert len(article_ids) == 5
            assert all(isinstance(aid, str) for aid in article_ids)


# =============================================================================
# Test Classes for S3 Storage Module
# =============================================================================

@pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed")
class TestS3Storage:
    """Test S3 storage operations and metadata management."""

    @pytest.fixture
    def mock_s3_client(self):
        client = MockS3Client()
        # Patch the factory the storage module actually calls so initialization
        # (head_bucket) and uploads use our in-memory mock.
        with patch("src.database.s3_storage.get_client", return_value=client):
            yield client

    def test_s3_storage_config_creation(self):
        """Test S3 storage configuration creation."""
        from src.database.s3_storage import S3StorageConfig

        config = S3StorageConfig(bucket_name="test-bucket")

        assert config.bucket_name == "test-bucket"
        assert config.region == "us-east-1"
        assert hasattr(config, "raw_prefix")
        assert hasattr(config, "processed_prefix")

    def test_s3_article_metadata_creation(self):
        """Test article metadata creation."""
        from src.database.s3_storage import ArticleMetadata, ArticleType

        metadata = ArticleMetadata(
            article_id="test-123",
            source="test-source",
            url="https://example.com/article",
            title="Test Article",
            published_date="2024-01-01",
            scraped_date="2024-01-01",
            content_hash="abc123",
            file_size=1024,
            s3_key="test/key.json",
            article_type=ArticleType.RAW,
        )

        assert metadata.article_id == "test-123"
        assert metadata.article_type == ArticleType.RAW
        assert metadata.file_size == 1024

    def test_s3_storage_initialization(self, mock_s3_client):
        """Test S3 storage initialization."""
        from src.database.s3_storage import S3Storage

        storage = S3Storage(
            bucket_name="test-bucket",
            aws_region="us-west-2",
            prefix="test_articles",
        )

        assert storage.bucket_name == "test-bucket"
        assert storage.prefix == "test_articles"
        assert hasattr(storage, "config")
        assert storage.config.bucket_name == "test-bucket"

    def test_s3_article_upload(self, mock_s3_client):
        """Test S3 article upload."""
        from src.database.s3_storage import S3Storage

        storage = S3Storage(bucket_name="test-bucket")

        article = {
            "title": "Test Article",
            "content": "Test content for the article",
            "source": "test-source",
            "url": "https://example.com/article",
            "published_date": "2024-01-01",
        }

        s3_key = storage.upload_article(article)

        assert isinstance(s3_key, str)
        assert len(s3_key) > 0
        assert f"test-bucket/{s3_key}" in mock_s3_client.objects

    def test_s3_legacy_key_generation(self, mock_s3_client):
        """Test S3 key generation."""
        from src.database.s3_storage import S3Storage

        storage = S3Storage(bucket_name="test-bucket")

        article = {
            "title": "Test Article",
            "content": "Test content",
            "source": "test-source",
            "published_date": "2024-01-01",
        }

        s3_key = storage._generate_s3_key(article)

        assert isinstance(s3_key, str)
        assert "test-source" in s3_key
        assert "2024" in s3_key


# =============================================================================
# Test Classes for DynamoDB Metadata Manager
# =============================================================================

@pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed")
class TestDynamoDBMetadataManager:
    """Test DynamoDB metadata indexing and search operations."""

    @pytest.fixture
    def mock_dynamodb_resource(self):
        mock_table = MockDynamoDBTable("test-table")
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        with patch(
            "src.database.dynamodb_metadata_manager.get_resource",
            return_value=mock_resource,
        ), patch(
            "src.database.dynamodb_metadata_manager.get_client",
            return_value=MagicMock(),
        ):
            yield mock_table

    def test_dynamodb_metadata_index_creation(self):
        """Test article metadata index creation."""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        metadata = ArticleMetadataIndex(
            article_id="test-123",
            title="Test Article",
            source="test-source",
            published_date="2024-01-01",
            url="https://example.com/article",
            content_hash="abc123",
            tags=["tech", "news"],
        )

        assert metadata.article_id == "test-123"
        assert metadata.title == "Test Article"
        assert "tech" in metadata.tags

    def test_dynamodb_manager_initialization(self, mock_dynamodb_resource):
        """Test DynamoDB manager initialization."""
        from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager

        manager = DynamoDBMetadataManager("test-table")

        assert manager.table_name == "test-table"
        assert hasattr(manager, "table")
        assert manager.table is mock_dynamodb_resource

    @pytest.mark.asyncio
    async def test_dynamodb_article_indexing(self, mock_dynamodb_resource):
        """Test article metadata indexing."""
        from src.database.dynamodb_metadata_manager import (
            DynamoDBMetadataManager,
            ArticleMetadataIndex,
        )

        manager = DynamoDBMetadataManager("test-table")

        article = {
            "id": "test-123",
            "title": "Test Article",
            "source": "test-source",
            "published_date": "2024-01-01",
            "url": "https://example.com/article",
            "tags": ["tech"],
            "content": "Test preview",
        }

        result = await manager.index_article_metadata(article)

        assert isinstance(result, ArticleMetadataIndex)
        assert result.article_id == "test-123"
        assert "test-123" in mock_dynamodb_resource.items


# =============================================================================
# Test Classes for Data Validation Pipeline
# =============================================================================

def _reputation_config(trusted=None, questionable=None, banned=None):
    """Build a SourceReputationConfig with the keys the current analyzer reads."""
    from src.database.data_validation_pipeline import SourceReputationConfig

    return SourceReputationConfig(
        trusted_domains=trusted or [],
        questionable_domains=questionable or [],
        banned_domains=banned or [],
        reputation_thresholds=dict(REPUTATION_THRESHOLDS),
    )


class TestDataValidationPipeline:
    """Test data validation and cleaning operations."""

    def test_source_reputation_config_creation(self):
        """Test source reputation configuration."""
        from src.database.data_validation_pipeline import SourceReputationConfig

        config = SourceReputationConfig(
            trusted_domains=["trusted.com"],
            questionable_domains=["questionable.com"],
            banned_domains=["banned.com"],
            reputation_thresholds={"trusted": 0.9, "reliable": 0.7},
        )

        assert "trusted.com" in config.trusted_domains
        assert "banned.com" in config.banned_domains
        assert config.reputation_thresholds["trusted"] == 0.9

    def test_validation_result_creation(self):
        """Test validation result creation."""
        from src.database.data_validation_pipeline import ValidationResult

        result = ValidationResult(
            score=0.85,
            is_valid=True,
            issues=[],
            warnings=["Minor warning"],
            cleaned_data={"title": "Clean Title"},
        )

        assert result.score == 0.85
        assert result.is_valid
        assert len(result.warnings) == 1
        assert result.cleaned_data["title"] == "Clean Title"

    def test_html_cleaner_initialization(self):
        """Test HTML cleaner initialization."""
        from src.database.data_validation_pipeline import HTMLCleaner

        cleaner = HTMLCleaner()

        assert hasattr(cleaner, "clean_content")
        assert hasattr(cleaner, "clean_title")

    def test_html_content_cleaning(self):
        """Test HTML content cleaning."""
        from src.database.data_validation_pipeline import HTMLCleaner

        cleaner = HTMLCleaner()

        dirty_html = "<script>alert('xss')</script><p>Clean content &amp; more</p>"
        clean_content = cleaner.clean_content(dirty_html)

        assert "<script>" not in clean_content
        assert "Clean content" in clean_content

    def test_duplicate_detector_initialization(self):
        """Test duplicate detector initialization."""
        from src.database.data_validation_pipeline import DuplicateDetector

        detector = DuplicateDetector()

        assert hasattr(detector, "is_duplicate")
        # The current detector tracks seen content via these caches.
        assert hasattr(detector, "title_cache")
        assert hasattr(detector, "content_hashes")

    def test_content_validator_initialization(self):
        """Test content validator initialization."""
        from src.database.data_validation_pipeline import ContentValidator

        validator = ContentValidator()

        assert hasattr(validator, "validate_content")

    def test_data_validation_pipeline_initialization(self):
        """Test data validation pipeline initialization."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        pipeline = DataValidationPipeline(_reputation_config(trusted=["trusted.com"]))

        assert hasattr(pipeline, "html_cleaner")
        assert hasattr(pipeline, "duplicate_detector")
        assert hasattr(pipeline, "source_analyzer")
        assert hasattr(pipeline, "content_validator")
        assert pipeline.processed_count == 0

    def test_article_processing(self):
        """Test article processing through pipeline."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        pipeline = DataValidationPipeline(_reputation_config(trusted=["trusted.com"]))

        article = {
            "title": "Test Article Title",
            "content": (
                "Detailed coverage about the subject with enough words to clear "
                "the validation threshold for word count and length requirements "
                "set by the validator system."
            ),
            "url": "https://trusted.com/article",
            "author": "Test Author",
            "published_date": "2024-01-01T12:00:00Z",
            "source": "trusted.com",
        }

        result = pipeline.process_article(article)

        # A valid article yields a ValidationResult with a score.
        assert result is not None
        assert hasattr(result, "score")
        assert pipeline.processed_count == 1


# =============================================================================
# Test Classes for Snowflake Integration
# =============================================================================

class TestSnowflakeIntegration:
    """Test Snowflake analytics connector and data loading."""

    @staticmethod
    def _make_config():
        from src.database.snowflake_analytics_connector import SnowflakeConfig

        return SnowflakeConfig(
            account="test-account",
            user="test-user",
            password="test-password",
            warehouse="test-warehouse",
            database="test-database",
            schema="test-schema",
        )

    def test_snowflake_config_creation(self):
        """Test Snowflake configuration creation."""
        config = self._make_config()

        assert config.account == "test-account"
        assert config.warehouse == "test-warehouse"

    def test_snowflake_connector_initialization(self):
        """Test Snowflake connector initialization."""
        from src.database.snowflake_analytics_connector import (
            SnowflakeAnalyticsConnector,
        )

        config = self._make_config()
        connector = SnowflakeAnalyticsConnector(config)

        assert connector.config == config
        assert hasattr(connector, "connection")


# =============================================================================
# Test Classes for DynamoDB Pipeline Integration
# =============================================================================

class TestDynamoDBPipelineIntegration:
    """Test DynamoDB pipeline integration."""

    def test_pipeline_config_creation(self):
        """Test pipeline configuration creation."""
        from src.database.dynamodb_pipeline_integration import DynamoDBMetadataConfig

        config = DynamoDBMetadataConfig(
            table_name="test-table",
            region="us-east-1",
            batch_size=25,
        )

        assert config.table_name == "test-table"
        assert config.batch_size == 25

    def test_pipeline_processor_initialization(self):
        """Test pipeline processor initialization."""
        from src.database.dynamodb_pipeline_integration import (
            DynamoDBMetadataPipeline,
            DynamoDBMetadataConfig,
        )

        config = DynamoDBMetadataConfig(
            table_name="test-table",
            region="us-east-1",
        )

        # The pipeline lazily builds its manager (which needs AWS access), so
        # patch the client factories to avoid any real network calls.
        with patch(
            "src.database.dynamodb_metadata_manager.get_resource",
            return_value=MagicMock(),
        ), patch(
            "src.database.dynamodb_metadata_manager.get_client",
            return_value=MagicMock(),
        ):
            pipeline = DynamoDBMetadataPipeline(config)

        assert pipeline.config == config
        assert hasattr(pipeline, "manager")


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed")
class TestDatabaseIntegration:
    """Test end-to-end database integration scenarios."""

    def test_basic_article_workflow(self):
        """Test basic article workflow across database modules."""
        from src.database.data_validation_pipeline import DataValidationPipeline
        from src.database.s3_storage import S3Storage

        pipeline = DataValidationPipeline(_reputation_config(trusted=["trusted.com"]))

        with patch(
            "src.database.s3_storage.get_client", return_value=MockS3Client()
        ):
            storage = S3Storage(bucket_name="test-bucket")

            article = {
                "title": "Test Integration Article",
                "content": (
                    "This is comprehensive test content for integration testing "
                    "with enough words to clear the validation thresholds for "
                    "word count and overall content length requirements."
                ),
                "source": "trusted.com",
                "url": "https://trusted.com/article",
                "published_date": "2024-01-01T12:00:00Z",
            }

            # Step 1: Process through validation pipeline
            validation_result = pipeline.process_article(article)

            # Step 2: If valid, upload cleaned data to S3
            if validation_result and validation_result.is_valid:
                s3_key = storage.upload_article(validation_result.cleaned_data)
                assert isinstance(s3_key, str)

            # Workflow completed and the article was counted as processed
            assert pipeline.processed_count == 1

    def test_error_handling_resilience(self):
        """Test error handling and system resilience."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        pipeline = DataValidationPipeline(_reputation_config(banned=["banned.com"]))

        # A non-dict article is rejected before processing; it returns None and
        # is not counted as a processed article.
        result = pipeline.process_article(None)
        assert result is None
        assert pipeline.processed_count == 0

        # An empty article dict is likewise rejected and not counted.
        result = pipeline.process_article({})
        assert result is None
        assert pipeline.processed_count == 0


# =============================================================================
# Performance Tests
# =============================================================================

class TestDatabasePerformance:
    """Test database performance and scalability."""

    def test_validation_performance(self):
        """Test validation pipeline performance."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        pipeline = DataValidationPipeline(_reputation_config(trusted=["trusted.com"]))

        # Unique vocabulary so each article's title and body are distinct and the
        # duplicate detector does not reject later items in the batch.
        vocab = [
            f"{a}{b}{c}{d}"
            for a in "bcdfghjk"
            for b in "aeiou"
            for c in "mnprs"
            for d in "tkl"
        ]
        articles = []
        for i in range(10):
            words = vocab[i * 6:(i + 1) * 6]
            articles.append(
                {
                    "title": " ".join(w.capitalize() for w in words[:5]),
                    "content": " ".join(words * 6) + " completed.",
                    "source": "trusted.com",
                    "url": f"https://trusted.com/article-{i}",
                    "published_date": "2024-01-01T12:00:00Z",
                }
            )

        import time

        start_time = time.time()

        results = [pipeline.process_article(article) for article in articles]

        processing_time = time.time() - start_time

        assert len(results) == 10
        assert all(r is not None for r in results)
        assert pipeline.processed_count == 10
        assert processing_time < 10.0  # Should be fast


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
