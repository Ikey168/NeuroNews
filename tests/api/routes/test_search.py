"""Tests for the search API endpoints."""
import pytest
from fastapi.testclient import TestClient
from src.api.app import app  # Replace with your actual application import

client = TestClient(app)


def test_search_news_success(test_app):
    """Test successful search for news articles."""
    response = test_app.get("/api/v1/search?q=test")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_search_news_no_query(test_app):
    """Test search without query parameter."""
    response = test_app.get("/api/v1/search")
    assert response.status_code == 422  # FastAPI validation error for missing required query


def test_search_news_empty_query(test_app):
    """Test search with an empty query parameter."""
    response = test_app.get("/api/v1/search?q=")
    assert response.status_code == 400  # Bad Request
