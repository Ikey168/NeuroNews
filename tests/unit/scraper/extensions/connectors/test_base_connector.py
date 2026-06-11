"""
Test cases for base connector functionality.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.scraper.extensions.connectors.base import (
    BaseConnector, 
    ConnectorError,
    AuthenticationError,
    ConnectionError,
    DataFormatError
)


class ConcreteConnector(BaseConnector):
    """Concrete implementation of BaseConnector for testing."""
    
    def __init__(self, config, auth_config=None):
        super().__init__(config, auth_config)
        self._test_connected = False
    
    async def connect(self):
        self._test_connected = True
        self._connected = True
        return True
    
    async def disconnect(self):
        self._test_connected = False
        self._connected = False
    
    async def fetch_data(self, **kwargs):
        if not self.is_connected:
            raise ConnectionError("Not connected")
        return [{"test": "data", "source": "test"}]
    
    def validate_config(self):
        return "test_field" in self.config
    
    def validate_data_format(self, data):
        return isinstance(data, dict) and "test" in data


class TestBaseConnector:
    """Test cases for BaseConnector class."""

    def test_init(self):
        """Test connector initialization."""
        config = {"test_field": "test_value"}
        auth_config = {"username": "test_user"}
        
        connector = ConcreteConnector(config, auth_config)
        
        assert connector.config == config
        assert connector.auth_config == auth_config
        assert not connector.is_connected
        assert connector.last_error is None

    def test_init_without_auth_config(self):
        """Test connector initialization without auth config."""
        config = {"test_field": "test_value"}
        
        connector = ConcreteConnector(config)
        
        assert connector.config == config
        assert connector.auth_config == {}
        assert not connector.is_connected

    def test_is_connected_property(self):
        """Test is_connected property."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        assert not connector.is_connected
        
        connector._connected = True
        assert connector.is_connected

    def test_last_error_property(self):
        """Test last_error property."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        assert connector.last_error is None
        
        error = ConnectionError("Test error")
        connector._last_error = error
        assert connector.last_error == error

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful connection."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected
        assert connector._test_connected

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnection."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        await connector.connect()
        assert connector.is_connected
        
        await connector.disconnect()
        assert not connector.is_connected
        assert not connector._test_connected

    @pytest.mark.asyncio
    async def test_fetch_data_when_connected(self):
        """Test fetching data when connected."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        await connector.connect()
        data = await connector.fetch_data()
        
        assert len(data) == 1
        assert data[0]["test"] == "data"
        assert data[0]["source"] == "test"

    @pytest.mark.asyncio
    async def test_fetch_data_when_not_connected(self):
        """Test fetching data when not connected raises error."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected"):
            await connector.fetch_data()

    def test_validate_config_success(self):
        """Test successful config validation."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_failure(self):
        """Test failed config validation."""
        config = {"wrong_field": "test_value"}
        connector = ConcreteConnector(config)
        
        result = connector.validate_config()
        assert result is False

    def test_validate_data_format_success(self):
        """Test successful data format validation."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        data = {"test": "value"}
        result = connector.validate_data_format(data)
        assert result is True

    def test_validate_data_format_failure(self):
        """Test failed data format validation."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        data = {"wrong": "value"}
        result = connector.validate_data_format(data)
        assert result is False

    @pytest.mark.asyncio
    async def test_authenticate_without_auth_config(self):
        """Test authentication without auth config."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        result = await connector.authenticate()
        assert result is True

    @pytest.mark.asyncio
    async def test_authenticate_with_auth_config(self):
        """Test authentication with auth config."""
        config = {"test_field": "test_value"}
        auth_config = {"username": "test_user"}
        connector = ConcreteConnector(config, auth_config)
        
        result = await connector.authenticate()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """Test successful connection test."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        result = await connector.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """Test failed connection test."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        # Mock connect to raise an exception
        original_connect = connector.connect
        async def failing_connect():
            raise ConnectionError("Test connection failure")
        connector.connect = failing_connect
        
        result = await connector.test_connection()
        assert result is False
        assert isinstance(connector.last_error, ConnectionError)

    def test_get_status_when_connected(self):
        """Test get_status when connected."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        connector._connected = True
        
        status = connector.get_status()
        
        assert status["connector_type"] == "ConcreteConnector"
        assert status["connected"] is True
        assert status["last_error"] is None
        assert status["config_valid"] is True
        assert "last_check" in status

    def test_get_status_with_error(self):
        """Test get_status with error."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        connector._connected = False
        connector._last_error = ConnectionError("Test error")
        
        status = connector.get_status()
        
        assert status["connector_type"] == "ConcreteConnector"
        assert status["connected"] is False
        assert status["last_error"] == "Test error"

    @pytest.mark.asyncio
    async def test_async_context_manager_success(self):
        """Test async context manager with successful connection."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        async with connector as conn:
            assert conn is connector
            assert connector.is_connected

    @pytest.mark.asyncio
    async def test_async_context_manager_failure(self):
        """Test async context manager with failed connection."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        # Mock connect to return False
        async def failing_connect():
            return False
        connector.connect = failing_connect
        
        with pytest.raises(ConnectionError, match="Failed to establish connection"):
            async with connector as conn:
                pass

    @pytest.mark.asyncio
    async def test_async_context_manager_disconnect_on_exit(self):
        """Test async context manager disconnects on exit."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        async with connector:
            assert connector.is_connected
            
        assert not connector.is_connected

    @pytest.mark.asyncio
    async def test_async_context_manager_disconnect_on_exception(self):
        """Test async context manager disconnects on exception."""
        config = {"test_field": "test_value"}
        connector = ConcreteConnector(config)
        
        try:
            async with connector:
                assert connector.is_connected
                raise ValueError("Test exception")
        except ValueError:
            pass
            
        assert not connector.is_connected


class TestConnectorExceptions:
    """Test cases for connector exceptions."""

    def test_connector_error(self):
        """Test ConnectorError exception."""
        error = ConnectorError("Test error")
        assert str(error) == "Test error"

    def test_authentication_error(self):
        """Test AuthenticationError exception."""
        error = AuthenticationError("Auth failed")
        assert str(error) == "Auth failed"
        assert isinstance(error, ConnectorError)

    def test_connection_error(self):
        """Test ConnectionError exception."""
        error = ConnectionError("Connection failed")
        assert str(error) == "Connection failed"
        assert isinstance(error, ConnectorError)

    def test_data_format_error(self):
        """Test DataFormatError exception."""
        error = DataFormatError("Invalid format")
        assert str(error) == "Invalid format"
        assert isinstance(error, ConnectorError)
