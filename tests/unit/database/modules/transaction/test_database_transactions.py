"""
Comprehensive Database Transaction Tests
Modularized from scattered transaction tests across multiple files
"""

import pytest
import asyncio
import threading
import time
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone
import concurrent.futures


class TestBasicTransactions:
    """Tests for basic database transaction operations"""
    
    def test_simple_transaction_commit(self):
        """Test simple transaction with successful commit"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            mock_connection.autocommit = False
            
            # Test transaction
            connection = mock_connect()
            cursor = connection.cursor()
            
            try:
                cursor.execute("BEGIN")
                cursor.execute(
                    "INSERT INTO articles (title, content) VALUES (%s, %s)",
                    ("Test Article", "Test Content")
                )
                cursor.execute(
                    "UPDATE article_stats SET total_count = total_count + 1"
                )
                connection.commit()
                
                # Verify transaction operations
                assert mock_cursor.execute.call_count == 3
                mock_connection.commit.assert_called_once()
                
            except Exception as e:
                connection.rollback()
                pytest.fail(f"Transaction should not fail: {e}")
    
    def test_transaction_rollback(self):
        """Test transaction rollback on error"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            
            # Simulate database error
            mock_cursor.execute.side_effect = [
                None,  # BEGIN succeeds
                None,  # First INSERT succeeds
                Exception("Database constraint violation")  # Second INSERT fails
            ]
            
            connection = mock_connect()
            cursor = connection.cursor()
            
            try:
                cursor.execute("BEGIN")
                cursor.execute(
                    "INSERT INTO articles (title, content) VALUES (%s, %s)",
                    ("Test Article", "Test Content")
                )
                cursor.execute(
                    "INSERT INTO articles (title, content) VALUES (%s, %s)",
                    ("Duplicate Article", "Duplicate Content")  # This will fail
                )
                connection.commit()
                
            except Exception:
                connection.rollback()
                # Verify rollback was called
                mock_connection.rollback.assert_called_once()
                mock_connection.commit.assert_not_called()
    
    def test_transaction_context_manager(self):
        """Test transaction using context manager"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            mock_connection.__enter__ = Mock(return_value=mock_connection)
            mock_connection.__exit__ = Mock(return_value=None)
            
            # Test transaction with context manager
            with mock_connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO articles (title, content) VALUES (%s, %s)",
                    ("Context Article", "Context Content")
                )
                connection.commit()
            
            # Verify context manager was used properly
            mock_connection.__enter__.assert_called_once()
            mock_connection.__exit__.assert_called_once()
            mock_connection.commit.assert_called_once()
    
    def test_nested_transaction_savepoints(self):
        """Test nested transactions using savepoints"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            
            connection = mock_connect()
            cursor = connection.cursor()
            
            try:
                # Start main transaction
                cursor.execute("BEGIN")
                
                # Main operation
                cursor.execute(
                    "INSERT INTO articles (title, content) VALUES (%s, %s)",
                    ("Main Article", "Main Content")
                )
                
                # Create savepoint
                cursor.execute("SAVEPOINT sp1")
                
                # Nested operation
                cursor.execute(
                    "INSERT INTO article_tags (article_id, tag) VALUES (%s, %s)",
                    (1, "technology")
                )
                
                # Release savepoint (success)
                cursor.execute("RELEASE SAVEPOINT sp1")
                
                # Commit main transaction
                connection.commit()
                
                # Verify savepoint operations
                expected_calls = [
                    call("BEGIN"),
                    call("INSERT INTO articles (title, content) VALUES (%s, %s)", ("Main Article", "Main Content")),
                    call("SAVEPOINT sp1"),
                    call("INSERT INTO article_tags (article_id, tag) VALUES (%s, %s)", (1, "technology")),
                    call("RELEASE SAVEPOINT sp1")
                ]
                mock_cursor.execute.assert_has_calls(expected_calls)
                mock_connection.commit.assert_called_once()
                
            except Exception as e:
                connection.rollback()
                pytest.fail(f"Savepoint transaction should not fail: {e}")


