import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import os

from src.api.routes.news_routes import router as news_api_router
from fastapi import FastAPI
from src.database.redshift_loader import RedshiftLoader


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Set required environment variables for tests."""
    with patch.dict(
        os.environ,
        {
            "REDSHIFT_HOST": "test-host",
            "REDSHIFT_DB": "test-db",
            "REDSHIFT_USER": "test-user",
            "REDSHIFT_PASSWORD": "test-pass",
        },
    ):
        yield


@pytest.fixture
def app():
    """Create test FastAPI app with news routes."""
    app = FastAPI()
    app.include_router(news_api_router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Create mock RedshiftLoader."""
    mock = AsyncMock(spec=RedshiftLoader)
    mock.connect = AsyncMock()
    mock.close = AsyncMock()
    mock.execute_query = AsyncMock()

    # Mock constructor args
    mock._host = "test-host"
    mock._database = "test-db"
    mock._user = "test-user"
    mock._password = "test-pass"

    return mock


def test_get_articles_by_topic(client, mock_db):
    """Test retrieving articles by topic."""
    # Mock database response
    mock_articles = [
        (
            "article1",
            "AI Revolution in Healthcare",
            "http://example.com/1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            "TestSource",
            "Technology",
            0.8,
            "POSITIVE",
        )
    ]
    mock_db.execute_query.return_value = mock_articles

    with patch("src.api.routes.news_routes.RedshiftLoader", return_value=mock_db):
        response = client.get("/news/articles/topic/AI", params={"limit": 10})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    article = data[0]

    assert article["id"] == "article1"
    assert article["title"] == "AI Revolution in Healthcare"

    # Verify query parameters
    query_call = mock_db.execute_query.call_args[0][0]
    params = mock_db.execute_query.call_args[0][1]

    assert "ILIKE" in query_call
    assert "LIMIT" in query_call
    assert len(params) == 3
    assert params[0] == "%AI%"  # Topic pattern
    assert params[2] == 10  # Limit


def test_get_articles_by_topic_validation(client, mock_db):
    """Test input validation for topic search."""
    with patch("src.api.routes.news_routes.RedshiftLoader", return_value=mock_db):
        # Test invalid limit
        response = client.get("/news/articles/topic/AI", params={"limit": 0})
        assert response.status_code == 422

        response = client.get("/news/articles/topic/AI", params={"limit": 101})
        assert response.status_code == 422


def test_get_articles(client, mock_db):
    """Test retrieving articles list."""
    mock_articles = [
        (
            "article1",
            "Test Article",
            "http://example.com/1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            "TestSource",
            "Technology",
            0.8,
            "POSITIVE",
        )
    ]
    mock_db.execute_query.return_value = mock_articles

    with patch("src.api.routes.news_routes.RedshiftLoader", return_value=mock_db):
        response = client.get("/news/articles")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    article = data[0]

    assert article["id"] == "article1"
    assert article["title"] == "Test Article"
    assert article["url"] == "http://example.com/1"
    assert article["publish_date"] == "2024-01-01T00:00:00+00:00"
    assert article["source"] == "TestSource"
    assert article["category"] == "Technology"
    assert article["sentiment"]["score"] == 0.8
    assert article["sentiment"]["label"] == "POSITIVE"


def test_get_articles_with_filters(client, mock_db):
    """Test retrieving articles with query filters."""
    mock_db.execute_query.return_value = []

    with patch("src.api.routes.news_routes.RedshiftLoader", return_value=mock_db):
        response = client.get(
            "/news/articles",
            params={
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-01-31T23:59:59Z",
                "source": "TestSource",
                "category": "Technology",
            },
        )

    assert response.status_code == 200

    # Verify query parameters were used
    query_call = mock_db.execute_query.call_args[0][0]
    params = mock_db.execute_query.call_args[0][1]

    assert "publish_date >= %s" in query_call
    assert "publish_date <= %s" in query_call
    assert "source = %s" in query_call
    assert "category = %s" in query_call
    assert len(params) == 4
    assert params[0] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert params[1] == datetime(2024, 1, 31, 23, 59, 59, tzinfo=timezone.utc)
    assert params[2] == "TestSource"
    assert params[3] == "Technology"


def test_get_article_by_id(client, mock_db):
    """Test retrieving a specific article."""
    mock_article = [
        (
            "article1",
            "Test Article",
            "http://example.com/1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            "TestSource",
            "Technology",
            "Article content",
            0.8,
            "POSITIVE",
            ["Entity1", "Entity2"],
        )
    ]
    mock_db.execute_query.return_value = mock_article

    with patch("src.api.routes.news_routes.RedshiftLoader", return_value=mock_db):
        response = client.get("/news/articles/article1")

    assert response.status_code == 200
    article = response.json()

    assert article["id"] == "article1"
    assert article["title"] == "Test Article"
    assert article["content"] == "Article content"
    assert article["entities"] == ["Entity1", "Entity2"]


def test_get_article_not_found(client, mock_db):
    """Test 404 response for non-existent article."""
    mock_db.execute_query.return_value = []

    with patch("src.api.routes.news_routes.RedshiftLoader", return_value=mock_db):
        response = client.get("/news/articles/nonexistent")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_database_error_handling(client, mock_db):
    """Test error handling for database failures."""
    mock_db.execute_query.side_effect = Exception("Database error")

    with patch("src.api.routes.news_routes.RedshiftLoader", return_value=mock_db):
        response = client.get("/news/articles")

    assert response.status_code == 500
    assert "Database error" in response.json()["detail"]


def test_missing_redshift_host():
    """Test error when REDSHIFT_HOST env var is missing."""
    app = FastAPI()
    app.include_router(news_api_router)
    client = TestClient(app)

    with patch.dict(os.environ, {}, clear=True):
        response = client.get("/news/articles")

    assert response.status_code == 500
    assert "REDSHIFT_HOST environment variable not set" in response.json()["detail"]
