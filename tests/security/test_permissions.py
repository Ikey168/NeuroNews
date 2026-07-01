"""
Test suite for the RBAC permission system in src/api/auth/permissions.py.

Tests the actual permission API shipped in this codebase:
- Permission enum values and namespaces
- ROLE_PERMISSIONS mapping (admin / editor / user)
- has_permission(role, permission)
- get_user_permissions(role)
- PermissionChecker helper class
- require_permissions decorator enforcement
"""

import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException, Request

from src.api.auth.permissions import (
    Permission,
    ROLE_PERMISSIONS,
    PermissionChecker,
    has_permission,
    require_permissions,
    get_user_permissions,
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
        assert "editor" in ROLE_PERMISSIONS
        assert "user" in ROLE_PERMISSIONS

    def test_admin_permissions(self):
        """Test admin has all permissions."""
        admin_perms = ROLE_PERMISSIONS["admin"]
        all_permissions = set(Permission.__members__.values())

        assert admin_perms == all_permissions
        assert len(admin_perms) == len(Permission.__members__)

    def test_editor_permissions(self):
        """Test editor user permissions."""
        editor_perms = ROLE_PERMISSIONS["editor"]

        # Editor should have content read/write and view permissions
        assert Permission.READ_ARTICLES in editor_perms
        assert Permission.CREATE_ARTICLES in editor_perms
        assert Permission.READ_USERS in editor_perms
        assert Permission.VIEW_METRICS in editor_perms
        assert Permission.VIEW_NLP_RESULTS in editor_perms
        assert Permission.READ_GRAPH in editor_perms

        # Editor should have NLP job execution
        assert Permission.RUN_NLP_JOBS in editor_perms

        # Editor should NOT have admin-level user management
        assert Permission.DELETE_USERS not in editor_perms
        assert Permission.MANAGE_SYSTEM not in editor_perms
        assert Permission.CREATE_USERS not in editor_perms

    def test_user_permissions(self):
        """Test basic user permissions."""
        user_perms = ROLE_PERMISSIONS["user"]

        # User should have basic read permissions
        assert Permission.READ_ARTICLES in user_perms
        assert Permission.VIEW_NLP_RESULTS in user_perms
        assert Permission.READ_GRAPH in user_perms

        # User should NOT have write/admin permissions
        assert Permission.CREATE_ARTICLES not in user_perms
        assert Permission.UPDATE_ARTICLES not in user_perms
        assert Permission.DELETE_ARTICLES not in user_perms
        assert Permission.MANAGE_SYSTEM not in user_perms
        assert Permission.RUN_NLP_JOBS not in user_perms

    def test_role_hierarchy(self):
        """Test role permission hierarchy."""
        admin_perms = ROLE_PERMISSIONS["admin"]
        editor_perms = ROLE_PERMISSIONS["editor"]
        user_perms = ROLE_PERMISSIONS["user"]

        # Admin should have more permissions than editor
        assert len(admin_perms) > len(editor_perms)

        # Editor should have more permissions than user
        assert len(editor_perms) > len(user_perms)

        # User permissions should be subset of editor
        assert user_perms.issubset(editor_perms)

        # Editor permissions should be subset of admin
        assert editor_perms.issubset(admin_perms)

    def test_permission_inheritance(self):
        """Test that higher roles include lower role permissions."""
        user_perms = ROLE_PERMISSIONS["user"]
        editor_perms = ROLE_PERMISSIONS["editor"]
        admin_perms = ROLE_PERMISSIONS["admin"]

        # Every user permission should be in editor
        for perm in user_perms:
            assert perm in editor_perms, f"Editor missing user permission: {perm}"

        # Every editor permission should be in admin
        for perm in editor_perms:
            assert perm in admin_perms, f"Admin missing editor permission: {perm}"


class TestHasPermission:
    """Test the has_permission(role, permission) function."""

    def test_has_permission_valid(self):
        """Test checking valid role permissions."""
        assert has_permission("admin", Permission.MANAGE_SYSTEM) is True
        assert has_permission("editor", Permission.READ_ARTICLES) is True
        assert has_permission("user", Permission.READ_ARTICLES) is True

    def test_has_permission_invalid(self):
        """Test checking permissions the role lacks."""
        assert has_permission("user", Permission.MANAGE_SYSTEM) is False
        assert has_permission("editor", Permission.DELETE_USERS) is False
        assert has_permission("user", Permission.CREATE_ARTICLES) is False

    def test_has_permission_unknown_role(self):
        """Test checking permissions for an unknown role."""
        assert has_permission("unknown", Permission.READ_ARTICLES) is False
        assert has_permission("", Permission.READ_ARTICLES) is False

    def test_has_permission_case_sensitivity(self):
        """Role names must be matched case-sensitively."""
        assert has_permission("ADMIN", Permission.MANAGE_SYSTEM) is False
        assert has_permission("Admin", Permission.MANAGE_SYSTEM) is False
        assert has_permission("admin", Permission.MANAGE_SYSTEM) is True


class TestGetUserPermissions:
    """Test the get_user_permissions(role) function."""

    def test_get_user_permissions_by_role(self):
        """Test getting permission sets for each role."""
        admin_perms = get_user_permissions("admin")
        editor_perms = get_user_permissions("editor")
        user_perms = get_user_permissions("user")

        assert isinstance(admin_perms, set)
        assert isinstance(editor_perms, set)
        assert isinstance(user_perms, set)

        assert len(admin_perms) > len(editor_perms) > len(user_perms)

        # Verify specific permissions
        assert Permission.MANAGE_SYSTEM in admin_perms
        assert Permission.MANAGE_SYSTEM not in editor_perms
        assert Permission.READ_ARTICLES in user_perms

    def test_get_user_permissions_unknown_role(self):
        """Test getting permissions for an unknown role."""
        assert get_user_permissions("unknown") == set()
        assert get_user_permissions("") == set()


class TestPermissionChecker:
    """Test the PermissionChecker helper class."""

    def test_can_valid(self):
        """Test .can() returns True for granted permissions."""
        admin = PermissionChecker("admin")
        editor = PermissionChecker("editor")
        user = PermissionChecker("user")

        assert admin.can(Permission.MANAGE_SYSTEM) is True
        assert editor.can(Permission.READ_ARTICLES) is True
        assert user.can(Permission.READ_ARTICLES) is True

    def test_can_invalid(self):
        """Test .can() returns False for denied permissions."""
        editor = PermissionChecker("editor")
        user = PermissionChecker("user")

        assert editor.can(Permission.MANAGE_SYSTEM) is False
        assert user.can(Permission.CREATE_ARTICLES) is False

    def test_can_unknown_role(self):
        """Test .can() denies everything for an unknown role."""
        checker = PermissionChecker("unknown")
        for perm in Permission:
            assert checker.can(perm) is False

    def test_require_allows_granted(self):
        """Test .require() does not raise when permission is present."""
        admin = PermissionChecker("admin")
        # Should not raise
        admin.require(Permission.MANAGE_SYSTEM, Permission.READ_ARTICLES)

    def test_require_raises_on_missing(self):
        """Test .require() raises HTTPException(403) for missing permission."""
        user = PermissionChecker("user")
        with pytest.raises(HTTPException) as exc_info:
            user.require(Permission.MANAGE_SYSTEM)
        assert exc_info.value.status_code == 403

    def test_checker_permissions_snapshot(self):
        """Test that the checker exposes the role's full permission set."""
        admin = PermissionChecker("admin")
        assert admin.permissions == set(Permission.__members__.values())


class TestRequirePermissionsDecorator:
    """Test the require_permissions endpoint decorator."""

    @pytest.mark.asyncio
    async def test_decorator_allows_authorized_user(self):
        """Authorized user in request.state passes and endpoint executes."""

        @require_permissions(Permission.READ_ARTICLES)
        async def protected(request: Request):
            return {"message": "success"}

        request = MagicMock(spec=Request)
        request.state.user = {"role": "user"}

        result = await protected(request)
        assert result == {"message": "success"}

    @pytest.mark.asyncio
    async def test_decorator_denies_insufficient_permissions(self):
        """User lacking the required permission gets a 403."""

        @require_permissions(Permission.MANAGE_SYSTEM)
        async def admin_only(request: Request):
            return {"message": "admin"}

        request = MagicMock(spec=Request)
        request.state.user = {"role": "user"}

        with pytest.raises(HTTPException) as exc_info:
            await admin_only(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_decorator_requires_authentication(self):
        """Missing user on request.state raises a 401."""

        @require_permissions(Permission.READ_ARTICLES)
        async def protected(request: Request):
            return {"message": "success"}

        request = MagicMock(spec=Request)
        request.state.user = None

        with pytest.raises(HTTPException) as exc_info:
            await protected(request)
        assert exc_info.value.status_code == 401


class TestPermissionSecurity:
    """Test permission security and edge cases."""

    def test_privilege_escalation_protection(self):
        """A basic user must not obtain admin-only permissions."""
        admin_only_permissions = [
            Permission.MANAGE_SYSTEM,
            Permission.DELETE_USERS,
            Permission.CREATE_USERS,
            Permission.VIEW_LOGS,
        ]

        for perm in admin_only_permissions:
            assert has_permission("user", perm) is False

    def test_injection_role_names_denied(self):
        """Malicious role strings must never grant permissions."""
        malicious_roles = [
            "admin'; DROP TABLE users; --",
            "admin OR 1=1",
            "admin UNION SELECT * FROM passwords",
            "<script>alert('xss')</script>",
            "admin\x00",
        ]
        for role in malicious_roles:
            assert has_permission(role, Permission.READ_ARTICLES) is False
            assert has_permission(role, Permission.MANAGE_SYSTEM) is False

    def test_unicode_role_handling(self):
        """Unicode look-alike role names must not match real roles."""
        unicode_roles = [
            "admin™",
            "admïn",
            "admin​",  # zero-width space
            "admin ",  # non-breaking space
        ]
        for role in unicode_roles:
            assert has_permission(role, Permission.READ_ARTICLES) is False

    def test_permission_enumeration_matches_mapping(self):
        """The set of permissions a user role grants must equal its mapping."""
        allowed = [
            perm for perm in Permission.__members__.values()
            if has_permission("user", perm)
        ]
        assert set(allowed) == ROLE_PERMISSIONS["user"]

    def test_permission_checks_are_stable(self):
        """Repeated checks return consistent results (no hidden state)."""
        results = [has_permission("admin", Permission.MANAGE_SYSTEM) for _ in range(5)]
        assert results == [True, True, True, True, True]
        results_free = [has_permission("user", Permission.MANAGE_SYSTEM) for _ in range(5)]
        assert results_free == [False, False, False, False, False]

    def test_concurrent_permission_checks(self):
        """Permission checks must be thread-safe and consistent."""
        import concurrent.futures

        def check():
            return [
                has_permission("admin", Permission.MANAGE_SYSTEM),
                has_permission("user", Permission.READ_ARTICLES),
                has_permission("user", Permission.MANAGE_SYSTEM),
            ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check) for _ in range(50)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for result in results:
            assert result == [True, True, False]
