"""
Comprehensive Database Integration Tests for Issue #417

This module provides test coverage for the database modules in src/database/.
The tests are aligned to the CURRENT source APIs:

Modules covered:
- setup.py: Database connection management and setup
- s3_storage.py: S3 storage operations (S3Storage legacy interface)
- dynamodb_metadata_manager.py: DynamoDB article metadata indexing
- data_validation_pipeline.py: Data validation and cleaning
- snowflake_analytics_connector.py: Snowflake analytics integration

Features:
- Mock-based testing for CI/CD compatibility
- Optional-dependency imports (asyncpg, snowflake) are stubbed so the
  source modules import cleanly without the real packages installed.
"""

import json
import logging
import sys
import types
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Optional-dependency stubs
#
# src/database/setup.py imports ``asyncpg`` at module top level, which is an
# optional dependency that may not be installed in the test environment.
# Stub it (and ``snowflake``) so importing the source modules never crashes
# collection. The stubs are only installed if the real package is absent.
# =============================================================================

def _ensure_module(name: str) -> None:
    try:
        __import__(name)
    except ImportError:
        module = types.ModuleType(name)
        module.__dict__["connect"] = MagicMock()
        # asyncpg.Connection is referenced as a type annotation in setup.py
        module.__dict__["Connection"] = MagicMock
        sys.modules[name] = module


_ensure_module("asyncpg")


# =============================================================================
# Mock Classes for Database Modules
# =============================================================================

class MockPostgresConnection:
    """Mock PostgreSQL connection for testing."""

    def __init__(self, config=None):
        self.config = config or {}
        self.closed = False
        self.in_transaction = False
        self.autocommit = True

    def cursor(self, cursor_factory=None):
        return MockCursor(cursor_factory=cursor_factory)

    def commit(self):
        if self.closed:
            raise Exception("Connection is closed")
        return True

    def rollback(self):
        if self.closed:
            raise Exception("Connection is closed")
        return True

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class MockCursor:
    """Mock database cursor for testing."""

    def __init__(self, cursor_factory=None):
        self.cursor_factory = cursor_factory
        self.results = []
        self.current_query = None

    def execute(self, query, params=None):
        self.current_query = query
        if "SELECT" in query.upper() and "information_schema" in query:
            # setup.setup_test_database queries for table names; return none
            self.results = []
        elif "SELECT" in query.upper():
            self.results = [{"id": 1, "title": "Test Article", "content": "Test content"}]
        elif "INSERT" in query.upper() and "RETURNING" in query.upper():
            self.results = [{"id": 1}]
        else:
            self.results = []

    def fetchone(self):
        return self.results[0] if self.results else None

    def fetchall(self):
        return self.results

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockS3Body:
    """Mock S3 object body supporting .read()."""

    def __init__(self, content):
        if isinstance(content, str):
            content = content.encode("utf-8")
        self.content = content

    def read(self):
        return self.content


class MockS3Client:
    """Mock S3 client compatible with src.database.s3_storage usage."""

    def __init__(self):
        self.objects = {}

    def head_bucket(self, Bucket, **kwargs):
        # Bucket always "exists" for the mock so _ensure_bucket_exists passes.
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_bucket_versioning(self, Bucket, **kwargs):
        return {}

    def put_bucket_versioning(self, **kwargs):
        return {}

    def put_bucket_encryption(self, **kwargs):
        return {}

    def put_bucket_lifecycle_configuration(self, **kwargs):
        return {}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects["{0}/{1}".format(Bucket, Key)] = Body
        return {"ETag": '"{0}"'.format(uuid.uuid4())}

    def get_object(self, Bucket, Key, **kwargs):
        key_path = "{0}/{1}".format(Bucket, Key)
        if key_path not in self.objects:
            raise Exception("Object {0} not found".format(Key))
        return {"Body": MockS3Body(self.objects[key_path])}

    def delete_object(self, Bucket, Key, **kwargs):
        self.objects.pop("{0}/{1}".format(Bucket, Key), None)
        return {"DeleteMarker": False}


