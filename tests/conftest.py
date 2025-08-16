# Simplified pytest configuration for containerized testing
import os
import asyncio
import pytest
from typing import Generator
import psycopg2
from psycopg2.extras import RealDictCursor

# Set testing environment
os.environ['TESTING'] = 'true'

from src.database.setup import get_sync_connection, setup_test_database, cleanup_test_database, create_test_articles


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_env():
    """Set up test environment before running tests."""
    # Set up test database
    await setup_test_database()
    yield
    # Clean up after all tests
    await cleanup_test_database()


@pytest.fixture(scope="function")
def db_connection():
    """Provide a database connection for testing."""
    conn = get_sync_connection(testing=True)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="function")
def clean_db(db_connection):
    """Ensure clean database state for each test."""
    # Clear test data before test
    with db_connection.cursor() as cur:
        cur.execute("""
            TRUNCATE TABLE neuronews.article_clusters,
                          neuronews.article_embeddings,
                          neuronews.article_keywords,
                          neuronews.article_topics,
                          neuronews.article_translations,
                          neuronews.event_clusters,
                          neuronews.articles
            RESTART IDENTITY CASCADE
        """)
        db_connection.commit()
    
    yield db_connection
    
    # Clean up after test (optional, but good practice)
    with db_connection.cursor() as cur:
        cur.execute("""
            TRUNCATE TABLE neuronews.article_clusters,
                          neuronews.article_embeddings,
                          neuronews.article_keywords,
                          neuronews.article_topics,
                          neuronews.article_translations,
                          neuronews.event_clusters,
                          neuronews.articles
            RESTART IDENTITY CASCADE
        """)
        db_connection.commit()


@pytest.fixture
def sample_articles(clean_db):
    """Create sample articles for testing."""
    return create_test_articles(count=5)


@pytest.fixture
def mock_sentence_transformer():
    """Provide a simple mock for SentenceTransformer in isolated tests."""
    class MockTransformer:
        def __init__(self, *args, **kwargs):
            self.embedding_dimension = 384
        
        def encode(self, texts, **kwargs):
            import numpy as np
            if isinstance(texts, str):
                texts = [texts]
            return np.random.rand(len(texts), 384)
        
        def get_sentence_embedding_dimension(self):
            return 384
    
    return MockTransformer


# Environment-specific configurations
@pytest.fixture
def app_config():
    """Provide application configuration for tests."""
    return {
        'database': {
            'host': os.getenv('DB_HOST', 'test-postgres'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'neuronews_test'),
            'user': os.getenv('DB_USER', 'test_user'),
            'password': os.getenv('DB_PASSWORD', 'test_password')
        },
        'redis': {
            'host': os.getenv('REDIS_HOST', 'test-redis'),
            'port': int(os.getenv('REDIS_PORT', 6379))
        },
        's3': {
            'endpoint': os.getenv('S3_ENDPOINT', 'http://test-minio:9000'),
            'access_key': os.getenv('S3_ACCESS_KEY', 'testuser'),
            'secret_key': os.getenv('S3_SECRET_KEY', 'testpassword'),
            'bucket': os.getenv('S3_BUCKET', 'test-bucket')
        }
    }
