"""
Tests for role-based access control.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.jwt_auth import auth_handler
from src.api.middleware.auth_middleware import configure_auth_middleware
from src.api.routes.article_routes import router as article_router

# Test data
TEST_ARTICLE = {
    "title": "Test Article",
    "content": "Test content",
    "category": "test",
    "source": "test",
}


@pytest.fixture
def app():
    """Create test FastAPI application."""
    app = FastAPI()
    app.include_router(article_router)
    configure_auth_middleware(app)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def test_db(monkeypatch):
    """Mock database with test articles."""
    articles = {}

    async def mock_execute_query(self, query, params=None):
        if "SELECT" in query:
            if "WHERE id = " in query:
                article_id = params[0]
                return [articles[article_id]] if article_id in articles else []
            return list(articles.values())

        if "INSERT" in query:
            article_id = f"test_{len(articles) + 1}"
            article = {
                "id": article_id,
                "title": params[0],
                "content": params[1],
                "category": params[2],
                "source": params[3],
                "created_by": params[4],
                "created_at": params[5],
                "updated_at": None,
                "sentiment_score": None,
                "sentiment_label": None,
            }
            articles[article_id] = article
            return [article]

        if "UPDATE" in query:
            article_id = params[5]
            if article_id in articles:
                articles[article_id].update(
                    {
                        "title": params[0],
                        "content": params[1],
                        "category": params[2],
                        "source": params[3],
                        "updated_at": params[4],
                    }
                )
                return [articles[article_id]]
            return []

        if "DELETE" in query:
            article_id = params[0]
            if article_id in articles:
                del articles[article_id]

        return []

    monkeypatch.setattr(
        "src.database.redshift_loader.RedshiftLoader.execute_query", mock_execute_query
    )
    return articles


def create_token(role: str = "user", user_id: str = "test_user"):
    """Create test JWT token."""
    return auth_handler.create_access_token(
        {"sub": user_id, "role": role, "email": f"{role}@example.com"}
    )


def test_read_articles_user(client, test_db):
    """Test regular user can read articles."""
    token = create_token("user")
    response = client.get("/articles", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_create_article_editor(client, test_db):
    """Test editor can create articles."""
    token = create_token("editor")
    response = client.post(
        "/articles", headers={"Authorization": f"Bearer {token}"}, json=TEST_ARTICLE
    )
    assert response.status_code == 200
    assert response.json()["title"] == TEST_ARTICLE["title"]


def test_create_article_user_forbidden(client, test_db):
    """Test regular user cannot create articles."""
    token = create_token("user")
    response = client.post(
        "/articles", headers={"Authorization": f"Bearer {token}"}, json=TEST_ARTICLE
    )
    assert response.status_code == 403
    assert "Missing required permissions" in response.json()["detail"]


def test_update_own_article_editor(client, test_db):
    """Test editor can update their own article."""
    token = create_token("editor", "editor1")

    # Create article
    create_response = client.post(
        "/articles", headers={"Authorization": f"Bearer {token}"}, json=TEST_ARTICLE
    )
    article_id = create_response.json()["id"]

    # Update article
    update_data = dict(TEST_ARTICLE)
    update_data["title"] = "Updated Title"
    response = client.put(
        f"/articles/{article_id}",
        headers={"Authorization": f"Bearer {token}"},
        json=update_data,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


def test_update_others_article_editor(client, test_db):
    """Test editor cannot update another editor's article."""
    # First editor creates article
    token1 = create_token("editor", "editor1")
    create_response = client.post(
        "/articles", headers={"Authorization": f"Bearer {token1}"}, json=TEST_ARTICLE
    )
    article_id = create_response.json()["id"]

    # Second editor tries to update
    token2 = create_token("editor", "editor2")
    update_data = dict(TEST_ARTICLE)
    update_data["title"] = "Updated Title"
    response = client.put(
        f"/articles/{article_id}",
        headers={"Authorization": f"Bearer {token2}"},
        json=update_data,
    )
    assert response.status_code == 403


def test_update_any_article_admin(client, test_db):
    """Test admin can update any article."""
    # Editor creates article
    editor_token = create_token("editor", "editor1")
    create_response = client.post(
        "/articles",
        headers={"Authorization": f"Bearer {editor_token}"},
        json=TEST_ARTICLE,
    )
    article_id = create_response.json()["id"]

    # Admin updates article
    admin_token = create_token("admin", "admin1")
    update_data = dict(TEST_ARTICLE)
    update_data["title"] = "Admin Updated"
    response = client.put(
        f"/articles/{article_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=update_data,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Admin Updated"


def test_delete_article_permissions(client, test_db):
    """Test delete permissions for different roles."""
    # Editor creates article
    editor_token = create_token("editor", "editor1")
    create_response = client.post(
        "/articles",
        headers={"Authorization": f"Bearer {editor_token}"},
        json=TEST_ARTICLE,
    )
    article_id = create_response.json()["id"]

    # User cannot delete
    user_token = create_token("user")
    response = client.delete(
        f"/articles/{article_id}", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 403

    # Different editor cannot delete
    editor2_token = create_token("editor", "editor2")
    response = client.delete(
        f"/articles/{article_id}", headers={"Authorization": f"Bearer {editor2_token}"}
    )
    assert response.status_code == 403

    # Original editor can delete
    response = client.delete(
        f"/articles/{article_id}", headers={"Authorization": f"Bearer {editor_token}"}
    )
    assert response.status_code == 200


def test_missing_token(client):
    """Test requests without authentication token."""
    response = client.get("/articles")
    assert response.status_code == 401
    assert "No authorization token provided" in response.json()["detail"]


def test_invalid_token(client):
    """Test requests with invalid token."""
    response = client.get(
        "/articles", headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401
    assert "Invalid token" in response.json()["detail"]