# =============================================================================
# Test Classes for Database Setup Module
# =============================================================================

class TestDatabaseSetup:
    """Test database setup and connection management."""

    @pytest.fixture
    def mock_psycopg2(self):
        with patch("src.database.setup.psycopg2") as mock:
            # Preserve the real OperationalError type for retry logic.
            import psycopg2 as real_psycopg2
            mock.OperationalError = real_psycopg2.OperationalError
            # Return a fresh connection on every connect() so that closing one
            # (e.g. in the readiness probe) does not affect subsequent uses.
            mock.connect.side_effect = lambda *a, **k: MockPostgresConnection()
            yield mock

    @pytest.fixture
    def mock_asyncpg(self):
        with patch("src.database.setup.asyncpg") as mock:
            mock.connect = MagicMock()
            yield mock

    def test_get_db_config_production(self, mock_psycopg2):
        """Test production database configuration."""
        from src.database.setup import get_db_config

        # Ensure TESTING env does not force the test branch.
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("TESTING", None)
            config = get_db_config(testing=False)

        assert isinstance(config, dict)
        assert "host" in config
        assert "port" in config
        assert "database" in config
        assert "user" in config
        assert "password" in config
        # Default production database name from source.
        assert config["database"] == "neuronews_dev"

    def test_get_db_config_testing(self, mock_psycopg2):
        """Test testing database configuration."""
        from src.database.setup import get_db_config

        config = get_db_config(testing=True)

        assert isinstance(config, dict)
        assert config["database"] == "neuronews_test"
        assert config["host"] == "test-postgres"

    def test_get_sync_connection_success(self, mock_psycopg2):
        """Test successful synchronous connection."""
        from src.database.setup import get_sync_connection

        conn = get_sync_connection(testing=True)

        assert conn is not None
        assert isinstance(conn, MockPostgresConnection)
        mock_psycopg2.connect.assert_called_once()

    def test_get_sync_connection_failure(self, mock_psycopg2):
        """Test synchronous connection failure handling."""
        from src.database.setup import get_sync_connection

        mock_psycopg2.connect.side_effect = Exception("Connection failed")

        with pytest.raises(Exception):
            get_sync_connection(testing=True)

    @pytest.mark.asyncio
    async def test_get_async_connection_success(self, mock_asyncpg):
        """Test successful asynchronous connection."""
        from src.database.setup import get_async_connection

        sentinel = object()

        async def fake_connect(**kwargs):
            return sentinel

        mock_asyncpg.connect = fake_connect

        conn = await get_async_connection(testing=True)

        assert conn is sentinel

    @pytest.mark.asyncio
    async def test_get_async_connection_failure(self, mock_asyncpg):
        """Test asynchronous connection failure handling."""
        from src.database.setup import get_async_connection

        async def fake_connect(**kwargs):
            raise Exception("Connection failed")

        mock_asyncpg.connect = fake_connect

        with pytest.raises(Exception):
            await get_async_connection(testing=True)

    @pytest.mark.asyncio
    async def test_setup_test_database_success(self, mock_psycopg2):
        """Test successful test database setup."""
        from src.database.setup import setup_test_database

        await setup_test_database()

        # Verify connection was attempted.
        mock_psycopg2.connect.assert_called()

    @pytest.mark.asyncio
    async def test_setup_test_database_retry_logic(self, mock_psycopg2):
        """Test database setup retry logic on OperationalError."""
        from src.database.setup import setup_test_database

        # First few calls fail with OperationalError, then succeed.
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise mock_psycopg2.OperationalError("Connection failed")
            return MockPostgresConnection()

        mock_psycopg2.connect.side_effect = side_effect

        # Patch sleep so the retry loop does not actually wait.
        with patch("src.database.setup.asyncio.sleep", new=_async_noop):
            await setup_test_database()

        assert call_count[0] >= 3

    @pytest.mark.asyncio
    async def test_cleanup_test_database(self, mock_psycopg2):
        """Test test database cleanup."""
        from src.database.setup import cleanup_test_database

        await cleanup_test_database()

        mock_psycopg2.connect.assert_called()

    def test_create_test_articles_success(self, mock_psycopg2):
        """Test successful test article creation."""
        from src.database.setup import create_test_articles

        article_ids = create_test_articles(count=5)

        assert len(article_ids) == 5
        assert all(isinstance(aid, str) for aid in article_ids)

    def test_create_test_articles_failure(self, mock_psycopg2):
        """Test test article creation failure handling."""
        from src.database.setup import create_test_articles

        mock_psycopg2.connect.side_effect = Exception("Database error")

        with pytest.raises(Exception):
            create_test_articles(count=5)


