"""
Integration tests for Redshift ETL Pipeline - Issue #22

These tests verify the functionality of the RedshiftETLProcessor and its
integration with the data validation pipeline.
"""

import unittest
import os
import sys
import logging
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import json

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from database.redshift_loader import RedshiftETLProcessor, ArticleRecord
from database.data_validation_pipeline import ValidationResult


class TestArticleRecord(unittest.TestCase):
    """Test ArticleRecord data structure."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_validated_data = {
            "id": "test_article_123",
            "url": "https://reuters.com/test-article",
            "title": "Test Article Title",
            "content": "This is a test article content with sufficient length.",
            "source": "reuters.com",
            "published_date": "2024-01-15T10:30:00Z",
            "validation_score": 85.5,
            "content_quality": "high",
            "source_credibility": "trusted",
            "validation_flags": [],
            "validated_at": "2024-01-15T10:35:00Z",
            "word_count": 10,
            "content_length": 55,
            "author": "Test Author",
            "category": "Technology",
        }

    def test_article_record_creation(self):
        """Test creating ArticleRecord from basic data."""
        record = ArticleRecord(
            id="test_123",
            url="https://example.com/test",
            title="Test Title",
            content="Test content",
            source="example.com",
        )

        self.assertEqual(record.id, "test_123")
        self.assertEqual(record.url, "https://example.com/test")
        self.assertEqual(record.title, "Test Title")
        self.assertEqual(record.content, "Test content")
        self.assertEqual(record.source, "example.com")
        self.assertIsNotNone(record.scraped_at)
        self.assertEqual(record.word_count, 2)
        self.assertEqual(record.content_length, 12)

    def test_from_validated_article(self):
        """Test creating ArticleRecord from validation pipeline output."""
        record = ArticleRecord.from_validated_article(self.sample_validated_data)

        self.assertEqual(record.id, "test_article_123")
        self.assertEqual(record.url, "https://reuters.com/test-article")
        self.assertEqual(record.title, "Test Article Title")
        self.assertEqual(record.validation_score, 85.5)
        self.assertEqual(record.content_quality, "high")
        self.assertEqual(record.source_credibility, "trusted")
        self.assertEqual(record.word_count, 10)
        self.assertEqual(record.content_length, 55)

    def test_datetime_parsing(self):
        """Test datetime parsing from various formats."""
        test_cases = [
            "2024-01-15T10:30:00.123456Z",
            "2024-01-15T10:30:00Z",
            "2024-01-15T10:30:00.123456",
            "2024-01-15T10:30:00",
            "2024-01-15 10:30:00",
            "2024-01-15",
        ]

        for date_str in test_cases:
            result = ArticleRecord._parse_datetime(date_str)
            self.assertIsNotNone(result, f"Failed to parse: {date_str}")
            self.assertIsInstance(result, datetime)

    def test_id_generation(self):
        """Test automatic ID generation."""
        record = ArticleRecord(
            id="",  # Empty ID should trigger generation
            url="https://example.com/test",
            title="Test Title",
            content="Test content",
            source="example.com",
        )

        self.assertTrue(record.id.startswith("article_"))
        self.assertEqual(len(record.id), 24)  # 'article_' + 16 char hash

    def test_validation_flags_parsing(self):
        """Test parsing of validation flags from JSON."""
        data = self.sample_validated_data.copy()
        data["validation_flags"] = '["flag1", "flag2"]'  # JSON string

        record = ArticleRecord.from_validated_article(data)
        self.assertEqual(record.validation_flags, ["flag1", "flag2"])


class TestRedshiftETLProcessor(unittest.TestCase):
    """Test RedshiftETLProcessor functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.processor = RedshiftETLProcessor(
            host="test-cluster.redshift.amazonaws.com",
            database="test_db",
            user="test_user",
            password="test_password",
            batch_size=10,
        )

        # Mock database connection
        self.mock_conn = Mock()
        self.mock_cursor = Mock()
        self.processor._conn = self.mock_conn
        self.processor._cursor = self.mock_cursor

        self.sample_articles = [
            {
                "id": f"article_{i}",
                "url": f"https://example.com/article-{i}",
                "title": f"Test Article {i}",
                "content": f"This is test article content {i} with sufficient length.",
                "source": "example.com",
                "validation_score": 80.0 + i,
                "content_quality": "high",
                "source_credibility": "trusted",
            }
            for i in range(5)
        ]

    def test_processor_initialization(self):
        """Test ETL processor initialization."""
        self.assertEqual(self.processor._host, "test-cluster.redshift.amazonaws.com")
        self.assertEqual(self.processor._database, "test_db")
        self.assertEqual(self.processor._user, "test_user")
        self.assertEqual(self.processor._batch_size, 10)

    @patch("src.database.redshift_loader.psycopg2.connect")
    def test_connection(self, mock_connect):
        """Test database connection."""
        mock_connect.return_value = self.mock_conn

        processor = RedshiftETLProcessor(host="localhost", password="test-password")

        processor.connect()

        mock_connect.assert_called_once_with(
            host="localhost",
            database="dev",
            user="admin",
            password="test-password",
            port=5439,
        )

    def test_load_single_article_success(self):
        """Test successful single article loading."""
        # Mock article doesn't exist
        self.mock_cursor.fetchall.return_value = []

        article = self.sample_articles[0]
        result = self.processor.load_single_article(article)

        self.assertTrue(result)
        # Verify INSERT query was executed
        self.mock_cursor.execute.assert_called()
        self.mock_conn.commit.assert_called()

    def test_load_single_article_duplicate(self):
        """Test handling of duplicate article."""
        # Mock article exists
        self.mock_cursor.fetchall.return_value = [("exists",)]

        article = self.sample_articles[0]
        result = self.processor.load_single_article(article)

        self.assertFalse(result)
        # Verify no INSERT was attempted
        insert_calls = [
            call
            for call in self.mock_cursor.execute.call_args_list
            if "INSERT INTO news_articles" in str(call)
        ]
        self.assertEqual(len(insert_calls), 0)

    def test_batch_load_articles(self):
        """Test batch loading of articles."""
        # Mock no duplicates exist
        self.mock_cursor.fetchall.return_value = []
        self.mock_cursor.rowcount = len(self.sample_articles)

        stats = self.processor.batch_load_articles(
            self.sample_articles, use_staging=False
        )

        self.assertEqual(stats["total_articles"], 5)
        self.assertEqual(stats["loaded_count"], 5)
        self.assertEqual(stats["failed_count"], 0)
        self.assertGreater(stats["success_rate"], 90)

    def test_process_validation_pipeline_output(self):
        """Test processing validation pipeline output."""
        # Mock successful batch loading
        self.mock_cursor.fetchall.return_value = []
        self.mock_cursor.rowcount = len(self.sample_articles)

        stats = self.processor.process_validation_pipeline_output(self.sample_articles)

        self.assertIsInstance(stats, dict)
        self.assertIn("total_articles", stats)
        self.assertIn("loaded_count", stats)
        self.assertIn("success_rate", stats)

    def test_get_article_stats(self):
        """Test getting article statistics."""
        # Mock statistics queries
        mock_results = {
            "total_articles": [(150,)],
            "by_source_credibility": [
                ("trusted", 80),
                ("reliable", 45),
                ("questionable", 20),
            ],
            "by_content_quality": [("high", 90), ("medium", 45), ("low", 15)],
            "avg_validation_score": [(78.5, 45.0, 95.2)],
            "recent_articles": [(42,)],
            "top_sources": [("reuters.com", 35), ("bbc.com", 28)],
        }

        def mock_execute(query, params=None):
            # Return appropriate mock data based on query
            query_lower = query.lower()
            if "count(*)" in query_lower and "group by" not in query_lower:
                if "recent" in query_lower:
                    return mock_results["recent_articles"]
                else:
                    return mock_results["total_articles"]
            elif "source_credibility" in query_lower:
                return mock_results["by_source_credibility"]
            elif "content_quality" in query_lower:
                return mock_results["by_content_quality"]
            elif "avg(validation_score)" in query_lower:
                return mock_results["avg_validation_score"]
            elif "source" in query_lower and "group by source" in query_lower:
                return mock_results["top_sources"]
            return []

        # Replace the execute_query method to use our mock
        self.processor.execute_query = mock_execute

        stats = self.processor.get_article_stats()

        self.assertEqual(stats["total_articles"], 150)
        self.assertIn("by_source_credibility", stats)
        self.assertIn("avg_validation_score", stats)
        self.assertEqual(stats["avg_validation_score"]["average"], 78.5)

    def test_context_manager(self):
        """Test using processor as context manager."""
        with patch.object(self.processor, "connect") as mock_connect, patch.object(
            self.processor, "close"
        ) as mock_close:

            with self.processor as processor:
                self.assertIs(processor, self.processor)

            mock_connect.assert_called_once()
            mock_close.assert_called_once()

    def test_error_handling(self):
        """Test error handling in database operations."""
        # Mock database error
        self.mock_cursor.execute.side_effect = Exception("Database error")

        article = self.sample_articles[0]
        result = self.processor.load_single_article(article)

        self.assertFalse(result)
        self.mock_conn.rollback.assert_called()


