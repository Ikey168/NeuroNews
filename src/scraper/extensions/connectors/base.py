"""
Base connector interface for data sources.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import asyncio
import logging
from datetime import datetime


class ConnectorError(Exception):
    """Base exception for connector errors."""
    pass


class AuthenticationError(ConnectorError):
    """Raised when authentication fails."""
    pass


class ConnectionError(ConnectorError):
    """Raised when connection to data source fails."""
    pass


class DataFormatError(ConnectorError):
    """Raised when data format validation fails."""
    pass


class BaseConnector(ABC):
    """
    Base class for all data source connectors.
    """

    def __init__(self, config: Dict[str, Any], auth_config: Optional[Dict[str, Any]] = None):
        """
        Initialize connector with configuration.
        
        Args:
            config: Connection configuration
            auth_config: Authentication configuration
        """
        self.config = config
        self.auth_config = auth_config or {}
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")
        self._connected = False
        self._last_error = None

    @property
    def is_connected(self) -> bool:
        """Check if connector is connected."""
        return self._connected

    @property
    def last_error(self) -> Optional[Exception]:
        """Get last error that occurred."""
        return self._last_error

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to data source.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to data source."""
        pass

    @abstractmethod
    async def fetch_data(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch data from source.
        
        Returns:
            List of data records
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """
        Validate connector configuration.
        
        Returns:
            True if configuration is valid
        """
        pass

    @abstractmethod
    def validate_data_format(self, data: Any) -> bool:
        """
        Validate data format from source.
        
        Args:
            data: Data to validate
            
        Returns:
            True if data format is valid
        """
        pass

    async def authenticate(self) -> bool:
        """
        Authenticate with data source.
        
        Returns:
            True if authentication successful
        """
        if not self.auth_config:
            return True
            
        try:
            # Base authentication logic - to be overridden
            return True
        except Exception as e:
            self._last_error = AuthenticationError(f"Authentication failed: {e}")
            return False

    async def test_connection(self) -> bool:
        """
        Test connection to data source.
        
        Returns:
            True if connection test successful
        """
        try:
            if await self.connect():
                await self.disconnect()
                return True
            return False
        except Exception as e:
            self._last_error = ConnectionError(f"Connection test failed: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Get connector status information.
        
        Returns:
            Status dictionary
        """
        return {
            "connector_type": self.__class__.__name__,
            "connected": self.is_connected,
            "last_error": str(self._last_error) if self._last_error else None,
            "config_valid": self.validate_config(),
            "last_check": datetime.utcnow().isoformat(),
        }

    async def __aenter__(self):
        """Async context manager entry."""
        if await self.connect():
            return self
        raise ConnectionError("Failed to establish connection")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