async def _async_noop(*args, **kwargs):
    return None


# =============================================================================
# Test Classes for S3 Storage Module
# =============================================================================

class TestS3Storage:
    """Test S3 storage operations via the legacy S3Storage interface."""

    @pytest.fixture
    def mock_s3_client(self):
        client = MockS3Client()
        with patch("src.database.s3_storage.get_client", return_value=client):
            yield client

    def test_s3_storage_initialization(self, mock_s3_client):
        """Test S3 storage class initialization."""
        from src.database.s3_storage import S3Storage

        storage = S3Storage("test-bucket")

        assert storage.config.bucket_name == "test-bucket"
        assert hasattr(storage, "s3_client")
        assert storage.s3_client is mock_s3_client

    def test_s3_article_upload(self, mock_s3_client):
        """Test article upload to S3 (returns the generated S3 key)."""
        from src.database.s3_storage import S3Storage

        storage = S3Storage("test-bucket")

        article_data = {
            "id": "test-123",
            "title": "Test Article",
            "content": "Test content",
            "url": "https://example.com/article",
            "source": "test-source",
            "published_date": "2024-01-01",
        }

        s3_key = storage.upload_article(article_data)

        assert isinstance(s3_key, str)
        assert s3_key.endswith(".json")
        # The object was stored in the mock S3 client.
        assert "test-bucket/{0}".format(s3_key) in mock_s3_client.objects

    def test_s3_article_download(self, mock_s3_client):
        """Test article download from S3 via get_article."""
        from src.database.s3_storage import S3Storage

        storage = S3Storage("test-bucket")

        article_data = {
            "id": "test-123",
            "title": "Test Article",
            "content": "Test content",
            "source": "test-source",
        }

        # Upload first so the object exists, then read it back.
        s3_key = storage.upload_article(article_data)
        result = storage.get_article(s3_key)

        assert result is not None
        assert result["title"] == "Test Article"

    def test_s3_article_deletion(self, mock_s3_client):
        """Test article deletion from S3."""
        from src.database.s3_storage import S3Storage

        storage = S3Storage("test-bucket")

        article_data = {
            "title": "Test Article",
            "content": "Test content",
            "source": "test-source",
        }
        s3_key = storage.upload_article(article_data)
        assert "test-bucket/{0}".format(s3_key) in mock_s3_client.objects

        # delete_article returns None but removes the object.
        storage.delete_article(s3_key)
        assert "test-bucket/{0}".format(s3_key) not in mock_s3_client.objects

    def test_s3_error_handling(self, mock_s3_client):
        """Test S3 error handling for missing required fields."""
        from src.database.s3_storage import S3Storage

        storage = S3Storage("test-bucket")

        # Missing required 'content' and 'source' fields should raise ValueError.
        article_data = {"id": "test", "title": "Test"}

        with pytest.raises(ValueError):
            storage.upload_article(article_data)


# =============================================================================
# Test Classes for DynamoDB Metadata Manager
# =============================================================================

