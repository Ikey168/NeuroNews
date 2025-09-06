"""
Enhanced comprehensive test suite for RBAC System Classes - Issue #476.

Tests all RBAC system requirements for authentication security testing:
- RBACSystem tests (role-based access control orchestration)
- Role tests (role definition and hierarchy management)
- Permission tests (permission definition and validation)
- Integration with authentication and authorization systems
- Performance and security under load
- Edge cases and security boundary testing
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.api.rbac.rbac_system import (
    DynamoDBPermissionStore,
    Permission,
    RBACManager,
    RoleDefinition,
    RolePermissionManager,
    UserRole,
    rbac_manager,
)


class TestEnhancedRBACSystemOrchestration:
    """Test RBAC system orchestration and coordination."""

    @pytest.fixture
    def rbac_orchestration_manager(self):
        """Create RBAC manager for orchestration testing."""
        with patch('src.api.rbac.rbac_system.DynamoDBPermissionStore') as mock_store_class:
            mock_store = MagicMock()
            mock_store_class.return_value = mock_store
            
            manager = RBACManager()
            manager.permission_store = mock_store
            return manager, mock_store

    @pytest.mark.asyncio
    async def test_end_to_end_role_assignment(self, rbac_orchestration_manager):
        """Test end-to-end role assignment orchestration."""
        manager, mock_store = rbac_orchestration_manager
        
        # Mock successful storage
        mock_store.store_user_permissions.return_value = True
        mock_store.get_user_permissions.return_value = {
            "user_id": "user123",
            "role": "premium",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Step 1: Assign role
        assignment_result = await manager.assign_role_to_user("user123", UserRole.PREMIUM)
        assert assignment_result is True
        
        # Step 2: Verify role assignment
        user_role = await manager.get_user_role("user123")
        assert user_role == UserRole.PREMIUM
        
        # Step 3: Verify permissions are properly orchestrated
        user_permissions = await manager.get_user_permissions("user123")
        expected_premium_perms = manager.role_manager.get_role_permissions(UserRole.PREMIUM)
        assert user_permissions == expected_premium_perms

    @pytest.mark.asyncio
    async def test_role_upgrade_orchestration(self, rbac_orchestration_manager):
        """Test role upgrade orchestration."""
        manager, mock_store = rbac_orchestration_manager
        
        # User starts as FREE
        mock_store.get_user_permissions.return_value = {
            "user_id": "user456",
            "role": "free",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        initial_perms = await manager.get_user_permissions("user456")
        free_perms = manager.role_manager.get_role_permissions(UserRole.FREE)
        assert initial_perms == free_perms
        
        # Upgrade to PREMIUM
        mock_store.update_user_role.return_value = True
        mock_store.get_user_permissions.return_value = {
            "user_id": "user456",
            "role": "premium",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        upgrade_result = await manager.update_user_role("user456", UserRole.PREMIUM)
        assert upgrade_result is True
        
        # Verify permission expansion
        upgraded_perms = await manager.get_user_permissions("user456")
        premium_perms = manager.role_manager.get_role_permissions(UserRole.PREMIUM)
        assert upgraded_perms == premium_perms
        assert len(upgraded_perms) > len(free_perms)

    @pytest.mark.asyncio
    async def test_bulk_permission_orchestration(self, rbac_orchestration_manager):
        """Test bulk permission operations orchestration."""
        manager, mock_store = rbac_orchestration_manager
        
        # Setup multiple users
        users = [f"user_{i}" for i in range(10)]
        roles = [UserRole.FREE, UserRole.PREMIUM, UserRole.ADMIN]
        
        # Mock bulk storage operations
        mock_store.bulk_assign_roles.return_value = True
        
        # Test bulk role assignment
        assignments = [(user, roles[i % 3]) for i, user in enumerate(users)]
        
        result = await manager.bulk_assign_roles(assignments)
        assert result is True
        
        # Verify orchestration called store correctly
        mock_store.bulk_assign_roles.assert_called_once_with(assignments)

    @pytest.mark.asyncio
    async def test_permission_cascade_orchestration(self, rbac_orchestration_manager):
        """Test permission cascade when role definitions change."""
        manager, mock_store = rbac_orchestration_manager
        
        # Mock getting all users with a specific role
        premium_users = [
            {"user_id": "premium1", "role": "premium"},
            {"user_id": "premium2", "role": "premium"},
            {"user_id": "premium3", "role": "premium"}
        ]
        mock_store.list_users_by_role.return_value = premium_users
        mock_store.bulk_update_permissions.return_value = True
        
        # Simulate permission cascade update
        result = await manager.cascade_permission_update(
            UserRole.PREMIUM,
            added_permissions=[Permission.IMPORT_DATA],
            removed_permissions=[]
        )
        
        assert result is True
        mock_store.bulk_update_permissions.assert_called_once()

    @pytest.mark.asyncio
    async def test_role_inheritance_orchestration(self, rbac_orchestration_manager):
        """Test role inheritance orchestration."""
        manager, mock_store = rbac_orchestration_manager
        
        # Test inheritance chain validation
        free_perms = manager.role_manager.get_role_permissions(UserRole.FREE)
        premium_perms = manager.role_manager.get_role_permissions(UserRole.PREMIUM)
        admin_perms = manager.role_manager.get_role_permissions(UserRole.ADMIN)
        
        # Orchestration should maintain inheritance
        assert free_perms.issubset(premium_perms), "Premium should inherit free permissions"
        assert premium_perms.issubset(admin_perms), "Admin should inherit premium permissions"
        
        # Test inheritance validation in permission checking
        mock_store.get_user_permissions.return_value = {"role": "admin"}
        
        # Admin should have all inherited permissions
        for perm in free_perms | premium_perms:
            has_perm = await manager.check_user_permission("admin_user", perm)
            assert has_perm is True, f"Admin missing inherited permission: {perm}"


class TestAdvancedRoleHierarchyManagement:
    """Test advanced role hierarchy and management features."""

    @pytest.fixture
    def role_hierarchy_manager(self):
        """Create role manager for hierarchy testing."""
        return RolePermissionManager()

    def test_role_hierarchy_depth_validation(self, role_hierarchy_manager):
        """Test role hierarchy depth and structure validation."""
        # Get role definitions
        free_def = role_hierarchy_manager.get_role_definition(UserRole.FREE)
        premium_def = role_hierarchy_manager.get_role_definition(UserRole.PREMIUM)
        admin_def = role_hierarchy_manager.get_role_definition(UserRole.ADMIN)
        
        # Validate hierarchy depth
        assert free_def.inherits_from is None  # Root level
        assert premium_def.inherits_from == free_def  # Level 1
        assert admin_def.inherits_from == premium_def  # Level 2
        
        # Validate hierarchy consistency
        assert len(admin_def.get_all_permissions()) > len(premium_def.get_all_permissions())
        assert len(premium_def.get_all_permissions()) > len(free_def.get_all_permissions())

    def test_role_permission_aggregation(self, role_hierarchy_manager):
        """Test permission aggregation across role hierarchy."""
        # Get individual role permissions
        free_only = role_hierarchy_manager.get_role_definition(UserRole.FREE).permissions
        premium_only = role_hierarchy_manager.get_role_definition(UserRole.PREMIUM).permissions
        admin_only = role_hierarchy_manager.get_role_definition(UserRole.ADMIN).permissions
        
        # Get aggregated permissions
        premium_all = role_hierarchy_manager.get_role_permissions(UserRole.PREMIUM)
        admin_all = role_hierarchy_manager.get_role_permissions(UserRole.ADMIN)
        
        # Verify aggregation correctness
        assert premium_all == free_only | premium_only
        assert admin_all == free_only | premium_only | admin_only

    def test_role_privilege_escalation_prevention(self, role_hierarchy_manager):
        """Test prevention of unintended privilege escalation."""
        # Free user should not have admin permissions
        free_perms = role_hierarchy_manager.get_role_permissions(UserRole.FREE)
        admin_only_perms = {
            Permission.MANAGE_SYSTEM,
            Permission.DELETE_USERS,
            Permission.ACCESS_ADMIN_PANEL,
            Permission.IMPORT_DATA
        }
        
        # No overlap should exist
        escalation_perms = free_perms & admin_only_perms
        assert len(escalation_perms) == 0, f"Free user has admin permissions: {escalation_perms}"
        
        # Premium user should not have admin-only permissions
        premium_perms = role_hierarchy_manager.get_role_permissions(UserRole.PREMIUM)
        admin_exclusive = admin_only_perms - premium_perms
        assert len(admin_exclusive) > 0, "Premium user has all admin permissions"

    def test_role_definition_immutability(self, role_hierarchy_manager):
        """Test that role definitions maintain consistency."""
        # Get role definitions multiple times
        free_def_1 = role_hierarchy_manager.get_role_definition(UserRole.FREE)
        free_def_2 = role_hierarchy_manager.get_role_definition(UserRole.FREE)
        
        # Should be consistent
        assert free_def_1.permissions == free_def_2.permissions
        assert free_def_1.name == free_def_2.name
        assert free_def_1.description == free_def_2.description

    def test_custom_role_hierarchy_support(self, role_hierarchy_manager):
        """Test support for custom role hierarchies."""
        # Create custom role definition
        custom_perms = {Permission.READ_ARTICLES, Permission.EXPORT_DATA}
        custom_role = RoleDefinition(
            name="Custom Role",
            description="Custom test role",
            permissions=custom_perms,
            inherits_from=role_hierarchy_manager.get_role_definition(UserRole.FREE)
        )
        
        # Should inherit from free + have custom permissions
        all_custom_perms = custom_role.get_all_permissions()
        free_perms = role_hierarchy_manager.get_role_permissions(UserRole.FREE)
        
        assert free_perms.issubset(all_custom_perms)
        assert custom_perms.issubset(all_custom_perms)


class TestAdvancedPermissionValidation:
    """Test advanced permission validation and security."""

    @pytest.fixture
    def permission_validator(self):
        """Create permission manager for validation testing."""
        return RolePermissionManager()

    def test_permission_namespace_validation(self, permission_validator):
        """Test permission namespace consistency and validation."""
        # Group permissions by namespace
        namespaces = {}
        for perm in Permission:
            if "_" in perm.value:
                namespace = perm.value.split("_", 1)[0]
                if namespace not in namespaces:
                    namespaces[namespace] = []
                namespaces[namespace].append(perm)
        
        # Validate namespace consistency
        expected_namespaces = {
            "read", "create", "update", "delete",  # CRUD operations
            "access", "view", "manage",  # Access levels
            "export", "import"  # Data operations
        }
        
        actual_namespaces = set(namespaces.keys())
        assert expected_namespaces.issubset(actual_namespaces), \
            f"Missing namespaces: {expected_namespaces - actual_namespaces}"

    def test_permission_completeness_validation(self, permission_validator):
        """Test that permission sets are complete for each role."""
        for role in UserRole:
            perms = permission_validator.get_role_permissions(role)
            
            # Each role should have at least basic read access
            assert Permission.READ_ARTICLES in perms or Permission.ACCESS_BASIC_API in perms, \
                f"Role {role} lacks basic read permissions"
            
            # Roles should have logical permission combinations
            if Permission.CREATE_ARTICLES in perms:
                assert Permission.READ_ARTICLES in perms, \
                    f"Role {role} can create but not read articles"
            
            if Permission.UPDATE_ARTICLES in perms:
                assert Permission.READ_ARTICLES in perms, \
                    f"Role {role} can update but not read articles"

    def test_permission_security_boundaries(self, permission_validator):
        """Test security boundaries between permission levels."""
        # Define security boundaries
        security_boundaries = {
            "user_management": {
                Permission.READ_USERS,
                Permission.CREATE_USERS,
                Permission.UPDATE_USERS,
                Permission.DELETE_USERS
            },
            "system_management": {
                Permission.MANAGE_SYSTEM,
                Permission.ACCESS_ADMIN_PANEL,
                Permission.IMPORT_DATA
            },
            "content_creation": {
                Permission.CREATE_ARTICLES,
                Permission.UPDATE_ARTICLES,
                Permission.DELETE_ARTICLES
            }
        }
        
        # Free users should not cross security boundaries
        free_perms = permission_validator.get_role_permissions(UserRole.FREE)
        for boundary_name, boundary_perms in security_boundaries.items():
            overlap = free_perms & boundary_perms
            assert len(overlap) == 0, \
                f"Free user has {boundary_name} permissions: {overlap}"
        
        # Admin should have permissions from all boundaries
        admin_perms = permission_validator.get_role_permissions(UserRole.ADMIN)
        for boundary_name, boundary_perms in security_boundaries.items():
            assert boundary_perms.issubset(admin_perms), \
                f"Admin missing {boundary_name} permissions"

    def test_permission_transitivity_validation(self, permission_validator):
        """Test permission transitivity and logical consistency."""
        # If you can delete, you should be able to read and update
        for role in UserRole:
            perms = permission_validator.get_role_permissions(role)
            
            if Permission.DELETE_ARTICLES in perms:
                assert Permission.READ_ARTICLES in perms, \
                    f"Role {role} can delete but not read articles"
                assert Permission.UPDATE_ARTICLES in perms, \
                    f"Role {role} can delete but not update articles"
            
            if Permission.DELETE_USERS in perms:
                assert Permission.READ_USERS in perms, \
                    f"Role {role} can delete but not read users"

    def test_permission_least_privilege_validation(self, permission_validator):
        """Test least privilege principle adherence."""
        # Free users should have minimal necessary permissions
        free_perms = permission_validator.get_role_permissions(UserRole.FREE)
        
        # Should not exceed reasonable basic permissions count
        assert len(free_perms) <= 5, \
            f"Free user has too many permissions ({len(free_perms)}): {free_perms}"
        
        # Should only have read-only permissions
        write_permissions = {
            Permission.CREATE_ARTICLES,
            Permission.UPDATE_ARTICLES,
            Permission.DELETE_ARTICLES,
            Permission.CREATE_USERS,
            Permission.UPDATE_USERS,
            Permission.DELETE_USERS,
            Permission.MANAGE_SYSTEM,
            Permission.IMPORT_DATA,
            Permission.UPDATE_KNOWLEDGE_GRAPH
        }
        
        free_write_perms = free_perms & write_permissions
        assert len(free_write_perms) == 0, \
            f"Free user has write permissions: {free_write_perms}"


class TestRBACSecurityScenarios:
    """Test RBAC security scenarios and attack prevention."""

    @pytest.fixture
    def security_rbac_manager(self):
        """Create RBAC manager for security testing."""
        with patch('src.api.rbac.rbac_system.DynamoDBPermissionStore') as mock_store:
            manager = RBACManager()
            manager.permission_store = mock_store.return_value
            return manager

    @pytest.mark.asyncio
    async def test_role_injection_prevention(self, security_rbac_manager):
        """Test prevention of role injection attacks."""
        manager = security_rbac_manager
        
        # Test malicious role values
        malicious_roles = [
            "admin'; DROP TABLE users; --",
            "admin OR 1=1",
            "admin UNION SELECT * FROM permissions",
            "<script>alert('xss')</script>",
            "admin\x00",
            "admin\nadmin",  # Newline injection
            "admin\radmin",  # Carriage return injection
        ]
        
        for malicious_role in malicious_roles:
            # Should not crash or allow privilege escalation
            try:
                # Mock user with malicious role
                manager.permission_store.get_user_permissions.return_value = {
                    "user_id": "test_user",
                    "role": malicious_role
                }
                
                user_role = await manager.get_user_role("test_user")
                # Should either return None or handle gracefully
                assert user_role is None or isinstance(user_role, UserRole)
                
            except (ValueError, TypeError):
                # Expected for invalid role values
                pass

    @pytest.mark.asyncio
    async def test_permission_enumeration_prevention(self, security_rbac_manager):
        """Test prevention of permission enumeration attacks."""
        manager = security_rbac_manager
        
        # Mock free user
        manager.permission_store.get_user_permissions.return_value = {
            "user_id": "free_user",
            "role": "free"
        }
        
        # Test all permissions against free user
        free_allowed_perms = []
        for permission in Permission:
            has_perm = await manager.check_user_permission("free_user", permission)
            if has_perm:
                free_allowed_perms.append(permission)
        
        # Should only have expected free permissions
        expected_free_perms = manager.role_manager.get_role_permissions(UserRole.FREE)
        actual_free_perms = set(free_allowed_perms)
        
        assert actual_free_perms == expected_free_perms, \
            f"Permission enumeration revealed unexpected permissions: {actual_free_perms - expected_free_perms}"

    @pytest.mark.asyncio
    async def test_concurrent_role_modification_safety(self, security_rbac_manager):
        """Test safety of concurrent role modifications."""
        manager = security_rbac_manager
        
        # Mock successful operations
        manager.permission_store.store_user_permissions.return_value = True
        manager.permission_store.update_user_role.return_value = True
        
        async def modify_user_role(user_id, role):
            try:
                await manager.assign_role_to_user(user_id, role)
                await manager.update_user_role(user_id, UserRole.ADMIN)
                return True
            except Exception:
                return False
        
        # Run concurrent modifications
        tasks = []
        for i in range(20):
            task = modify_user_role(f"user_{i}", UserRole.PREMIUM)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should handle concurrent operations safely
        successful_results = [r for r in results if r is True]
        assert len(successful_results) > 0, "No concurrent operations succeeded"

    @pytest.mark.asyncio
    async def test_privilege_escalation_prevention(self, security_rbac_manager):
        """Test prevention of privilege escalation."""
        manager = security_rbac_manager
        
        # User starts as FREE
        manager.permission_store.get_user_permissions.return_value = {
            "user_id": "test_user",
            "role": "free"
        }
        
        # Attempt to check admin permissions
        admin_perms = [
            Permission.MANAGE_SYSTEM,
            Permission.DELETE_USERS,
            Permission.ACCESS_ADMIN_PANEL,
            Permission.IMPORT_DATA
        ]
        
        escalation_attempts = []
        for admin_perm in admin_perms:
            has_perm = await manager.check_user_permission("test_user", admin_perm)
            if has_perm:
                escalation_attempts.append(admin_perm)
        
        # Should not have any admin permissions
        assert len(escalation_attempts) == 0, \
            f"Privilege escalation detected: {escalation_attempts}"

    def test_role_tampering_detection(self, security_rbac_manager):
        """Test detection of role tampering attempts."""
        manager = security_rbac_manager
        
        # Test with invalid role objects
        invalid_roles = [
            None,
            "",
            123,
            [],
            {},
            object(),
        ]
        
        for invalid_role in invalid_roles:
            try:
                permissions = manager.role_manager.get_role_permissions(invalid_role)
                # Should return empty set for invalid roles
                assert permissions == set()
            except (AttributeError, TypeError, KeyError):
                # Expected for invalid role objects
                pass


class TestRBACIntegrationAndPerformance:
    """Test RBAC system integration and performance characteristics."""

    @pytest.fixture
    def integration_rbac_manager(self):
        """Create RBAC manager for integration testing."""
        return RBACManager()

    def test_rbac_role_manager_integration(self, integration_rbac_manager):
        """Test integration between RBAC components."""
        manager = integration_rbac_manager
        
        # Should have role manager integrated
        assert manager.role_manager is not None
        assert isinstance(manager.role_manager, RolePermissionManager)
        
        # Role manager should have all standard roles
        for role in UserRole:
            role_def = manager.role_manager.get_role_definition(role)
            assert role_def is not None
            assert isinstance(role_def, RoleDefinition)

    def test_rbac_performance_under_load(self, integration_rbac_manager):
        """Test RBAC performance under load."""
        manager = integration_rbac_manager
        
        import time
        start_time = time.time()
        
        # Simulate high-frequency permission checks
        for _ in range(1000):
            # Check various role-permission combinations
            manager.role_manager.has_permission(UserRole.ADMIN, Permission.MANAGE_SYSTEM)
            manager.role_manager.has_permission(UserRole.PREMIUM, Permission.ACCESS_PREMIUM_API)
            manager.role_manager.has_permission(UserRole.FREE, Permission.READ_ARTICLES)
            
            # Get role permissions
            manager.role_manager.get_role_permissions(UserRole.ADMIN)
            manager.role_manager.get_role_permissions(UserRole.PREMIUM)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle high load efficiently (5000 operations < 2 seconds)
        assert duration < 2.0, f"RBAC operations too slow: {duration}s for 5000 operations"

    def test_rbac_memory_efficiency(self, integration_rbac_manager):
        """Test RBAC memory usage efficiency."""
        manager = integration_rbac_manager
        
        import gc
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Perform many RBAC operations
        for i in range(500):
            for role in UserRole:
                manager.role_manager.get_role_permissions(role)
                for perm in Permission:
                    manager.role_manager.has_permission(role, perm)
            
            # Periodic cleanup
            if i % 100 == 0:
                gc.collect()
        
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Memory usage should remain stable
        object_growth = final_objects - initial_objects
        assert object_growth < 10000, f"Memory usage grew by {object_growth} objects"

    def test_global_rbac_manager_singleton(self):
        """Test global RBAC manager singleton pattern."""
        # Global manager should exist
        assert rbac_manager is not None
        assert isinstance(rbac_manager, RBACManager)
        
        # Should have consistent behavior
        admin_perms1 = rbac_manager.role_manager.get_role_permissions(UserRole.ADMIN)
        admin_perms2 = rbac_manager.role_manager.get_role_permissions(UserRole.ADMIN)
        assert admin_perms1 == admin_perms2
        
        # Should maintain state consistency
        has_perm1 = rbac_manager.role_manager.has_permission(UserRole.ADMIN, Permission.MANAGE_SYSTEM)
        has_perm2 = rbac_manager.role_manager.has_permission(UserRole.ADMIN, Permission.MANAGE_SYSTEM)
        assert has_perm1 == has_perm2 == True