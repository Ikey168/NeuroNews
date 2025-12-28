import sys
from unittest.mock import MagicMock, patch, AsyncMock
import os
import pytest

# Mock asyncpg and psycopg2 before importing modules that use them
sys.modules["asyncpg"] = MagicMock()
sys.modules["psycopg2"] = MagicMock()
sys.modules["psycopg2.extras"] = MagicMock()
sys.modules["psycopg2.extensions"] = MagicMock()

from src.config import get_db_config as get_main_db_config
from src.database.setup import (
    get_db_config as get_setup_db_config,
    get_sync_connection,
    get_async_connection,
    setup_test_database
)

class TestConfigDB:
    """Test src/config.py database configuration."""

    def test_get_db_config_default(self):
        """Test get_db_config with default values."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_main_db_config(testing=False)
            assert config["host"] == "localhost"
            assert config["port"] == 5432
            assert config["database"] == "neuronews"
            assert config["user"] == "neuronews"
            assert config["password"] == "password"

    def test_get_db_config_testing(self):
        """Test get_db_config with testing=True."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_main_db_config(testing=True)
            assert config["host"] == "localhost"
            assert config["port"] == 5432
            assert config["database"] == "neuronews_test"
            assert config["user"] == "test_user"
            assert config["password"] == "test_password"

    def test_get_db_config_env_vars(self):
        """Test get_db_config with environment variables."""
        env_vars = {
            "DB_HOST": "custom_host",
            "DB_PORT": "5433",
            "DB_NAME": "custom_db",
            "DB_USER": "custom_user",
            "DB_PASSWORD": "custom_password"
        }
        with patch.dict(os.environ, env_vars, clear=True):
            config = get_main_db_config(testing=False)
            assert config["host"] == "custom_host"
            assert config["port"] == 5433
            assert config["database"] == "custom_db"
            assert config["user"] == "custom_user"
            assert config["password"] == "custom_password"

class TestSetupDB:
    """Test src/database/setup.py database setup."""

    def test_get_db_config_default(self):
        """Test get_db_config with default values."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_setup_db_config(testing=False)
            assert config["host"] == "postgres"
            assert config["port"] == 5432
            assert config["database"] == "neuronews_dev"
            assert config["user"] == "neuronews"
            assert config["password"] == "dev_password"

    def test_get_db_config_testing(self):
        """Test get_db_config with testing=True."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_setup_db_config(testing=True)
            assert config["host"] == "test-postgres"
            assert config["port"] == 5432
            assert config["database"] == "neuronews_test"
            assert config["user"] == "test_user"
            assert config["password"] == "test_password"

    def test_get_db_config_testing_env(self):
        """Test get_db_config with TESTING env var."""
        with patch.dict(os.environ, {"TESTING": "true"}, clear=True):
            config = get_setup_db_config()
            assert config["database"] == "neuronews_test"

    @patch("src.database.setup.psycopg2.connect")
    def test_get_sync_connection(self, mock_connect):
        """Test get_sync_connection."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        conn = get_sync_connection(testing=True)
        
        assert conn == mock_conn
        mock_connect.assert_called_once()
        call_args = mock_connect.call_args[1]
        assert call_args["database"] == "neuronews_test"

    def test_get_async_connection(self):
        """Test get_async_connection."""
        import asyncio
        
        async def run_test():
            with patch("src.database.setup.asyncpg.connect", new_callable=AsyncMock) as mock_connect:
                mock_conn = AsyncMock()
                mock_connect.return_value = mock_conn
                
                conn = await get_async_connection(testing=True)
                
                assert conn == mock_conn
                mock_connect.assert_called_once()
                call_args = mock_connect.call_args[1]
                assert call_args["database"] == "neuronews_test"
        
        asyncio.run(run_test())

    def test_setup_test_database(self):
        """Test setup_test_database."""
        import asyncio
        
        async def run_test():
            with patch("src.database.setup.get_sync_connection") as mock_get_conn, \
                 patch("asyncio.sleep") as mock_sleep:
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                
                # Configure connection context manager
                mock_conn.__enter__.return_value = mock_conn
                mock_conn.__exit__.return_value = None
                
                # Configure cursor context manager
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_conn.cursor.return_value.__exit__.return_value = None
                
                mock_get_conn.return_value = mock_conn
                
                # Mock successful execution
                await setup_test_database()
                
                assert mock_get_conn.called
                assert mock_cursor.execute.called
        
        asyncio.run(run_test())