@pytest.fixture
def patched_dynamodb_manager():
    """Provide a DynamoDBMetadataManager with mocked boto3 resource/client.

    The manager looks up a table via get_resource().Table(); we make
    describe_table succeed so _initialize_table uses the existing table.
    """
    from src.database import dynamodb_metadata_manager as ddb_module

    mock_table = MagicMock()
    # _initialize_table calls table.meta.client.describe_table(...) - succeed.
    mock_table.meta.client.describe_table.return_value = {"Table": {}}

    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    with patch.object(ddb_module, "get_resource", return_value=mock_resource), \
            patch.object(ddb_module, "get_client", return_value=MagicMock()):
        manager = ddb_module.DynamoDBMetadataManager("test-table")
        manager._mock_table = mock_table
        yield manager


class TestDynamoDBMetadataManager:
    """Test DynamoDB metadata indexing and search operations."""

    def test_dynamodb_manager_initialization(self, patched_dynamodb_manager):
        """Test DynamoDB manager initialization."""
        manager = patched_dynamodb_manager

        assert manager.table_name == "test-table"
        assert manager.table is not None

    @pytest.mark.asyncio
    async def test_dynamodb_article_indexing(self, patched_dynamodb_manager):
        """Test article metadata indexing in DynamoDB."""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        manager = patched_dynamodb_manager

        article_data = {
            "id": "test-123",
            "title": "Test Article",
            "source": "test-source",
            "published_date": "2024-01-01",
            "tags": ["tech", "news"],
            "content": "Test content preview",
        }

        result = await manager.index_article_metadata(article_data)

        assert isinstance(result, ArticleMetadataIndex)
        assert result.article_id == "test-123"
        manager._mock_table.put_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_dynamodb_article_search_by_source(self, patched_dynamodb_manager):
        """Test article search by source in DynamoDB."""
        from src.database.dynamodb_metadata_manager import QueryResult

        manager = patched_dynamodb_manager
        manager._mock_table.query.return_value = {"Items": []}

        result = await manager.get_articles_by_source("test-source")

        assert isinstance(result, QueryResult)
        assert isinstance(result.items, list)

    @pytest.mark.asyncio
    async def test_dynamodb_article_search_by_date_range(self, patched_dynamodb_manager):
        """Test article search by date range in DynamoDB."""
        from src.database.dynamodb_metadata_manager import QueryResult

        manager = patched_dynamodb_manager
        manager._mock_table.scan.return_value = {"Items": []}

        result = await manager.get_articles_by_date_range("2024-01-01", "2024-12-31")

        assert isinstance(result, QueryResult)
        assert isinstance(result.items, list)

    @pytest.mark.asyncio
    async def test_dynamodb_fulltext_search(self, patched_dynamodb_manager):
        """Test full-text search in DynamoDB via search_articles."""
        from src.database.dynamodb_metadata_manager import QueryResult, SearchQuery

        manager = patched_dynamodb_manager
        manager._mock_table.scan.return_value = {"Items": []}

        query = SearchQuery(query_text="test query")
        result = await manager.search_articles(query)

        assert isinstance(result, QueryResult)
        assert isinstance(result.items, list)

    @pytest.mark.asyncio
    async def test_dynamodb_batch_indexing(self, patched_dynamodb_manager):
        """Test batch article indexing in DynamoDB."""
        manager = patched_dynamodb_manager
        # batch_index_articles uses table.batch_writer() as a context manager.
        batch_writer = MagicMock()
        manager._mock_table.batch_writer.return_value.__enter__.return_value = batch_writer

        articles = [
            {
                "id": "test-{0}".format(i),
                "title": "Article {0}".format(i),
                "source": "test-source",
                "published_date": "2024-01-01",
                "tags": ["tech"],
                "content": "Preview {0}".format(i),
            }
            for i in range(5)
        ]

        result = await manager.batch_index_articles(articles)

        assert result is not None
        assert result["indexed_count"] == 5
        assert result["failed_count"] == 0

    @pytest.mark.asyncio
    async def test_dynamodb_article_deletion(self, patched_dynamodb_manager):
        """Test article metadata deletion from DynamoDB."""
        manager = patched_dynamodb_manager
        manager._mock_table.delete_item.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

        result = await manager.delete_article_metadata("test-123")

        assert result is True
        manager._mock_table.delete_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_dynamodb_error_handling(self, patched_dynamodb_manager):
        """Test DynamoDB error handling when put_item fails."""
        manager = patched_dynamodb_manager
        manager._mock_table.put_item.side_effect = Exception("DynamoDB error")

        article_data = {
            "id": "test-err",
            "title": "Test",
            "source": "test-source",
            "published_date": "2024-01-01",
            "content": "content",
        }

        with pytest.raises(Exception):
            await manager.index_article_metadata(article_data)