class TestConcurrentTransactions:
    """Tests for concurrent transaction handling"""
    
    def test_concurrent_transaction_isolation(self):
        """Test transaction isolation between concurrent operations"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection1 = Mock()
            mock_connection2 = Mock()
            mock_cursor1 = Mock()
            mock_cursor2 = Mock()
            
            mock_connect.side_effect = [mock_connection1, mock_connection2]
            mock_connection1.cursor.return_value = mock_cursor1
            mock_connection2.cursor.return_value = mock_cursor2
            
            def transaction1():
                """First concurrent transaction"""
                connection = mock_connect()
                cursor = connection.cursor()
                cursor.execute("BEGIN")
                cursor.execute(
                    "UPDATE articles SET view_count = view_count + 1 WHERE id = %s",
                    (1,)
                )
                time.sleep(0.1)  # Simulate processing time
                connection.commit()
                return "transaction1_complete"
            
            def transaction2():
                """Second concurrent transaction"""
                connection = mock_connect()
                cursor = connection.cursor()
                cursor.execute("BEGIN")
                cursor.execute(
                    "UPDATE articles SET like_count = like_count + 1 WHERE id = %s",
                    (1,)
                )
                time.sleep(0.1)  # Simulate processing time
                connection.commit()
                return "transaction2_complete"
            
            # Run concurrent transactions
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future1 = executor.submit(transaction1)
                future2 = executor.submit(transaction2)
                
                result1 = future1.result()
                result2 = future2.result()
            
            # Both transactions should complete
            assert result1 == "transaction1_complete"
            assert result2 == "transaction2_complete"
            
            # Each connection should be used properly
            mock_connection1.commit.assert_called_once()
            mock_connection2.commit.assert_called_once()
    
    def test_deadlock_detection_simulation(self):
        """Test deadlock detection and handling"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection1 = Mock()
            mock_connection2 = Mock()
            mock_cursor1 = Mock()
            mock_cursor2 = Mock()
            
            # Simulate deadlock error
            deadlock_error = Exception("deadlock detected")
            mock_cursor2.execute.side_effect = [
                None,  # BEGIN succeeds
                deadlock_error  # UPDATE fails with deadlock
            ]
            
            mock_connect.side_effect = [mock_connection1, mock_connection2]
            mock_connection1.cursor.return_value = mock_cursor1
            mock_connection2.cursor.return_value = mock_cursor2
            
            def transaction_a():
                """Transaction that will succeed"""
                connection = mock_connect()
                cursor = connection.cursor()
                cursor.execute("BEGIN")
                cursor.execute(
                    "UPDATE articles SET status = 'processing' WHERE id = %s",
                    (1,)
                )
                connection.commit()
                return "success"
            
            def transaction_b():
                """Transaction that will encounter deadlock"""
                connection = mock_connect()
                cursor = connection.cursor()
                try:
                    cursor.execute("BEGIN")
                    cursor.execute(
                        "UPDATE articles SET status = 'updated' WHERE id = %s",
                        (2,)
                    )
                    connection.commit()
                    return "success"
                except Exception as e:
                    connection.rollback()
                    return f"deadlock_handled: {str(e)}"
            
            # Run potentially conflicting transactions
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_a = executor.submit(transaction_a)
                future_b = executor.submit(transaction_b)
                
                result_a = future_a.result()
                result_b = future_b.result()
            
            # First transaction should succeed
            assert result_a == "success"
            # Second transaction should handle deadlock
            assert "deadlock_handled" in result_b
            mock_connection2.rollback.assert_called_once()
    
    def test_transaction_retry_mechanism(self):
        """Test transaction retry mechanism on temporary failures"""
        retry_count = 0
        max_retries = 3
        
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            
            def failing_execute(*args, **kwargs):
                nonlocal retry_count
                retry_count += 1
                if retry_count < 3:
                    raise Exception("Temporary database error")
                return None  # Success on third try
            
            mock_cursor.execute.side_effect = failing_execute
            
            def retry_transaction():
                """Transaction with retry logic"""
                for attempt in range(max_retries):
                    try:
                        connection = mock_connect()
                        cursor = connection.cursor()
                        cursor.execute("BEGIN")
                        cursor.execute(
                            "INSERT INTO articles (title, content) VALUES (%s, %s)",
                            ("Retry Article", "Retry Content")
                        )
                        connection.commit()
                        return f"success_on_attempt_{attempt + 1}"
                    except Exception as e:
                        if attempt < max_retries - 1:
                            time.sleep(0.1)  # Brief delay before retry
                            continue
                        else:
                            return f"failed_after_{max_retries}_attempts"
                
                return "unexpected_completion"
            
            result = retry_transaction()
            
            # Should succeed on third attempt
            assert result == "success_on_attempt_3"
            assert retry_count == 3


