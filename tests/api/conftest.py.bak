"""Configuration for API tests."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import (
    auth_routes,
    news_routes,
    graph_routes,
    api_key_routes,
)
from src.api.routes import search_routes


@pytest.fixture(scope="module")
def test_app():
    """Create a test app with only the necessary routers."""
    app = FastAPI()

    # Include routers needed for tests
    app.include_router(auth_routes.router, prefix="/api/v1", tags=["Authentication"])
    app.include_router(news_routes.router, prefix="/api/v1", tags=["News"])
    app.include_router(graph_routes.router, prefix="/api/v1", tags=["Graph"])
    app.include_router(search_routes.router, prefix="/api/v1", tags=["Search"])
    app.include_router(api_key_routes.router, prefix="/api/v1", tags=["API Keys"])

    with TestClient(app) as client:
        yield client