# =============================================================================
# Test Classes for Data Validation Pipeline
# =============================================================================

_DISTINCT_TOPICS = [
    "Quantum Computing Breakthrough Announced",
    "Renewable Energy Policy Shift Worldwide",
    "Global Financial Markets Rally Sharply",
    "Major Archaeology Discovery In Egypt",
    "Marine Biology Coral Reef Study",
    "Space Telescope Captures Distant Galaxy",
    "New Vaccine Trial Shows Strong Results",
    "Electric Vehicle Adoption Accelerates",
    "Ancient Manuscript Decoded By Scholars",
    "Deep Sea Expedition Finds New Species",
]


def _distinct_articles(count):
    """Build articles with genuinely distinct titles/content/urls.

    The source DuplicateDetector rejects near-identical short titles via
    fuzzy matching, so batch test data must be substantive and unique.
    """
    articles = []
    for i in range(count):
        topic = _DISTINCT_TOPICS[i % len(_DISTINCT_TOPICS)]
        articles.append(
            {
                "id": "test-{0}".format(i),
                "title": "{0} (Report {1})".format(topic, i),
                "content": (
                    "In-depth reporting about {0} with comprehensive analysis and "
                    "many distinct supporting details that make this article "
                    "substantial and unique, item number {1}.".format(topic, i)
                ),
                "url": "https://trusted.com/article-{0}".format(i),
                "source": "trusted.com",
                "published_date": "2024-01-01T12:00:00Z",
            }
        )
    return articles


def _make_config():
    from src.database.data_validation_pipeline import SourceReputationConfig

    return SourceReputationConfig(
        trusted_domains=["trusted.com"],
        questionable_domains=["questionable.com"],
        banned_domains=["banned.com"],
        # The source uses these threshold keys in _get_credibility_level.
        reputation_thresholds={
            "trusted": 0.9,
            "reliable": 0.7,
            "questionable": 0.4,
            "unreliable": 0.2,
        },
    )


