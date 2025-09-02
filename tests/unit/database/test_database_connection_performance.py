#!/usr/bin/env python3
"""
Comprehensive Database Connection & Performance Tests
Issue #429: Database: Connection & Performance Tests

This module provides comprehensive testing for:
- Database connection management
- Connection pooling performance
- Query performance and timing
- Cache effectiveness
- Error handling and recovery
- Concurrent connection handling
"""

import asyncio
import concurrent.futures
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import psycopg2
from psycopg2.extras import RealDictCursor

# Test imports with mocking for CI/CD compatibility
try:
    from src.database.setup import (
        cleanup_test_database,
        create_test_articles,
        get_async_connection,
        get_db_config,
        get_sync_connection,
        setup_test_database,
    )
    from src.nlp.summary_database import SummaryDatabase, SummaryRecord
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


class TestDatabaseConnectionBasics:
    """Test basic database connection functionality."""

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    def test_get_db_config_production(self):
        """Test production database configuration."""
        config = get_db_config(testing=False)
        
        assert isinstance(config, dict)
        assert "host" in config
        assert "port" in config
        assert "database" in config
        assert "user" in config
        assert "password" in config
        
        # Verify default values
        assert config["port"] == int(os.getenv("DB_PORT", 5432))
        assert config["host"] == os.getenv("DB_HOST", "postgres")

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    def test_get_db_config_testing(self):
        """Test testing database configuration."""
        config = get_db_config(testing=True)
        
        assert isinstance(config, dict)
        assert config["host"] == os.getenv("DB_HOST", "test-postgres")
        assert config["database"] == os.getenv("DB_NAME", "neuronews_test")
        assert config["user"] == os.getenv("DB_USER", "test_user")

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_get_sync_connection_success(self, mock_connect):
        """Test successful synchronous database connection."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        conn = get_sync_connection(testing=True)
        
        assert conn == mock_conn
        mock_connect.assert_called_once()

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_get_sync_connection_failure(self, mock_connect):
        """Test synchronous database connection failure."""
        mock_connect.side_effect = psycopg2.OperationalError("Connection failed")
        
        with pytest.raises(psycopg2.OperationalError):
            get_sync_connection(testing=True)

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @pytest.mark.asyncio
    @patch('asyncpg.connect')
    async def test_get_async_connection_success(self, mock_connect):
        """Test successful asynchronous database connection."""
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        
        conn = await get_async_connection(testing=True)
        
        assert conn == mock_conn
        mock_connect.assert_called_once()

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @pytest.mark.asyncio
    @patch('asyncpg.connect')
    async def test_get_async_connection_failure(self, mock_connect):
        """Test asynchronous database connection failure."""
        mock_connect.side_effect = Exception("Async connection failed")
        
        with pytest.raises(Exception):
            await get_async_connection(testing=True)


class TestDatabaseConnectionPerformance:
    """Test database connection performance characteristics."""

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_connection_timing(self, mock_connect):
        """Test database connection timing performance."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        # Test connection timing
        start_time = time.time()
        conn = get_sync_connection(testing=True)
        connection_time = time.time() - start_time
        
        assert conn is not None
        assert connection_time < 1.0  # Should connect quickly (mocked)

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_multiple_connections_performance(self, mock_connect):
        """Test performance of multiple sequential connections."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        connection_times = []
        num_connections = 5
        
        for i in range(num_connections):
            start_time = time.time()
            conn = get_sync_connection(testing=True)
            connection_time = time.time() - start_time
            connection_times.append(connection_time)
            
            assert conn is not None
        
        # Verify all connections completed quickly
        avg_time = sum(connection_times) / len(connection_times)
        assert avg_time < 0.1
        assert max(connection_times) < 0.5

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_concurrent_connections(self, mock_connect):
        """Test concurrent database connections performance."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        def create_connection():
            start_time = time.time()
            conn = get_sync_connection(testing=True)
            return time.time() - start_time, conn is not None
        
        # Test concurrent connections
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(create_connection) for _ in range(3)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # Verify all connections succeeded
        for connection_time, success in results:
            assert success
            assert connection_time < 1.0

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @pytest.mark.asyncio
    @patch('asyncpg.connect')
    async def test_async_connection_pool_simulation(self, mock_connect):
        """Test asynchronous connection pooling simulation."""
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        
        async def create_async_connection():
            start_time = time.time()
            conn = await get_async_connection(testing=True)
            return time.time() - start_time, conn is not None
        
        # Test multiple async connections
        tasks = [create_async_connection() for _ in range(3)]
        results = await asyncio.gather(*tasks)
        
        # Verify all async connections succeeded
        for connection_time, success in results:
            assert success
            assert connection_time < 1.0


