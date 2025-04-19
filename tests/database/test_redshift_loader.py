"""
Tests for the RedshiftLoader class.
"""
import os
import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from src.database.redshift_loader import RedshiftLoader
from src.database.s3_storage import S3Storage

# Test data
SAMPLE_ARTICLE = {
    'id': 'test_article_001',
    'source': 'test-news',
    'title': 'Test Article',
    'content': 'This is a test article content.',
    'published_date': '2025-04-19T20:00:00Z',
    'sentiment': 0.8,
    'entities': {'PERSON': ['John Doe'], 'ORG': ['Test Corp']},
    'keywords': ['test', 'article', 'news']
}

@pytest.fixture
def mock_s3_storage():
    """Create a mock S3Storage instance."""
    mock_storage = MagicMock(spec=S3Storage)
    mock_storage.get_article.return_value = {'data': SAMPLE_ARTICLE}
    mock_storage.list_articles.return_value = [
        {'key': 'test_key', 'metadata': {}}
    ]
    return mock_storage

@pytest.fixture
def mock_redshift_connection():
    """Create a mock psycopg2 connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (SAMPLE_ARTICLE['id'],)
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.__enter__.return_value = mock_cursor
    return mock_conn

@pytest.fixture
def redshift_loader(mock_s3_storage):
    """Create a RedshiftLoader instance with mock S3 storage."""
    return RedshiftLoader(
        host='test-host',
        password='test-password',
        s3_storage=mock_s3_storage
    )

def test_init_without_password():
    """Test initialization without password raises error."""
    with pytest.raises(ValueError):
        RedshiftLoader(host='test-host')

def test_init_with_env_password():
    """Test initialization with password from environment."""
    mock_s3_storage = MagicMock(spec=S3Storage)
    with patch.dict(os.environ, {'REDSHIFT_PASSWORD': 'test-password'}):
        with patch('src.database.redshift_loader.S3Storage', return_value=mock_s3_storage):
            loader = RedshiftLoader(host='test-host')
            assert loader.password == 'test-password'

def test_load_article(redshift_loader, mock_redshift_connection):
    """Test loading a single article."""
    with patch('psycopg2.connect', return_value=mock_redshift_connection):
        article_id = redshift_loader.load_article(SAMPLE_ARTICLE)
        assert article_id == SAMPLE_ARTICLE['id']

        # Verify SQL execution
        cursor = mock_redshift_connection.cursor()
        cursor.execute.assert_called_once()
        args = cursor.execute.call_args[0]
        assert 'INSERT INTO news_articles' in args[0]
        assert len(args[1]) == 8  # Check all fields are included

def test_load_article_missing_fields(redshift_loader):
    """Test loading article with missing required fields raises error."""
    invalid_article = {
        'title': 'Test Article',
        'content': 'Content'
        # Missing required fields
    }
    with pytest.raises(ValueError) as exc_info:
        redshift_loader.load_article(invalid_article)
    assert 'Missing required article fields' in str(exc_info.value)

def test_load_articles_from_s3(redshift_loader, mock_redshift_connection):
    """Test loading multiple articles from S3."""
    with patch('psycopg2.connect', return_value=mock_redshift_connection):
        article_ids = redshift_loader.load_articles_from_s3(batch_size=2)
        assert len(article_ids) == 1
        assert article_ids[0] == SAMPLE_ARTICLE['id']

def test_load_articles_from_s3_with_max(redshift_loader, mock_redshift_connection):
    """Test loading articles with max_articles limit."""
    with patch('psycopg2.connect', return_value=mock_redshift_connection):
        article_ids = redshift_loader.load_articles_from_s3(max_articles=1)
        assert len(article_ids) == 1

def test_delete_article(redshift_loader, mock_redshift_connection):
    """Test deleting an article."""
    with patch('psycopg2.connect', return_value=mock_redshift_connection):
        redshift_loader.delete_article(SAMPLE_ARTICLE['id'])
        
        # Verify SQL execution
        cursor = mock_redshift_connection.cursor()
        cursor.execute.assert_called_once_with(
            "DELETE FROM news_articles WHERE id = %s",
            (SAMPLE_ARTICLE['id'],)
        )

def test_connect_error(redshift_loader):
    """Test database connection error handling."""
    with patch('psycopg2.connect', side_effect=Exception('Connection failed')):
        with pytest.raises(Exception) as exc_info:
            redshift_loader.connect()
        assert 'Connection failed' in str(exc_info.value)