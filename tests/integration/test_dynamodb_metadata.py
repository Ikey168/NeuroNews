"""
Test suite for DynamoDB Article Metadata Manager - Issue #23

Tests comprehensive metadata indexing functionality including:
- Article metadata indexing and retrieval
- Query API for quick lookups by various fields
- Full-text search capabilities
- Batch operations and performance
- Integration with existing systems
"""

import asyncio
import json
import os

# Import the modules to test
import sys
import time
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from src.database.dynamodb_metadata_manager import (
    ArticleMetadataIndex,
    DynamoDBMetadataConfig,
    DynamoDBMetadataManager,
    QueryResult,
    SearchMode,
    SearchQuery,
    integrate_with_redshift_etl,
    integrate_with_s3_storage,
    sync_metadata_from_scraper,
)


class TestArticleMetadataIndex(unittest.TestCase):
    """Test ArticleMetadataIndex data class."""

    def setUp(self):
        """Set up test data."""
        self.sample_metadata = ArticleMetadataIndex(
            article_id="test-article-123",
            content_hash="sha256-hash-example",
            title="AI Breakthrough in Healthcare Technology",
            source="TechNews",
            published_date="2025-08-13",
            tags=["AI", "Healthcare", "Technology"],
            url="https://technews.com/ai-healthcare",
            author="Dr. Jane Smith",
            category="Technology",
            content_summary="Revolutionary AI system transforms healthcare diagnostics...",
            word_count=1250,
            sentiment_score=0.85,
        )

    def test_metadata_creation(self):
        """Test ArticleMetadataIndex creation and field validation."""
        metadata = self.sample_metadata

        # Verify required fields
        self.assertEqual(metadata.article_id, "test-article-123")
        self.assertEqual(metadata.title, "AI Breakthrough in Healthcare Technology")
        self.assertEqual(metadata.source, "TechNews")
        self.assertEqual(metadata.published_date, "2025-08-13")
        self.assertEqual(metadata.tags, ["AI", "Healthcare", "Technology"])

        # Verify auto-generated fields
        self.assertIsNotNone(metadata.indexed_date)
        self.assertIsNotNone(metadata.last_updated)
        self.assertIsInstance(metadata.title_tokens, list)
        self.assertGreater(len(metadata.title_tokens), 0)

    def test_title_tokenization(self):
        """Test automatic title tokenization for search."""
        metadata = self.sample_metadata

        # Check that title is properly tokenized
        expected_tokens = ["breakthrough", "healthcare", "technology"]
        for token in expected_tokens:
            self.assertIn(token, metadata.title_tokens)

        # Check that short words are filtered out
        self.assertNotIn("ai", metadata.title_tokens)  # Too short
        self.assertNotIn("in", metadata.title_tokens)  # Too short

    def test_dynamodb_serialization(self):
        """Test conversion to/from DynamoDB format."""
        metadata = self.sample_metadata

        # Convert to DynamoDB item
        item = metadata.to_dynamodb_item()

        # Verify required fields are present
        self.assertEqual(item["article_id"], "test-article-123")
        self.assertEqual(item["title"], "AI Breakthrough in Healthcare Technology")
        self.assertEqual(item["source"], "TechNews")
        self.assertIn("source_date", item)
        self.assertIn("date_source", item)

        # Convert back from DynamoDB item
        restored_metadata = ArticleMetadataIndex.from_dynamodb_item(item)

        # Verify data integrity
        self.assertEqual(restored_metadata.article_id, metadata.article_id)
        self.assertEqual(restored_metadata.title, metadata.title)
        self.assertEqual(restored_metadata.tags, metadata.tags)
        self.assertEqual(restored_metadata.word_count, metadata.word_count)


