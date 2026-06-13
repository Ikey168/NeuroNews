"""
Compatibility shim for the historical ``snowflake_connector`` module name.

The implementation lives in :mod:`src.database.snowflake_analytics_connector`;
several routes and processors still import it under this name.
"""

try:
    from src.database.snowflake_analytics_connector import (
        SnowflakeAnalyticsConnector,
    )
except ImportError:  # imported as top-level ``database`` package
    from database.snowflake_analytics_connector import (
        SnowflakeAnalyticsConnector,
    )

# Older call sites used this alias
SnowflakeConnection = SnowflakeAnalyticsConnector

__all__ = ["SnowflakeAnalyticsConnector", "SnowflakeConnection"]
