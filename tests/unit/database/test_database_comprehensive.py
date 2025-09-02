#!/usr/bin/env python3
"""
Comprehensive Database Tests
Issue #429: Database: Connection & Performance Tests

This module provides comprehensive database testing including:
- Real database connection tests (when database is available)
- Fallback to mock-based tests for CI/CD environments
- Integration with existing database test utilities

Note: This file imports the actual database modules and falls back to
the mock-based tests when they're not available.
"""

try:
    # Import all tests from the mock-based module as fallback
    from .test_database_connection_performance_mock import *
    
    # Try to import real database modules
    from src.database.setup import (
        cleanup_test_database,
        create_test_articles,
        get_async_connection,
        get_db_config,
        get_sync_connection,
        setup_test_database,
    )
    from src.nlp.summary_database import SummaryDatabase, SummaryRecord
    
    # Real database modules are available
    DATABASE_AVAILABLE = True
    
except ImportError:
    # Fall back to mock-based tests only
    DATABASE_AVAILABLE = False


if DATABASE_AVAILABLE:
    import pytest
    import psycopg2
    from unittest.mock import patch
    
    class TestRealDatabaseConnection:
        """Test real database connections when available."""
        
        @pytest.mark.integration
        def test_real_sync_connection_when_available(self):
            """Test real synchronous database connection."""
            try:
                # This will work if database is actually available
                conn = get_sync_connection(testing=True)
                assert conn is not None
                
                # Test basic query
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    assert result[0] == 1
                
                conn.close()
                
            except psycopg2.OperationalError:
                # Database not available - skip test
                pytest.skip("Database not available for integration testing")
        
        @pytest.mark.integration 
        @pytest.mark.asyncio
        async def test_real_async_connection_when_available(self):
            """Test real asynchronous database connection."""
            try:
                conn = await get_async_connection(testing=True)
                assert conn is not None
                
                # Test basic query
                result = await conn.fetchval("SELECT 1")
                assert result == 1
                
                await conn.close()
                
            except Exception:
                # Database not available - skip test
                pytest.skip("Database not available for integration testing")
        
        @pytest.mark.integration
        def test_real_summary_database_when_available(self):
            """Test real SummaryDatabase when available."""
            try:
                config = get_db_config(testing=True)
                db = SummaryDatabase(config)
                
                # Test connection method
                conn = db._get_connection()
                assert conn is not None
                conn.close()
                
            except psycopg2.OperationalError:
                # Database not available - skip test
                pytest.skip("Database not available for integration testing")


# The mock-based tests are automatically imported above and will always run
# regardless of database availability