class TestDataValidationPipeline:
    """Test data validation and cleaning operations."""

    def test_validation_pipeline_initialization(self):
        """Test validation pipeline initialization."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        config = _make_config()
        pipeline = DataValidationPipeline(config)

        # The pipeline holds the config inside its source_analyzer component.
        assert pipeline.source_analyzer.config == config
        assert hasattr(pipeline, "duplicate_detector")
        assert hasattr(pipeline, "html_cleaner")
        assert hasattr(pipeline, "content_validator")

    def test_article_validation_success(self):
        """Test successful article validation."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        config = _make_config()
        pipeline = DataValidationPipeline(config)

        article = {
            "title": "Test Article Title",
            "content": "This is a test article with sufficient content length for validation.",
            "url": "https://trusted.com/article",
            "author": "Test Author",
            "published_date": "2024-01-01T12:00:00Z",
            "source": "trusted.com",
        }

        result = pipeline.validate_article(article)

        assert result.is_valid
        # Score is on a 0-100 scale in the current source.
        assert result.score > 50
        assert isinstance(result.cleaned_data, dict)

    def test_article_validation_failure(self):
        """Test article validation failure cases (banned domain)."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        config = _make_config()
        pipeline = DataValidationPipeline(config)

        article = {
            "title": "Bad Article",
            "content": "Short",
            "url": "https://banned.com/article",
            "author": "",
            "published_date": "invalid-date",
            "source": "banned.com",
        }

        result = pipeline.validate_article(article)

        assert not result.is_valid
        assert len(result.issues) > 0

    def test_duplicate_detection(self):
        """Test duplicate article detection via the duplicate_detector component."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        config = _make_config()
        pipeline = DataValidationPipeline(config)

        article1 = {
            "title": "Test Article",
            "content": "This is test content for duplicate detection.",
            "url": "https://trusted.com/article1",
        }

        article2 = {
            "title": "Test Article",
            "content": "This is test content for duplicate detection.",
            "url": "https://trusted.com/article2",
        }

        # is_duplicate returns a (bool, reason) tuple.
        is_dup1, _ = pipeline.duplicate_detector.is_duplicate(article1)
        assert not is_dup1

        # Same title/content should now be detected as a duplicate.
        is_dup2, reason2 = pipeline.duplicate_detector.is_duplicate(article2)
        assert is_dup2
        assert reason2 in ("duplicate_title", "duplicate_content", "similar_title")

    def test_content_cleaning(self):
        """Test content cleaning and sanitization via the html_cleaner component."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        config = _make_config()
        pipeline = DataValidationPipeline(config)

        dirty_content = "<script>alert('xss')</script><p>Clean content &amp; more</p>"
        cleaned = pipeline.html_cleaner.clean_content(dirty_content)

        assert "<script>" not in cleaned
        assert "Clean content" in cleaned
        # HTML entities should be decoded (&amp; -> &).
        assert "&amp;" not in cleaned

    def test_source_reputation_scoring(self):
        """Test source reputation scoring via the source_analyzer component."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        config = _make_config()
        pipeline = DataValidationPipeline(config)
        analyzer = pipeline.source_analyzer

        # Trusted domain scores high (0.95 in source).
        score_trusted = analyzer._calculate_reputation_score("trusted.com", "trusted.com")
        assert score_trusted >= 0.9

        # Questionable domain scores below trusted.
        score_questionable = analyzer._calculate_reputation_score(
            "questionable.com", "questionable.com"
        )
        assert score_questionable < 0.9

        # Banned domain scores low (0.1 in source).
        score_banned = analyzer._calculate_reputation_score("banned.com", "banned.com")
        assert score_banned < 0.2

    def test_batch_validation(self):
        """Test batch article validation."""
        from src.database.data_validation_pipeline import DataValidationPipeline

        config = _make_config()
        pipeline = DataValidationPipeline(config)

        articles = _distinct_articles(5)

        results = pipeline.batch_validate_articles(articles)

        assert len(results) == 5
        assert all(result.is_valid for result in results)


# =============================================================================
# Test Classes for Snowflake Integration
# =============================================================================

class TestSnowflakeIntegration:
    """Test Snowflake analytics connector (mock implementation)."""

    def _make_connector(self):
        from src.database.snowflake_analytics_connector import (
            SnowflakeAnalyticsConnector,
            SnowflakeConfig,
        )

        config = SnowflakeConfig(
            account="test-account",
            user="test-user",
            password="test-password",
            warehouse="test-warehouse",
            database="test-database",
            schema="test-schema",
        )
        return SnowflakeAnalyticsConnector(config)

    def test_snowflake_connector_initialization(self):
        """Test Snowflake connector initialization."""
        connector = self._make_connector()

        assert connector.config is not None
        assert connector.config.account == "test-account"
        assert hasattr(connector, "connection")

    def test_snowflake_query_execution(self):
        """Test Snowflake query execution."""
        connector = self._make_connector()
        connector.connect()

        result = connector.execute_query("SELECT COUNT(*) FROM articles")

        assert result is not None
        assert isinstance(result, list)

    def test_snowflake_query_requires_connection(self):
        """Test that executing a query without connecting raises an error."""
        connector = self._make_connector()

        # execute_query raises ConnectionError when not connected.
        with pytest.raises(ConnectionError):
            connector.execute_query("SELECT 1")

    def test_snowflake_analytics_summary(self):
        """Test Snowflake analytics summary operations."""
        connector = self._make_connector()
        connector.connect()

        summary = connector.get_analytics_summary()

        assert summary is not None
        assert summary["connection_status"] == "connected"
        assert summary["database"] == "test-database"

    def test_snowflake_bulk_insert(self):
        """Test Snowflake bulk insert operation."""
        connector = self._make_connector()
        connector.connect()

        data = [
            {"id": 1, "title": "Article 1", "content": "Content 1"},
            {"id": 2, "title": "Article 2", "content": "Content 2"},
        ]

        inserted = connector.bulk_insert("articles", data)

        assert inserted == 2