class TestSummaryDatabasePerformance:
    """Test SummaryDatabase performance characteristics."""

    @pytest.fixture
    def mock_connection_params(self):
        """Provide mock database connection parameters."""
        return {
            "host": "test-host",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_summary_database_initialization(self, mock_connect, mock_connection_params):
        """Test SummaryDatabase initialization performance."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        start_time = time.time()
        db = SummaryDatabase(mock_connection_params)
        init_time = time.time() - start_time
        
        assert db is not None
        assert init_time < 0.1  # Should initialize quickly
        assert db.connection_params == mock_connection_params
        assert isinstance(db.metrics, dict)
        assert "queries_executed" in db.metrics

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_summary_database_connection_method(self, mock_connect, mock_connection_params):
        """Test SummaryDatabase _get_connection method."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        db = SummaryDatabase(mock_connection_params)
        
        start_time = time.time()
        conn = db._get_connection()
        connection_time = time.time() - start_time
        
        assert conn == mock_conn
        assert connection_time < 0.1
        mock_connect.assert_called_with(**mock_connection_params)

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    def test_summary_database_metrics_update(self, mock_connection_params):
        """Test SummaryDatabase metrics update performance."""
        with patch('psycopg2.connect'):
            db = SummaryDatabase(mock_connection_params)
            
            # Test metrics update timing
            start_time = time.time()
            db._update_metrics(0.05, cache_hit=False)
            update_time = time.time() - start_time
            
            assert update_time < 0.01  # Metrics update should be very fast
            assert db.metrics["queries_executed"] == 1
            assert db.metrics["cache_misses"] == 1
            assert db.metrics["total_query_time"] == 0.05

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    def test_summary_database_cache_operations(self, mock_connection_params):
        """Test SummaryDatabase cache performance."""
        with patch('psycopg2.connect'):
            db = SummaryDatabase(mock_connection_params)
            
            # Create mock summary record
            mock_record = MagicMock()
            mock_record.article_id = "test-article-1"
            
            cache_key = "test-key"
            
            # Test cache set performance
            start_time = time.time()
            db._cache_set(cache_key, mock_record)
            cache_set_time = time.time() - start_time
            
            assert cache_set_time < 0.01
            assert cache_key in db._cache
            assert cache_key in db._cache_timestamps
            
            # Test cache get performance
            start_time = time.time()
            retrieved_record = db._cache_get(cache_key)
            cache_get_time = time.time() - start_time
            
            assert cache_get_time < 0.01
            assert retrieved_record == mock_record

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    def test_summary_database_cache_invalidation(self, mock_connection_params):
        """Test SummaryDatabase cache invalidation performance."""
        with patch('psycopg2.connect'):
            db = SummaryDatabase(mock_connection_params)
            db._cache_timeout = 0.1  # Short timeout for testing
            
            mock_record = MagicMock()
            cache_key = "expire-test"
            
            # Set cache entry
            db._cache_set(cache_key, mock_record)
            
            # Wait for expiration
            time.sleep(0.2)
            
            # Test expired cache retrieval performance
            start_time = time.time()
            retrieved_record = db._cache_get(cache_key)
            cache_cleanup_time = time.time() - start_time
            
            assert cache_cleanup_time < 0.01
            assert retrieved_record is None
            assert cache_key not in db._cache  # Should be cleaned up

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    def test_summary_database_performance_metrics_collection(self, mock_connection_params):
        """Test SummaryDatabase performance metrics collection."""
        with patch('psycopg2.connect'):
            db = SummaryDatabase(mock_connection_params)
            
            # Simulate multiple operations
            for i in range(5):
                db._update_metrics(0.1 + (i * 0.01), cache_hit=(i % 2 == 0))
            
            metrics = db.get_performance_metrics()
            
            assert metrics["queries_executed"] == 5
            assert metrics["cache_hits"] == 3
            assert metrics["cache_misses"] == 2
            assert metrics["total_query_time"] == 0.6  # 0.1 + 0.11 + 0.12 + 0.13 + 0.14
            assert metrics["average_query_time"] == 0.12


class TestDatabaseErrorHandling:
    """Test database error handling and recovery."""

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_connection_retry_logic(self, mock_connect):
        """Test database connection retry logic."""
        # Simulate intermittent connection failures
        mock_connect.side_effect = [
            psycopg2.OperationalError("Connection failed"),
            psycopg2.OperationalError("Still failing"),
            MagicMock()  # Third attempt succeeds
        ]
        
        # This test would need retry logic in the actual implementation
        # For now, test that the exception is properly raised
        with pytest.raises(psycopg2.OperationalError):
            get_sync_connection(testing=True)

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_connection_timeout_handling(self, mock_connect):
        """Test database connection timeout handling."""
        mock_connect.side_effect = psycopg2.OperationalError("Timeout")
        
        start_time = time.time()
        with pytest.raises(psycopg2.OperationalError):
            get_sync_connection(testing=True)
        error_time = time.time() - start_time
        
        # Should fail quickly without hanging
        assert error_time < 1.0

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_summary_database_connection_error_handling(self, mock_connect):
        """Test SummaryDatabase connection error handling."""
        mock_connection_params = {
            "host": "test-host",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }
        
        mock_connect.side_effect = psycopg2.OperationalError("Database unavailable")
        
        db = SummaryDatabase(mock_connection_params)
        
        with pytest.raises(psycopg2.OperationalError):
            db._get_connection()


class TestDatabaseSetupPerformance:
    """Test database setup and cleanup performance."""

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('src.database.setup.get_sync_connection')
    @patch('asyncio.sleep')
    async def test_setup_test_database_performance(self, mock_sleep, mock_get_connection):
        """Test setup_test_database performance."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        
        mock_get_connection.return_value = mock_conn
        mock_cursor.fetchall.return_value = [
            ('articles',), ('article_embeddings',), ('api_keys',)
        ]
        
        start_time = time.time()
        await setup_test_database()
        setup_time = time.time() - start_time
        
        assert setup_time < 5.0  # Should complete within reasonable time
        mock_get_connection.assert_called()

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('src.database.setup.get_sync_connection')
    def test_cleanup_test_database_performance(self, mock_get_connection):
        """Test cleanup_test_database performance."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        
        mock_get_connection.return_value = mock_conn
        
        start_time = time.time()
        cleanup_test_database()  # This is a sync function
        cleanup_time = time.time() - start_time
        
        assert cleanup_time < 2.0  # Should complete quickly
        mock_get_connection.assert_called()

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('src.database.setup.get_sync_connection')
    def test_create_test_articles_performance(self, mock_get_connection):
        """Test create_test_articles performance."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        
        # Mock fetchone to return article IDs
        mock_cursor.fetchone.side_effect = [{"id": i} for i in range(1, 11)]
        
        mock_get_connection.return_value = mock_conn
        
        start_time = time.time()
        article_ids = create_test_articles(count=10)
        creation_time = time.time() - start_time
        
        assert creation_time < 1.0  # Should create articles quickly
        assert len(article_ids) == 10
        assert mock_cursor.execute.call_count == 10


class TestConnectionPoolingSimulation:
    """Test connection pooling behavior simulation."""

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_connection_reuse_pattern(self, mock_connect):
        """Test connection reuse patterns."""
        connections = []
        mock_connect.side_effect = lambda **kwargs: connections.append(MagicMock()) or connections[-1]
        
        # Simulate multiple operations using connections
        for i in range(5):
            conn = get_sync_connection(testing=True)
            assert conn is not None
        
        # Verify that connections were created
        assert len(connections) == 5
        assert mock_connect.call_count == 5

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    @patch('psycopg2.connect')
    def test_connection_lifecycle_performance(self, mock_connect):
        """Test complete connection lifecycle performance."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Setup mock connection with cursor
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        
        mock_connect.return_value = mock_conn
        
        start_time = time.time()
        
        # Simulate full connection lifecycle
        conn = get_sync_connection(testing=True)
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        
        lifecycle_time = time.time() - start_time
        
        assert lifecycle_time < 0.1  # Should complete very quickly (mocked)
        assert conn is not None

    @pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
    def test_cache_performance_under_load(self):
        """Test cache performance under simulated load."""
        mock_connection_params = {
            "host": "test-host",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }
        
        with patch('psycopg2.connect'):
            db = SummaryDatabase(mock_connection_params)
            
            # Simulate high cache usage
            num_operations = 100
            cache_operations = []
            
            start_time = time.time()
            
            for i in range(num_operations):
                cache_key = f"test-key-{i % 10}"  # Reuse some keys
                mock_record = MagicMock()
                mock_record.article_id = f"article-{i}"
                
                # Set and get operations
                db._cache_set(cache_key, mock_record)
                retrieved = db._cache_get(cache_key)
                cache_operations.append(retrieved is not None)
            
            total_time = time.time() - start_time
            avg_time_per_op = total_time / (num_operations * 2)  # set + get
            
            assert avg_time_per_op < 0.001  # Very fast cache operations
            assert all(cache_operations)  # All operations should succeed


@pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database modules not available")
class TestDatabaseIntegrationPerformance:
    """Integration tests for database performance."""

    def test_end_to_end_database_operations(self):
        """Test end-to-end database operations performance."""
        mock_connection_params = {
            "host": "test-host",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }
        
        with patch('psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            
            # Setup full mock connection
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
            mock_conn.__enter__ = Mock(return_value=mock_conn)
            mock_conn.__exit__ = Mock(return_value=None)
            mock_cursor.fetchone.return_value = [123]
            
            mock_connect.return_value = mock_conn
            
            # Test full workflow
            start_time = time.time()
            
            # Initialize database
            db = SummaryDatabase(mock_connection_params)
            
            # Simulate operations
            for i in range(3):
                db._update_metrics(0.05, cache_hit=(i % 2 == 0))
            
            metrics = db.get_performance_metrics()
            
            total_time = time.time() - start_time
            
            assert total_time < 0.5  # Should complete quickly
            assert metrics["queries_executed"] == 3
            assert metrics["cache_hits"] == 2
            assert metrics["cache_misses"] == 1

    def test_database_performance_monitoring(self):
        """Test database performance monitoring capabilities."""
        mock_connection_params = {
            "host": "test-host",
            "port": 5432,
            "database": "test_db", 
            "user": "test_user",
            "password": "test_pass"
        }
        
        with patch('psycopg2.connect'):
            db = SummaryDatabase(mock_connection_params)
            
            # Simulate various query times
            query_times = [0.05, 0.1, 0.15, 0.08, 0.12]
            
            start_time = time.time()
            
            for i, query_time in enumerate(query_times):
                db._update_metrics(query_time, cache_hit=(i % 3 == 0))
            
            monitoring_time = time.time() - start_time
            
            metrics = db.get_performance_metrics()
            
            assert monitoring_time < 0.1  # Monitoring should be very fast
            assert metrics["queries_executed"] == 5
            assert metrics["total_query_time"] == sum(query_times)
            assert abs(metrics["average_query_time"] - (sum(query_times) / 5)) < 0.001


if __name__ == "__main__":
    pytest.main([__file__])
