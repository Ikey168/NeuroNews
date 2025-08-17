"""
Database setup and utilities for NeuroNews.
This module provides functions to set up test databases and manage connections.
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import asyncpg

logger = logging.getLogger(__name__)


def get_db_config(testing: bool = False) -> Dict[str, Any]:
    """
    Get database configuration based on environment.
    
    Args:
        testing: If True, return test database configuration
        
    Returns:
        Database configuration dictionary
    """
    if testing or os.getenv('TESTING'):
        return {
            'host': os.getenv('DB_HOST', 'test-postgres'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'neuronews_test'),
            'user': os.getenv('DB_USER', 'test_user'),
            'password': os.getenv('DB_PASSWORD', 'test_password')
        }
    else:
        return {
            'host': os.getenv('DB_HOST', 'postgres'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'neuronews_dev'),
            'user': os.getenv('DB_USER', 'neuronews'),
            'password': os.getenv('DB_PASSWORD', 'dev_password')
        }


def get_sync_connection(testing: bool = False) -> psycopg2.extensions.connection:
    """
    Get synchronous database connection.
    
    Args:
        testing: If True, connect to test database
        
    Returns:
        psycopg2 connection object
    """
    config = get_db_config(testing)
    return psycopg2.connect(**config)


async def get_async_connection(testing: bool = False) -> asyncpg.Connection:
    """
    Get asynchronous database connection.
    
    Args:
        testing: If True, connect to test database
        
    Returns:
        asyncpg connection object
    """
    config = get_db_config(testing)
    return await asyncpg.connect(**config)


async def setup_test_database():
    """
    Set up test database with required tables and data.
    This is called during test container initialization.
    """
    logger.info("Setting up test database...")
    
    try:
        # Wait for database to be ready
        max_retries = 30
        for attempt in range(max_retries):
            try:
                conn = get_sync_connection(testing=True)
                conn.close()
                logger.info("Database is ready!")
                break
            except psycopg2.OperationalError:
                if attempt == max_retries - 1:
                    raise
                logger.info(f"Waiting for database... (attempt {attempt + 1})")
                await asyncio.sleep(2)
        
        # Create tables if they don't exist (handled by init script)
        with get_sync_connection(testing=True) as conn:
            with conn.cursor() as cur:
                # Verify tables exist
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'neuronews'
                """)
                tables = [row[0] for row in cur.fetchall()]
                logger.info(f"Available tables: {tables}")
                
                # Clear existing test data
                test_tables = [
                    'article_clusters', 'article_embeddings', 'article_keywords',
                    'article_topics', 'article_translations', 'event_clusters',
                    'api_keys', 'articles'
                ]
                
                for table in test_tables:
                    if table in tables:
                        cur.execute(f"TRUNCATE TABLE neuronews.{table} CASCADE")
                        logger.info(f"Cleared table: {table}")
                
                conn.commit()
                logger.info("Test database setup complete!")
                
    except Exception as e:
        logger.error(f"Failed to set up test database: {e}")
        raise


async def cleanup_test_database():
    """
    Clean up test database after tests.
    """
    logger.info("Cleaning up test database...")
    
    try:
        with get_sync_connection(testing=True) as conn:
            with conn.cursor() as cur:
                # Clear all data
                cur.execute("""
                    TRUNCATE TABLE neuronews.article_clusters,
                                  neuronews.article_embeddings,
                                  neuronews.article_keywords,
                                  neuronews.article_topics,
                                  neuronews.article_translations,
                                  neuronews.event_clusters,
                                  neuronews.api_keys,
                                  neuronews.articles
                    CASCADE
                """)
                conn.commit()
                logger.info("Test database cleanup complete!")
                
    except Exception as e:
        logger.error(f"Failed to clean up test database: {e}")


def create_test_articles(count: int = 10) -> list:
    """
    Create test articles in the database.
    
    Args:
        count: Number of test articles to create
        
    Returns:
        List of created article IDs
    """
    sample_articles = [
        {
            'url': f'https://example.com/article-{i}',
            'title': f'Test Article {i}',
            'content': f'This is test content for article {i}. ' * 20,
            'author': f'Author {i}',
            'source': 'test-source',
            'category': 'technology' if i % 2 == 0 else 'politics',
            'language': 'en'
        }
        for i in range(1, count + 1)
    ]
    
    article_ids = []
    
    try:
        with get_sync_connection(testing=True) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                for article in sample_articles:
                    cur.execute("""
                        INSERT INTO neuronews.articles 
                        (url, title, content, author, source, category, language)
                        VALUES (%(url)s, %(title)s, %(content)s, %(author)s, 
                               %(source)s, %(category)s, %(language)s)
                        RETURNING id
                    """, article)
                    article_id = cur.fetchone()['id']
                    article_ids.append(str(article_id))
                
                conn.commit()
                logger.info(f"Created {len(article_ids)} test articles")
                
    except Exception as e:
        logger.error(f"Failed to create test articles: {e}")
        raise
    
    return article_ids


if __name__ == "__main__":
    # Run database setup when called directly
    asyncio.run(setup_test_database())
