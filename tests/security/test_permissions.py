"""
Comprehensive test suite for Permission Management System - Issue #476.

Tests all permission and RBAC requirements:
- Role hierarchy and inheritance validation
- Permission checking for various user roles
- Access control enforcement at endpoint level
- Administrative permission escalation testing
- Role-permission mapping and validation
- Security boundary testing
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, Request

from src.api.auth.permissions import (
    Permission,
    ROLE_PERMISSIONS,
    PermissionManager,
    has_permission,
    require_permission,
    get_user_permissions
)


class TestPermissionEnum:
    """Test Permission enumeration and constants."""

    def test_permission_values(self):
        """Test that all permissions have correct string values."""
        assert Permission.READ_ARTICLES == "read:articles"
        assert Permission.CREATE_ARTICLES == "create:articles"
        assert Permission.UPDATE_ARTICLES == "update:articles"
        assert Permission.DELETE_ARTICLES == "delete:articles"
        
        assert Permission.READ_USERS == "read:users"
        assert Permission.CREATE_USERS == "create:users"
        assert Permission.UPDATE_USERS == "update:users"
        assert Permission.DELETE_USERS == "delete:users"
        
        assert Permission.VIEW_METRICS == "view:metrics"
        assert Permission.MANAGE_SYSTEM == "manage:system"
        assert Permission.VIEW_LOGS == "view:logs"
        
        assert Permission.RUN_NLP_JOBS == "run:nlp_jobs"
        assert Permission.VIEW_NLP_RESULTS == "view:nlp_results"
        
        assert Permission.READ_GRAPH == "read:graph"
        assert Permission.WRITE_GRAPH == "write:graph"

    def test_permission_completeness(self):
        """Test that all defined permissions are included."""
        expected_permissions = {
            "read:articles", "create:articles", "update:articles", "delete:articles",
            "read:users", "create:users", "update:users", "delete:users",
            "view:metrics", "manage:system", "view:logs",
            "run:nlp_jobs", "view:nlp_results",
            "read:graph", "write:graph"
        }
        
        actual_permissions = set(Permission.__members__.values())
        assert actual_permissions == expected_permissions

    def test_permission_string_representation(self):
        """Test permission string representation."""
        for permission in Permission:
            assert isinstance(permission, str)
            assert ":" in permission  # Should follow namespace:action pattern

    def test_permission_namespaces(self):
        """Test permission namespace consistency."""
        namespaces = set()
        for permission in Permission:
            namespace = permission.split(":")[0]
            namespaces.add(namespace)
        
        expected_namespaces = {
            "read", "create", "update", "delete",
            "view", "manage", "run", "write"
        }
        assert namespaces == expected_namespaces


class TestRolePermissions:
    """Test role-permission mapping."""

    def test_role_permissions_structure(self):
        """Test role permissions mapping structure."""
        assert isinstance(ROLE_PERMISSIONS, dict)
        assert "admin" in ROLE_PERMISSIONS
        assert "premium" in ROLE_PERMISSIONS
        assert "free" in ROLE_PERMISSIONS

    def test_admin_permissions(self):
        """Test admin has all permissions."""
        admin_perms = ROLE_PERMISSIONS["admin"]
        all_permissions = set(Permission.__members__.values())
        
        assert admin_perms == all_permissions
        assert len(admin_perms) == len(Permission.__members__)

    def test_premium_permissions(self):
        """Test premium user permissions."""
        premium_perms = ROLE_PERMISSIONS["premium"]
        
        # Premium should have read/view permissions
        assert Permission.READ_ARTICLES in premium_perms
        assert Permission.READ_USERS in premium_perms
        assert Permission.VIEW_METRICS in premium_perms
        assert Permission.VIEW_NLP_RESULTS in premium_perms
        assert Permission.READ_GRAPH in premium_perms
        
        # Premium should have NLP job execution
        assert Permission.RUN_NLP_JOBS in premium_perms
        
        # Premium should NOT have admin-level permissions
        assert Permission.DELETE_USERS not in premium_perms
        assert Permission.MANAGE_SYSTEM not in premium_perms
        assert Permission.CREATE_USERS not in premium_perms

    def test_free_permissions(self):
        """Test free user permissions."""
        free_perms = ROLE_PERMISSIONS["free"]
        
        # Free should have basic read permissions
        assert Permission.READ_ARTICLES in free_perms
        assert Permission.VIEW_NLP_RESULTS in free_perms
        assert Permission.READ_GRAPH in free_perms
        
        # Free should NOT have write/admin permissions
        assert Permission.CREATE_ARTICLES not in free_perms
        assert Permission.UPDATE_ARTICLES not in free_perms
        assert Permission.DELETE_ARTICLES not in free_perms
        assert Permission.MANAGE_SYSTEM not in free_perms
        assert Permission.RUN_NLP_JOBS not in free_perms

    def test_role_hierarchy(self):
        """Test role permission hierarchy."""
        admin_perms = ROLE_PERMISSIONS["admin"]
        premium_perms = ROLE_PERMISSIONS["premium"] 
        free_perms = ROLE_PERMISSIONS["free"]
        
        # Admin should have more permissions than premium
        assert len(admin_perms) > len(premium_perms)
        
        # Premium should have more permissions than free
        assert len(premium_perms) > len(free_perms)
        
        # Free permissions should be subset of premium
        assert free_perms.issubset(premium_perms)
        
        # Premium permissions should be subset of admin
        assert premium_perms.issubset(admin_perms)

    def test_permission_inheritance(self):
        """Test that higher roles inherit lower role permissions."""
        free_perms = ROLE_PERMISSIONS["free"]
        premium_perms = ROLE_PERMISSIONS["premium"]
        admin_perms = ROLE_PERMISSIONS["admin"]
        
        # Every free permission should be in premium
        for perm in free_perms:
            assert perm in premium_perms, f"Premium missing free permission: {perm}"
        
        # Every premium permission should be in admin
        for perm in premium_perms:
            assert perm in admin_perms, f"Admin missing premium permission: {perm}"


class TestPermissionManager:
    """Test PermissionManager class."""

    @pytest.fixture
    def permission_manager(self):
        """Create PermissionManager instance."""
        return PermissionManager()

    def test_has_role_permission_valid(self, permission_manager):
        """Test checking valid role permissions."""
        assert permission_manager.has_role_permission("admin", Permission.MANAGE_SYSTEM) is True
        assert permission_manager.has_role_permission("premium", Permission.READ_ARTICLES) is True
        assert permission_manager.has_role_permission("free", Permission.READ_ARTICLES) is True

    def test_has_role_permission_invalid(self, permission_manager):
        """Test checking invalid role permissions."""
        assert permission_manager.has_role_permission("free", Permission.MANAGE_SYSTEM) is False
        assert permission_manager.has_role_permission("premium", Permission.DELETE_USERS) is False
        assert permission_manager.has_role_permission("free", Permission.CREATE_ARTICLES) is False

    def test_has_role_permission_unknown_role(self, permission_manager):
        """Test checking permissions for unknown role."""
        assert permission_manager.has_role_permission("unknown", Permission.READ_ARTICLES) is False
        assert permission_manager.has_role_permission("", Permission.READ_ARTICLES) is False
        assert permission_manager.has_role_permission(None, Permission.READ_ARTICLES) is False

    def test_get_role_permissions(self, permission_manager):
        """Test getting all permissions for a role."""
        admin_perms = permission_manager.get_role_permissions("admin")
        premium_perms = permission_manager.get_role_permissions("premium")
        free_perms = permission_manager.get_role_permissions("free")
        
        assert isinstance(admin_perms, set)
        assert isinstance(premium_perms, set)
        assert isinstance(free_perms, set)
        
        assert len(admin_perms) > len(premium_perms) > len(free_perms)

    def test_get_role_permissions_unknown_role(self, permission_manager):
        """Test getting permissions for unknown role."""
        unknown_perms = permission_manager.get_role_permissions("unknown")
        assert unknown_perms == set()
        
        none_perms = permission_manager.get_role_permissions(None)
        assert none_perms == set()

    def test_check_user_permission_valid(self, permission_manager):
        """Test checking user permission with valid user."""
        user_admin = {"role": "admin", "user_id": "123"}
        user_premium = {"role": "premium", "user_id": "456"}
        user_free = {"role": "free", "user_id": "789"}
        
        assert permission_manager.check_user_permission(user_admin, Permission.MANAGE_SYSTEM) is True
        assert permission_manager.check_user_permission(user_premium, Permission.READ_ARTICLES) is True
        assert permission_manager.check_user_permission(user_free, Permission.READ_ARTICLES) is True

    def test_check_user_permission_invalid(self, permission_manager):
        """Test checking user permission with insufficient privileges."""
        user_premium = {"role": "premium", "user_id": "456"}
        user_free = {"role": "free", "user_id": "789"}
        
        assert permission_manager.check_user_permission(user_premium, Permission.MANAGE_SYSTEM) is False
        assert permission_manager.check_user_permission(user_free, Permission.CREATE_ARTICLES) is False

    def test_check_user_permission_missing_role(self, permission_manager):
        """Test checking permission for user without role."""
        user_no_role = {"user_id": "123"}
        user_empty_role = {"role": "", "user_id": "456"}
        user_none_role = {"role": None, "user_id": "789"}
        
        assert permission_manager.check_user_permission(user_no_role, Permission.READ_ARTICLES) is False
        assert permission_manager.check_user_permission(user_empty_role, Permission.READ_ARTICLES) is False
        assert permission_manager.check_user_permission(user_none_role, Permission.READ_ARTICLES) is False

    def test_check_user_permission_none_user(self, permission_manager):
        """Test checking permission for None user."""
        assert permission_manager.check_user_permission(None, Permission.READ_ARTICLES) is False

    def test_validate_permission_assignment(self, permission_manager):
        """Test permission assignment validation."""
        # Valid assignments
        assert permission_manager.validate_permission_assignment("admin", [Permission.MANAGE_SYSTEM]) is True
        assert permission_manager.validate_permission_assignment("premium", [Permission.READ_ARTICLES]) is True
        
        # Invalid assignments
        assert permission_manager.validate_permission_assignment("free", [Permission.MANAGE_SYSTEM]) is False
        assert permission_manager.validate_permission_assignment("premium", [Permission.DELETE_USERS]) is False

    def test_get_all_roles(self, permission_manager):
        """Test getting all available roles."""
        roles = permission_manager.get_all_roles()
        assert isinstance(roles, list)
        assert "admin" in roles
        assert "premium" in roles
        assert "free" in roles
        assert len(roles) == 3

    def test_get_all_permissions(self, permission_manager):
        """Test getting all available permissions."""
        permissions = permission_manager.get_all_permissions()
        assert isinstance(permissions, list)
        assert len(permissions) == len(Permission.__members__)
        
        for perm in Permission:
            assert perm in permissions


class TestPermissionDecorators:
    """Test permission decorator functions."""

    def test_has_permission_function(self):
        """Test has_permission helper function."""
        user_admin = {"role": "admin"}
        user_free = {"role": "free"}
        
        assert has_permission(user_admin, Permission.MANAGE_SYSTEM) is True
        assert has_permission(user_free, Permission.MANAGE_SYSTEM) is False
        assert has_permission(user_free, Permission.READ_ARTICLES) is True

    def test_has_permission_invalid_user(self):
        """Test has_permission with invalid user."""
        assert has_permission(None, Permission.READ_ARTICLES) is False
        assert has_permission({}, Permission.READ_ARTICLES) is False
        assert has_permission({"role": None}, Permission.READ_ARTICLES) is False

    def test_get_user_permissions_function(self):
        """Test get_user_permissions helper function."""
        user_admin = {"role": "admin"}
        user_premium = {"role": "premium"}
        user_free = {"role": "free"}
        
        admin_perms = get_user_permissions(user_admin)
        premium_perms = get_user_permissions(user_premium)
        free_perms = get_user_permissions(user_free)
        
        assert isinstance(admin_perms, set)
        assert len(admin_perms) > len(premium_perms) > len(free_perms)
        
        # Verify specific permissions
        assert Permission.MANAGE_SYSTEM in admin_perms
        assert Permission.MANAGE_SYSTEM not in premium_perms
        assert Permission.READ_ARTICLES in free_perms

    def test_get_user_permissions_invalid_user(self):
        """Test get_user_permissions with invalid user."""
        assert get_user_permissions(None) == set()
        assert get_user_permissions({}) == set()
        assert get_user_permissions({"role": "unknown"}) == set()

    def test_require_permission_decorator(self):
        """Test require_permission decorator."""
        @require_permission(Permission.READ_ARTICLES)
        async def protected_function(user: dict):
            return {"message": "success"}
        
        # Test with valid user
        user_valid = {"role": "free"}
        result = protected_function.__wrapped__(user_valid)
        assert result == {"message": "success"}

    def test_require_permission_decorator_insufficient(self):
        """Test require_permission decorator with insufficient permissions."""
        @require_permission(Permission.MANAGE_SYSTEM)
        async def admin_function(user: dict):
            return {"message": "admin_success"}
        
        # Test with insufficient permissions should raise exception
        user_free = {"role": "free"}
        
        with pytest.raises(HTTPException) as exc_info:
            admin_function.__wrapped__(user_free)
        
        assert exc_info.value.status_code == 403


class TestPermissionSecurity:
    """Test permission security and edge cases."""

    @pytest.fixture
    def permission_manager(self):
        return PermissionManager()

    def test_role_case_sensitivity(self, permission_manager):
        """Test role name case sensitivity."""
        # Should be case sensitive
        assert permission_manager.has_role_permission("ADMIN", Permission.MANAGE_SYSTEM) is False
        assert permission_manager.has_role_permission("Admin", Permission.MANAGE_SYSTEM) is False
        assert permission_manager.has_role_permission("admin", Permission.MANAGE_SYSTEM) is True

    def test_permission_case_sensitivity(self, permission_manager):
        """Test permission case sensitivity."""
        user_admin = {"role": "admin"}
        
        # Permissions should be exact string matches
        assert permission_manager.check_user_permission(user_admin, "MANAGE:SYSTEM") is False
        assert permission_manager.check_user_permission(user_admin, "manage:system") is False
        assert permission_manager.check_user_permission(user_admin, Permission.MANAGE_SYSTEM) is True

    def test_sql_injection_protection(self, permission_manager):
        """Test protection against SQL injection in role names."""
        malicious_roles = [
            "admin'; DROP TABLE users; --",
            "admin OR 1=1",
            "admin UNION SELECT * FROM passwords",
            "<script>alert('xss')</script>",
            "admin\x00"
        ]
        
        for role in malicious_roles:
            user = {"role": role}
            assert permission_manager.check_user_permission(user, Permission.READ_ARTICLES) is False

    def test_unicode_role_handling(self, permission_manager):
        """Test handling of Unicode characters in roles."""
        unicode_roles = [
            "admin™",
            "admïn",
            "adm𝓲n",
            "admin\u200b",  # Zero-width space
            "admin\u00a0"   # Non-breaking space
        ]
        
        for role in unicode_roles:
            user = {"role": role}
            assert permission_manager.check_user_permission(user, Permission.READ_ARTICLES) is False

    def test_privilege_escalation_protection(self, permission_manager):
        """Test protection against privilege escalation."""
        # Free user trying to access admin permissions
        user_free = {"role": "free"}
        
        admin_only_permissions = [
            Permission.MANAGE_SYSTEM,
            Permission.DELETE_USERS,
            Permission.CREATE_USERS,
            Permission.VIEW_LOGS
        ]
        
        for perm in admin_only_permissions:
            assert permission_manager.check_user_permission(user_free, perm) is False

    def test_role_modification_protection(self, permission_manager):
        """Test that role cannot be modified during permission check."""
        user = {"role": "free"}
        original_role = user["role"]
        
        # Check permission (should not modify user object)
        permission_manager.check_user_permission(user, Permission.READ_ARTICLES)
        
        assert user["role"] == original_role

    def test_permission_enumeration_protection(self, permission_manager):
        """Test protection against permission enumeration."""
        user_free = {"role": "free"}
        
        # Try to check all possible permissions
        all_perms = list(Permission.__members__.values())
        allowed_perms = []
        
        for perm in all_perms:
            if permission_manager.check_user_permission(user_free, perm):
                allowed_perms.append(perm)
        
        # Free user should only have specific permissions
        expected_free_perms = ROLE_PERMISSIONS["free"]
        assert set(allowed_perms) == expected_free_perms

    def test_concurrent_permission_checks(self, permission_manager):
        """Test thread safety of permission checks."""
        import concurrent.futures
        import threading
        
        user_admin = {"role": "admin"}
        user_free = {"role": "free"}
        
        def check_permissions():
            results = []
            results.append(permission_manager.check_user_permission(user_admin, Permission.MANAGE_SYSTEM))
            results.append(permission_manager.check_user_permission(user_free, Permission.READ_ARTICLES))
            results.append(permission_manager.check_user_permission(user_free, Permission.MANAGE_SYSTEM))
            return results
        
        # Run concurrent permission checks
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_permissions) for _ in range(50)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All results should be consistent
        for result in results:
            assert result == [True, True, False]  # admin can manage, free can read, free can't manage

    def test_permission_caching_behavior(self, permission_manager):
        """Test permission caching doesn't cause security issues."""
        user_admin = {"role": "admin"}
        
        # Multiple calls should return consistent results
        result1 = permission_manager.check_user_permission(user_admin, Permission.MANAGE_SYSTEM)
        result2 = permission_manager.check_user_permission(user_admin, Permission.MANAGE_SYSTEM)
        result3 = permission_manager.check_user_permission(user_admin, Permission.MANAGE_SYSTEM)
        
        assert result1 == result2 == result3 == True
        
        # Change user role and verify no caching issues
        user_admin["role"] = "free"
        result4 = permission_manager.check_user_permission(user_admin, Permission.MANAGE_SYSTEM)
        assert result4 is False