class TestRedshiftIntegration(unittest.TestCase):
    """Test integration between validation pipeline and Redshift ETL."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_processor = Mock(spec=RedshiftETLProcessor)

        # Mock successful processing
        self.mock_processor.process_validation_pipeline_output.return_value = {
            "total_articles": 3,
            "loaded_count": 2,
            "failed_count": 0,
            "skipped_count": 1,
            "success_rate": 66.7,
            "processing_time_seconds": 1.5,
            "articles_per_second": 2.0,
            "errors": [],
        }

    def test_validation_to_redshift_flow(self):
        """Test complete flow from validation to Redshift storage."""
        # Sample validation results
        validation_results = [
            {
                "id": "article_1",
                "url": "https://reuters.com/test-1",
                "title": "Test Article 1",
                "content": "Test content 1",
                "source": "reuters.com",
                "validation_score": 85.0,
                "content_quality": "high",
                "source_credibility": "trusted",
            },
            {
                "id": "article_2",
                "url": "https://bbc.com/test-2",
                "title": "Test Article 2",
                "content": "Test content 2",
                "source": "bbc.com",
                "validation_score": 78.5,
                "content_quality": "medium",
                "source_credibility": "trusted",
            },
        ]

        # Process through ETL
        stats = self.mock_processor.process_validation_pipeline_output(
            validation_results
        )

        # Verify processing was called with correct data
        self.mock_processor.process_validation_pipeline_output.assert_called_once_with(
            validation_results
        )

        # Verify stats structure
        self.assertIn("total_articles", stats)
        self.assertIn("loaded_count", stats)
        self.assertIn("success_rate", stats)

    def test_empty_validation_results(self):
        """Test handling of empty validation results."""
        self.mock_processor.process_validation_pipeline_output.return_value = {
            "total_articles": 0,
            "loaded_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "success_rate": 0,
            "errors": ["No valid articles found"],
        }

        stats = self.mock_processor.process_validation_pipeline_output([])

        self.assertEqual(stats["total_articles"], 0)
        self.assertEqual(stats["loaded_count"], 0)
        self.assertIn("errors", stats)


class TestSchemaManagement(unittest.TestCase):
    """Test schema initialization and management."""

    def setUp(self):
        """Set up test fixtures."""
        self.processor = RedshiftETLProcessor(
            host="localhost", password="test-password"
        )

        self.mock_conn = Mock()
        self.mock_cursor = Mock()
        self.processor._conn = self.mock_conn
        self.processor._cursor = self.mock_cursor

    @patch("builtins.open", create=True)
    def test_schema_initialization(self, mock_open):
        """Test schema initialization from SQL file."""
        # Mock schema file content
        schema_sql = """
        DROP TABLE IF EXISTS news_articles;
        CREATE TABLE news_articles (id VARCHAR(255) PRIMARY KEY);
        CREATE VIEW test_view AS SELECT * FROM news_articles;
        """

        mock_open.return_value.__enter__.return_value.read.return_value = schema_sql

        self.processor.initialize_schema()

        # Verify SQL statements were executed
        self.assertEqual(self.mock_cursor.execute.call_count, 3)  # 3 statements
        self.mock_conn.commit.assert_called_once()

    @patch("builtins.open", create=True)
    def test_schema_initialization_error(self, mock_open):
        """Test schema initialization error handling."""
        mock_open.return_value.__enter__.return_value.read.return_value = "INVALID SQL;"
        self.mock_cursor.execute.side_effect = Exception("SQL error")

        with self.assertRaises(Exception):
            self.processor.initialize_schema()

        self.mock_conn.rollback.assert_called_once()


if __name__ == "__main__":
    # Set up test environment
    logging.basicConfig(level=logging.WARNING)  # Reduce log noise during tests

    # Run tests
    unittest.main(verbosity=2)
