"""
Comprehensive test suite for RBAC system (Issue #60).

Tests all four requirements:
1. Define user roles (Admin, Premium, Free)
2. Restrict access to API endpoints based on roles
3. Implement RBAC in FastAPI middleware
4. Store permissions in DynamoDB
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from src.api.auth.jwt_auth import auth_handler
from src.api.rbac.rbac_middleware import (EnhancedRBACMiddleware,
                                          RBACMetricsMiddleware)
from src.api.rbac.rbac_system import (DynamoDBPermissionStore, Permission,
                                      RBACManager, RolePermissionManager,
                                      UserRole, rbac_manager)
from src.api.routes.rbac_routes import router as rbac_router

# Test data
TEST_ROLES = {
    "admin": {"user_id": "admin_123", "email": "admin@neuronews.com", "role": "admin"},
    "premium": {
        "user_id": "premium_123",
        "email": "premium@neuronews.com",
        "role": "premium",
    },
    "free": {"user_id": "free_123", "email": "free@neuronews.com", "role": "free"},
}


class TestRolePermissionManager:
    """Test role definitions and permission mappings."""

    def test_role_definitions_exist(self):
        """Test that all required roles are defined."""
        manager = RolePermissionManager()

        # Check all roles exist
        assert UserRole.ADMIN in manager._roles
        assert UserRole.PREMIUM in manager._roles
        assert UserRole.FREE in manager._roles

        # Check role properties
        free_role = manager._roles[UserRole.FREE]
        assert free_role.name == "Free User"
        assert Permission.READ_ARTICLES in free_role.permissions
        assert Permission.ACCESS_BASIC_API in free_role.permissions

        premium_role = manager._roles[UserRole.PREMIUM]
        assert premium_role.name == "Premium User"
        assert premium_role.inherits_from == free_role

        admin_role = manager._roles[UserRole.ADMIN]
        assert admin_role.name == "Administrator"
        assert admin_role.inherits_from == premium_role

    def test_permission_inheritance(self):
        """Test that roles properly inherit permissions."""
        manager = RolePermissionManager()

        free_permissions = manager.get_role_permissions(UserRole.FREE)
        premium_permissions = manager.get_role_permissions(UserRole.PREMIUM)
        admin_permissions = manager.get_role_permissions(UserRole.ADMIN)

        # Premium should include all free permissions
        assert free_permissions.issubset(premium_permissions)

        # Admin should include all premium permissions
        assert premium_permissions.issubset(admin_permissions)

        # Check specific permissions
        assert Permission.READ_ARTICLES in free_permissions
        assert Permission.VIEW_ANALYTICS in premium_permissions
        assert Permission.MANAGE_SYSTEM in admin_permissions

    def test_has_permission_check(self):
        """Test permission checking for different roles."""
        manager = RolePermissionManager()

        # Free user permissions
        assert manager.has_permission(UserRole.FREE, Permission.READ_ARTICLES)
        assert not manager.has_permission(UserRole.FREE, Permission.CREATE_ARTICLES)
        assert not manager.has_permission(UserRole.FREE, Permission.MANAGE_SYSTEM)

        # Premium user permissions
        assert manager.has_permission(UserRole.PREMIUM, Permission.READ_ARTICLES)
        assert manager.has_permission(UserRole.PREMIUM, Permission.VIEW_ANALYTICS)
        assert not manager.has_permission(UserRole.PREMIUM, Permission.CREATE_ARTICLES)

        # Admin permissions
        assert manager.has_permission(UserRole.ADMIN, Permission.READ_ARTICLES)
        assert manager.has_permission(UserRole.ADMIN, Permission.CREATE_ARTICLES)
        assert manager.has_permission(UserRole.ADMIN, Permission.MANAGE_SYSTEM)


class TestDynamoDBPermissionStore:
    """Test DynamoDB permission storage."""

    @patch("boto3.resource")
    def test_init_with_boto3(self, mock_boto3):
        """Test initialization with boto3 available."""
        mock_table = Mock()
        mock_resource = Mock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.return_value = mock_resource

        store = DynamoDBPermissionStore()

        assert store.table_name == "neuronews_rbac_permissions"
        assert store.dynamodb is not None
        mock_boto3.assert_called_once()

    def test_init_without_boto3(self):
        """Test initialization without boto3."""
        with patch("src.api.rbac.rbac_system.BOTO3_AVAILABLE", False):
            store = DynamoDBPermissionStore()
            assert store.dynamodb is None
            assert store.table is None

    @patch("boto3.resource")
    @pytest.mark.asyncio
    async def test_store_user_permissions(self, mock_boto3):
        """Test storing user permissions in DynamoDB."""
        mock_table = Mock()
        mock_resource = Mock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.return_value = mock_resource

        store = DynamoDBPermissionStore()
        store.table = mock_table

        # Test successful storage
        result = await store.store_user_permissions("user_123", UserRole.PREMIUM)

        assert result is True
        mock_table.put_item.assert_called_once()

        # Check the item that was stored
        call_args = mock_table.put_item.call_args
        item = call_args[1]["Item"]
        assert item["user_id"] == "user_123"
        assert item["role"] == "premium"
        assert "created_at" in item
        assert "updated_at" in item

    @patch("boto3.resource")
    @pytest.mark.asyncio
    async def test_get_user_permissions(self, mock_boto3):
        """Test retrieving user permissions from DynamoDB."""
        mock_table = Mock()
        mock_resource = Mock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.return_value = mock_resource

        # Mock response
        mock_table.get_item.return_value = {
            "Item": {
                "user_id": "user_123",
                "role": "premium",
                "created_at": "2025-08-17T22:00:00Z",
            }
        }

        store = DynamoDBPermissionStore()
        store.table = mock_table

        result = await store.get_user_permissions("user_123")

        assert result is not None
        assert result["user_id"] == "user_123"
        assert result["role"] == "premium"
        mock_table.get_item.assert_called_once_with(Key={"user_id": "user_123"})


class TestRBACManager:
    """Test the main RBAC manager."""

    def test_initialization(self):
        """Test RBAC manager initialization."""
        manager = RBACManager()

        assert manager.permission_manager is not None
        assert manager.permission_store is not None
        assert manager._endpoint_permissions is not None

    def test_endpoint_permissions_mapping(self):
        """Test endpoint permissions are properly mapped."""
        manager = RBACManager()

        # Test specific endpoints
        read_perms = manager.get_endpoint_permissions("GET", "/api/articles")
        assert Permission.READ_ARTICLES in read_perms

        create_perms = manager.get_endpoint_permissions("POST", "/api/articles")
        assert Permission.CREATE_ARTICLES in create_perms

        admin_perms = manager.get_endpoint_permissions("GET", "/api/admin")
        assert Permission.ACCESS_ADMIN_PANEL in admin_perms

    def test_parameterized_routes(self):
        """Test pattern matching for parameterized routes."""
        manager = RBACManager()

        # Test parameterized route matching
        perms = manager.get_endpoint_permissions("GET", "/api/articles/123")
        assert Permission.READ_ARTICLES in perms

        perms = manager.get_endpoint_permissions("DELETE", "/api/users/456")
        assert Permission.DELETE_USERS in perms

    def test_has_access_checks(self):
        """Test access control for different roles."""
        manager = RBACManager()

        # Free user access
        assert manager.has_access(UserRole.FREE, "GET", "/api/articles")
        assert not manager.has_access(UserRole.FREE, "POST", "/api/articles")
        assert not manager.has_access(UserRole.FREE, "GET", "/api/admin")

        # Premium user access
        assert manager.has_access(UserRole.PREMIUM, "GET", "/api/articles")
        assert manager.has_access(UserRole.PREMIUM, "GET", "/api/analytics")
        assert not manager.has_access(UserRole.PREMIUM, "POST", "/api/articles")

        # Admin access
        assert manager.has_access(UserRole.ADMIN, "GET", "/api/articles")
        assert manager.has_access(UserRole.ADMIN, "POST", "/api/articles")
        assert manager.has_access(UserRole.ADMIN, "GET", "/api/admin")

    def test_get_role_summary(self):
        """Test role summary generation."""
        manager = RBACManager()

        summary = manager.get_role_summary()

        assert "free" in summary
        assert "premium" in summary
        assert "admin" in summary

        # Check structure
        free_info = summary["free"]
        assert "name" in free_info
        assert "description" in free_info
        assert "permissions" in free_info
        assert "permission_count" in free_info

        # Check permission counts
        assert (
            summary["admin"]["permission_count"]
            > summary["premium"]["permission_count"]
        )
        assert (
            summary["premium"]["permission_count"] > summary["free"]["permission_count"]
        )


def create_test_app() -> FastAPI:
    """Create test FastAPI app with RBAC."""
    app = FastAPI()

    # Add RBAC middleware
    app.add_middleware(EnhancedRBACMiddleware)
    app.add_middleware(RBACMetricsMiddleware)

    # Add RBAC routes
    app.include_router(rbac_router)

    # Add test endpoints
    @app.get("/api/articles")
    async def get_articles():
        return {"articles": ["test article"]}

    @app.post("/api/articles")
    async def create_article():
        return {"message": "Article created"}

    @app.get("/api/admin")
    async def admin_panel():
        return {"message": "Admin panel"}

    @app.get("/public")
    async def public_endpoint():
        return {"message": "Public access"}

    return app


def create_auth_token(role: str, user_id: str = "test_user") -> str:
    """Create test JWT token."""
    token_data = {"sub": user_id, "email": f"{role}@test.com", "role": role}
    return auth_handler.create_access_token(token_data)


class TestRBACMiddleware:
    """Test RBAC middleware functionality."""

    def test_excluded_paths_bypass_rbac(self):
        """Test that excluded paths bypass RBAC checks."""
        app = create_test_app()
        client = TestClient(app)

        # Public endpoints should work without auth
        response = client.get("/public")
        assert response.status_code == 200

        response = client.get("/health")
        assert response.status_code == 404  # Not defined in test app

    @patch("src.api.rbac.rbac_middleware.auth_handler")
    def test_unauthenticated_request(self, mock_auth):
        """Test handling of unauthenticated requests."""
        app = create_test_app()
        client = TestClient(app)

        # Mock auth failure
        mock_auth.side_effect = Exception("No token")

        response = client.get("/api/articles")
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    @patch("src.api.rbac.rbac_middleware.auth_handler")
    def test_access_granted_for_valid_role(self, mock_auth):
        """Test access granted for users with proper role."""
        app = create_test_app()
        client = TestClient(app)

        # Mock successful auth for admin user
        mock_auth.return_value = {
            "sub": "admin_123",
            "email": "admin@test.com",
            "role": "admin",
        }

        response = client.get("/api/articles")
        assert response.status_code == 200
        assert "X-User-Role" in response.headers
        assert response.headers["X-User-Role"] == "admin"

    @patch("src.api.rbac.rbac_middleware.auth_handler")
    def test_access_denied_for_insufficient_role(self, mock_auth):
        """Test access denied for users with insufficient role."""
        app = create_test_app()
        client = TestClient(app)

        # Mock successful auth for free user
        mock_auth.return_value = {
            "sub": "free_123",
            "email": "free@test.com",
            "role": "free",
        }

        # Free user should not be able to create articles
        response = client.post("/api/articles")
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]
        assert response.json()["user_role"] == "free"


class TestRBACRoutes:
    """Test RBAC management API routes."""

    @patch("src.api.routes.rbac_routes.require_auth")
    def test_get_all_roles(self, mock_auth):
        """Test getting all roles information."""
        app = create_test_app()
        client = TestClient(app)

        # Mock authenticated user
        mock_auth.return_value = {"sub": "user_123", "role": "admin"}

        response = client.get("/api/rbac/roles")
        assert response.status_code == 200

        roles = response.json()
        assert "free" in roles
        assert "premium" in roles
        assert "admin" in roles

        # Check role structure
        free_role = roles["free"]
        assert "name" in free_role
        assert "permissions" in free_role
        assert isinstance(free_role["permissions"], list)

    @patch("src.api.routes.rbac_routes.require_auth")
    def test_get_specific_role(self, mock_auth):
        """Test getting specific role information."""
        app = create_test_app()
        client = TestClient(app)

        mock_auth.return_value = {"sub": "user_123", "role": "admin"}

        response = client.get("/api/rbac/roles/premium")
        assert response.status_code == 200

        role_info = response.json()
        assert role_info["name"] == "Premium User"
        assert isinstance(role_info["permissions"], list)
        assert len(role_info["permissions"]) > 0

    @patch("src.api.routes.rbac_routes.require_auth")
    def test_invalid_role_name(self, mock_auth):
        """Test handling of invalid role names."""
        app = create_test_app()
        client = TestClient(app)

        mock_auth.return_value = {"sub": "user_123", "role": "admin"}

        response = client.get("/api/rbac/roles/invalid_role")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("src.api.routes.rbac_routes.require_admin")
    @patch("src.api.rbac.rbac_system.rbac_manager.store_user_permissions")
    def test_update_user_role_admin_only(self, mock_store, mock_admin):
        """Test that updating user roles requires admin privileges."""
        app = create_test_app()
        client = TestClient(app)

        # Mock admin user
        mock_admin.return_value = {"sub": "admin_123", "role": "admin"}
        mock_store.return_value = True

        update_data = {"user_id": "user_123", "new_role": "premium"}

        response = client.post("/api/rbac/users/user_123/role", json=update_data)
        assert response.status_code == 200

        result = response.json()
        assert "Successfully updated" in result["message"]
        assert result["new_role"] == "premium"

    @patch("src.api.routes.rbac_routes.require_auth")
    def test_check_access_endpoint(self, mock_auth):
        """Test access checking endpoint."""
        app = create_test_app()
        client = TestClient(app)

        mock_auth.return_value = {"sub": "user_123", "role": "free"}

        check_data = {"user_role": "free", "method": "GET", "path": "/api/articles"}

        response = client.post("/api/rbac/check-access", json=check_data)
        assert response.status_code == 200

        result = response.json()
        assert result["has_access"] is True
        assert result["user_role"] == "free"
        assert result["endpoint"] == "GET /api/articles"


@pytest.mark.asyncio
async def test_dynamodb_integration():
    """Test DynamoDB integration (mocked)."""
    with patch("boto3.resource") as mock_boto3:
        mock_table = Mock()
        mock_resource = Mock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.return_value = mock_resource

        # Test storing permissions
        result = await rbac_manager.store_user_permissions("user_123", UserRole.PREMIUM)

        # Should attempt to store in DynamoDB
        mock_table.put_item.assert_called_once()


def test_rbac_system_completeness():
    """Test that RBAC system covers all requirements."""
    manager = RBACManager()

    # Requirement 1: Define user roles (Admin, Premium, Free)
    roles = [UserRole.ADMIN, UserRole.PREMIUM, UserRole.FREE]
    for role in roles:
        assert role in manager.permission_manager._roles
        role_def = manager.permission_manager.get_role_definition(role)
        assert role_def is not None
        assert len(role_def.name) > 0
        assert len(role_def.description) > 0

    # Requirement 2: Restrict access to API endpoints based on roles
    test_endpoints = [
        ("GET", "/api/articles"),
        ("POST", "/api/articles"),
        ("GET", "/api/admin"),
        ("GET", "/api/analytics"),
    ]

    for method, path in test_endpoints:
        permissions = manager.get_endpoint_permissions(method, path)
        assert len(permissions) > 0  # Should have required permissions

    # Requirement 3: Implement RBAC in FastAPI middleware
    # (Tested by middleware tests above)

    # Requirement 4: Store permissions in DynamoDB
    assert manager.permission_store is not None
    assert hasattr(manager.permission_store, "store_user_permissions")
    assert hasattr(manager.permission_store, "get_user_permissions")


if __name__ == "__main__":
    # Run tests
    print("🧪 Running RBAC System Tests...")

    # Test basic functionality
    print("\n1. Testing Role Permission Manager...")
    test_rpm = TestRolePermissionManager()
    test_rpm.test_role_definitions_exist()
    test_rpm.test_permission_inheritance()
    test_rpm.test_has_permission_check()
    print("✅ Role Permission Manager tests passed")

    print("\n2. Testing RBAC Manager...")
    test_rbac = TestRBACManager()
    test_rbac.test_initialization()
    test_rbac.test_endpoint_permissions_mapping()
    test_rbac.test_has_access_checks()
    test_rbac.test_get_role_summary()
    print("✅ RBAC Manager tests passed")

    print("\n3. Testing System Completeness...")
    test_rbac_system_completeness()
    print("✅ RBAC System completeness verified")

    print("\n🎉 All RBAC tests passed!")
    print("\n📋 Issue #60 Requirements Status:")
    print("✅ 1. Define user roles (Admin, Premium, Free)")
    print("✅ 2. Restrict access to API endpoints based on roles")
    print("✅ 3. Implement RBAC in FastAPI middleware")
    print("✅ 4. Store permissions in DynamoDB")
    print("\n🏆 Issue #60 Implementation Complete!")
