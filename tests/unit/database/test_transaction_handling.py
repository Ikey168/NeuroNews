import sys
from unittest.mock import MagicMock, patch

# Mock snowflake.connector and pandas before importing modules that use them
sys.modules["snowflake"] = MagicMock()
sys.modules["snowflake.connector"] = MagicMock()
sys.modules["snowflake.connector.pandas_tools"] = MagicMock()
sys.modules["pandas"] = MagicMock()

import pytest
from src.neuronews.data.database.snowflake_loader import SnowflakeETLProcessor, SnowflakeArticleRecord

class TestTransactionHandling:
    """Test transaction handling and ACID compliance in SnowflakeETLProcessor."""

    def setup_method(self):
        self.config = {
            "account": "test_account",
            "user": "test_user",
            "password": "test_password",
            "warehouse": "test_wh",
            "database": "test_db",
            "schema": "test_schema"
        }
        self.processor = SnowflakeETLProcessor(**self.config)
        
        # Mock connection and cursor
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value = self.mock_cursor
        
        # Inject mock connection
        with patch("src.neuronews.data.database.snowflake_loader.snowflake.connector.connect", return_value=self.mock_conn):
            self.processor.connect()

    def test_commit_method(self):
        """Test explicit commit method."""
        self.processor.commit()
        self.mock_conn.commit.assert_called_once()

    def test_rollback_method(self):
        """Test explicit rollback method."""
        self.processor.rollback()
        self.mock_conn.rollback.assert_called_once()

    def test_initialize_schema_success_commits(self):
        """Test initialize_schema commits on success."""
        with patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value="CREATE TABLE test;")))))):
            self.processor.initialize_schema("dummy_path.sql")
            
        self.mock_cursor.execute.assert_called()
        self.mock_conn.commit.assert_called()
        self.mock_conn.rollback.assert_not_called()

    def test_initialize_schema_failure_rollbacks(self):
        """Test initialize_schema rollbacks on failure."""
        with patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value="CREATE TABLE test;")))))):
            self.mock_cursor.execute.side_effect = Exception("SQL Error")
            
            with pytest.raises(Exception):
                self.processor.initialize_schema("dummy_path.sql")
            
        self.mock_conn.rollback.assert_called()

    def test_load_single_article_success_commits(self):
        """Test load_single_article commits on success."""
        article = {
            "id": "123",
            "url": "http://test.com",
            "title": "Test",
            "content": "Content",
            "source": "Source"
        }
        
        # Mock _article_exists to return False
        self.processor._article_exists = MagicMock(return_value=False)
        
        result = self.processor.load_single_article(article)
        
        assert result is True
        self.mock_conn.commit.assert_called()
        self.mock_conn.rollback.assert_not_called()

    def test_load_single_article_failure_rollbacks(self):
        """Test load_single_article rollbacks on failure."""
        article = {
            "id": "123",
            "url": "http://test.com",
            "title": "Test",
            "content": "Content",
            "source": "Source"
        }
        
        # Mock _article_exists to return False
        self.processor._article_exists = MagicMock(return_value=False)
        
        # Make execute fail
        self.mock_cursor.execute.side_effect = Exception("Insert failed")
        
        result = self.processor.load_single_article(article)
        
        assert result is False
        self.mock_conn.rollback.assert_called()

    def test_load_articles_batch_failure_rollbacks(self):
        """Test load_articles_batch rollbacks on catastrophic failure."""
        articles = [{"id": "1", "url": "u1", "title": "t1", "content": "c1", "source": "s1"}]
        
        # We need to trigger an exception inside the main try block.
        # We can mock logger.info to raise an exception.
        
        with patch("src.neuronews.data.database.snowflake_loader.logger.info") as mock_logger:
            mock_logger.side_effect = Exception("Logger failed")
            
            with pytest.raises(Exception):
                self.processor.load_articles_batch(articles)
                
            self.mock_conn.rollback.assert_called()

    def test_context_manager_rollback_on_error(self):
        """Test context manager rollbacks on unhandled exception."""
        # We need to patch connect again because we are creating a new instance via context manager
        with patch("src.neuronews.data.database.snowflake_loader.snowflake.connector.connect") as mock_connect_cls:
            mock_conn = MagicMock()
            mock_connect_cls.return_value = mock_conn
            
            try:
                with SnowflakeETLProcessor(**self.config) as processor:
                    raise ValueError("Crash")
            except ValueError:
                pass
            
            mock_conn.rollback.assert_called()