class TestDynamoDBMetadataManager(unittest.TestCase):
    """Test DynamoDBMetadataManager functionality."""

    def setUp(self):
        """Set up test environment."""
        self.config = DynamoDBMetadataConfig(
            table_name="test-neuronews-metadata",
            region="us-east-1",
            read_capacity_units=5,
            write_capacity_units=5,
        )

        # Mock AWS clients
        self.mock_session = Mock()
        self.mock_dynamodb = Mock()
        self.mock_table = Mock()
        self.mock_client = Mock()

        # Sample test articles
        self.sample_articles = [
            {
                "id": "article-1",
                "title": "AI Revolution in Healthcare",
                "source": "HealthTech",
                "published_date": "2025-08-13",
                "tags": ["AI", "Healthcare"],
                "url": "https://healthtech.com/ai-revolution",
                "author": "Dr. Smith",
                "category": "Technology",
                "content": "Artificial intelligence is transforming healthcare...",
                "word_count": 1500,
                "scraped_date": "2025-08-13T10:00:00Z",
            },
            {
                "id": "article-2",
                "title": "Quantum Computing Breakthrough",
                "source": "ScienceDaily",
                "published_date": "2025-08-12",
                "tags": ["Quantum", "Computing"],
                "url": "https://sciencedaily.com/quantum-breakthrough",
                "author": "Prof. Johnson",
                "category": "Science",
                "content": "Scientists achieve quantum supremacy...",
                "word_count": 1200,
                "scraped_date": "2025-08-13T11:00:00Z",
            },
        ]

    @patch("boto3.Session")
    def test_manager_initialization(self, mock_session_class):
        """Test DynamoDB manager initialization."""
        mock_session_class.return_value = self.mock_session
        self.mock_session.resource.return_value = self.mock_dynamodb
        self.mock_session.client.return_value = self.mock_client
        self.mock_dynamodb.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        manager = DynamoDBMetadataManager(self.config)

        # Verify initialization
        self.assertEqual(manager.config, self.config)
        self.assertEqual(manager.table_name, "test-neuronews-metadata")
        self.assertIsNotNone(manager.table)

    @patch("boto3.Session")
    async def test_index_single_article(self, mock_session_class):
        """Test indexing a single article."""
        mock_session_class.return_value = self.mock_session
        self.mock_session.resource.return_value = self.mock_dynamodb
        self.mock_session.client.return_value = self.mock_client
        self.mock_dynamodb.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        manager = DynamoDBMetadataManager(self.config)

        # Mock successful put_item
        self.mock_table.put_item.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

        # Test indexing
        article_data = self.sample_articles[0]
        result = await manager.index_article_metadata(article_data)

        # Verify result
        self.assertIsInstance(result, ArticleMetadataIndex)
        self.assertEqual(result.title, article_data["title"])
        self.assertEqual(result.source, article_data["source"])
        self.assertEqual(result.tags, article_data["tags"])

        # Verify put_item was called
        self.mock_table.put_item.assert_called_once()

    @patch("boto3.Session")
    async def test_batch_indexing(self, mock_session_class):
        """Test batch indexing multiple articles."""
        mock_session_class.return_value = self.mock_session
        self.mock_session.resource.return_value = self.mock_dynamodb
        self.mock_session.client.return_value = self.mock_client
        self.mock_dynamodb.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        # Mock batch writer
        mock_batch_writer = Mock()
        self.mock_table.batch_writer.return_value.__enter__.return_value = (
            mock_batch_writer
        )

        manager = DynamoDBMetadataManager(self.config)

        # Test batch indexing
        result = await manager.batch_index_articles(self.sample_articles)

        # Verify result
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["total_articles"], 2)
        self.assertEqual(result["indexed_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        self.assertIn("execution_time_ms", result)
        self.assertIn("indexing_rate", result)

        # Verify batch writer was used
        self.assertEqual(mock_batch_writer.put_item.call_count, 2)


class TestQueryAPI(unittest.TestCase):
    """Test query API functionality."""

    def setUp(self):
        """Set up test environment."""
        self.config = DynamoDBMetadataConfig()
        self.mock_table = Mock()

        # Sample query results
        self.sample_items = [
            {
                "article_id": "article-1",
                "title": "AI in Healthcare",
                "source": "HealthTech",
                "published_date": "2025-08-13",
                "tags": ["AI", "Healthcare"],
                "content_summary": "AI transforming healthcare diagnostics",
            },
            {
                "article_id": "article-2",
                "title": "Quantum Computing",
                "source": "ScienceDaily",
                "published_date": "2025-08-12",
                "tags": ["Quantum", "Computing"],
                "content_summary": "Quantum supremacy achieved",
            },
        ]

    @patch("boto3.Session")
    async def test_get_article_by_id(self, mock_session_class):
        """Test getting article by ID."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.resource.return_value = Mock()
        mock_session.client.return_value = Mock()
        mock_session.resource.return_value.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        manager = DynamoDBMetadataManager(self.config)

        # Mock get_item response
        self.mock_table.get_item.return_value = {"Item": self.sample_items[0]}

        # Test get by ID
        result = await manager.get_article_by_id("article-1")

        # Verify result
        self.assertIsInstance(result, ArticleMetadataIndex)
        self.assertEqual(result.article_id, "article-1")
        self.assertEqual(result.title, "AI in Healthcare")

        # Test article not found
        self.mock_table.get_item.return_value = {}
        result = await manager.get_article_by_id("nonexistent")
        self.assertIsNone(result)

    @patch("boto3.Session")
    async def test_get_articles_by_source(self, mock_session_class):
        """Test getting articles by source."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.resource.return_value = Mock()
        mock_session.client.return_value = Mock()
        mock_session.resource.return_value.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        manager = DynamoDBMetadataManager(self.config)

        # Mock query response
        self.mock_table.query.return_value = {
            "Items": [self.sample_items[0]],
            "Count": 1,
        }

        # Test get by source
        result = await manager.get_articles_by_source("HealthTech")

        # Verify result
        self.assertIsInstance(result, QueryResult)
        self.assertEqual(result.count, 1)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source, "HealthTech")
        self.assertIsNotNone(result.execution_time_ms)

    @patch("boto3.Session")
    async def test_get_articles_by_date_range(self, mock_session_class):
        """Test getting articles by date range."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.resource.return_value = Mock()
        mock_session.client.return_value = Mock()
        mock_session.resource.return_value.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        manager = DynamoDBMetadataManager(self.config)

        # Mock scan response
        self.mock_table.scan.return_value = {"Items": self.sample_items, "Count": 2}

        # Test get by date range
        result = await manager.get_articles_by_date_range("2025-08-12", "2025-08-13")

        # Verify result
        self.assertIsInstance(result, QueryResult)
        self.assertEqual(result.count, 2)
        self.assertEqual(len(result.items), 2)
        self.assertIsNotNone(result.execution_time_ms)

    @patch("boto3.Session")
    async def test_get_articles_by_tags(self, mock_session_class):
        """Test getting articles by tags."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.resource.return_value = Mock()
        mock_session.client.return_value = Mock()
        mock_session.resource.return_value.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        manager = DynamoDBMetadataManager(self.config)

        # Mock scan response
        self.mock_table.scan.return_value = {
            "Items": [self.sample_items[0]],  # Only AI article
            "Count": 1,
        }

        # Test get by tags
        result = await manager.get_articles_by_tags(["AI"], match_all=False)

        # Verify result
        self.assertIsInstance(result, QueryResult)
        self.assertEqual(result.count, 1)
        self.assertEqual(result.items[0].article_id, "article-1")


class TestFullTextSearch(unittest.TestCase):
    """Test full-text search functionality."""

    def setUp(self):
        """Set up test environment."""
        self.config = DynamoDBMetadataConfig()
        self.mock_table = Mock()

        # Enhanced sample items with title tokens
        self.sample_items = [
            {
                "article_id": "article-1",
                "title": "AI Revolution in Healthcare",
                "source": "HealthTech",
                "published_date": "2025-08-13",
                "title_tokens": ["revolution", "healthcare"],
                "content_summary": "AI transforming healthcare diagnostics and treatment",
            },
            {
                "article_id": "article-2",
                "title": "Quantum Computing Breakthrough",
                "source": "ScienceDaily",
                "published_date": "2025-08-12",
                "title_tokens": ["quantum", "computing", "breakthrough"],
                "content_summary": "Quantum supremacy achieved in latest experiment",
            },
        ]

    @patch("boto3.Session")
    async def test_search_articles_basic(self, mock_session_class):
        """Test basic article search functionality."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.resource.return_value = Mock()
        mock_session.client.return_value = Mock()
        mock_session.resource.return_value.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        manager = DynamoDBMetadataManager(self.config)

        # Mock scan response
        self.mock_table.scan.return_value = {
            "Items": [self.sample_items[0]],  # Only healthcare article
            "Count": 1,
        }

        # Create search query
        search_query = SearchQuery(
            query_text="healthcare AI",
            fields=["title", "content_summary"],
            search_mode=SearchMode.CONTAINS,
            limit=50,
        )

        # Test search
        result = await manager.search_articles(search_query)

        # Verify result
        self.assertIsInstance(result, QueryResult)
        self.assertGreater(result.count, 0)
        self.assertIsNotNone(result.execution_time_ms)
        self.assertIn("query", result.query_info)
        self.assertIn("tokens", result.query_info)

    @patch("boto3.Session")
    async def test_search_with_filters(self, mock_session_class):
        """Test search with additional filters."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.resource.return_value = Mock()
        mock_session.client.return_value = Mock()
        mock_session.resource.return_value.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        manager = DynamoDBMetadataManager(self.config)

        # Mock scan response
        self.mock_table.scan.return_value = {
            "Items": [self.sample_items[0]],
            "Count": 1,
        }

        # Create search query with filters
        search_query = SearchQuery(
            query_text="AI",
            fields=["title"],
            filters={"source": "HealthTech"},
            date_range={"start": "2025-08-01", "end": "2025-08-31"},
            limit=25,
        )

        # Test search with filters
        result = await manager.search_articles(search_query)

        # Verify result
        self.assertIsInstance(result, QueryResult)
        self.assertIsNotNone(result.execution_time_ms)

    def test_tokenize_search_query(self):
        """Test search query tokenization."""
        manager = DynamoDBMetadataManager.__new__(DynamoDBMetadataManager)

        # Test basic tokenization
        tokens = manager._tokenize_search_query("AI healthcare technology")
        self.assertIn("ai", tokens)
        self.assertIn("healthcare", tokens)
        self.assertIn("technology", tokens)

        # Test punctuation removal
        tokens = manager._tokenize_search_query("AI, machine-learning & healthcare!")
        self.assertIn("ai", tokens)
        self.assertIn("machine", tokens)
        self.assertIn("learning", tokens)
        self.assertIn("healthcare", tokens)

        # Test short word filtering
        tokens = manager._tokenize_search_query("AI in ML")
        self.assertIn("ai", tokens)
        self.assertIn("ml", tokens)
        self.assertNotIn("in", tokens)  # Too short

    def test_relevance_scoring(self):
        """Test search result relevance scoring."""
        manager = DynamoDBMetadataManager.__new__(DynamoDBMetadataManager)

        # Create test metadata
        metadata = ArticleMetadataIndex(
            article_id="test-1",
            content_hash="hash-1",
            title="AI Healthcare Revolution",
            source="TechNews",
            published_date="2025-08-13",
            title_tokens=["ai", "healthcare", "revolution"],
            content_summary="AI is revolutionizing healthcare diagnostics",
        )

        # Test scoring
        search_tokens = ["ai", "healthcare"]
        search_fields = ["title", "title_tokens", "content_summary"]

        score = manager._calculate_relevance_score(
            metadata, search_tokens, search_fields
        )

        # Verify scoring
        self.assertGreater(score, 0)
        self.assertIsInstance(score, float)


class TestIntegrationFunctions(unittest.TestCase):
    """Test integration functions with existing systems."""

    def setUp(self):
        """Set up test environment."""
        self.config = DynamoDBMetadataConfig()
        self.mock_manager = Mock()

        # Sample S3 metadata
        self.s3_metadata = {
            "article_id": "article-123",
            "title": "AI Healthcare Innovation",
            "source": "MedTech",
            "published_date": "2025-08-13",
            "url": "https://medtech.com/ai-innovation",
            "s3_key": "raw_articles/2025/08/13/article-123.json",
            "content_hash": "sha256-hash-example",
            "scraped_date": "2025-08-13T10:00:00Z",
            "processing_status": "stored",
        }

        # Sample Redshift record
        self.redshift_record = {
            "article_id": "article-123",
            "title": "AI Healthcare Innovation",
            "content": "Full article content...",
            "processed_date": "2025-08-13T11:00:00Z",
        }

    async def test_s3_integration(self):
        """Test integration with S3 storage."""
        # Mock manager response
        self.mock_manager.index_article_metadata = AsyncMock()
        expected_metadata = ArticleMetadataIndex(
            article_id=self.s3_metadata["article_id"],
            content_hash=self.s3_metadata["content_hash"],
            title=self.s3_metadata["title"],
            source=self.s3_metadata["source"],
            published_date=self.s3_metadata["published_date"],
        )
        self.mock_manager.index_article_metadata.return_value = expected_metadata

        # Test integration
        result = await integrate_with_s3_storage(self.s3_metadata, self.mock_manager)

        # Verify integration
        self.assertIsInstance(result, ArticleMetadataIndex)
        self.assertEqual(result.article_id, self.s3_metadata["article_id"])
        self.mock_manager.index_article_metadata.assert_called_once()

    async def test_redshift_integration(self):
        """Test integration with Redshift ETL."""
        # Mock manager response
        self.mock_manager.update_article_metadata = AsyncMock(return_value=True)

        # Test integration
        result = await integrate_with_redshift_etl(
            self.redshift_record, self.mock_manager
        )

        # Verify integration
        self.assertTrue(result)
        self.mock_manager.update_article_metadata.assert_called_once()

        # Check update parameters
        call_args = self.mock_manager.update_article_metadata.call_args
        article_id, updates = call_args[0]
        self.assertEqual(article_id, "article-123")
        self.assertTrue(updates["redshift_loaded"])
        self.assertEqual(updates["processing_status"], "processed")

    async def test_scraper_sync(self):
        """Test sync from scraper."""
        # Mock manager response
        self.mock_manager.batch_index_articles = AsyncMock()
        expected_result = {
            "status": "completed",
            "total_articles": 2,
            "indexed_count": 2,
            "failed_count": 0,
        }
        self.mock_manager.batch_index_articles.return_value = expected_result

        # Sample scraped articles
        articles = [
            {"title": "Article 1", "source": "Source1"},
            {"title": "Article 2", "source": "Source2"},
        ]

        # Test sync
        result = await sync_metadata_from_scraper(articles, self.mock_manager)

        # Verify sync
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["indexed_count"], 2)
        self.mock_manager.batch_index_articles.assert_called_once_with(articles)


