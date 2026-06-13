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


class MockDynamoDBTable:
    """Mock DynamoDB table for testing."""
    
    def __init__(self, table_name):
        self.table_name = table_name
        self.items = {}
        self.indexes = {}
        
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
        with patch('psycopg2') as mock:
            mock.connect.return_value = MockPostgresConnection()
            yield mock
            
    @pytest.fixture
    def mock_asyncpg(self):
        with patch('asyncpg') as mock:
            mock.connect.return_value = MockAsyncConnection()
            yield mock
    
    def test_get_db_config_production(self, mock_psycopg2):
        """Test production database configuration."""
        try:
            import sys
            sys.path.insert(0, '/workspaces/NeuroNews/src')
            from database.setup import get_db_config
            
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

class TestS3Storage:
    """Test S3 storage operations and metadata management."""
    
    @pytest.fixture
    def mock_s3_client(self):
        with patch('boto3.client') as mock:
            mock.return_value = MockS3Client()
            yield mock.return_value
    
    def test_s3_storage_initialization(self, mock_s3_client):
        """Test S3 storage class initialization."""
        try:
            from src.database.s3_storage import S3Storage, S3StorageConfig
            
            config = S3StorageConfig(bucket_name="test-bucket")
            storage = S3Storage(config)
            
            assert storage.config.bucket_name == "test-bucket"
            assert hasattr(storage, 's3_client')
            
        except ImportError:
            pytest.skip("S3 storage module not available")
    
    def test_s3_bucket_creation(self, mock_s3_client):
        """Test S3 bucket creation."""
        try:
            from src.database.s3_storage import S3Storage, S3StorageConfig
            
            config = S3StorageConfig(bucket_name="test-bucket")
            storage = S3Storage(config)
            
            # Mock successful bucket creation
            result = storage.create_bucket()
            
            assert result is not None
            
        except ImportError:
            pytest.skip("S3 storage module not available")
    
    def test_s3_article_upload(self, mock_s3_client):
        """Test article upload to S3."""
        try:
            from src.database.s3_storage import S3Storage, S3StorageConfig, ArticleType
            
            config = S3StorageConfig(bucket_name="test-bucket")
            storage = S3Storage(config)
            
            # Create test bucket first
            mock_s3_client.create_bucket(Bucket="test-bucket")
            
            article_data = {
                "id": "test-123",
                "title": "Test Article",
                "content": "Test content",
                "url": "https://example.com/article",
                "source": "test-source",
                "published_date": "2024-01-01"
            }
            
            result = storage.upload_article(article_data, ArticleType.RAW)
            
            assert result is not None
            assert "s3_key" in result
            
        except ImportError:
            pytest.skip("S3 storage module not available")
    
    def test_s3_article_download(self, mock_s3_client):
        """Test article download from S3."""
        try:
            from src.database.s3_storage import S3Storage, S3StorageConfig, ArticleType
            
            config = S3StorageConfig(bucket_name="test-bucket")
            storage = S3Storage(config)
            
            # Create test bucket and upload article first
            mock_s3_client.create_bucket(Bucket="test-bucket")
            
            article_data = {
                "id": "test-123",
                "title": "Test Article",
                "content": "Test content"
            }
            
            # Mock upload
            mock_s3_client.put_object(
                Bucket="test-bucket",
                Key="raw_articles/test-123.json",
                Body=json.dumps(article_data)
            )
            
            result = storage.download_article("raw_articles/test-123.json")
            
            assert result is not None
            
        except ImportError:
            pytest.skip("S3 storage module not available")
    
    def test_s3_article_deletion(self, mock_s3_client):
        """Test article deletion from S3."""
        try:
            from src.database.s3_storage import S3Storage, S3StorageConfig
            
            config = S3StorageConfig(bucket_name="test-bucket")
            storage = S3Storage(config)
            
            # Create test bucket first
            mock_s3_client.create_bucket(Bucket="test-bucket")
            
            result = storage.delete_article("raw_articles/test-123.json")
            
            assert result is not None
            
        except ImportError:
            pytest.skip("S3 storage module not available")
    
    def test_s3_batch_upload(self, mock_s3_client):
        """Test batch article upload to S3."""
        try:
            from src.database.s3_storage import S3Storage, S3StorageConfig, ArticleType
            
            config = S3StorageConfig(bucket_name="test-bucket")
            storage = S3Storage(config)
            
            # Create test bucket first
            mock_s3_client.create_bucket(Bucket="test-bucket")
            
            articles = [
                {"id": f"test-{i}", "title": f"Article {i}", "content": f"Content {i}"}
                for i in range(5)
            ]
            
            results = storage.batch_upload_articles(articles, ArticleType.RAW)
            
            assert len(results) == 5
            assert all("s3_key" in result for result in results)
            
        except ImportError:
            pytest.skip("S3 storage module not available")
    
    def test_s3_error_handling(self, mock_s3_client):
        """Test S3 error handling."""
        try:
            from src.database.s3_storage import S3Storage, S3StorageConfig
            
            config = S3StorageConfig(bucket_name="nonexistent-bucket")
            storage = S3Storage(config)
            
            # Attempt operation on nonexistent bucket
            article_data = {"id": "test", "title": "Test"}
            
            with pytest.raises(Exception):
                storage.upload_article(article_data)
                
        except ImportError:
            pytest.skip("S3 storage module not available")


