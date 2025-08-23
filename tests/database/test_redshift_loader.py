"""Tests for RedshiftLoader class."""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

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
        return RedshiftLoader(host="test-host", database="test-db", user="test-user")


@pytest.mark.asyncio
async def test_get_latest_articles_with_pagination(loader, mock_cursor, mock_conn):
    """Test paginated article retrieval."""
    loader._cursor = mock_cursor
    loader._conn = mock_conn

    # Mock total count query
    mock_cursor.fetchall.side_effect = [
        [(25,)],  # Total count result
        [  # Page 2 articles
            (
                "article11",
                "Test Article 11",
                "http://example.com/11",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                "Technology",
                "TestSource",
                0.8,
                "POSITIVE",
            )
        ],
    ]

    # Request page 2 with 10 items per page
    articles, pagination = await loader.get_latest_articles(page=2, per_page=10)

    # Verify pagination metadata
    assert pagination["total"] == 25
    assert pagination["page"] == 2
    assert pagination["per_page"] == 10
    assert pagination["pages"] == 3

    # Verify OFFSET calculation
    # Second query (after count)
    query = mock_cursor.execute.call_args_list[1][0][0]
    params = mock_cursor.execute.call_args_list[1][0][1]

    assert "OFFSET" in query
    assert params[-1] == 10  # OFFSET for page 2
    assert params[-2] == 10  # LIMIT


@pytest.mark.asyncio
async def test_pagination_validation(loader):
    """Test pagination parameter validation."""
    with pytest.raises(ValueError, match="Page number must be >= 1"):
        await loader.get_latest_articles(page=0)

    with pytest.raises(ValueError, match="Items per page must be between 1 and 100"):
        await loader.get_latest_articles(per_page=0)

    with pytest.raises(ValueError, match="Items per page must be between 1 and 100"):
        await loader.get_latest_articles(per_page=101)


@pytest.mark.asyncio
async def test_get_latest_articles_with_filters(loader, mock_cursor, mock_conn):
    """Test article retrieval with filters."""
    loader._cursor = mock_cursor
    loader._conn = mock_conn

    mock_cursor.fetchall.side_effect = [
        [(5,)],  # Count query result
        [],  # Empty page for this test
    ]

    # Test with all filters
    articles, pagination = await loader.get_latest_articles(
        page=1, per_page=10, min_score=0.7, sentiment="POSITIVE", category="Technology"
    )

    # Verify query conditions
    query = mock_cursor.execute.call_args_list[1][0][0]  # Main query
    params = mock_cursor.execute.call_args_list[1][0][1]

    assert "sentiment_score >= %s" in query
    assert "sentiment_label = %s" in query
    assert "category = %s" in query
    assert len(params) == 5  # 3 filters + LIMIT + OFFSET
    assert params[0] == 0.7
    assert params[1] == "POSITIVE"
    assert params[2] == "Technology"


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
        "sentiment_label": "POSITIVE",
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
        "title": "Test Article",
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
    mock_cursor.execute.assert_called_with("DELETE FROM news_articles WHERE id = %s", ["article1"])
    mock_conn.commit.assert_called_once()
