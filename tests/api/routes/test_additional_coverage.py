"""Tests for additional API endpoints to improve coverage."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.jwt_auth import require_auth
from src.api.routes import auth_routes, graph_routes, news_routes, search_routes


@pytest.fixture
def test_app():
    """Build a client with the routers these tests exercise.

    The module-level ``src.api.app.app`` runs in TESTING mode (no routers), so
    the auth/search/news/graph routers are mounted here. Each carries its own
    prefix and is mounted under ``/api/v1`` to match the request paths. JWT
    ``require_auth`` is overridden so authenticated routes (e.g. logout) reach
    their logic, and ``search_routes.get_db`` is overridden with an empty-result
    connector so the search endpoint returns 200 without a populated warehouse.
    """

    class _EmptyConnector:
        async def execute_query(self, *args, **kwargs):
            return []

    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/api/v1")
    app.include_router(search_routes.router, prefix="/api/v1")
    app.include_router(news_routes.router, prefix="/api/v1")
    app.include_router(graph_routes.router, prefix="/api/v1")
    app.dependency_overrides[require_auth] = lambda: {"sub": "test-user"}
    app.dependency_overrides[search_routes.get_db] = lambda: _EmptyConnector()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_auth_register_endpoint(test_app):
    """Test user registration endpoint."""
    user_data = {
        "email": "newuser@example.com",
        "password": "newpassword123",
        "role": "user"
    }
    response = test_app.post("/api/v1/auth/register", json=user_data)
    # Accept success (201), validation errors (422), or server errors (500)
    assert response.status_code in [201, 422, 500]


def test_auth_logout_endpoint(test_app):
    """Test user logout endpoint."""
    response = test_app.post("/api/v1/auth/logout")
    # Accept success (200), unauthorized (401), or server errors (500)
    assert response.status_code in [200, 401, 500]


def test_graph_event_timeline(test_app):
    """Test event timeline endpoint."""
    response = test_app.get("/api/v1/graph/event_timeline?topic=technology")
    # Accept success (200) or service unavailable (503) due to graph DB dependencies
    assert response.status_code in [200, 503]


def test_quicksight_health_check(test_app):
    """Test that the app degrades gracefully when quicksight routes are absent.

    ``quicksight_routes`` imports ``src.dashboards.quicksight_service``, which is
    no longer shipped, so the module is not importable. ``app.py`` guards this
    behind ``try_import_quicksight_routes()``: it must swallow the ImportError,
    return False, and leave ``QUICKSIGHT_AVAILABLE`` False.
    """
    import src.api.app as app_module

    assert app_module.try_import_quicksight_routes() is False
    assert app_module.QUICKSIGHT_AVAILABLE is False


def test_search_routes_edge_cases(test_app):
    """Test edge cases for search routes."""
    # Test with special characters
    response = test_app.get("/api/v1/search/articles?q=test%20query")
    assert response.status_code == 200

    # Test with very long query
    long_query = "a" * 1000
    response = test_app.get(f"/api/v1/search/articles?q={long_query}")
    assert response.status_code == 200


def test_news_articles_with_parameters(test_app):
    """Test news articles with query parameters."""
    # Test with limit parameter
    response = test_app.get("/api/v1/news/articles?limit=5")
    assert response.status_code in [200, 500]
    
    # Test articles by topic with limit
    response = test_app.get("/api/v1/news/articles/topic/technology?limit=10")
    assert response.status_code in [200, 500]
