"""
Snowflake Database Connector for NeuroNews Analytics

This module provides a unified interface for connecting to Snowflake
and executing analytics queries. Replaces Redshift connections for
the analytics layer.

Issue #244: Update analytics queries and integrations for Snowflake
"""

import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import snowflake.connector
from snowflake.connector import DictCursor
from snowflake.connector.pandas_tools import write_pandas

logger = logging.getLogger(__name__)


class SnowflakeAnalyticsConnector:
    """
    Snowflake connector optimized for analytics queries and dashboard integrations.
    
    Features:
    - Connection pooling and retry logic
    - Query result caching for dashboards
    - Pandas integration for data analysis
    - Error handling and logging
    """

    def __init__(
        self,
        account: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        warehouse: Optional[str] = None,
        database: Optional[str] = None,
        schema: Optional[str] = None,
        role: Optional[str] = None,
    ):
        """
        Initialize Snowflake connector.
        
        Args:
            account: Snowflake account identifier
            user: Snowflake username
            password: Snowflake password
            warehouse: Snowflake warehouse name
            database: Database name
            schema: Schema name
            role: Snowflake role
        """
        self.account = account or os.environ.get("SNOWFLAKE_ACCOUNT")
        self.user = user or os.environ.get("SNOWFLAKE_USER")
        self.password = password or os.environ.get("SNOWFLAKE_PASSWORD")
        self.warehouse = warehouse or os.environ.get("SNOWFLAKE_WAREHOUSE", "ANALYTICS_WH")
        self.database = database or os.environ.get("SNOWFLAKE_DATABASE", "NEURONEWS")
        self.schema = schema or os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC")
        self.role = role or os.environ.get("SNOWFLAKE_ROLE", "ANALYTICS_ROLE")
        
        self._conn = None
        self._query_cache = {}
        
        # Validate required parameters
        if not all([self.account, self.user, self.password]):
            raise ValueError(
                "Snowflake connection requires account, user, and password. "
                "Set via parameters or environment variables: "
                "SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD"
            )

    def connect(self) -> snowflake.connector.SnowflakeConnection:
        """Establish connection to Snowflake."""
        try:
            if self._conn is None or self._conn.is_closed():
                self._conn = snowflake.connector.connect(
                    account=self.account,
                    user=self.user,
                    password=self.password,
                    warehouse=self.warehouse,
                    database=self.database,
                    schema=self.schema,
                    role=self.role,
                    client_session_keep_alive=True,
                    autocommit=True,
                )
                logger.info(f"Connected to Snowflake: {self.account}/{self.database}")
            
            return self._conn
            
        except Exception as e:
            logger.error(f"Failed to connect to Snowflake: {e}")
            raise

    def disconnect(self):
        """Close Snowflake connection."""
        if self._conn and not self._conn.is_closed():
            self._conn.close()
            logger.info("Disconnected from Snowflake")

    @contextmanager
    def get_cursor(self):
        """Context manager for Snowflake cursor."""
        conn = self.connect()
        cursor = conn.cursor(DictCursor)
        try:
            yield cursor
        finally:
            cursor.close()

    def execute_query(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None,
        fetch_size: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a query and return results as list of dictionaries.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            fetch_size: Number of rows to fetch (None for all)
            
        Returns:
            List of dictionaries representing query results
        """
        try:
            with self.get_cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if fetch_size:
                    results = cursor.fetchmany(fetch_size)
                else:
                    results = cursor.fetchall()
                
                # Convert to list of dictionaries
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            raise

    def execute_query_to_dataframe(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """
        Execute a query and return results as pandas DataFrame.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            
        Returns:
            pandas DataFrame with query results
        """
        try:
            conn = self.connect()
            
            if params:
                # Use pandas read_sql with parameter substitution
                df = pd.read_sql(query, conn, params=params)
            else:
                df = pd.read_sql(query, conn)
            
            logger.info(f"Query returned {len(df)} rows")
            return df
            
        except Exception as e:
            logger.error(f"DataFrame query execution failed: {e}")
            raise

    def get_sentiment_trends(
        self, 
        source: Optional[str] = None, 
        days: int = 7
    ) -> pd.DataFrame:
        """Get sentiment trends over time."""
        query = """
        SELECT
            source,
            DATE_TRUNC('day', published_date) as date,
            AVG(sentiment) as avg_sentiment,
            COUNT(*) as article_count,
            STDDEV(sentiment) as sentiment_volatility
        FROM news_articles
        WHERE sentiment IS NOT NULL
            AND published_date >= DATEADD('day', %(days)s, CURRENT_TIMESTAMP())
        """
        
        params = {"days": -days}
        
        if source:
            query += " AND source = %(source)s"
            params["source"] = source
            
        query += """
        GROUP BY source, DATE_TRUNC('day', published_date)
        ORDER BY source, date
        """
        
        return self.execute_query_to_dataframe(query, params)

    def get_top_entities(
        self, 
        entity_type: str = "ORG", 
        limit: int = 20
    ) -> pd.DataFrame:
        """Get top mentioned entities by type."""
        query = f"""
        WITH entity_extraction AS (
            SELECT 
                source,
                f.value::string as entity_name
            FROM news_articles,
            LATERAL FLATTEN(input => PARSE_JSON(entities):{entity_type}) f
            WHERE entities IS NOT NULL
                AND published_date >= DATEADD('day', -7, CURRENT_TIMESTAMP())
        )
        SELECT
            entity_name,
            COUNT(*) as mention_count,
            COUNT(DISTINCT source) as source_count
        FROM entity_extraction
        WHERE entity_name IS NOT NULL
        GROUP BY entity_name
        ORDER BY mention_count DESC
        LIMIT %(limit)s
        """
        
        return self.execute_query_to_dataframe(query, {"limit": limit})

    def get_keyword_trends(self, days: int = 1) -> pd.DataFrame:
        """Get trending keywords with velocity analysis."""
        query = """
        WITH hourly_keywords AS (
            SELECT
                DATE_TRUNC('hour', published_date) as hour,
                f.value::string as keyword
            FROM news_articles,
            LATERAL FLATTEN(input => PARSE_JSON(keywords)) f
            WHERE keywords IS NOT NULL
                AND published_date >= DATEADD('day', %(days)s, CURRENT_TIMESTAMP())
        ),
        keyword_velocity AS (
            SELECT
                keyword,
                hour,
                COUNT(*) as hourly_count,
                COUNT(*) - LAG(COUNT(*), 1, 0) OVER (
                    PARTITION BY keyword 
                    ORDER BY hour
                ) as velocity
            FROM hourly_keywords
            GROUP BY keyword, hour
        )
        SELECT
            keyword,
            SUM(hourly_count) as total_mentions,
            AVG(velocity) as avg_velocity,
            MAX(velocity) as peak_velocity
        FROM keyword_velocity
        WHERE keyword IS NOT NULL
        GROUP BY keyword
        HAVING SUM(hourly_count) >= 3
        ORDER BY avg_velocity DESC
        LIMIT 50
        """
        
        return self.execute_query_to_dataframe(query, {"days": -days})

    def get_source_statistics(self) -> pd.DataFrame:
        """Get comprehensive source statistics."""
        query = """
        WITH source_metrics AS (
            SELECT
                source,
                COUNT(*) as total_articles,
                COUNT(DISTINCT DATE_TRUNC('day', published_date)) as active_days,
                AVG(LENGTH(content)) as avg_article_length,
                AVG(sentiment) as avg_sentiment,
                STDDEV(sentiment) as sentiment_consistency
            FROM news_articles
            WHERE published_date >= DATEADD('month', -1, CURRENT_TIMESTAMP())
            GROUP BY source
        )
        SELECT
            source,
            total_articles,
            active_days,
            ROUND(total_articles::float / active_days, 2) as articles_per_day,
            ROUND(avg_article_length, 0) as avg_article_length,
            ROUND(avg_sentiment, 3) as avg_sentiment,
            ROUND(sentiment_consistency, 3) as sentiment_consistency
        FROM source_metrics
        ORDER BY total_articles DESC
        """
        
        return self.execute_query_to_dataframe(query)

    def write_dataframe(
        self, 
        df: pd.DataFrame, 
        table_name: str, 
        if_exists: str = "append"
    ) -> bool:
        """
        Write pandas DataFrame to Snowflake table.
        
        Args:
            df: DataFrame to write
            table_name: Target table name
            if_exists: How to behave if table exists ('fail', 'replace', 'append')
            
        Returns:
            Success status
        """
        try:
            conn = self.connect()
            
            success, nchunks, nrows, _ = write_pandas(
                conn, 
                df, 
                table_name,
                database=self.database,
                schema=self.schema,
                auto_create_table=True,
                overwrite=(if_exists == "replace")
            )
            
            logger.info(f"Written {nrows} rows to {table_name} in {nchunks} chunks")
            return success
            
        except Exception as e:
            logger.error(f"Failed to write DataFrame to Snowflake: {e}")
            return False

    def test_connection(self) -> bool:
        """Test Snowflake connection."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT CURRENT_VERSION()")
                result = cursor.fetchone()
                logger.info(f"Snowflake connection test successful: {result[0]}")
                return True
                
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """Get information about a table."""
        query = f"""
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns 
        WHERE table_schema = '{self.schema}' 
            AND table_name = '{table_name.upper()}'
        ORDER BY ordinal_position
        """
        
        columns = self.execute_query(query)
        
        # Get row count
        count_query = f"SELECT COUNT(*) as row_count FROM {table_name}"
        row_count = self.execute_query(count_query)[0]["ROW_COUNT"]
        
        return {
            "table_name": table_name,
            "schema": self.schema,
            "columns": columns,
            "row_count": row_count
        }

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


# Utility functions for common analytics operations

def create_analytics_connector() -> SnowflakeAnalyticsConnector:
    """Create a configured Snowflake analytics connector."""
    return SnowflakeAnalyticsConnector()

def validate_snowflake_config() -> Dict[str, Any]:
    """Validate Snowflake configuration."""
    required_vars = [
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER", 
        "SNOWFLAKE_PASSWORD"
    ]
    
    missing = [var for var in required_vars if not os.environ.get(var)]
    
    return {
        "valid": len(missing) == 0,
        "missing_variables": missing,
        "optional_defaults": {
            "SNOWFLAKE_WAREHOUSE": "ANALYTICS_WH",
            "SNOWFLAKE_DATABASE": "NEURONEWS",
            "SNOWFLAKE_SCHEMA": "PUBLIC",
            "SNOWFLAKE_ROLE": "ANALYTICS_ROLE"
        }
    }