# =============================================================================
# Test Classes for DynamoDB Metadata Manager
# =============================================================================

class TestDynamoDBMetadataManager:
    """Test DynamoDB metadata indexing and search operations."""
    
    @pytest.fixture
    def mock_dynamodb_resource(self):
        with patch('boto3.resource') as mock:
            mock_table = MockDynamoDBTable("test-table")
            mock.return_value.Table.return_value = mock_table
            yield mock_table
    
    def test_dynamodb_manager_initialization(self, mock_dynamodb_resource):
        """Test DynamoDB manager initialization."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager
            
            manager = DynamoDBMetadataManager("test-table")
            
            assert manager.table_name == "test-table"
            assert hasattr(manager, 'table')
            
        except ImportError:
            pytest.skip("DynamoDB manager module not available")
    
    def test_dynamodb_article_indexing(self, mock_dynamodb_resource):
        """Test article metadata indexing in DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager, ArticleMetadataIndex
            
            manager = DynamoDBMetadataManager("test-table")
            
            metadata = ArticleMetadataIndex(
                article_id="test-123",
                title="Test Article",
                source="test-source",
                published_date="2024-01-01",
                tags=["tech", "news"],
                content_preview="Test content preview"
            )
            
            result = manager.index_article_metadata(metadata)
            
            assert result is not None
            
        except ImportError:
            pytest.skip("DynamoDB manager module not available")
    
    def test_dynamodb_article_search_by_source(self, mock_dynamodb_resource):
        """Test article search by source in DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager
            
            manager = DynamoDBMetadataManager("test-table")
            
            results = manager.search_by_source("test-source")
            
            assert isinstance(results, list)
            
        except ImportError:
            pytest.skip("DynamoDB manager module not available")
    
    def test_dynamodb_article_search_by_date_range(self, mock_dynamodb_resource):
        """Test article search by date range in DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager
            
            manager = DynamoDBMetadataManager("test-table")
            
            results = manager.search_by_date_range("2024-01-01", "2024-12-31")
            
            assert isinstance(results, list)
            
        except ImportError:
            pytest.skip("DynamoDB manager module not available")
    
    def test_dynamodb_fulltext_search(self, mock_dynamodb_resource):
        """Test full-text search in DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager, SearchMode
            
            manager = DynamoDBMetadataManager("test-table")
            
            results = manager.fulltext_search("test query", SearchMode.CONTAINS)
            
            assert isinstance(results, list)
            
        except ImportError:
            pytest.skip("DynamoDB manager module not available")
    
    def test_dynamodb_batch_indexing(self, mock_dynamodb_resource):
        """Test batch article indexing in DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager, ArticleMetadataIndex
            
            manager = DynamoDBMetadataManager("test-table")
            
            metadata_list = [
                ArticleMetadataIndex(
                    article_id=f"test-{i}",
                    title=f"Article {i}",
                    source="test-source",
                    published_date="2024-01-01",
                    tags=["tech"],
                    content_preview=f"Preview {i}"
                )
                for i in range(5)
            ]
            
            results = manager.batch_index_articles(metadata_list)
            
            assert results is not None
            
        except ImportError:
            pytest.skip("DynamoDB manager module not available")
    
    def test_dynamodb_article_deletion(self, mock_dynamodb_resource):
        """Test article metadata deletion from DynamoDB."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager
            
            manager = DynamoDBMetadataManager("test-table")
            
            result = manager.delete_article_metadata("test-123")
            
            assert result is not None
            
        except ImportError:
            pytest.skip("DynamoDB manager module not available")
    
    def test_dynamodb_error_handling(self, mock_dynamodb_resource):
        """Test DynamoDB error handling."""
        try:
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager
            
            manager = DynamoDBMetadataManager("test-table")
            
            # Mock table operation to raise exception
            mock_dynamodb_resource.put_item.side_effect = Exception("DynamoDB error")
            
            with pytest.raises(Exception):
                manager.index_article_metadata(None)
                
        except ImportError:
            pytest.skip("DynamoDB manager module not available")


# =============================================================================
# Test Classes for Data Validation Pipeline
# =============================================================================

class TestDataValidationPipeline:
    """Test data validation and cleaning operations."""
    
    def test_validation_pipeline_initialization(self):
        """Test validation pipeline initialization."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            
            config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=["questionable.com"],
                banned_domains=["banned.com"],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            pipeline = DataValidationPipeline(config)
            
            assert pipeline.config == config
            assert hasattr(pipeline, 'duplicate_detector')
            
        except ImportError:
            pytest.skip("Data validation module not available")
    
    def test_article_validation_success(self):
        """Test successful article validation."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            
            config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=[],
                banned_domains=[],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            pipeline = DataValidationPipeline(config)
            
            article = {
                "title": "Test Article Title",
                "content": "This is a test article with sufficient content length for validation.",
                "url": "https://trusted.com/article",
                "author": "Test Author",
                "published_date": "2024-01-01T12:00:00Z",
                "source": "trusted.com"
            }
            
            result = pipeline.validate_article(article)
            
            assert result.is_valid
            assert result.score > 0.5
            assert isinstance(result.cleaned_data, dict)
            
        except ImportError:
            pytest.skip("Data validation module not available")
    
    def test_article_validation_failure(self):
        """Test article validation failure cases."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            
            config = SourceReputationConfig(
                trusted_domains=[],
                questionable_domains=[],
                banned_domains=["banned.com"],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            pipeline = DataValidationPipeline(config)
            
            # Article from banned domain
            article = {
                "title": "Bad Article",
                "content": "Short",
                "url": "https://banned.com/article",
                "author": "",
                "published_date": "invalid-date",
                "source": "banned.com"
            }
            
            result = pipeline.validate_article(article)
            
            assert not result.is_valid
            assert len(result.issues) > 0
            
        except ImportError:
            pytest.skip("Data validation module not available")
    
    def test_duplicate_detection(self):
        """Test duplicate article detection."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            
            config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=[],
                banned_domains=[],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            pipeline = DataValidationPipeline(config)
            
            article1 = {
                "title": "Test Article",
                "content": "This is test content for duplicate detection.",
                "url": "https://trusted.com/article1"
            }
            
            article2 = {
                "title": "Test Article",
                "content": "This is test content for duplicate detection.",
                "url": "https://trusted.com/article2"
            }
            
            # First article should not be duplicate
            is_duplicate1 = pipeline.is_duplicate(article1)
            assert not is_duplicate1
            
            # Second article should be detected as duplicate
            is_duplicate2 = pipeline.is_duplicate(article2)
            assert is_duplicate2
            
        except ImportError:
            pytest.skip("Data validation module not available")
    
    def test_content_cleaning(self):
        """Test content cleaning and sanitization."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            
            config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=[],
                banned_domains=[],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            pipeline = DataValidationPipeline(config)
            
            dirty_content = "<script>alert('xss')</script><p>Clean content &amp; more</p>"
            cleaned = pipeline.clean_content(dirty_content)
            
            assert "<script>" not in cleaned
            assert "Clean content" in cleaned
            assert "&amp;" not in cleaned  # HTML entities should be decoded
            
        except ImportError:
            pytest.skip("Data validation module not available")
    
    def test_source_reputation_scoring(self):
        """Test source reputation scoring."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            
            config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=["questionable.com"],
                banned_domains=["banned.com"],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            pipeline = DataValidationPipeline(config)
            
            # Test trusted domain
            score_trusted = pipeline.calculate_source_reputation("trusted.com")
            assert score_trusted >= 0.8
            
            # Test questionable domain
            score_questionable = pipeline.calculate_source_reputation("questionable.com")
            assert score_questionable < 0.8
            
            # Test banned domain
            score_banned = pipeline.calculate_source_reputation("banned.com")
            assert score_banned == 0.0
            
        except ImportError:
            pytest.skip("Data validation module not available")
    
    def test_batch_validation(self):
        """Test batch article validation."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            
            config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=[],
                banned_domains=[],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            pipeline = DataValidationPipeline(config)
            
            articles = [
                {
                    "title": f"Article {i}",
                    "content": f"Content for article {i} with sufficient length.",
                    "url": f"https://trusted.com/article{i}",
                    "source": "trusted.com"
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
    """Test Snowflake analytics connector and data loading."""
    
    @pytest.fixture
    def mock_snowflake_connector(self):
        with patch('snowflake.connector.connect') as mock:
            mock.return_value = MockSnowflakeConnection()
            yield mock
    
    def test_snowflake_connector_initialization(self, mock_snowflake_connector):
        """Test Snowflake connector initialization."""
        try:
            from src.database.snowflake_analytics_connector import SnowflakeConnector
            
            config = {
                "account": "test-account",
                "user": "test-user",
                "password": "test-password",
                "warehouse": "test-warehouse",
                "database": "test-database",
                "schema": "test-schema"
            }
            
            connector = SnowflakeConnector(config)
            
            assert connector.config == config
            assert hasattr(connector, 'connection')
            
        except ImportError:
            pytest.skip("Snowflake connector module not available")
    
    def test_snowflake_query_execution(self, mock_snowflake_connector):
        """Test Snowflake query execution."""
        try:
            from src.database.snowflake_analytics_connector import SnowflakeConnector
            
            config = {
                "account": "test-account",
                "user": "test-user",
                "password": "test-password",
                "warehouse": "test-warehouse",
                "database": "test-database",
                "schema": "test-schema"
            }
            
            connector = SnowflakeConnector(config)
            
            result = connector.execute_query("SELECT COUNT(*) FROM articles")
            
            assert result is not None
            
        except ImportError:
            pytest.skip("Snowflake connector module not available")
    
    def test_snowflake_data_loading(self, mock_snowflake_connector):
        """Test Snowflake data loading operations."""
        try:
            from src.database.snowflake_loader import SnowflakeLoader
            
            config = {
                "account": "test-account",
                "user": "test-user", 
                "password": "test-password",
                "warehouse": "test-warehouse",
                "database": "test-database",
                "schema": "test-schema"
            }
            
            loader = SnowflakeLoader(config)
            
            # Test data loading
            test_data = [
                {"id": 1, "title": "Article 1", "content": "Content 1"},
                {"id": 2, "title": "Article 2", "content": "Content 2"}
            ]
            
            result = loader.load_articles(test_data)
            
            assert result is not None
            
        except ImportError:
            pytest.skip("Snowflake loader module not available")
    
    def test_snowflake_analytics_queries(self, mock_snowflake_connector):
        """Test Snowflake analytics query operations."""
        try:
            from src.database.snowflake_analytics_connector import SnowflakeConnector
            
            config = {
                "account": "test-account",
                "user": "test-user",
                "password": "test-password",
                "warehouse": "test-warehouse",
                "database": "test-database",
                "schema": "test-schema"
            }
            
            connector = SnowflakeConnector(config)
            
            # Test analytics queries
            result1 = connector.get_article_counts_by_source()
            result2 = connector.get_trending_topics()
            result3 = connector.get_sentiment_analysis()
            
            assert result1 is not None
            assert result2 is not None
            assert result3 is not None
            
        except ImportError:
            pytest.skip("Snowflake connector module not available")
    
    def test_snowflake_error_handling(self, mock_snowflake_connector):
        """Test Snowflake error handling."""
        try:
            from src.database.snowflake_analytics_connector import SnowflakeConnector
            
            config = {
                "account": "test-account",
                "user": "test-user",
                "password": "test-password",
                "warehouse": "test-warehouse",
                "database": "test-database",
                "schema": "test-schema"
            }
            
            connector = SnowflakeConnector(config)
            
            # Mock connection failure
            mock_snowflake_connector.side_effect = Exception("Connection failed")
            
            with pytest.raises(Exception):
                connector.reconnect()
                
        except ImportError:
            pytest.skip("Snowflake connector module not available")


# =============================================================================
# Integration Tests for Database Pipeline
# =============================================================================

class TestDatabasePipelineIntegration:
    """Test end-to-end database pipeline integration."""
    
    @pytest.fixture
    def mock_all_services(self):
        """Mock all external services for integration testing."""
        with patch('boto3.client') as mock_s3, \
             patch('boto3.resource') as mock_dynamodb, \
             patch('src.database.setup.psycopg2') as mock_postgres, \
             patch('snowflake.connector.connect') as mock_snowflake:
            
            # Set up mocks
            mock_s3.return_value = MockS3Client()
            mock_dynamodb.return_value.Table.return_value = MockDynamoDBTable("test-table")
            mock_postgres.connect.return_value = MockPostgresConnection()
            mock_snowflake.return_value = MockSnowflakeConnection()
            
            yield {
                "s3": mock_s3.return_value,
                "dynamodb": mock_dynamodb.return_value.Table.return_value,
                "postgres": mock_postgres,
                "snowflake": mock_snowflake.return_value
            }
    
    def test_end_to_end_article_processing(self, mock_all_services):
        """Test complete article processing pipeline."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            from src.database.s3_storage import S3Storage, S3StorageConfig, ArticleType
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager, ArticleMetadataIndex
            
            # Initialize components
            validation_config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=[],
                banned_domains=[],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            validator = DataValidationPipeline(validation_config)
            
            s3_config = S3StorageConfig(bucket_name="test-bucket")
            s3_storage = S3Storage(s3_config)
            
            dynamodb_manager = DynamoDBMetadataManager("test-table")
            
            # Create test bucket
            mock_all_services["s3"].create_bucket(Bucket="test-bucket")
            
            # Test article
            article = {
                "id": "test-123",
                "title": "Test Article for Integration",
                "content": "This is a comprehensive test article with sufficient content for validation.",
                "url": "https://trusted.com/test-article",
                "author": "Test Author",
                "source": "trusted.com",
                "published_date": "2024-01-01T12:00:00Z",
                "category": "technology"
            }
            
            # Step 1: Validate article
            validation_result = validator.validate_article(article)
            assert validation_result.is_valid
            
            # Step 2: Store in S3
            s3_result = s3_storage.upload_article(validation_result.cleaned_data, ArticleType.RAW)
            assert s3_result is not None
            
            # Step 3: Index in DynamoDB
            metadata = ArticleMetadataIndex(
                article_id=article["id"],
                title=article["title"],
                source=article["source"],
                published_date=article["published_date"],
                tags=["technology"],
                content_preview=article["content"][:200]
            )
            
            index_result = dynamodb_manager.index_article_metadata(metadata)
            assert index_result is not None
            
            # Step 4: Search and retrieve
            search_results = dynamodb_manager.search_by_source("trusted.com")
            assert len(search_results) >= 0
            
        except ImportError:
            pytest.skip("Integration test modules not available")
    
    def test_batch_processing_performance(self, mock_all_services):
        """Test batch processing performance and reliability."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            from src.database.s3_storage import S3Storage, S3StorageConfig, ArticleType
            from src.database.dynamodb_metadata_manager import DynamoDBMetadataManager, ArticleMetadataIndex
            
            # Initialize components
            validation_config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=[],
                banned_domains=[],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            validator = DataValidationPipeline(validation_config)
            s3_config = S3StorageConfig(bucket_name="test-bucket")
            s3_storage = S3Storage(s3_config)
            dynamodb_manager = DynamoDBMetadataManager("test-table")
            
            # Create test bucket
            mock_all_services["s3"].create_bucket(Bucket="test-bucket")
            
            # Generate batch of articles
            articles = [
                {
                    "id": f"test-{i}",
                    "title": f"Test Article {i}",
                    "content": f"Content for test article {i} with sufficient length for validation.",
                    "url": f"https://trusted.com/article-{i}",
                    "source": "trusted.com",
                    "published_date": "2024-01-01T12:00:00Z"
                }
                for i in range(10)
            ]
            
            # Batch validation
            validation_results = validator.batch_validate_articles(articles)
            assert len(validation_results) == 10
            assert all(result.is_valid for result in validation_results)
            
            # Batch S3 upload
            valid_articles = [result.cleaned_data for result in validation_results]
            s3_results = s3_storage.batch_upload_articles(valid_articles, ArticleType.RAW)
            assert len(s3_results) == 10
            
            # Batch DynamoDB indexing
            metadata_list = [
                ArticleMetadataIndex(
                    article_id=article["id"],
                    title=article["title"],
                    source=article["source"],
                    published_date=article["published_date"],
                    tags=["technology"],
                    content_preview=article["content"][:200]
                )
                for article in valid_articles
            ]
            
            index_result = dynamodb_manager.batch_index_articles(metadata_list)
            assert index_result is not None
            
        except ImportError:
            pytest.skip("Integration test modules not available")
    
    def test_error_recovery_and_resilience(self, mock_all_services):
        """Test error recovery and system resilience."""
        try:
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            from src.database.s3_storage import S3Storage, S3StorageConfig
            
            # Initialize components
            validation_config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=[],
                banned_domains=[],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            validator = DataValidationPipeline(validation_config)
            s3_config = S3StorageConfig(bucket_name="nonexistent-bucket")
            s3_storage = S3Storage(s3_config)
            
            # Test graceful handling of S3 errors
            article = {
                "title": "Test Article",
                "content": "Test content",
                "url": "https://trusted.com/article"
            }
            
            validation_result = validator.validate_article(article)
            assert validation_result.is_valid
            
            # Attempt S3 upload to nonexistent bucket (should handle gracefully)
            with pytest.raises(Exception):
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
            from src.database.data_validation_pipeline import DataValidationPipeline, SourceReputationConfig
            
            validation_config = SourceReputationConfig(
                trusted_domains=["trusted.com"],
                questionable_domains=[],
                banned_domains=[],
                reputation_thresholds={"high": 0.8, "medium": 0.5, "low": 0.2}
            )
            
            validator = DataValidationPipeline(validation_config)
            
            # Generate large dataset
            articles = [
                {
                    "title": f"Article {i}",
                    "content": f"Content for article {i} " * 50,  # Longer content
                    "url": f"https://trusted.com/article-{i}",
                    "source": "trusted.com",
                    "published_date": "2024-01-01T12:00:00Z"
                }
                for i in range(100)  # Large batch
            ]
            
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