# =============================================================================
# Integration Tests for Database Pipeline
# =============================================================================

class TestDatabasePipelineIntegration:
    """Test end-to-end database pipeline integration."""

    @pytest.fixture
    def mock_services(self):
        """Mock S3 and DynamoDB services for integration testing."""
        from src.database import s3_storage as s3_module
        from src.database import dynamodb_metadata_manager as ddb_module

        s3_client = MockS3Client()

        mock_table = MagicMock()
        mock_table.meta.client.describe_table.return_value = {"Table": {}}
        mock_table.query.return_value = {"Items": []}
        batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__.return_value = batch_writer
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table

        with patch.object(s3_module, "get_client", return_value=s3_client), \
                patch.object(ddb_module, "get_resource", return_value=mock_resource), \
                patch.object(ddb_module, "get_client", return_value=MagicMock()):
            yield {"s3": s3_client, "dynamodb_table": mock_table}

    @pytest.mark.asyncio
    async def test_end_to_end_article_processing(self, mock_services):
        """Test complete article processing pipeline."""
        from src.database.data_validation_pipeline import DataValidationPipeline
        from src.database.s3_storage import S3Storage
        from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager

        validator = DataValidationPipeline(_make_config())
        s3_storage = S3Storage("test-bucket")
        dynamodb_manager = DynamoDBMetadataManager("test-table")

        article = {
            "id": "test-123",
            "title": "Test Article for Integration",
            "content": "This is a comprehensive test article with sufficient content for validation.",
            "url": "https://trusted.com/test-article",
            "author": "Test Author",
            "source": "trusted.com",
            "published_date": "2024-01-01T12:00:00Z",
            "category": "technology",
        }

        # Step 1: Validate article.
        validation_result = validator.validate_article(article)
        assert validation_result.is_valid

        # Step 2: Store in S3 (returns the generated key).
        s3_key = s3_storage.upload_article(validation_result.cleaned_data)
        assert isinstance(s3_key, str)

        # Step 3: Index in DynamoDB.
        index_result = await dynamodb_manager.index_article_metadata(article)
        assert index_result is not None

        # Step 4: Search and retrieve.
        search_result = await dynamodb_manager.get_articles_by_source("trusted.com")
        assert search_result.count >= 0

    @pytest.mark.asyncio
    async def test_batch_processing(self, mock_services):
        """Test batch processing reliability across components."""
        from src.database.data_validation_pipeline import DataValidationPipeline
        from src.database.s3_storage import S3Storage
        from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager

        validator = DataValidationPipeline(_make_config())
        s3_storage = S3Storage("test-bucket")
        dynamodb_manager = DynamoDBMetadataManager("test-table")

        articles = _distinct_articles(10)

        # Batch validation.
        validation_results = validator.batch_validate_articles(articles)
        assert len(validation_results) == 10
        assert all(result.is_valid for result in validation_results)

        # S3 upload of each valid article.
        valid_articles = [result.cleaned_data for result in validation_results]
        s3_keys = [s3_storage.upload_article(a) for a in valid_articles]
        assert len(s3_keys) == 10
        assert all(isinstance(k, str) for k in s3_keys)

        # Batch DynamoDB indexing.
        index_result = await dynamodb_manager.batch_index_articles(articles)
        assert index_result is not None
        assert index_result["indexed_count"] == 10

    def test_error_recovery_and_resilience(self, mock_services):
        """Test error recovery and system resilience."""
        from src.database.data_validation_pipeline import DataValidationPipeline
        from src.database.s3_storage import S3Storage

        validator = DataValidationPipeline(_make_config())
        s3_storage = S3Storage("test-bucket")

        article = {
            "title": "Test Article",
            "content": "Test content with enough length to pass validation checks.",
            "url": "https://trusted.com/article",
            "source": "trusted.com",
        }

        validation_result = validator.validate_article(article)
        assert validation_result.is_valid

        # Uploading an article missing required fields raises gracefully.
        with pytest.raises(ValueError):
            s3_storage.upload_article({"title": "incomplete"})


