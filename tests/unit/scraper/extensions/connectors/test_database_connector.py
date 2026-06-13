"""
Test cases for database connector functionality.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.scraper.extensions.connectors.database_connector import DatabaseConnector
from src.scraper.extensions.connectors.base import ConnectionError


class TestDatabaseConnector:
    """Test cases for DatabaseConnector class."""

    def test_init(self):
        """Test database connector initialization."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        auth_config = {"username": "test_user", "password": "test_pass"}
        
        connector = DatabaseConnector(config, auth_config)
        
        assert connector.config == config
        assert connector.auth_config == auth_config
        assert connector._connection is None
        assert connector.db_type == "postgresql"

    def test_validate_config_postgresql_success(self):
        """Test successful config validation for PostgreSQL."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_mysql_success(self):
        """Test successful config validation for MySQL."""
        config = {
            "type": "mysql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_sqlite_success(self):
        """Test successful config validation for SQLite."""
        config = {
            "type": "sqlite",
            "database": "/path/to/test.db"
        }
        connector = DatabaseConnector(config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_missing_type(self):
        """Test config validation with missing type."""
        config = {
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        result = connector.validate_config()
        assert result is False

    def test_validate_config_unsupported_type(self):
        """Test config validation with unsupported database type."""
        config = {
            "type": "oracle",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        result = connector.validate_config()
        assert result is False

    def test_validate_config_postgresql_missing_required_fields(self):
        """Test PostgreSQL config validation with missing required fields."""
        config = {
            "type": "postgresql",
            "host": "localhost"
            # Missing database
        }
        connector = DatabaseConnector(config)
        
        result = connector.validate_config()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_postgresql_success(self):
        """Test successful PostgreSQL connection."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }
        connector = DatabaseConnector(config)
        
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        
        with patch('asyncpg.connect', return_value=mock_connection):
            result = await connector.connect()
            
            assert result is True
            assert connector.is_connected
            assert connector._connection == mock_connection

    @pytest.mark.asyncio
    async def test_connect_mysql_success(self):
        """Test successful MySQL connection."""
        config = {
            "type": "mysql",
            "host": "localhost",
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }
        connector = DatabaseConnector(config)
        
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        
        with patch('aiomysql.connect', return_value=mock_connection):
            result = await connector.connect()
            
            assert result is True
            assert connector.is_connected
            assert connector._connection == mock_connection

    @pytest.mark.asyncio
    async def test_connect_sqlite_success(self):
        """Test successful SQLite connection."""
        config = {
            "type": "sqlite",
            "database": "/tmp/test.db"
        }
        connector = DatabaseConnector(config)
        
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        
        with patch('aiosqlite.connect', return_value=mock_connection):
            result = await connector.connect()
            
            assert result is True
            assert connector.is_connected
            assert connector._connection == mock_connection

    @pytest.mark.asyncio
    async def test_connect_unsupported_database_type(self):
        """Test connection with unsupported database type."""
        config = {
            "type": "oracle",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        result = await connector.connect()
        
        assert result is False
        assert not connector.is_connected
        assert connector.last_error is not None

    @pytest.mark.asyncio
    async def test_connect_existing_connection(self):
        """Test connecting when connection already exists."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        # Set existing connection
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        connector._connection = mock_connection
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected

    @pytest.mark.asyncio
    async def test_disconnect_postgresql(self):
        """Test PostgreSQL disconnection."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        # Set up connection
        mock_connection = AsyncMock()
        connector._connection = mock_connection
        connector._connected = True
        
        await connector.disconnect()
        
        assert not connector.is_connected
        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_data_postgresql_success(self):
        """Test successful PostgreSQL data fetching."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        # Mock connection and results
        mock_row1 = MagicMock()
        mock_row1.__iter__ = lambda self: iter([('id', 1), ('name', 'Test 1')])
        mock_row2 = MagicMock()
        mock_row2.__iter__ = lambda self: iter([('id', 2), ('name', 'Test 2')])
        
        mock_connection = AsyncMock()
        mock_connection.fetch.return_value = [mock_row1, mock_row2]
        connector._connection = mock_connection
        
        data = await connector.fetch_data("SELECT * FROM test_table")
        
        assert len(data) == 2
        mock_connection.fetch.assert_called_once_with("SELECT * FROM test_table")

    @pytest.mark.asyncio
    async def test_fetch_data_postgresql_with_parameters(self):
        """Test PostgreSQL data fetching with parameters."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_connection = AsyncMock()
        mock_connection.fetch.return_value = []
        connector._connection = mock_connection
        
        parameters = ['active']
        await connector.fetch_data("SELECT * FROM test_table WHERE status = $1", parameters)
        
        mock_connection.fetch.assert_called_once_with("SELECT * FROM test_table WHERE status = $1", 'active')

    @pytest.mark.asyncio
    async def test_fetch_data_mysql_success(self):
        """Test successful MySQL data fetching."""
        config = {
            "type": "mysql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Test 1'},
            {'id': 2, 'name': 'Test 2'}
        ]
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=False)
        
        mock_connection = AsyncMock()
        mock_connection.cursor.return_value = mock_cursor
        connector._connection = mock_connection
        
        data = await connector.fetch_data("SELECT * FROM test_table")
        
        assert len(data) == 2
        assert data[0]['id'] == 1
        assert data[1]['name'] == 'Test 2'

    @pytest.mark.asyncio
    async def test_fetch_data_sqlite_success(self):
        """Test successful SQLite data fetching."""
        config = {
            "type": "sqlite",
            "database": "/tmp/test.db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_row1 = MagicMock()
        mock_row1.__iter__ = lambda self: iter([('id', 1), ('name', 'Test 1')])
        mock_row2 = MagicMock()
        mock_row2.__iter__ = lambda self: iter([('id', 2), ('name', 'Test 2')])
        
        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [mock_row1, mock_row2]
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=False)
        
        mock_connection = AsyncMock()
        mock_connection.execute.return_value = mock_cursor
        connector._connection = mock_connection
        
        data = await connector.fetch_data("SELECT * FROM test_table")
        
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_fetch_data_not_connected(self):
        """Test fetching data when not connected."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to database"):
            await connector.fetch_data("SELECT * FROM test_table")

    @pytest.mark.asyncio
    async def test_fetch_data_unsupported_type(self):
        """Test fetching data with unsupported database type."""
        config = {
            "type": "oracle",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        with pytest.raises(ConnectionError, match="Unsupported database type"):
            await connector.fetch_data("SELECT * FROM test_table")

    @pytest.mark.asyncio
    async def test_execute_query_postgresql_success(self):
        """Test successful PostgreSQL query execution."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_connection = AsyncMock()
        mock_connection.execute.return_value = "INSERT 0 5"  # PostgreSQL format
        connector._connection = mock_connection
        
        affected_rows = await connector.execute_query("INSERT INTO test_table VALUES (1, 'test')")
        
        assert affected_rows == 5
        mock_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_mysql_success(self):
        """Test successful MySQL query execution."""
        config = {
            "type": "mysql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 3
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=False)
        
        mock_connection = AsyncMock()
        mock_connection.cursor.return_value = mock_cursor
        mock_connection.commit = AsyncMock()
        connector._connection = mock_connection
        
        affected_rows = await connector.execute_query("UPDATE test_table SET name='updated'")
        
        assert affected_rows == 3
        mock_connection.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_sqlite_success(self):
        """Test successful SQLite query execution."""
        config = {
            "type": "sqlite",
            "database": "/tmp/test.db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_connection = AsyncMock()
        mock_connection.total_changes = 2
        mock_connection.execute = AsyncMock()
        mock_connection.commit = AsyncMock()
        connector._connection = mock_connection
        
        affected_rows = await connector.execute_query("DELETE FROM test_table WHERE id > 10")
        
        assert affected_rows == 2
        mock_connection.execute.assert_called_once()
        mock_connection.commit.assert_called_once()

    def test_validate_data_format_success(self):
        """Test successful data format validation."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        data = {"id": 1, "name": "Test", "created_at": "2024-01-01"}
        
        result = connector.validate_data_format(data)
        assert result is True

    def test_validate_data_format_non_dict(self):
        """Test data format validation with non-dictionary data."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        result = connector.validate_data_format("not a dict")
        assert result is False

    def test_validate_data_format_non_serializable(self):
        """Test data format validation with non-serializable data."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        # Create non-serializable object
        class NonSerializable:
            pass
        
        data = {"id": 1, "obj": NonSerializable()}
        
        result = connector.validate_data_format(data)
        assert result is False

    @pytest.mark.asyncio
    async def test_test_query_success(self):
        """Test successful test query."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_connection = AsyncMock()
        mock_connection.fetch.return_value = [{'result': 1}]
        connector._connection = mock_connection
        
        result = await connector.test_query("SELECT 1 as result")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_test_query_failure(self):
        """Test failed test query."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_connection = AsyncMock()
        mock_connection.fetch.side_effect = Exception("Query failed")
        connector._connection = mock_connection
        
        result = await connector.test_query("SELECT invalid_syntax")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_table_info_postgresql_success(self):
        """Test successful PostgreSQL table info retrieval."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_columns = [
            {'column_name': 'id', 'data_type': 'integer', 'is_nullable': 'NO', 'column_default': None},
            {'column_name': 'name', 'data_type': 'varchar', 'is_nullable': 'YES', 'column_default': None}
        ]
        
        mock_connection = AsyncMock()
        mock_connection.fetch.return_value = [MagicMock(**col) for col in mock_columns]
        connector._connection = mock_connection
        
        table_info = await connector.get_table_info("test_table")
        
        assert table_info['table_name'] == 'test_table'
        assert table_info['column_count'] == 2
        assert len(table_info['columns']) == 2
        mock_connection.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_table_info_sqlite_success(self):
        """Test successful SQLite table info retrieval."""
        config = {
            "type": "sqlite",
            "database": "/tmp/test.db"
        }
        connector = DatabaseConnector(config)
        connector._connected = True
        
        mock_pragma_result = [
            {'name': 'id', 'type': 'INTEGER', 'notnull': 1, 'dflt_value': None},
            {'name': 'name', 'type': 'TEXT', 'notnull': 0, 'dflt_value': None}
        ]
        
        # Mock the fetch_data method for PRAGMA
        original_fetch = connector.fetch_data
        async def mock_fetch_data(query):
            if 'PRAGMA' in query:
                return mock_pragma_result
            return await original_fetch(query)
        
        connector.fetch_data = mock_fetch_data
        
        table_info = await connector.get_table_info("test_table")
        
        assert table_info['table_name'] == 'test_table'
        assert table_info['column_count'] == 2
        assert table_info['columns'][0]['column_name'] == 'id'
        assert table_info['columns'][0]['is_nullable'] == 'NO'  # notnull=1 becomes NO
        assert table_info['columns'][1]['is_nullable'] == 'YES'  # notnull=0 becomes YES

    @pytest.mark.asyncio
    async def test_get_table_info_not_connected(self):
        """Test getting table info when not connected."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to database"):
            await connector.get_table_info("test_table")

    @pytest.mark.asyncio
    async def test_disconnect_with_no_connection(self):
        """Test disconnecting when no connection exists."""
        config = {
            "type": "postgresql",
            "host": "localhost",
            "database": "test_db"
        }
        connector = DatabaseConnector(config)
        
        # Should not raise error
        await connector.disconnect()
        
        assert not connector.is_connected
