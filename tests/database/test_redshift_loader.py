"""Tests for RedshiftLoader class."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import os

from src.database.redshift_loader import RedshiftLoader

@pytest.fixture
def mock_cursor():
    """Create mock database cursor."""
    cursor = MagicMock()
    cursor.fetchall = MagicMock()
    cursor.rowcount = 1
    return cursor

@pytest.fixture
def mock_conn():
    """Create mock database connection."""
    conn = MagicMock()
    conn.commit = MagicMock()
    return conn

@pytest.fixture
def loader():
    """Create RedshiftLoader instance with test config."""
    with patch.dict(os.environ, {"REDSHIFT_PASSWORD": "test-pass"}):
        return RedshiftLoader(
            host="test-host",
            database="test-db",
            user="test-user"
        )

@pytest.mark.asyncio
async def test_get_latest_articles(loader, mock_cursor, mock_conn):
    """Test fetching latest articles without filters."""
    # Mock database connection
    loader._cursor = mock_cursor
    loader._conn = mock_conn
    
    # Mock query results
    mock_articles = [
        (
            "article1",
            "Test Article",
            "http://example.com/1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            "Technology",
            "TestSource",
            0.8,
            "POSITIVE"
        )
    ]
    mock_cursor.fetchall.return_value = mock_articles
    
    # Test default parameters
    articles = await loader.get_latest_articles()
    
    # Verify query construction
    query = mock_cursor.execute.call_args[0][0]
    params = mock_cursor.execute.call_args[0][1]
    
    assert "ORDER BY publish_date DESC" in query
    assert "LIMIT %s" in query
    assert len(params) == 1
    assert params[0] == 10  # Default limit
    
    # Verify result formatting
    assert len(articles) == 1
    article = articles[0]
    assert article["id"] == "article1"
    assert article["title"] == "Test Article"
    assert article["publish_date"] == "2024-01-01T00:00:00+00:00"
    assert article["sentiment"]["score"] == 0.8
    assert article["sentiment"]["label"] == "POSITIVE"

@pytest.mark.asyncio
async def test_get_latest_articles_with_filters(loader, mock_cursor, mock_conn):
    """Test fetching articles with sentiment and category filters."""
    loader._cursor = mock_cursor
    loader._conn = mock_conn
    mock_cursor.fetchall.return_value = []
    
    # Test with all filters
    await loader.get_latest_articles(
        limit=5,
        min_score=0.7,
        sentiment="POSITIVE",
        category="Technology"
    )
    
    # Verify query parameters
    query = mock_cursor.execute.call_args[0][0]
    params = mock_cursor.execute.call_args[0][1]
    
    assert "sentiment_score >= %s" in query
    assert "sentiment_label = %s" in query
    assert "category = %s" in query
    assert len(params) == 4
    assert params[0] == 0.7
    assert params[1] == "POSITIVE"
    assert params[2] == "Technology"
    assert params[3] == 5  # Limit

@pytest.mark.asyncio
async def test_load_article(loader, mock_cursor, mock_conn):
    """Test loading a single article."""
    loader._cursor = mock_cursor
    loader._conn = mock_conn
    
    article_data = {
        "id": "article1",
        "title": "Test Article",
        "url": "http://example.com/1",
        "content": "Article content",
        "publish_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "source": "TestSource",
        "category": "Technology",
        "sentiment_score": 0.8,
        "sentiment_label": "POSITIVE"
    }
    
    await loader.load_article(article_data)
    
    # Verify database operations
    mock_cursor.execute.assert_called_once()
    mock_conn.commit.assert_called_once()
    
    # Verify query parameters
    query = mock_cursor.execute.call_args[0][0]
    params = mock_cursor.execute.call_args[0][1]
    
    assert "INSERT INTO news_articles" in query
    assert len(params) == 9
    assert params[0] == "article1"
    assert params[8] == "POSITIVE"

@pytest.mark.asyncio
async def test_load_article_missing_fields(loader):
    """Test error handling for missing required fields."""
    article_data = {
        "id": "article1",
        "title": "Test Article"
        # Missing url and content
    }
    
    with pytest.raises(ValueError) as exc:
        await loader.load_article(article_data)
    assert "Missing required fields" in str(exc.value)

@pytest.mark.asyncio
async def test_delete_article(loader, mock_cursor, mock_conn):
    """Test deleting an article."""
    loader._cursor = mock_cursor
    loader._conn = mock_conn
    
    success = await loader.delete_article("article1")
    
    assert success is True
    mock_cursor.execute.assert_called_with(
        "DELETE FROM news_articles WHERE id = %s",
        ["article1"]
    )
    mock_conn.commit.assert_called_once()