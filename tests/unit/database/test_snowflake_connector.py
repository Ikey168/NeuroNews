import pytest
from src.database.snowflake_analytics_connector import SnowflakeConfig, SnowflakeAnalyticsConnector
from unittest.mock import MagicMock, patch

class TestSnowflakeConfig:
    """Test SnowflakeConfig dataclass."""

    def test_initialization(self):
        """Test initialization."""
        config = SnowflakeConfig(
            account="test-account",
            user="test-user",
            password="test-password",
            warehouse="test-warehouse",
            database="test-db",
            schema="test-schema",
            role="test-role"
        )
        
        assert config.account == "test-account"
        assert config.user == "test-user"
        assert config.password == "test-password"
        assert config.warehouse == "test-warehouse"
        assert config.database == "test-db"
        assert config.schema == "test-schema"
        assert config.role == "test-role"

class TestSnowflakeAnalyticsConnector:
    """Test SnowflakeAnalyticsConnector."""

    def test_initialization(self):
        """Test initialization."""
        config = SnowflakeConfig(
            account="test-account",
            user="test-user",
            password="test-password",
            warehouse="test-warehouse",
            database="test-db",
            schema="test-schema"
        )
        connector = SnowflakeAnalyticsConnector(config)
        assert connector.config == config
        assert connector._is_connected is False

    def test_connect_disconnect(self):
        """Test connect and disconnect."""
        connector = SnowflakeAnalyticsConnector()
        
        assert connector.connect() is True
        assert connector.is_connected() is True
        
        connector.disconnect()
        assert connector.is_connected() is False

    def test_execute_query_not_connected(self):
        """Test execute_query when not connected."""
        connector = SnowflakeAnalyticsConnector()
        with pytest.raises(ConnectionError):
            connector.execute_query("SELECT * FROM table")

    def test_execute_query_select(self):
        """Test execute_query with SELECT."""
        connector = SnowflakeAnalyticsConnector()
        connector.connect()
        
        result = connector.execute_query("SELECT * FROM table")
        assert len(result) == 2
        assert result[0]["name"] == "Mock Data"

    def test_execute_query_other(self):
        """Test execute_query with other queries."""
        connector = SnowflakeAnalyticsConnector()
        connector.connect()
        
        result = connector.execute_query("INSERT INTO table VALUES (1)")
        assert result[0]["affected_rows"] == 1

    def test_get_table_info(self):
        """Test get_table_info."""
        config = SnowflakeConfig(
            account="test-account",
            user="test-user",
            password="test-password",
            warehouse="test-warehouse",
            database="test-db",
            schema="test-schema"
        )
        connector = SnowflakeAnalyticsConnector(config)
        connector.connect()
        
        info = connector.get_table_info("test_table")
        assert info["table_name"] == "test_table"
        assert info["database"] == "test-db"
        assert info["schema"] == "test-schema"
        assert len(info["columns"]) == 3

    def test_bulk_insert(self):
        """Test bulk_insert."""
        connector = SnowflakeAnalyticsConnector()
        connector.connect()
        
        data = [{"id": 1}, {"id": 2}]
        # The method returns None in the current implementation (implicit)
        # But let's check it doesn't raise error
        connector.bulk_insert("test_table", data)