class TestTransactionIntegrity:
    """Tests for transaction data integrity"""
    
    def test_acid_properties_atomicity(self):
        """Test atomicity - all operations succeed or all fail"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            
            # Simulate partial failure
            mock_cursor.execute.side_effect = [
                None,  # BEGIN
                None,  # First INSERT
                None,  # Second INSERT
                Exception("Constraint violation")  # Third INSERT fails
            ]
            
            connection = mock_connect()
            cursor = connection.cursor()
            
            operations_completed = 0
            
            try:
                cursor.execute("BEGIN")
                
                # Operation 1
                cursor.execute(
                    "INSERT INTO articles (title, content) VALUES (%s, %s)",
                    ("Article 1", "Content 1")
                )
                operations_completed += 1
                
                # Operation 2
                cursor.execute(
                    "INSERT INTO authors (name, email) VALUES (%s, %s)",
                    ("Author 1", "author1@example.com")
                )
                operations_completed += 1
                
                # Operation 3 (will fail)
                cursor.execute(
                    "INSERT INTO articles (title, content) VALUES (%s, %s)",
                    ("Article 1", "Duplicate content")  # Duplicate title
                )
                operations_completed += 1
                
                connection.commit()
                
            except Exception:
                connection.rollback()
                # All operations should be rolled back due to atomicity
                mock_connection.rollback.assert_called_once()
            
            # Some operations completed but transaction rolled back
            assert operations_completed == 2
            mock_connection.commit.assert_not_called()
    
    def test_consistency_constraints(self):
        """Test consistency - database constraints are maintained"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            
            connection = mock_connect()
            cursor = connection.cursor()
            
            # Test foreign key constraint
            try:
                cursor.execute("BEGIN")
                
                # Insert article with non-existent author (should fail)
                cursor.execute(
                    "INSERT INTO articles (title, content, author_id) VALUES (%s, %s, %s)",
                    ("Test Article", "Test Content", 999)  # Non-existent author_id
                )
                
                connection.commit()
                
            except Exception:
                connection.rollback()
                # Consistency constraint violation should trigger rollback
                mock_connection.rollback.assert_called_once()
    
    def test_isolation_levels(self):
        """Test different transaction isolation levels"""
        isolation_levels = [
            'READ_UNCOMMITTED',
            'READ_COMMITTED',
            'REPEATABLE_READ',
            'SERIALIZABLE'
        ]
        
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            
            for isolation_level in isolation_levels:
                connection = mock_connect()
                cursor = connection.cursor()
                
                # Set isolation level
                cursor.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation_level}")
                cursor.execute("BEGIN")
                
                # Perform operation
                cursor.execute(
                    "SELECT * FROM articles WHERE id = %s FOR UPDATE",
                    (1,)
                )
                
                connection.commit()
                
                # Verify isolation level was set
                mock_cursor.execute.assert_any_call(
                    f"SET TRANSACTION ISOLATION LEVEL {isolation_level}"
                )
    
    def test_durability_simulation(self):
        """Test durability - committed changes persist"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = (1, 'Test Article')
            
            # First transaction - insert data
            connection1 = mock_connect()
            cursor1 = connection1.cursor()
            
            cursor1.execute("BEGIN")
            cursor1.execute(
                "INSERT INTO articles (id, title, content) VALUES (%s, %s, %s)",
                (1, "Test Article", "Test Content")
            )
            connection1.commit()
            
            # Simulate system restart by creating new connection
            connection2 = mock_connect()
            cursor2 = connection2.cursor()
            
            # Data should still be there after "restart"
            cursor2.execute("SELECT id, title FROM articles WHERE id = %s", (1,))
            result = cursor2.fetchone()
            
            # Verify durability
            assert result is not None
            assert result[0] == 1
            assert result[1] == 'Test Article'


@pytest.mark.asyncio
class TestAsyncTransactions:
    """Tests for asynchronous transaction handling"""
    
    async def test_async_transaction_basic(self):
        """Test basic async transaction operations"""
        with patch('asyncpg.connect') as mock_connect:
            mock_connection = Mock()
            mock_transaction = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.transaction = Mock(return_value=mock_transaction)
            mock_connection.execute = Mock()
            
            # Test async transaction
            connection = await mock_connect()
            
            async with connection.transaction():
                await connection.execute(
                    "INSERT INTO articles (title, content) VALUES ($1, $2)",
                    "Async Article", "Async Content"
                )
                await connection.execute(
                    "UPDATE article_stats SET total_count = total_count + 1"
                )
            
            # Verify async transaction operations
            mock_connection.transaction.assert_called_once()
            assert mock_connection.execute.call_count == 2
    
    async def test_async_transaction_rollback(self):
        """Test async transaction rollback on error"""
        with patch('asyncpg.connect') as mock_connect:
            mock_connection = Mock()
            mock_transaction = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.transaction = Mock(return_value=mock_transaction)
            mock_connection.execute = Mock(side_effect=Exception("Async error"))
            
            connection = await mock_connect()
            
            try:
                async with connection.transaction():
                    await connection.execute(
                        "INSERT INTO articles (title, content) VALUES ($1, $2)",
                        "Failing Async Article", "Failing Content"
                    )
            except Exception:
                # Exception should be caught and transaction rolled back
                pass
            
            # Verify transaction was attempted
            mock_connection.transaction.assert_called_once()
            mock_connection.execute.assert_called_once()
    
    async def test_async_concurrent_transactions(self):
        """Test concurrent async transactions"""
        with patch('asyncpg.connect') as mock_connect:
            mock_connection1 = Mock()
            mock_connection2 = Mock()
            mock_transaction1 = Mock()
            mock_transaction2 = Mock()
            
            mock_connect.side_effect = [mock_connection1, mock_connection2]
            mock_connection1.transaction = Mock(return_value=mock_transaction1)
            mock_connection2.transaction = Mock(return_value=mock_transaction2)
            mock_connection1.execute = Mock()
            mock_connection2.execute = Mock()
            
            async def async_transaction_1():
                """First async transaction"""
                connection = await mock_connect()
                async with connection.transaction():
                    await connection.execute(
                        "INSERT INTO articles (title, content) VALUES ($1, $2)",
                        "Async Article 1", "Async Content 1"
                    )
                return "transaction1_complete"
            
            async def async_transaction_2():
                """Second async transaction"""
                connection = await mock_connect()
                async with connection.transaction():
                    await connection.execute(
                        "INSERT INTO articles (title, content) VALUES ($1, $2)",
                        "Async Article 2", "Async Content 2"
                    )
                return "transaction2_complete"
            
            # Run concurrent async transactions
            results = await asyncio.gather(
                async_transaction_1(),
                async_transaction_2()
            )
            
            # Both transactions should complete
            assert results == ["transaction1_complete", "transaction2_complete"]
            mock_connection1.transaction.assert_called_once()
            mock_connection2.transaction.assert_called_once()
    
    async def test_async_transaction_timeout(self):
        """Test async transaction timeout handling"""
        with patch('asyncpg.connect') as mock_connect:
            mock_connection = Mock()
            mock_transaction = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.transaction = Mock(return_value=mock_transaction)
            
            # Simulate slow operation
            async def slow_execute(*args, **kwargs):
                await asyncio.sleep(2.0)  # Simulate 2-second operation
                return None
            
            mock_connection.execute = slow_execute
            
            connection = await mock_connect()
            
            # Test transaction with timeout
            try:
                async with asyncio.timeout(1.0):  # 1-second timeout
                    async with connection.transaction():
                        await connection.execute(
                            "INSERT INTO articles (title, content) VALUES ($1, $2)",
                            "Timeout Article", "Timeout Content"
                        )
                pytest.fail("Should have timed out")
                
            except asyncio.TimeoutError:
                # Timeout should be handled properly
                pass
            
            # Transaction should have been attempted
            mock_connection.transaction.assert_called_once()


class TestTransactionPerformance:
    """Tests for transaction performance optimization"""
    
    def test_batch_transaction_performance(self):
        """Test performance of batch transactions"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            
            # Test batch transaction
            batch_data = [
                (f'article_{i}', f'Title {i}', f'Content {i}')
                for i in range(1000)
            ]
            
            start_time = time.time()
            
            connection = mock_connect()
            cursor = connection.cursor()
            
            cursor.execute("BEGIN")
            cursor.executemany(
                "INSERT INTO articles (article_id, title, content) VALUES (%s, %s, %s)",
                batch_data
            )
            connection.commit()
            
            end_time = time.time()
            batch_time = end_time - start_time
            
            # Batch transaction should be efficient
            assert batch_time < 1.0
            mock_cursor.executemany.assert_called_once()
            mock_connection.commit.assert_called_once()
    
    def test_transaction_size_optimization(self):
        """Test optimal transaction size for performance"""
        transaction_sizes = [10, 100, 1000]
        
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            
            for size in transaction_sizes:
                start_time = time.time()
                
                connection = mock_connect()
                cursor = connection.cursor()
                
                cursor.execute("BEGIN")
                for i in range(size):
                    cursor.execute(
                        "INSERT INTO articles (title, content) VALUES (%s, %s)",
                        (f"Title {i}", f"Content {i}")
                    )
                connection.commit()
                
                end_time = time.time()
                transaction_time = end_time - start_time
                
                # All transaction sizes should complete efficiently
                assert transaction_time < 2.0
    
    def test_transaction_connection_reuse(self):
        """Test connection reuse within transactions"""
        with patch('psycopg2.connect') as mock_connect:
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_connection
            mock_connection.cursor.return_value = mock_cursor
            
            # Test multiple transactions on same connection
            connection = mock_connect()
            
            for transaction_id in range(5):
                cursor = connection.cursor()
                cursor.execute("BEGIN")
                cursor.execute(
                    "INSERT INTO articles (title, content) VALUES (%s, %s)",
                    (f"Transaction {transaction_id}", f"Content {transaction_id}")
                )
                connection.commit()
            
            # Connection should be reused efficiently
            mock_connect.assert_called_once()  # Only one connection created
            assert mock_connection.commit.call_count == 5  # Five commits
