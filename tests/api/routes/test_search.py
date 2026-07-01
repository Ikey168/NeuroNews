"""Tests for the search API endpoints.

These tests target the CURRENT search router API in
``src/api/routes/search_routes.py``. The router uses the ``/search`` prefix and
exposes ``/search/articles`` (backed by an async ``execute_query`` DB
dependency). We mount it on a fresh app and override the ``get_db`` dependency
so no live warehouse connection is required.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import search_routes


@pytest.fixture
def test_app():
    """Fresh app with only the search router mounted and DB dependency mocked."""
    app = FastAPI()
    app.include_router(search_routes.router)

    # get_db is an async dependency; override it with one returning a mock DB
    # whose execute_query is awaitable and yields no rows.
    mock_db = AsyncMock()
    mock_db.execute_query = AsyncMock(return_value=[])

    async def _override_get_db():
        return mock_db

    app.dependency_overrides[search_routes.get_db] = _override_get_db
    return TestClient(app)


def test_search_news_success(test_app):
    """A valid query returns 200 with a results list in the payload."""
    response = test_app.get("/search/articles?q=test")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["results"], list)
    assert body["query"] == "test"


def test_search_news_no_query(test_app):
    """Missing the required 'q' parameter yields a 422 validation error."""
    response = test_app.get("/search/articles")
    assert response.status_code == 422  # FastAPI validation error for missing required query


def test_search_news_empty_query(test_app):
    """An empty 'q' violates the min_length=1 constraint -> 422 validation error."""
    response = test_app.get("/search/articles?q=")
    assert response.status_code == 422  # min_length=1 validation failure
