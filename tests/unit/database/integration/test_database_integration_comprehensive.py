"""
Comprehensive Database Integration Tests for Issue #417

This module provides complete test coverage for all database modules in src/database/
to achieve 80%+ test coverage for the database layer.

Modules covered:
- setup.py: Database connection management and setup
- s3_storage.py: S3 storage operations and metadata
- dynamodb_metadata_manager.py: DynamoDB article metadata indexing
- data_validation_pipeline.py: Data validation and cleaning
- snowflake_analytics_connector.py: Snowflake analytics integration
- snowflake_loader.py: Snowflake data loading operations
- dynamodb_pipeline_integration.py: DynamoDB pipeline integration

Features:
- Mock-based testing for CI/CD compatibility
- Comprehensive error handling testing
- Performance and stress testing
- End-to-end integration workflows
- Database CRUD operations testing
- Data validation and cleaning testing
"""

import asyncio
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Guard optional dependencies so collection never crashes when they are absent.
try:  # boto3 backs S3 / DynamoDB mock fixtures
    import boto3  # noqa: F401
    HAS_BOTO3 = True
except ImportError:  # pragma: no cover - environment dependent
    HAS_BOTO3 = False

try:  # psycopg2 backs the sync connection paths
    import psycopg2  # noqa: F401
    HAS_PSYCOPG2 = True
except ImportError:  # pragma: no cover - environment dependent
    HAS_PSYCOPG2 = False

# Reputation thresholds the current SourceReputationConfig expects. The analyzer
# reads the "trusted"/"reliable"/"questionable"/"unreliable" keys, so every test
# config must provide them.
REPUTATION_THRESHOLDS = {
    "trusted": 0.9,
    "reliable": 0.7,
    "questionable": 0.4,
    "unreliable": 0.2,
}


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


class MockAsyncConnection:
    """Mock AsyncPG connection for testing."""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.closed = False
        
    async def execute(self, query, *args):
        if self.closed:
            raise Exception("Connection is closed")
        return "EXECUTED"
        
    async def fetch(self, query, *args):
        if self.closed:
            raise Exception("Connection is closed")
        return [{"id": 1, "title": "Test Article"}]
        
    async def fetchrow(self, query, *args):
        if self.closed:
            raise Exception("Connection is closed")
        return {"id": 1, "title": "Test Article"}
        
    async def close(self):
        self.closed = True


class MockCursor:
    """Mock database cursor for testing."""
    
    def __init__(self, cursor_factory=None):
        self.cursor_factory = cursor_factory
        self.results = []
        self.current_query = None
        
    def execute(self, query, params=None):
        self.current_query = query
        if "SELECT" in query.upper():
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