class TestStatisticsAndHealth(unittest.TestCase):
    """Test statistics and health monitoring."""

    def setUp(self):
        """Set up test environment."""
        self.config = DynamoDBMetadataConfig()
        self.mock_table = Mock()

    @patch("boto3.Session")
    async def test_metadata_statistics(self, mock_session_class):
        """Test metadata statistics generation."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.resource.return_value = Mock()
        mock_session.client.return_value = Mock()
        mock_session.resource.return_value.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }

        manager = DynamoDBMetadataManager(self.config)

        # Mock scan responses
        self.mock_table.scan.side_effect = [
            {"Count": 1000},  # Total count
            {  # Sample data
                "Items": [
                    {
                        "source": "TechNews",
                        "category": "Technology",
                        "published_date": "2025-08-13",
                    },
                    {
                        "source": "HealthNews",
                        "category": "Health",
                        "published_date": "2025-08-12",
                    },
                ]
            },
        ]

        # Test statistics
        stats = await manager.get_metadata_statistics()

        # Verify statistics
        self.assertEqual(stats["total_articles"], 1000)
        self.assertIn("source_distribution", stats)
        self.assertIn("category_distribution", stats)
        self.assertIn("monthly_distribution", stats)
        self.assertIn("execution_time_ms", stats)
        self.assertIn("table_info", stats)

    @patch("boto3.Session")
    async def test_health_check(self, mock_session_class):
        """Test health check functionality."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.resource.return_value = Mock()
        mock_session.client.return_value = Mock()
        mock_session.resource.return_value.Table.return_value = self.mock_table

        # Mock table exists
        self.mock_table.meta.client.describe_table.return_value = {
            "Table": {
                "TableStatus": "ACTIVE",
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 10,
                    "WriteCapacityUnits": 10,
                },
                "ItemCount": 1500,
                "TableSizeBytes": 1024000,
                "GlobalSecondaryIndexes": [{"IndexName": "source-date-index"}],
            }
        }

        # Mock scan for health check
        self.mock_table.scan.return_value = {"Items": [{}]}

        manager = DynamoDBMetadataManager(self.config)

        # Test health check
        health = await manager.health_check()

        # Verify health check
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["table_status"], "ACTIVE")
        self.assertEqual(health["read_capacity"], 10)
        self.assertEqual(health["write_capacity"], 10)
        self.assertEqual(health["item_count"], 1500)
        self.assertEqual(health["indexes"], 1)
        self.assertIn("timestamp", health)


