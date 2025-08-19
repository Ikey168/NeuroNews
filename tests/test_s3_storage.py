import asyncio
import json
import os
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import hashlib

import sys

sys.path.append("/workspaces/NeuroNews")

from src.database.s3_storage import (
    S3ArticleStorage,
    S3StorageConfig,
    ArticleType,
    ArticleMetadata,
    ingest_scraped_articles_to_s3,
    verify_s3_data_consistency,
)


class TestS3ArticleStorage:
    """Test suite for S3 article storage functionality."""

    @pytest.fixture
    def s3_config(self):
        """Create test S3 configuration."""
        return S3StorageConfig(
            bucket_name="test-neuronews-bucket",
            region="us-east-1",
            raw_prefix="raw_articles",
            processed_prefix="processed_articles",
            enable_versioning=True,
            enable_encryption=True,
            storage_class="STANDARD",
            lifecycle_days=365,
            max_file_size_mb=100,
        )

    @pytest.fixture
    def sample_article(self):
        """Create sample article data."""
        return {
            "title": "Test Article",
            "content": "This is test content for the article.",
            "url": "https://example.com/test-article",
            "source": "test-source",
            "published_date": "2025-08-13",
            "author": "Test Author",
            "tags": ["test", "news"],
        }

    @pytest.fixture
    def mock_s3_client(self):
        """Create mock S3 client."""
        client = Mock()
        client.head_bucket.return_value = None
        client.put_bucket_versioning.return_value = None
        client.put_bucket_lifecycle_configuration.return_value = None
        client.put_object.return_value = {"ETag": "test-etag"}
        client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=b'{"test": "data"}'))
        }
        client.head_object.return_value = {
            "ContentLength": 1000,
            "LastModified": datetime.now(timezone.utc),
        }
        client.delete_object.return_value = None
        client.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "test/key1.json"}, {"Key": "test/key2.json"}]}
        ]
        return client

    @patch("boto3.client")
    def test_s3_storage_initialization(self, mock_boto3, s3_config, mock_s3_client):
        """Test S3ArticleStorage initialization."""
        mock_boto3.return_value = mock_s3_client

        storage = S3ArticleStorage(s3_config)

        assert storage.config == s3_config
        assert storage.bucket_name == s3_config.bucket_name
        mock_boto3.assert_called_once_with("s3", region_name=s3_config.region)

    @patch("boto3.client")
    def test_generate_s3_key_raw_article(
        self, mock_boto3, s3_config, mock_s3_client, sample_article
    ):
        """Test S3 key generation for raw articles."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        key = storage._generate_s3_key(sample_article, ArticleType.RAW)

        assert key.startswith("raw_articles/2025/08/13/")
        assert key.endswith(".json")

    @patch("boto3.client")
    def test_generate_s3_key_processed_article(
        self, mock_boto3, s3_config, mock_s3_client, sample_article
    ):
        """Test S3 key generation for processed articles."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        key = storage._generate_s3_key(sample_article, ArticleType.PROCESSED)

        assert key.startswith("processed_articles/2025/08/13/")
        assert key.endswith(".json")

    @patch("boto3.client")
    def test_calculate_content_hash(self, mock_boto3, s3_config, mock_s3_client):
        """Test content hash calculation."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        content = "Test content"
        hash_result = storage._calculate_content_hash(content)
        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        assert hash_result == expected_hash

    @patch("boto3.client")
    async def test_store_raw_article_success(
        self, mock_boto3, s3_config, mock_s3_client, sample_article
    ):
        """Test successful raw article storage."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        metadata = await storage.store_raw_article(sample_article)

        assert isinstance(metadata, ArticleMetadata)
        assert metadata.article_type == ArticleType.RAW
        assert metadata.processing_status == "stored"
        assert metadata.source == sample_article["source"]
        assert metadata.url == sample_article["url"]
        assert metadata.title == sample_article["title"]

        mock_s3_client.put_object.assert_called_once()

    @patch("boto3.client")
    async def test_store_raw_article_missing_fields(
        self, mock_boto3, s3_config, mock_s3_client
    ):
        """Test raw article storage with missing required fields."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        incomplete_article = {"title": "Test"}  # Missing content and url

        with pytest.raises(ValueError, match="Missing required fields"):
            await storage.store_raw_article(incomplete_article)

    @patch("boto3.client")
    async def test_store_processed_article_success(
        self, mock_boto3, s3_config, mock_s3_client, sample_article
    ):
        """Test successful processed article storage."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        # Add processing metadata
        processing_metadata = {
            "nlp_processed": True,
            "sentiment_score": 0.8,
            "entities": ["test", "article"],
        }

        metadata = await storage.store_processed_article(
            sample_article, processing_metadata
        )

        assert isinstance(metadata, ArticleMetadata)
        assert metadata.article_type == ArticleType.PROCESSED
        assert metadata.processing_status == "processed"

        mock_s3_client.put_object.assert_called_once()

    @patch("boto3.client")
    async def test_retrieve_article_success(
        self, mock_boto3, s3_config, mock_s3_client
    ):
        """Test successful article retrieval."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        test_data = {"test": "data", "content": "test content"}
        mock_s3_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps(test_data).encode()))
        }

        result = await storage.retrieve_article("test/key.json")

        assert result == test_data
        mock_s3_client.get_object.assert_called_once_with(
            Bucket=s3_config.bucket_name, Key="test/key.json"
        )

    @patch("boto3.client")
    async def test_verify_article_integrity_success(
        self, mock_boto3, s3_config, mock_s3_client
    ):
        """Test successful article integrity verification."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        content = "test content"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        test_data = {"content": content, "content_hash": content_hash}

        mock_s3_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps(test_data).encode()))
        }

        is_valid = await storage.verify_article_integrity("test/key.json")

        assert is_valid is True

    @patch("boto3.client")
    async def test_verify_article_integrity_failure(
        self, mock_boto3, s3_config, mock_s3_client
    ):
        """Test article integrity verification failure."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        test_data = {"content": "test content", "content_hash": "invalid_hash"}

        mock_s3_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps(test_data).encode()))
        }

        is_valid = await storage.verify_article_integrity("test/key.json")

        assert is_valid is False

    @patch("boto3.client")
    async def test_list_articles_by_date(self, mock_boto3, s3_config, mock_s3_client):
        """Test listing articles by date."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "raw_articles/2025/08/13/article1.json"},
                    {"Key": "raw_articles/2025/08/13/article2.json"},
                ]
            }
        ]
        mock_s3_client.get_paginator.return_value = mock_paginator

        articles = await storage.list_articles_by_date("2025-08-13", ArticleType.RAW)

        assert len(articles) == 2
        assert all("2025/08/13" in key for key in articles)

    @patch("boto3.client")
    async def test_batch_store_raw_articles(
        self, mock_boto3, s3_config, mock_s3_client
    ):
        """Test batch storage of raw articles."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        articles = [
            {
                "title": f"Article {i}",
                "content": f"Content {i}",
                "url": f"https://example.com/article{i}",
                "source": "test-source",
            }
            for i in range(3)
        ]

        results = await storage.batch_store_raw_articles(articles)

        assert len(results) == 3
        assert all(isinstance(r, ArticleMetadata) for r in results)
        assert mock_s3_client.put_object.call_count == 3

    @patch("boto3.client")
    async def test_get_storage_statistics(self, mock_boto3, s3_config, mock_s3_client):
        """Test getting storage statistics."""
        mock_boto3.return_value = mock_s3_client
        storage = S3ArticleStorage(s3_config)

        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "raw_articles/article1.json"},
                    {"Key": "raw_articles/article2.json"},
                ]
            }
        ]
        mock_s3_client.get_paginator.return_value = mock_paginator

        stats = await storage.get_storage_statistics()

        assert "raw_articles" in stats
        assert "processed_articles" in stats
        assert "total_count" in stats
        assert isinstance(stats["raw_articles"]["count"], int)

    @patch("boto3.client")
    async def test_s3_client_unavailable(self, mock_boto3, s3_config):
        """Test behavior when S3 client is unavailable."""
        mock_boto3.side_effect = Exception("No credentials")

        storage = S3ArticleStorage(s3_config)

        assert storage.s3_client is None

        with pytest.raises(ValueError, match="S3 client not available"):
            await storage.store_raw_article(
                {"title": "test", "content": "test", "url": "test"}
            )


class TestS3IngestionFunctions:
    """Test suite for S3 ingestion functions."""

    @pytest.fixture
    def s3_config(self):
        """Create test S3 configuration."""
        return S3StorageConfig(bucket_name="test-bucket", region="us-east-1")

    @pytest.fixture
    def sample_articles(self):
        """Create sample articles for testing."""
        return [
            {
                "title": f"Article {i}",
                "content": f"Content for article {i}",
                "url": f"https://example.com/article{i}",
                "source": "test-source",
                "published_date": "2025-08-13",
            }
            for i in range(5)
        ]

    @patch("src.database.s3_storage.S3ArticleStorage")
    async def test_ingest_scraped_articles_success(
        self, mock_storage_class, s3_config, sample_articles
    ):
        """Test successful article ingestion."""
        # Mock storage instance
        mock_storage = Mock()
        mock_storage.batch_store_raw_articles.return_value = [
            ArticleMetadata(
                article_id=f"id{i}",
                source="test-source",
                url=f"https://example.com/article{i}",
                title=f"Article {i}",
                published_date="2025-08-13",
                scraped_date="2025-08-13T10:00:00Z",
                content_hash="hash",
                file_size=1000,
                s3_key=f"raw_articles/2025/08/13/id{i}.json",
                article_type=ArticleType.RAW,
                processing_status="stored",
            )
            for i in range(5)
        ]
        mock_storage.get_storage_statistics.return_value = {
            "total_count": 5,
            "raw_articles": {"count": 5},
        }
        mock_storage_class.return_value = mock_storage

        result = await ingest_scraped_articles_to_s3(sample_articles, s3_config)

        assert result["status"] == "success"
        assert result["total_articles"] == 5
        assert result["stored_articles"] == 5
        assert result["failed_articles"] == 0
        assert len(result["stored_keys"]) == 5

    @patch("src.database.s3_storage.S3ArticleStorage")
    async def test_ingest_empty_articles(self, mock_storage_class, s3_config):
        """Test ingestion with empty articles list."""
        result = await ingest_scraped_articles_to_s3([], s3_config)

        assert result["status"] == "success"
        assert result["total_articles"] == 0
        assert result["stored_articles"] == 0

    @patch("src.database.s3_storage.S3ArticleStorage")
    async def test_verify_s3_data_consistency_success(
        self, mock_storage_class, s3_config
    ):
        """Test successful data consistency verification."""
        # Mock storage instance
        mock_storage = Mock()
        mock_storage.list_articles_by_prefix.return_value = [
            "raw_articles/2025/08/13/article1.json",
            "raw_articles/2025/08/13/article2.json",
        ]
        mock_storage.verify_article_integrity.return_value = True
        mock_storage.get_storage_statistics.return_value = {"total_count": 2}
        mock_storage_class.return_value = mock_storage

        result = await verify_s3_data_consistency(s3_config, sample_size=10)

        assert result["status"] == "success"
        assert result["total_checked"] == 4  # 2 raw + 2 processed
        assert result["valid_articles"] == 4
        assert result["invalid_articles"] == 0
        assert result["integrity_rate"] == 100.0

    @patch("src.database.s3_storage.S3ArticleStorage")
    async def test_verify_s3_data_consistency_with_failures(
        self, mock_storage_class, s3_config
    ):
        """Test data consistency verification with some failures."""
        # Mock storage instance
        mock_storage = Mock()
        mock_storage.list_articles_by_prefix.return_value = [
            "raw_articles/2025/08/13/article1.json",
            "raw_articles/2025/08/13/article2.json",
        ]

        # Mock integrity check to return False for one article
        def mock_verify(key):
            return "article1" in key

        mock_storage.verify_article_integrity.side_effect = mock_verify
        mock_storage.get_storage_statistics.return_value = {"total_count": 2}
        mock_storage_class.return_value = mock_storage

        result = await verify_s3_data_consistency(s3_config, sample_size=10)

        assert result["status"] == "warning"
        assert result["total_checked"] == 4
        assert result["valid_articles"] == 2
        assert result["invalid_articles"] == 2
        assert result["integrity_rate"] == 50.0


if __name__ == "__main__":
    # Run basic tests
    print("Testing S3 Article Storage...")

    # Test configuration
    config = S3StorageConfig(
        bucket_name="test-bucket",
        region="us-east-1",
        raw_prefix="raw_articles",
        processed_prefix="processed_articles",
    )

    # Test article
    article = {
        "title": "Test Article",
        "content": "This is test content.",
        "url": "https://example.com/test",
        "source": "test-source",
        "published_date": "2025-08-13",
    }

    # Mock storage for basic functionality test
    try:
        storage = S3ArticleStorage(config)
        print("✅ S3ArticleStorage initialization successful")

        # Test key generation
        key = storage._generate_s3_key(article, ArticleType.RAW)
        print(f"✅ S3 key generated: {key}")

        # Test hash calculation
        content_hash = storage._calculate_content_hash(article["content"])
        print(f"✅ Content hash calculated: {content_hash[:16]}...")

        print("\n🎯 All basic tests passed!")
        print("Note: AWS integration tests require valid credentials")

    except Exception as e:
        print(f"⚠️  Basic test completed with expected credential warning: {e}")
        print("✅ This is normal in development environment without AWS credentials")
