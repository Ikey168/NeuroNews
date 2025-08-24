"""
Tests for authentication system.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.jwt_auth import auth_handler
from src.api.middleware.auth_middleware import configure_auth_middleware
from src.api.routes.auth_routes import router as auth_router

# Test data
TEST_USER = {
    "email": "test@example.com",
    "password": "SecurePass123!",
    "first_name": "Test",
    "last_name": "User",
    "role": "user",
}

TEST_ADMIN = {
    "email": "admin@example.com",
    "password": "AdminPass123!",
    "first_name": "Admin",
    "last_name": "User",
    "role": "admin",
}


@pytest.fixture
def app():
    """Create test FastAPI application."""
    app = FastAPI()
    app.include_router(auth_router)
    configure_auth_middleware(app)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def test_db(monkeypatch):
    """Mock database with test users."""
    users = {}

    async def mock_execute_query(self, query, params=None):
        if "SELECT" in query and params:
            email = params[0]
            return (
                [
                    (
                        users[email]["id"],
                        users[email]["password_hash"],
                        users[email]["role"],
                    )
                ]
                if email in users
                else []
            )

        if "INSERT" in query and params:
            email = params[0]
            users[email] = {
                "id": len(users) + 1,
                "email": email,
                "password_hash": params[1],
                "role": params[4],
            }
            return [(users[email]["id"],)]

    monkeypatch.setattr(
        "src.database.snowflake_connector.SnowflakeAnalyticsConnector.execute_query", mock_execute_query
    )
    return users


def test_register_user(client, test_db):
    """Test user registration."""
    response = client.post("/auth/register", json=TEST_USER)
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # Verify token contents
    payload = jwt.decode(
        data["access_token"],
        auth_handler.jwt_secret,
        algorithms=[auth_handler.jwt_algorithm],
    )
    assert payload["email"] == TEST_USER["email"]
    assert payload["role"] == TEST_USER["role"]


def test_register_duplicate_email(client, test_db):
    """Test registration with existing email."""
    # Register first user
    client.post("/auth/register", json=TEST_USER)

    # Try registering same email
    response = client.post("/auth/register", json=TEST_USER)
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


def test_login_success(client, test_db):
    """Test successful login."""
    # Register user first
    client.post("/auth/register", json=TEST_USER)

    # Login
    response = client.post(
        "/auth/login",
        json={"email": TEST_USER["email"], "password": TEST_USER["password"]},
    )
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_invalid_credentials(client, test_db):
    """Test login with wrong password."""
    # Register user
    client.post("/auth/register", json=TEST_USER)

    # Try login with wrong password
    response = client.post(
        "/auth/login",
        json={"email": TEST_USER["email"], "password": "WrongPassword123!"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_refresh_token(client):
    """Test token refresh."""
    # Create test tokens
    token_data = {"sub": 1, "email": TEST_USER["email"], "role": TEST_USER["role"]}
    refresh_token = auth_handler.create_refresh_token(token_data)

    # Refresh tokens
    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_refresh_invalid_token(client):
    """Test refresh with invalid token."""
    response = client.post("/auth/refresh", json={"refresh_token": "invalid-token"})
    assert response.status_code == 401


def test_verify_token(client):
    """Test token verification."""
    # Create test token
    token_data = {"sub": 1, "email": TEST_USER["email"], "role": TEST_USER["role"]}
    access_token = auth_handler.create_access_token(token_data)

    # Verify token
    response = client.get(
        "/auth/verify", headers={"Authorization": "Bearer {0}".format(access_token)}
    )
    assert response.status_code == 200


def test_verify_expired_token(client):
    """Test expired token verification."""
    # Create expired token
    token_data = {
        "sub": 1,
        "email": TEST_USER["email"],
        "role": TEST_USER["role"],
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(
        token_data, auth_handler.jwt_secret, algorithm=auth_handler.jwt_algorithm
    )

    # Try verifying
    response = client.get(
        "/auth/verify", headers={"Authorization": "Bearer {0}".format(expired_token)}
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_role_based_access(client, test_db):
    """Test role-based access control."""
    # Register admin and regular user
    client.post("/auth/register", json=TEST_ADMIN)
    client.post("/auth/register", json=TEST_USER)

    # Login as admin
    admin_response = client.post(
        "/auth/login",
        json={"email": TEST_ADMIN["email"], "password": TEST_ADMIN["password"]},
    )
    admin_token = admin_response.json()["access_token"]

    # Login as regular user
    user_response = client.post(
        "/auth/login",
        json={"email": TEST_USER["email"], "password": TEST_USER["password"]},
    )
    user_token = user_response.json()["access_token"]

    # Test admin-only endpoint
    admin_headers = {"Authorization": "Bearer {0}".format(admin_token)}
    user_headers = {"Authorization": "Bearer {0}".format(user_token)}

    # Admin should have access
    response = client.post("/api/users", headers=admin_headers, json={})
    assert response.status_code != 403

    # Regular user should be forbidden
    response = client.post("/api/users", headers=user_headers, json={})
    assert response.status_code == 403


def test_cors_configuration(client):
    """Test CORS configuration."""
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }

    response = client.options("/auth/login", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert "access-control-allow-methods" in response.headers
    assert "access-control-allow-headers" in response.headers
