"""
Role-Based Access Control (RBAC) System for NeuroNews API.

This module implements a comprehensive RBAC system that:
1. Defines user roles (Admin, Premium, Free)
2. Restricts access to API endpoints based on roles
3. Stores permissions in DynamoDB
4. Provides role management and permission checking
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

try:
    import boto3
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """User roles in the system."""

    ADMIN = "admin"
    PREMIUM = "premium"
    FREE = "free"


class Permission(Enum):
    """System permissions."""

    # Article permissions
    READ_ARTICLES = "read_articles"
    CREATE_ARTICLES = "create_articles"
    UPDATE_ARTICLES = "update_articles"
    DELETE_ARTICLES = "delete_articles"

    # User management permissions
    READ_USERS = "read_users"
    CREATE_USERS = "create_users"
    UPDATE_USERS = "update_users"
    DELETE_USERS = "delete_users"

    # System permissions
    ACCESS_ADMIN_PANEL = "access_admin_panel"
    VIEW_ANALYTICS = "view_analytics"
    MANAGE_SYSTEM = "manage_system"

    # API access permissions
    ACCESS_BASIC_API = "access_basic_api"
    ACCESS_PREMIUM_API = "access_premium_api"
    ACCESS_ADVANCED_API = "access_advanced_api"

    # Knowledge graph permissions
    READ_KNOWLEDGE_GRAPH = "read_knowledge_graph"
    UPDATE_KNOWLEDGE_GRAPH = "update_knowledge_graph"

    # Data permissions
    EXPORT_DATA = "export_data"
    IMPORT_DATA = "import_data"


@dataclass
class RoleDefinition:
    """Definition of a user role with its permissions."""

    name: str
    description: str
    permissions: Set[Permission]
    inherits_from: Optional["RoleDefinition"] = None

    def get_all_permissions(self) -> Set[Permission]:
        """Get all permissions including inherited ones."""
        permissions = self.permissions.copy()
        if self.inherits_from:
            permissions.update(self.inherits_from.get_all_permissions())
        return permissions


class RolePermissionManager:
    """Manages role definitions and permission mappings."""

    def __init__(self):
        """Initialize role definitions."""
        self._roles = self._define_roles()

    def _define_roles(self) -> Dict[UserRole, RoleDefinition]:
        """Define system roles and their permissions."""

        # Free tier role - basic access
        free_role = RoleDefinition(
            name="Free User",
            description="Basic user with limited access to news articles",
            permissions={Permission.READ_ARTICLES, Permission.ACCESS_BASIC_API},
        )

        # Premium tier role - enhanced access
        premium_role = RoleDefinition(
            name="Premium User",
            description="Premium user with advanced features",
            permissions={
                Permission.VIEW_ANALYTICS,
                Permission.ACCESS_PREMIUM_API,
                Permission.READ_KNOWLEDGE_GRAPH,
                Permission.EXPORT_DATA,
            },
            inherits_from=free_role,
        )

        # Admin role - full access
        admin_role = RoleDefinition(
            name="Administrator",
            description="Full system administrator",
            permissions={
                Permission.CREATE_ARTICLES,
                Permission.UPDATE_ARTICLES,
                Permission.DELETE_ARTICLES,
                Permission.READ_USERS,
                Permission.CREATE_USERS,
                Permission.UPDATE_USERS,
                Permission.DELETE_USERS,
                Permission.ACCESS_ADMIN_PANEL,
                Permission.MANAGE_SYSTEM,
                Permission.ACCESS_ADVANCED_API,
                Permission.UPDATE_KNOWLEDGE_GRAPH,
                Permission.IMPORT_DATA,
            },
            inherits_from=premium_role,
        )

        return {
            UserRole.FREE: free_role,
            UserRole.PREMIUM: premium_role,
            UserRole.ADMIN: admin_role,
        }

    def get_role_permissions(self, role: UserRole) -> Set[Permission]:
        """Get all permissions for a role."""
        if role not in self._roles:
            return set()
        return self._roles[role].get_all_permissions()

    def has_permission(self, role: UserRole, permission: Permission) -> bool:
        """Check if a role has a specific permission."""
        return permission in self.get_role_permissions(role)

    def get_role_definition(self, role: UserRole) -> Optional[RoleDefinition]:
        """Get role definition."""
        return self._roles.get(role)


class DynamoDBPermissionStore:
    """Stores and retrieves permissions from DynamoDB."""

    def __init__(self):
        """Initialize DynamoDB connection."""
        self.table_name = os.getenv("RBAC_DYNAMODB_TABLE", "neuronews_rbac_permissions")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.dynamodb = None
        self.table = None

        if BOTO3_AVAILABLE:
            try:
                self.dynamodb = boto3.resource("dynamodb", region_name=self.region)
                self.table = self.dynamodb.Table(self.table_name)
                self._ensure_table_exists()
            except Exception as e:
                logger.warning("Failed to initialize DynamoDB: {0}".format(e))
                self.dynamodb = None
                self.table = None
        else:
            logger.warning("boto3 not available - DynamoDB features disabled")

    def _ensure_table_exists(self):
        """Ensure the permissions table exists."""
        if not self.dynamodb:
            return

        try:
            # Check if table exists
            self.table.load()
            logger.info("DynamoDB table {0} exists".format(self.table_name))
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.info("Creating DynamoDB table {0}".format(self.table_name))
                self._create_table()
            else:
                logger.error("Error checking table: {0}".format(e))

    def _create_table(self):
        """Create the permissions table."""
        if not self.dynamodb:
            return

        try:
            table = self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
                AttributeDefinitions=[
                    {"AttributeName": "user_id", "AttributeType": "S"}
                ],
                BillingMode="PAY_PER_REQUEST",
                Tags=[
                    {"Key": "Application", "Value": "NeuroNews"},
                    {"Key": "Component", "Value": "RBAC"},
                ],
            )

            # Wait for table to be created
            table.wait_until_exists()
            self.table = table
            logger.info("Created DynamoDB table {0}".format(self.table_name))

        except Exception as e:
            logger.error("Failed to create table: {0}".format(e))

    async def store_user_permissions(
        self,
        user_id: str,
        role: UserRole,
        custom_permissions: Optional[List[str]] = None,
    ) -> bool:
        """Store user permissions in DynamoDB."""
        if not self.table:
            logger.warning("DynamoDB not available - permissions not stored")
            return False

        try:
            item = {
                "user_id": user_id,
                "role": role.value,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            if custom_permissions:
                item["custom_permissions"] = custom_permissions

            self.table.put_item(Item=item)
            logger.info("Stored permissions for user {0}".format(user_id))
            return True

        except Exception as e:
            logger.error(
                "Failed to store permissions for user {0}: {1}".format(user_id, e)
            )
            return False

    async def get_user_permissions(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user permissions from DynamoDB."""
        if not self.table:
            return None

        try:
            response = self.table.get_item(Key={"user_id": user_id})
            if "Item" in response:
                return response["Item"]
            return None

        except Exception as e:
            logger.error(
                "Failed to get permissions for user {0}: {1}".format(user_id, e)
            )
            return None

    async def update_user_role(self, user_id: str, new_role: UserRole) -> bool:
        """Update user role in DynamoDB."""
        if not self.table:
            return False

        try:
            self.table.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET #role =:role, updated_at =:updated_at",
                ExpressionAttributeNames={"#role": "role"},
                ExpressionAttributeValues={
                    ":role": new_role.value,
                    ":updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(
                "Updated role for user {0} to {1}".format(user_id, new_role.value)
            )
            return True

        except Exception as e:
            logger.error("Failed to update role for user {0}: {1}".format(user_id, e))
            return False

    async def delete_user_permissions(self, user_id: str) -> bool:
        """Delete user permissions from DynamoDB."""
        if not self.table:
            return False

        try:
            self.table.delete_item(Key={"user_id": user_id})
            logger.info("Deleted permissions for user {0}".format(user_id))
            return True

        except Exception as e:
            logger.error(
                "Failed to delete permissions for user {0}: {1}".format(user_id, e)
            )
            return False