# =============================================================================
# Performance and Stress Tests
# =============================================================================

class TestDatabasePerformance:
    """Test database performance and scalability."""

    def test_connection_pool_performance(self):
        """Test repeated synchronous connection creation."""
        from src.database.setup import get_sync_connection

        with patch("src.database.setup.psycopg2") as mock_psycopg2:
            mock_psycopg2.connect.return_value = MockPostgresConnection()

            connections = []
            for _ in range(10):
                conn = get_sync_connection(testing=True)
                connections.append(conn)

            assert len(connections) == 10
            assert all(isinstance(conn, MockPostgresConnection) for conn in connections)

            for conn in connections:
                conn.close()

    def test_large_dataset_validation(self):
        """Test validation performance and behavior with a large dataset.

        The source pipeline runs an aggressive fuzzy duplicate detector, so a
        large batch of near-identical articles is (correctly) rejected as
        duplicates. This test verifies the pipeline scales to 100 articles
        within the time budget, returns one ValidationResult per input, and
        validates genuinely distinct articles while flagging duplicates.
        """
        import time
        from src.database.data_validation_pipeline import (
            DataValidationPipeline,
            ValidationResult,
        )

        validator = DataValidationPipeline(_make_config())

        # A large batch of near-identical short-title articles. The pipeline
        # accepts the first and flags the rest as fuzzy-title duplicates.
        duplicate_batch = [
            {
                "title": "Article {0}".format(i),
                "content": "Content for article {0} ".format(i) * 50,
                "url": "https://trusted.com/article-{0}".format(i),
                "source": "trusted.com",
                "published_date": "2024-01-01T12:00:00Z",
            }
            for i in range(100)
        ]

        start_time = time.time()
        results = validator.batch_validate_articles(duplicate_batch)
        processing_time = time.time() - start_time

        # Performance: one result per input, completes well within budget.
        assert len(results) == 100
        assert processing_time < 30.0
        assert all(isinstance(r, ValidationResult) for r in results)
        # Duplicate detection is active: not every near-identical article passes.
        assert any(not r.is_valid for r in results)

        # Correctness: a fresh pipeline validates genuinely distinct articles.
        fresh_validator = DataValidationPipeline(_make_config())
        distinct = _distinct_articles(5)
        distinct_results = fresh_validator.batch_validate_articles(distinct)
        assert len(distinct_results) == 5
        assert all(r.is_valid for r in distinct_results)

    def test_concurrent_database_operations(self):
        """Test concurrent synchronous database operations."""
        import threading
        from src.database.setup import get_sync_connection

        with patch("src.database.setup.psycopg2") as mock_psycopg2:
            mock_psycopg2.connect.return_value = MockPostgresConnection()

            results = []
            errors = []

            def worker_function(worker_id):
                try:
                    conn = get_sync_connection(testing=True)
                    with conn.cursor() as cur:
                        cur.execute("SELECT * FROM articles LIMIT 10")
                        cur.fetchall()
                    results.append("Worker {0} completed".format(worker_id))
                    conn.close()
                except Exception as e:
                    errors.append("Worker {0} error: {1}".format(worker_id, e))

            threads = []
            for i in range(5):
                thread = threading.Thread(target=worker_function, args=(i,))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            assert len(results) == 5
            assert len(errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