class MockS3Client:
    """Mock S3 client for testing."""
    
    def __init__(self):
        self.buckets = {}
        self.objects = {}
        
    def create_bucket(self, Bucket, **kwargs):
        self.buckets[Bucket] = {"created": datetime.now()}
        return {"Location": f"/{Bucket}"}

    def head_bucket(self, Bucket, **kwargs):
        # S3ArticleStorage calls head_bucket during initialization to verify the
        # bucket is accessible. Returning successfully (rather than raising a
        # ClientError) signals that the bucket exists.
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_bucket_versioning(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_bucket_lifecycle_configuration(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_bucket_encryption(self, Bucket, **kwargs):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def put_object(self, Bucket, Key, Body, **kwargs):
        if Bucket not in self.buckets:
            raise Exception(f"Bucket {Bucket} does not exist")
        self.objects[f"{Bucket}/{Key}"] = {
            "Body": Body,
            "LastModified": datetime.now(),
            "ContentLength": len(str(Body)),
            **kwargs
        }
        return {"ETag": f'"{uuid.uuid4()}"'}
        
    def get_object(self, Bucket, Key):
        key_path = f"{Bucket}/{Key}"
        if key_path not in self.objects:
            raise Exception(f"Object {Key} not found")
        obj = self.objects[key_path]
        obj["Body"] = MockS3Object(obj["Body"])
        return obj
        
    def head_object(self, Bucket, Key):
        key_path = f"{Bucket}/{Key}"
        if key_path not in self.objects:
            raise Exception(f"Object {Key} not found")
        return self.objects[key_path]
        
    def delete_object(self, Bucket, Key):
        key_path = f"{Bucket}/{Key}"
        if key_path in self.objects:
            del self.objects[key_path]
        return {"DeleteMarker": False}
        
    def list_objects_v2(self, Bucket, Prefix="", **kwargs):
        objects = []
        for key_path, obj in self.objects.items():
            bucket, key = key_path.split("/", 1)
            if bucket == Bucket and key.startswith(Prefix):
                objects.append({
                    "Key": key,
                    "LastModified": obj["LastModified"],
                    "Size": obj["ContentLength"]
                })
        return {"Contents": objects}


class MockS3Object:
    """Mock S3 object body for testing."""
    
    def __init__(self, content):
        self.content = content
        
    def read(self):
        if isinstance(self.content, str):
            return self.content.encode('utf-8')
        return self.content


class MockDynamoDBBatchWriter:
    """Mock DynamoDB batch writer context manager."""

    def __init__(self, table):
        self.table = table

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def put_item(self, Item, **kwargs):
        self.table.put_item(Item=Item)


class MockDynamoDBTable:
    """Mock DynamoDB table for testing.

    Mirrors the boto3 resource Table surface the current
    DynamoDBMetadataManager relies on, including ``meta.client`` access (used
    during table initialization) and ``batch_writer`` (used for batch indexing).
    """

    def __init__(self, table_name):
        self.table_name = table_name
        self.items = {}
        self.indexes = {}
        # Manager calls self.table.meta.client.describe_table(...) on init to
        # detect whether the table already exists. A MagicMock returns a value
        # (rather than raising ResourceNotFoundException), so the manager treats
        # the table as existing and skips creation.
        self.meta = MagicMock()
        self.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

    def put_item(self, Item, **kwargs):
        item_id = Item.get("article_id") or Item.get("id") or str(uuid.uuid4())
        self.items[item_id] = Item
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_item(self, Key, **kwargs):
        key_value = list(Key.values())[0]
        item = self.items.get(key_value)
        if item:
            return {"Item": item}
        return {}

    def query(self, KeyConditionExpression=None, IndexName=None, **kwargs):
        # Simplified query simulation
        items = list(self.items.values())
        return {"Items": items[:10], "Count": len(items)}

    def scan(self, FilterExpression=None, **kwargs):
        items = list(self.items.values())
        return {"Items": items, "Count": len(items)}

    def delete_item(self, Key, **kwargs):
        key_value = list(Key.values())[0]
        if key_value in self.items:
            del self.items[key_value]
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def batch_writer(self, **kwargs):
        return MockDynamoDBBatchWriter(self)

    def batch_write_item(self, RequestItems, **kwargs):
        return {"UnprocessedItems": {}}


class MockSnowflakeConnection:
    """Mock Snowflake connection for testing."""
    
    def __init__(self):
        self.closed = False
        self.queries = []
        
    def cursor(self):
        return MockSnowflakeCursor()
        
    def close(self):
        self.closed = True
        
    def commit(self):
        pass
        
    def rollback(self):
        pass


class MockSnowflakeCursor:
    """Mock Snowflake cursor for testing."""
    
    def __init__(self):
        self.results = []
        
    def execute(self, query, params=None):
        self.results = [{"count": 100}] if "COUNT" in query.upper() else []
        return True
        
    def fetchall(self):
        return self.results
        
    def fetchone(self):
        return self.results[0] if self.results else None
        
    def close(self):
        pass


# =============================================================================
# Test Classes for Database Setup Module
# =============================================================================

class TestDatabaseSetup:
    """Test database setup and connection management."""
    
    @pytest.fixture
    def mock_psycopg2(self):
        # The setup module imports psycopg2/asyncpg at module scope, so patch the
        # symbol where setup looks it up. If the module can't be imported (e.g.
        # asyncpg is not installed), skip rather than erroring at fixture setup.
        try:
            import src.database.setup  # noqa: F401
        except ImportError:
            pytest.skip("Database setup module not available")
        with patch('src.database.setup.psycopg2') as mock:
            mock.connect.return_value = MockPostgresConnection()
            # OperationalError is referenced by the retry path in setup.
            mock.OperationalError = Exception
            yield mock

    @pytest.fixture
    def mock_asyncpg(self):
        try:
            import src.database.setup  # noqa: F401
        except ImportError:
            pytest.skip("Database setup module not available")
        with patch('src.database.setup.asyncpg') as mock:
            mock.connect = AsyncMock(return_value=MockAsyncConnection())
            yield mock
    
    def test_get_db_config_production(self, mock_psycopg2):
        """Test production database configuration."""
        try:
            from src.database.setup import get_db_config

            config = get_db_config(testing=False)
            
            assert isinstance(config, dict)
            assert "host" in config
            assert "port" in config
            assert "database" in config
            assert "user" in config
            assert "password" in config
            assert config["database"] == "neuronews_dev"
            
        except ImportError:
            pytest.skip("Database modules not available")
    
    def test_get_db_config_testing(self, mock_psycopg2):
        """Test testing database configuration."""
        try:
            from src.database.setup import get_db_config
            
            config = get_db_config(testing=True)
            
            assert isinstance(config, dict)
            assert config["database"] == "neuronews_test"
            assert config["host"] == "test-postgres"
            
        except ImportError:
            pytest.skip("Database modules not available")
    
    def test_get_sync_connection_success(self, mock_psycopg2):
        """Test successful synchronous connection."""
        try:
            from src.database.setup import get_sync_connection
            
            conn = get_sync_connection(testing=True)
            
            assert conn is not None
            assert isinstance(conn, MockPostgresConnection)
            
        except ImportError:
            pytest.skip("Database modules not available")
    
    def test_get_sync_connection_failure(self, mock_psycopg2):
        """Test synchronous connection failure handling."""
        try:
            from src.database.setup import get_sync_connection
            
            mock_psycopg2.connect.side_effect = Exception("Connection failed")
            
            with pytest.raises(Exception):
                get_sync_connection(testing=True)
                
        except ImportError:
            pytest.skip("Database modules not available")
    
    @pytest.mark.asyncio
    async def test_get_async_connection_success(self, mock_asyncpg):
        """Test successful asynchronous connection."""
        try:
            from src.database.setup import get_async_connection
            
            conn = await get_async_connection(testing=True)
            
            assert conn is not None
            assert isinstance(conn, MockAsyncConnection)
            
        except ImportError:
            pytest.skip("Database modules not available")
    
    @pytest.mark.asyncio
    async def test_get_async_connection_failure(self, mock_asyncpg):
        """Test asynchronous connection failure handling."""
        try:
            from src.database.setup import get_async_connection
            
            mock_asyncpg.connect.side_effect = Exception("Connection failed")
            
            with pytest.raises(Exception):
                await get_async_connection(testing=True)
                
        except ImportError:
            pytest.skip("Database modules not available")
    
    @pytest.mark.asyncio
    async def test_setup_test_database_success(self, mock_psycopg2):
        """Test successful test database setup."""
        try:
            from src.database.setup import setup_test_database
            
            # Mock successful connection and table operations
            mock_conn = MockPostgresConnection()
            mock_psycopg2.connect.return_value = mock_conn
            
            await setup_test_database()
            
            # Verify connection was attempted
            mock_psycopg2.connect.assert_called()
            
        except ImportError:
            pytest.skip("Database modules not available")
    
    @pytest.mark.asyncio
    async def test_setup_test_database_retry_logic(self, mock_psycopg2):
        """Test database setup retry logic."""
        try:
            from src.database.setup import setup_test_database
            import asyncio
            
            # First few calls fail, then succeed
            call_count = [0]
            
            def side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise Exception("Connection failed")
                return MockPostgresConnection()
            
            mock_psycopg2.connect.side_effect = side_effect
            
            # Patch sleep to make test faster
            with patch('asyncio.sleep'):
                await setup_test_database()
            
            assert call_count[0] >= 3
            
        except ImportError:
            pytest.skip("Database modules not available")
    
    @pytest.mark.asyncio
    async def test_cleanup_test_database(self, mock_psycopg2):
        """Test test database cleanup."""
        try:
            from src.database.setup import cleanup_test_database
            
            mock_conn = MockPostgresConnection()
            mock_psycopg2.connect.return_value = mock_conn
            
            await cleanup_test_database()
            
            mock_psycopg2.connect.assert_called()
            
        except ImportError:
            pytest.skip("Database modules not available")
    
    def test_create_test_articles_success(self, mock_psycopg2):
        """Test successful test article creation."""
        try:
            from src.database.setup import create_test_articles
            
            mock_conn = MockPostgresConnection()
            mock_psycopg2.connect.return_value = mock_conn
            
            article_ids = create_test_articles(count=5)
            
            assert len(article_ids) == 5
            assert all(isinstance(aid, str) for aid in article_ids)
            
        except ImportError:
            pytest.skip("Database modules not available")
    
    def test_create_test_articles_failure(self, mock_psycopg2):
        """Test test article creation failure handling."""
        try:
            from src.database.setup import create_test_articles
            
            mock_psycopg2.connect.side_effect = Exception("Database error")
            
            with pytest.raises(Exception):
                create_test_articles(count=5)
                
        except ImportError:
            pytest.skip("Database modules not available")


# =============================================================================
# Test Classes for S3 Storage Module
# =============================================================================

@pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed")
class TestS3Storage:
    """Test S3 storage operations and metadata management.

    The current S3Storage builds its client via
    ``src.database.s3_storage.get_client`` and takes a bucket-name string (not a
    config object). upload_article returns the generated S3 key string.
    """

    @pytest.fixture
    def mock_s3_client(self):
        client = MockS3Client()
        # Patch the factory the storage module actually calls, so initialization
        # (head_bucket) and uploads use our in-memory mock.
        with patch('src.database.s3_storage.get_client', return_value=client):
            yield client

    def test_s3_storage_initialization(self, mock_s3_client):
        """Test S3 storage class initialization."""
        try:
            from src.database.s3_storage import S3Storage

            storage = S3Storage(bucket_name="test-bucket")

            assert storage.config.bucket_name == "test-bucket"
            assert hasattr(storage, 's3_client')
            assert storage.s3_client is mock_s3_client

        except ImportError:
            pytest.skip("S3 storage module not available")

    def test_s3_article_upload(self, mock_s3_client):
        """Test article upload to S3."""
        try:
            from src.database.s3_storage import S3Storage

            storage = S3Storage(bucket_name="test-bucket")

            # Mock put_object requires the bucket to exist first.
            mock_s3_client.create_bucket(Bucket="test-bucket")

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
            # The object was actually written to the mock store.
            assert f"test-bucket/{s3_key}" in mock_s3_client.objects

        except ImportError:
            pytest.skip("S3 storage module not available")

    def test_s3_article_deletion(self, mock_s3_client):
        """Test article deletion from S3."""
        try:
            from src.database.s3_storage import S3Storage

            storage = S3Storage(bucket_name="test-bucket")

            # delete_article returns None on success and must not raise.
            result = storage.delete_article("raw_articles/test-123.json")

            assert result is None

        except ImportError:
            pytest.skip("S3 storage module not available")

    def test_s3_upload_missing_required_fields(self, mock_s3_client):
        """upload_article rejects articles missing required fields."""
        try:
            from src.database.s3_storage import S3Storage

            storage = S3Storage(bucket_name="test-bucket")
            mock_s3_client.create_bucket(Bucket="test-bucket")

            # Missing title/content/source -> ValueError before any S3 call.
            with pytest.raises(ValueError):
                storage.upload_article({"id": "test", "url": "https://x/y"})

        except ImportError:
            pytest.skip("S3 storage module not available")

    def test_s3_error_handling_no_client(self):
        """Operations fail clearly when the S3 client could not initialize."""
        try:
            from src.database.s3_storage import S3Storage

            # head_bucket raising a generic exception leaves s3_client as None.
            failing_client = MockS3Client()
            failing_client.head_bucket = MagicMock(
                side_effect=Exception("boom")
            )

            with patch(
                'src.database.s3_storage.get_client', return_value=failing_client
            ):
                storage = S3Storage(bucket_name="nonexistent-bucket")

            assert storage.s3_client is None

            article_data = {
                "title": "Test",
                "content": "Test content",
                "source": "test-source",
            }
            with pytest.raises(ValueError):
                storage.upload_article(article_data)

        except ImportError:
            pytest.skip("S3 storage module not available")


# =============================================================================
# Test Classes for DynamoDB Metadata Manager
# =============================================================================

@pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed")
class TestDynamoDBMetadataManager:
    """Test DynamoDB metadata indexing and search operations.

    The current manager builds clients via ``get_resource``/``get_client`` from
    ``src.utils.local_cloud`` (imported into the manager module). Its index,
    batch, search and delete methods are async and accept/return the current
    types (article dicts in, ArticleMetadataIndex/QueryResult/bool out).
    """

    @pytest.fixture
    def mock_dynamodb_resource(self):
        mock_table = MockDynamoDBTable("test-table")
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        with patch(
            'src.database.dynamodb_metadata_manager.get_resource',
            return_value=mock_resource,
        ), patch(
            'src.database.dynamodb_metadata_manager.get_client',
            return_value=MagicMock(),
        ):
            yield mock_table

    def test_dynamodb_manager_initialization(self, mock_dynamodb_resource):
        """Test DynamoDB manager initialization."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager

            manager = DynamoDBMetadataManager("test-table")

            assert manager.table_name == "test-table"
            assert hasattr(manager, 'table')
            assert manager.table is mock_dynamodb_resource

        except ImportError:
            pytest.skip("DynamoDB manager module not available")

    @pytest.mark.asyncio
    async def test_dynamodb_article_indexing(self, mock_dynamodb_resource):
        """Test article metadata indexing in DynamoDB."""
        try:
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
                "tags": ["tech", "news"],
                "content": "Test content preview",
            }

            result = await manager.index_article_metadata(article)

            assert isinstance(result, ArticleMetadataIndex)
            assert result.article_id == "test-123"
            # The item was persisted to the mock table.
            assert "test-123" in mock_dynamodb_resource.items

        except ImportError:
            pytest.skip("DynamoDB manager module not available")

    @pytest.mark.asyncio
    async def test_dynamodb_article_search_by_source(self, mock_dynamodb_resource):
        """Test article search by source in DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import (
                DynamoDBMetadataManager,
                QueryResult,
            )

            manager = DynamoDBMetadataManager("test-table")

            result = await manager.get_articles_by_source("test-source")

            assert isinstance(result, QueryResult)
            assert isinstance(result.items, list)

        except ImportError:
            pytest.skip("DynamoDB manager module not available")

    @pytest.mark.asyncio
    async def test_dynamodb_article_search_by_date_range(self, mock_dynamodb_resource):
        """Test article search by date range in DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import (
                DynamoDBMetadataManager,
                QueryResult,
            )

            manager = DynamoDBMetadataManager("test-table")

            result = await manager.get_articles_by_date_range(
                "2024-01-01", "2024-12-31"
            )

            assert isinstance(result, QueryResult)
            assert isinstance(result.items, list)

        except ImportError:
            pytest.skip("DynamoDB manager module not available")

    @pytest.mark.asyncio
    async def test_dynamodb_fulltext_search(self, mock_dynamodb_resource):
        """Test full-text search in DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import (
                DynamoDBMetadataManager,
                SearchQuery,
                SearchMode,
                QueryResult,
            )

            manager = DynamoDBMetadataManager("test-table")

            query = SearchQuery(query_text="test query", search_mode=SearchMode.CONTAINS)
            result = await manager.search_articles(query)

            assert isinstance(result, QueryResult)
            assert isinstance(result.items, list)

        except ImportError:
            pytest.skip("DynamoDB manager module not available")

    @pytest.mark.asyncio
    async def test_dynamodb_batch_indexing(self, mock_dynamodb_resource):
        """Test batch article indexing in DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager

            manager = DynamoDBMetadataManager("test-table")

            articles = [
                {
                    "id": f"test-{i}",
                    "title": f"Article {i}",
                    "source": "test-source",
                    "published_date": "2024-01-01",
                    "tags": ["tech"],
                    "content": f"Preview {i}",
                }
                for i in range(5)
            ]

            result = await manager.batch_index_articles(articles)

            assert result is not None
            assert result["status"] == "completed"
            assert result["indexed_count"] == 5
            assert result["failed_count"] == 0

        except ImportError:
            pytest.skip("DynamoDB manager module not available")

    @pytest.mark.asyncio
    async def test_dynamodb_article_deletion(self, mock_dynamodb_resource):
        """Test article metadata deletion from DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager

            manager = DynamoDBMetadataManager("test-table")

            result = await manager.delete_article_metadata("test-123")

            assert result is True

        except ImportError:
            pytest.skip("DynamoDB manager module not available")

    @pytest.mark.asyncio
    async def test_dynamodb_error_handling(self, mock_dynamodb_resource):
        """Test DynamoDB error handling."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager

            manager = DynamoDBMetadataManager("test-table")

            # Indexing a non-dict article raises inside metadata creation and is
            # re-raised by index_article_metadata.
            with pytest.raises(Exception):
                await manager.index_article_metadata(None)

        except ImportError:
            pytest.skip("DynamoDB manager module not available")


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


# Distinct, non-fuzzy-similar titles so the duplicate detector does not reject
# later articles in batch tests as near-duplicates of earlier ones.
DISTINCT_TITLES = [
    "Breaking technology news today",
    "Economic policy shifts worldwide",
    "Sports championship final results",
    "Health research breakthrough announced",
    "Climate summit reaches agreement",
]


def _valid_article_body(index: int) -> str:
    """Content long enough (>=100 chars, >=20 words) to pass content validation."""
    return (
        f"Detailed coverage number {index} about the subject with enough words to "
        "clear the validation threshold for word count and length requirements "
        "set by the validator system."
    )


class TestDataValidationPipeline:
    """Test data validation and cleaning operations.

    The current DataValidationPipeline composes helper components
    (html_cleaner, duplicate_detector, source_analyzer, content_validator)
    rather than exposing clean_content/is_duplicate/calculate_source_reputation
    directly. Validation scores are on a 0-100 scale and reputation scores on a
    0-1 scale.
    """

    def test_validation_pipeline_initialization(self):
        """Test validation pipeline initialization."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline

            config = _reputation_config(
                trusted=["trusted.com"],
                questionable=["questionable.com"],
                banned=["banned.com"],
            )

            pipeline = DataValidationPipeline(config)

            # The config is held by the source reputation analyzer.
            assert pipeline.source_analyzer.config == config
            assert hasattr(pipeline, 'duplicate_detector')
            assert hasattr(pipeline, 'html_cleaner')
            assert hasattr(pipeline, 'content_validator')

        except ImportError:
            pytest.skip("Data validation module not available")

    def test_article_validation_success(self):
        """Test successful article validation."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline

            pipeline = DataValidationPipeline(_reputation_config(trusted=["trusted.com"]))

            article = {
                "title": "Test Article Title",
                "content": _valid_article_body(1),
                "url": "https://trusted.com/article",
                "author": "Test Author",
                "published_date": "2024-01-01T12:00:00Z",
                "source": "trusted.com",
            }

            result = pipeline.validate_article(article)

            assert result.is_valid
            # Validation scores are on a 0-100 scale; valid means score >= 50.
            assert result.score >= 50
            assert isinstance(result.cleaned_data, dict)

        except ImportError:
            pytest.skip("Data validation module not available")

    def test_article_validation_failure(self):
        """Test article validation failure cases."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline

            pipeline = DataValidationPipeline(_reputation_config(banned=["banned.com"]))

            # Article from banned domain with thin content and a bad date.
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
            assert "banned_domain" in result.issues

        except ImportError:
            pytest.skip("Data validation module not available")

    def test_duplicate_detection(self):
        """Test duplicate article detection via the duplicate detector."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline

            pipeline = DataValidationPipeline(_reputation_config(trusted=["trusted.com"]))

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
            is_dup1, reason1 = pipeline.duplicate_detector.is_duplicate(article1)
            assert not is_dup1
            assert reason1 == "unique"

            # Same title -> detected as a duplicate.
            is_dup2, reason2 = pipeline.duplicate_detector.is_duplicate(article2)
            assert is_dup2
            assert reason2 == "duplicate_title"

        except ImportError:
            pytest.skip("Data validation module not available")

    def test_content_cleaning(self):
        """Test content cleaning and sanitization via the HTML cleaner."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline

            pipeline = DataValidationPipeline(_reputation_config(trusted=["trusted.com"]))

            dirty_content = "<script>alert('xss')</script><p>Clean content &amp; more</p>"
            cleaned = pipeline.html_cleaner.clean_content(dirty_content)

            assert "<script>" not in cleaned
            assert "Clean content" in cleaned
            assert "&amp;" not in cleaned  # HTML entities should be decoded
            assert "&" in cleaned          # ...to their literal character

        except ImportError:
            pytest.skip("Data validation module not available")

    def test_source_reputation_scoring(self):
        """Test source reputation scoring via the source analyzer."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline

            pipeline = DataValidationPipeline(
                _reputation_config(
                    trusted=["trusted.com"],
                    questionable=["questionable.com"],
                    banned=["banned.com"],
                )
            )
            analyzer = pipeline.source_analyzer

            # Trusted domains score highest.
            score_trusted = analyzer._calculate_reputation_score("trusted.com", "trusted.com")
            assert score_trusted >= 0.9

            # Questionable domains score lower than trusted.
            score_questionable = analyzer._calculate_reputation_score(
                "questionable.com", "questionable.com"
            )
            assert score_questionable < score_trusted

            # Banned domains score the lowest.
            score_banned = analyzer._calculate_reputation_score("banned.com", "banned.com")
            assert score_banned < score_questionable

        except ImportError:
            pytest.skip("Data validation module not available")

    def test_batch_validation(self):
        """Test batch article validation."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline

            pipeline = DataValidationPipeline(_reputation_config(trusted=["trusted.com"]))

            articles = [
                {
                    "title": DISTINCT_TITLES[i],
                    "content": _valid_article_body(i),
                    "url": f"https://trusted.com/article{i}",
                    "source": "trusted.com",
                    "published_date": "2024-01-01T12:00:00Z",
                }
                for i in range(5)
            ]

            results = pipeline.batch_validate_articles(articles)

            assert len(results) == 5
            assert all(result.is_valid for result in results)

        except ImportError:
            pytest.skip("Data validation module not available")


# =============================================================================
# Test Classes for Snowflake Integration
# =============================================================================

class TestSnowflakeIntegration:
    """Test Snowflake analytics connector.

    The current implementation (``SnowflakeAnalyticsConnector``) is a pure-Python
    mock connector that needs no Snowflake driver, so these tests exercise its
    real API directly rather than patching ``snowflake.connector``.
    """

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

    def test_snowflake_connector_initialization(self):
        """Test Snowflake connector initialization."""
        try:
            from src.database.snowflake_analytics_connector import (
                SnowflakeAnalyticsConnector,
            )

            config = self._make_config()
            connector = SnowflakeAnalyticsConnector(config)

            assert connector.config == config
            assert hasattr(connector, 'connection')
            assert connector.is_connected() is False

        except ImportError:
            pytest.skip("Snowflake connector module not available")

    def test_snowflake_query_execution(self):
        """Test Snowflake query execution."""
        try:
            from src.database.snowflake_analytics_connector import (
                SnowflakeAnalyticsConnector,
            )

            connector = SnowflakeAnalyticsConnector(self._make_config())
            assert connector.connect() is True

            result = connector.execute_query("SELECT COUNT(*) FROM articles")

            assert result is not None
            assert isinstance(result, list)
            assert len(result) > 0

        except ImportError:
            pytest.skip("Snowflake connector module not available")

    def test_snowflake_query_requires_connection(self):
        """Executing a query before connecting raises ConnectionError."""
        try:
            from src.database.snowflake_analytics_connector import (
                SnowflakeAnalyticsConnector,
            )

            connector = SnowflakeAnalyticsConnector(self._make_config())

            with pytest.raises(ConnectionError):
                connector.execute_query("SELECT 1")

        except ImportError:
            pytest.skip("Snowflake connector module not available")

    def test_snowflake_bulk_insert(self):
        """Test Snowflake bulk insert operation."""
        try:
            from src.database.snowflake_analytics_connector import (
                SnowflakeAnalyticsConnector,
            )

            connector = SnowflakeAnalyticsConnector(self._make_config())
            connector.connect()

            test_data = [
                {"id": 1, "title": "Article 1", "content": "Content 1"},
                {"id": 2, "title": "Article 2", "content": "Content 2"},
            ]

            inserted = connector.bulk_insert("articles", test_data)

            assert inserted == len(test_data)

        except ImportError:
            pytest.skip("Snowflake connector module not available")

    def test_snowflake_analytics_summary(self):
        """Test Snowflake analytics summary and table info."""
        try:
            from src.database.snowflake_analytics_connector import (
                SnowflakeAnalyticsConnector,
            )

            connector = SnowflakeAnalyticsConnector(self._make_config())
            connector.connect()

            summary = connector.get_analytics_summary()
            table_info = connector.get_table_info("articles")

            assert summary["connection_status"] == "connected"
            assert summary["database"] == "test-database"
            assert table_info["table_name"] == "articles"
            assert table_info["schema"] == "test-schema"

        except ImportError:
            pytest.skip("Snowflake connector module not available")

    def test_snowflake_error_handling(self):
        """Test Snowflake error handling for operations without a connection."""
        try:
            from src.database.snowflake_analytics_connector import (
                SnowflakeAnalyticsConnector,
            )

            connector = SnowflakeAnalyticsConnector(self._make_config())

            # Operations that require an active connection must raise when the
            # connector has not connected yet.
            with pytest.raises(ConnectionError):
                connector.get_table_info("articles")

        except ImportError:
            pytest.skip("Snowflake connector module not available")


# =============================================================================
# Integration Tests for Database Pipeline
# =============================================================================

@pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed")
class TestDatabasePipelineIntegration:
    """Test end-to-end database pipeline integration.

    Wires the validation pipeline, S3 storage and DynamoDB manager together
    using their current APIs, with the S3/DynamoDB client factories mocked.
    """

    @pytest.fixture
    def mock_all_services(self):
        """Mock the S3 and DynamoDB client factories for integration testing."""
        s3_client = MockS3Client()
        dynamo_table = MockDynamoDBTable("test-table")
        dynamo_resource = MagicMock()
        dynamo_resource.Table.return_value = dynamo_table

        with patch(
            'src.database.s3_storage.get_client', return_value=s3_client
        ), patch(
            'src.database.dynamodb_metadata_manager.get_resource',
            return_value=dynamo_resource,
        ), patch(
            'src.database.dynamodb_metadata_manager.get_client',
            return_value=MagicMock(),
        ):
            yield {"s3": s3_client, "dynamodb": dynamo_table}

    @pytest.mark.asyncio
    async def test_end_to_end_article_processing(self, mock_all_services):
        """Test complete article processing pipeline."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline
            from src.database.s3_storage import S3Storage
            from src.database.dynamodb_metadata_manager import (
                DynamoDBMetadataManager,
                ArticleMetadataIndex,
                QueryResult,
            )

            validator = DataValidationPipeline(
                _reputation_config(trusted=["trusted.com"])
            )
            s3_storage = S3Storage(bucket_name="test-bucket")
            dynamodb_manager = DynamoDBMetadataManager("test-table")

            # put_object requires the bucket to exist in the mock store.
            mock_all_services["s3"].create_bucket(Bucket="test-bucket")

            article = {
                "id": "test-123",
                "title": "Test Article for Integration",
                "content": _valid_article_body(7),
                "url": "https://trusted.com/test-article",
                "author": "Test Author",
                "source": "trusted.com",
                "published_date": "2024-01-01T12:00:00Z",
                "category": "technology",
            }

            # Step 1: Validate article
            validation_result = validator.validate_article(article)
            assert validation_result.is_valid

            # Step 2: Store cleaned data in S3 (returns the generated key string)
            s3_key = s3_storage.upload_article(validation_result.cleaned_data)
            assert isinstance(s3_key, str)

            # Step 3: Index in DynamoDB (async, accepts an article dict)
            index_result = await dynamodb_manager.index_article_metadata(article)
            assert isinstance(index_result, ArticleMetadataIndex)
            assert index_result.article_id == "test-123"

            # Step 4: Search and retrieve
            search_results = await dynamodb_manager.get_articles_by_source("trusted.com")
            assert isinstance(search_results, QueryResult)

        except ImportError:
            pytest.skip("Integration test modules not available")

    @pytest.mark.asyncio
    async def test_batch_processing_performance(self, mock_all_services):
        """Test batch processing performance and reliability."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline
            from src.database.s3_storage import S3Storage
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager

            validator = DataValidationPipeline(
                _reputation_config(trusted=["trusted.com"])
            )
            s3_storage = S3Storage(bucket_name="test-bucket")
            dynamodb_manager = DynamoDBMetadataManager("test-table")

            mock_all_services["s3"].create_bucket(Bucket="test-bucket")

            # Each article draws six unique words (shared with no other article)
            # so neither fuzzy-title nor content-hash duplicate detection rejects
            # later items in the batch.
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
                        "id": f"test-{i}",
                        "title": " ".join(w.capitalize() for w in words[:5]),
                        "content": " ".join(words * 6) + " completed.",
                        "url": f"https://trusted.com/article-{i}",
                        "source": "trusted.com",
                        "published_date": "2024-01-01T12:00:00Z",
                    }
                )

            # Batch validation
            validation_results = validator.batch_validate_articles(articles)
            assert len(validation_results) == 10
            assert all(result.is_valid for result in validation_results)

            # Per-article S3 upload of cleaned data
            valid_articles = [result.cleaned_data for result in validation_results]
            s3_keys = [s3_storage.upload_article(a) for a in valid_articles]
            assert len(s3_keys) == 10
            assert all(isinstance(k, str) for k in s3_keys)

            # Batch DynamoDB indexing (async, accepts article dicts)
            index_result = await dynamodb_manager.batch_index_articles(articles)
            assert index_result is not None
            assert index_result["indexed_count"] == 10

        except ImportError:
            pytest.skip("Integration test modules not available")

    def test_error_recovery_and_resilience(self, mock_all_services):
        """Test error recovery and system resilience."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline
            from src.database.s3_storage import S3Storage

            validator = DataValidationPipeline(
                _reputation_config(trusted=["trusted.com"])
            )
            # Build a storage whose client fails to initialize (s3_client = None).
            failing_client = MockS3Client()
            failing_client.head_bucket = MagicMock(side_effect=Exception("boom"))
            with patch(
                'src.database.s3_storage.get_client', return_value=failing_client
            ):
                s3_storage = S3Storage(bucket_name="nonexistent-bucket")
            assert s3_storage.s3_client is None

            article = {
                "title": "Test Article Title",
                "content": _valid_article_body(3),
                "url": "https://trusted.com/article",
                "source": "trusted.com",
                "published_date": "2024-01-01T12:00:00Z",
            }

            validation_result = validator.validate_article(article)
            assert validation_result.is_valid

            # Upload must fail clearly when no S3 client is available.
            with pytest.raises(ValueError):
                s3_storage.upload_article(validation_result.cleaned_data)

        except ImportError:
            pytest.skip("Integration test modules not available")


# =============================================================================
# Performance and Stress Tests
# =============================================================================

class TestDatabasePerformance:
    """Test database performance and scalability."""
    
    def test_connection_pool_performance(self):
        """Test database connection pool performance."""
        try:
            from src.database.setup import get_sync_connection
            
            with patch('src.database.setup.psycopg2') as mock_psycopg2:
                mock_psycopg2.connect.return_value = MockPostgresConnection()
                
                # Simulate multiple concurrent connections
                connections = []
                for i in range(10):
                    conn = get_sync_connection(testing=True)
                    connections.append(conn)
                
                assert len(connections) == 10
                assert all(isinstance(conn, MockPostgresConnection) for conn in connections)
                
                # Clean up connections
                for conn in connections:
                    conn.close()
                    
        except ImportError:
            pytest.skip("Database setup module not available")
    
    def test_large_dataset_validation(self):
        """Test validation performance with large datasets."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline

            validator = DataValidationPipeline(_reputation_config(trusted=["trusted.com"]))

            # A 600-word pseudo-vocabulary so each article draws six unique words
            # that appear in no other article. This keeps every title and body
            # distinct, so the duplicate detector (exact + fuzzy title + content
            # hash) does not reject later items in the batch.
            vocab = [
                f"{a}{b}{c}{d}"
                for a in "bcdfghjk"
                for b in "aeiou"
                for c in "mnprs"
                for d in "tkl"
            ]
            assert len(vocab) >= 600

            articles = []
            for i in range(100):
                words = vocab[i * 6:(i + 1) * 6]
                articles.append(
                    {
                        # Five distinct words per title, none shared across titles.
                        "title": " ".join(w.capitalize() for w in words[:5]),
                        # Repeat the unique words to exceed the length/word-count
                        # thresholds while staying unique per article.
                        "content": " ".join(words * 6) + " completed.",
                        "url": f"https://trusted.com/article-{i}",
                        "source": "trusted.com",
                        "published_date": "2024-01-01T12:00:00Z",
                    }
                )

            import time
            start_time = time.time()

            results = validator.batch_validate_articles(articles)

            end_time = time.time()
            processing_time = end_time - start_time

            assert len(results) == 100
            assert processing_time < 30.0  # Should complete within 30 seconds
            assert all(result.is_valid for result in results)

        except ImportError:
            pytest.skip("Data validation module not available")
    
    def test_concurrent_database_operations(self):
        """Test concurrent database operations."""
        try:
            import threading
            from src.database.setup import get_sync_connection
            
            with patch('src.database.setup.psycopg2') as mock_psycopg2:
                mock_psycopg2.connect.return_value = MockPostgresConnection()
                
                results = []
                errors = []
                
                def worker_function(worker_id):
                    try:
                        conn = get_sync_connection(testing=True)
                        # Simulate database work
                        with conn.cursor() as cur:
                            cur.execute("SELECT * FROM articles LIMIT 10")
                            data = cur.fetchall()
                        results.append(f"Worker {worker_id} completed")
                        conn.close()
                    except Exception as e:
                        errors.append(f"Worker {worker_id} error: {e}")
                
                # Create multiple worker threads
                threads = []
                for i in range(5):
                    thread = threading.Thread(target=worker_function, args=(i,))
                    threads.append(thread)
                    thread.start()
                
                # Wait for all threads to complete
                for thread in threads:
                    thread.join()
                
                assert len(results) == 5
                assert len(errors) == 0
                
        except ImportError:
            pytest.skip("Database setup module not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