class RBACManager:
    """Main RBAC management class."""

    def __init__(self):
        """Initialize RBAC manager."""
        self.permission_manager = RolePermissionManager()
        self.permission_store = DynamoDBPermissionStore()
        self._endpoint_permissions = self._define_endpoint_permissions()

    def _define_endpoint_permissions(self) -> Dict[str, Set[Permission]]:
        """Define which permissions are required for each endpoint."""
        return {
            # Public endpoints (no authentication required)
            "GET /": set(),
            "GET /health": set(),
            # Basic article endpoints
            "GET /api/articles": {Permission.READ_ARTICLES},
            "GET /api/articles/{id}": {Permission.READ_ARTICLES},
            "POST /api/articles": {Permission.CREATE_ARTICLES},
            "PUT /api/articles/{id}": {Permission.UPDATE_ARTICLES},
            "DELETE /api/articles/{id}": {Permission.DELETE_ARTICLES},
            # User management endpoints
            "GET /api/users": {Permission.READ_USERS},
            "POST /api/users": {Permission.CREATE_USERS},
            "PUT /api/users/{id}": {Permission.UPDATE_USERS},
            "DELETE /api/users/{id}": {Permission.DELETE_USERS},
            # Analytics endpoints
            "GET /api/analytics": {Permission.VIEW_ANALYTICS},
            "GET /api/analytics/dashboard": {Permission.VIEW_ANALYTICS},
            # Knowledge graph endpoints
            "GET /api/knowledge-graph": {Permission.READ_KNOWLEDGE_GRAPH},
            "POST /api/knowledge-graph": {Permission.UPDATE_KNOWLEDGE_GRAPH},
            "GET /api/v1/knowledge-graph/related_entities": {
                Permission.READ_KNOWLEDGE_GRAPH
            },
            "GET /api/v1/knowledge-graph/event_timeline": {
                Permission.READ_KNOWLEDGE_GRAPH
            },
            # Admin endpoints
            "GET /api/admin": {Permission.ACCESS_ADMIN_PANEL},
            "POST /api/admin/system": {Permission.MANAGE_SYSTEM},
            # Data endpoints
            "GET /api/export": {Permission.EXPORT_DATA},
            "POST /api/import": {Permission.IMPORT_DATA},
            # API access control endpoints
            "GET /api/api_limits": {Permission.ACCESS_BASIC_API},
            "GET /api/premium": {Permission.ACCESS_PREMIUM_API},
            "GET /api/advanced": {Permission.ACCESS_ADVANCED_API},
        }

    def get_endpoint_permissions(self, method: str, path: str) -> Set[Permission]:
        """Get required permissions for an endpoint."""
        endpoint_key = "{0} {1}".format(method.upper(), path)

        # Check exact match first
        if endpoint_key in self._endpoint_permissions:
            return self._endpoint_permissions[endpoint_key]

        # Check for parameterized routes
        for pattern, permissions in self._endpoint_permissions.items():
            if self._matches_pattern(endpoint_key, pattern):
                return permissions

        # Default: require basic API access for unknown endpoints
        return {Permission.ACCESS_BASIC_API}

    def _matches_pattern(self, endpoint: str, pattern: str) -> bool:
        """Check if endpoint matches a pattern with parameters."""
        endpoint_parts = endpoint.split("/")
        pattern_parts = pattern.split("/")

        if len(endpoint_parts) != len(pattern_parts):
            return False

        for ep, pp in zip(endpoint_parts, pattern_parts):
            if pp.startswith("{") and pp.endswith("}"):
                continue  # Parameter match
            if ep != pp:
                return False

        return True

    def has_access(self, user_role: UserRole, method: str, path: str) -> bool:
        """Check if user role has access to an endpoint."""
        required_permissions = self.get_endpoint_permissions(method, path)

        if not required_permissions:
            return True  # Public endpoint

        user_permissions = self.permission_manager.get_role_permissions(user_role)

        # User needs at least one of the required permissions
        return bool(required_permissions.intersection(user_permissions))

    async def store_user_permissions(self, user_id: str, role: UserRole) -> bool:
        """Store user permissions in DynamoDB."""
        return await self.permission_store.store_user_permissions(user_id, role)

    async def get_user_role_from_db(self, user_id: str) -> Optional[UserRole]:
        """Get user role from DynamoDB."""
        permissions = await self.permission_store.get_user_permissions(user_id)
        if permissions and "role" in permissions:
            try:
                return UserRole(permissions["role"])
            except ValueError:
                logger.warning(
                    f"Invalid role '{permissions['role']}' for user {user_id}"
                )
        return None

    def get_role_summary(self) -> Dict[str, Any]:
        """Get summary of all roles and their permissions."""
        summary = {}
        for role in UserRole:
            role_def = self.permission_manager.get_role_definition(role)
            permissions = self.permission_manager.get_role_permissions(role)

            summary[role.value] = {
                "name": role_def.name if role_def else role.value,
                "description": role_def.description if role_def else "",
                "permissions": [p.value for p in permissions],
                "permission_count": len(permissions),
            }

        return summary


# Global RBAC manager instance
rbac_manager = RBACManager()