class TestPermissionIntegration:
    """Test permission system integration."""

    @pytest.fixture
    def permission_manager(self):
        return PermissionManager()

    def test_fastapi_request_integration(self, permission_manager):
        """Test integration with FastAPI request context."""
        mock_request = MagicMock(spec=Request)
        mock_request.state.current_user = {"role": "admin", "user_id": "123"}
        
        # Should be able to extract user from request
        user = getattr(mock_request.state, 'current_user', None)
        assert user is not None
        assert permission_manager.check_user_permission(user, Permission.MANAGE_SYSTEM) is True

    def test_middleware_integration(self, permission_manager):
        """Test integration with middleware patterns."""
        def simulate_middleware_permission_check(user_data, required_permission):
            try:
                has_perm = permission_manager.check_user_permission(user_data, required_permission)
                if not has_perm:
                    raise HTTPException(status_code=403, detail="Insufficient permissions")
                return True
            except Exception:
                return False
        
        # Test valid permission
        admin_user = {"role": "admin"}
        assert simulate_middleware_permission_check(admin_user, Permission.MANAGE_SYSTEM) is True
        
        # Test invalid permission
        free_user = {"role": "free"}
        assert simulate_middleware_permission_check(free_user, Permission.MANAGE_SYSTEM) is False

    def test_database_role_integration(self, permission_manager):
        """Test integration with database-stored roles."""
        # Simulate database user objects
        db_users = [
            {"id": 1, "email": "admin@test.com", "role": "admin", "active": True},
            {"id": 2, "email": "premium@test.com", "role": "premium", "active": True},
            {"id": 3, "email": "free@test.com", "role": "free", "active": True},
            {"id": 4, "email": "inactive@test.com", "role": "admin", "active": False}
        ]
        
        for db_user in db_users:
            if not db_user["active"]:
                continue  # Skip inactive users
                
            user_context = {"role": db_user["role"], "user_id": str(db_user["id"])}
            
            if db_user["role"] == "admin":
                assert permission_manager.check_user_permission(user_context, Permission.MANAGE_SYSTEM) is True
            elif db_user["role"] == "premium":
                assert permission_manager.check_user_permission(user_context, Permission.RUN_NLP_JOBS) is True
                assert permission_manager.check_user_permission(user_context, Permission.MANAGE_SYSTEM) is False
            elif db_user["role"] == "free":
                assert permission_manager.check_user_permission(user_context, Permission.READ_ARTICLES) is True
                assert permission_manager.check_user_permission(user_context, Permission.RUN_NLP_JOBS) is False