async def run_async_tests():
    """Run all async tests."""
    # Create test instances
    metadata_test = TestArticleMetadataIndex()
    manager_test = TestDynamoDBMetadataManager()
    query_test = TestQueryAPI()
    search_test = TestFullTextSearch()
    integration_test = TestIntegrationFunctions()
    stats_test = TestStatisticsAndHealth()

    # Run async tests
    print("Testing DynamoDB Article Metadata Manager...")

    # Test single article indexing
    await manager_test.test_index_single_article()
    print("✅ Single article indexing test passed")

    # Test batch indexing
    await manager_test.test_batch_indexing()
    print("✅ Batch indexing test passed")

    # Test query API
    await query_test.test_get_article_by_id()
    print("✅ Get article by ID test passed")

    await query_test.test_get_articles_by_source()
    print("✅ Get articles by source test passed")

    await query_test.test_get_articles_by_date_range()
    print("✅ Get articles by date range test passed")

    await query_test.test_get_articles_by_tags()
    print("✅ Get articles by tags test passed")

    # Test search functionality
    await search_test.test_search_articles_basic()
    print("✅ Basic search test passed")

    await search_test.test_search_with_filters()
    print("✅ Search with filters test passed")

    # Test integration functions
    await integration_test.test_s3_integration()
    print("✅ S3 integration test passed")

    await integration_test.test_redshift_integration()
    print("✅ Redshift integration test passed")

    await integration_test.test_scraper_sync()
    print("✅ Scraper sync test passed")

    # Test statistics and health
    await stats_test.test_metadata_statistics()
    print("✅ Metadata statistics test passed")

    await stats_test.test_health_check()
    print("✅ Health check test passed")

    print("\n🎉 All DynamoDB metadata manager tests passed!")


if __name__ == "__main__":
    # Run synchronous tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestArticleMetadataIndex)
    unittest.TextTestRunner(verbosity=2).run(suite)

    # Run async tests
    asyncio.run(run_async_tests())
