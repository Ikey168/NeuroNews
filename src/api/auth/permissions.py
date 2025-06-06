"""
Role-based access control (RBAC) system for API endpoints.
"""

from enum import Enum
from typing import Dict, List, Set, Optional
import logging
from fastapi import HTTPException, Request
from functools import wraps

from src.api.auth.audit_log import security_logger

logger = logging.getLogger(__name__)

class Permission(str, Enum):
    """Defined permissions for API endpoints."""
    # Article permissions
    READ_ARTICLES = "read:articles"
    CREATE_ARTICLES = "create:articles"
    UPDATE_ARTICLES = "update:articles"
    DELETE_ARTICLES = "delete:articles"
    
    # User management permissions
    READ_USERS = "read:users"
    CREATE_USERS = "create:users"
    UPDATE_USERS = "update:users"
    DELETE_USERS = "delete:users"
    
    # System permissions
    VIEW_METRICS = "view:metrics"
    MANAGE_SYSTEM = "manage:system"
    VIEW_LOGS = "view:logs"
    
    # NLP job permissions
    RUN_NLP_JOBS = "run:nlp_jobs"
    VIEW_NLP_RESULTS = "view:nlp_results"
    
    # Knowledge graph permissions
    READ_GRAPH = "read:graph"
    WRITE_GRAPH = "write:graph"

# Role-permission mapping
ROLE_PERMISSIONS: Dict[str, Set[Permission]] = {
    "admin": {
        # Admin has all permissions
        *Permission.__members__.values()
    },
    "editor": {
        # Content management
        Permission.READ_ARTICLES,
        Permission.CREATE_ARTICLES,
        Permission.UPDATE_ARTICLES,
        Permission.DELETE_ARTICLES,
        
        # Limited user management
        Permission.READ_USERS,
        
        # System access
        Permission.VIEW_METRICS,
        Permission.VIEW_LOGS,
        
        # NLP access
        Permission.RUN_NLP_JOBS,
        Permission.VIEW_NLP_RESULTS,
        
        # Graph access
        Permission.READ_GRAPH,
        Permission.WRITE_GRAPH
    },
    "user": {
        # Basic permissions
        Permission.READ_ARTICLES,
        Permission.VIEW_NLP_RESULTS,
        Permission.READ_GRAPH
    }
}

def has_permission(role: str, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.
    
    Args:
        role: User role
        permission: Required permission
        
    Returns:
        True if role has permission, False otherwise
    """
    if role not in ROLE_PERMISSIONS:
        return False
    return permission in ROLE_PERMISSIONS[role]

def require_permissions(*permissions: Permission):
    """
    Decorator to require specific permissions for an endpoint.
    
    Args:
        *permissions: Required permissions
        
    Returns:
        Decorated function that checks permissions
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = next((arg for arg in args if isinstance(arg, Request)), None)
            if request is None:
                request = next((v for v in kwargs.values() if isinstance(v, Request)), None)
            if request is None:
                raise ValueError("No request object found")
                
            # Get user from request state (set by JWT middleware)
            user = getattr(request.state, "user", None)
            if not user or "role" not in user:
                # Log authentication failure
                await security_logger.log_auth_failure(
                    "Missing authentication",
                    request
                )
                raise HTTPException(status_code=401, detail="Authentication required")
                
            role = user["role"]
            
            # Check all required permissions
            missing_permissions = [
                p for p in permissions 
                if not has_permission(role, p)
            ]
            
            if missing_permissions:
                # Log permission denial
                for permission in missing_permissions:
                    await security_logger.log_permission_denied(
                        permission,
                        request,
                        user
                    )
                
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing required permissions: {', '.join(missing_permissions)}"
                )
                
            # Log successful authorization
            await security_logger.log_auth_success(request, user)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

class PermissionChecker:
    """Permission checking utility class."""
    
    def __init__(self, role: str):
        """
        Initialize with user role.
        
        Args:
            role: User role
        """
        self.role = role
        self.permissions = ROLE_PERMISSIONS.get(role, set())
    
    def can(self, permission: Permission) -> bool:
        """
        Check if user has a specific permission.
        
        Args:
            permission: Required permission
            
        Returns:
            True if user has permission
        """
        return permission in self.permissions
    
    def require(self, *permissions: Permission) -> None:
        """
        Raise exception if user lacks any required permission.
        
        Args:
            *permissions: Required permissions
            
        Raises:
            HTTPException: If user lacks permissions
        """
        missing = [p for p in permissions if not self.can(p)]
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required permissions: {', '.join(missing)}"
            )

def get_user_permissions(role: str) -> Set[Permission]:
    """
    Get all permissions for a role.
    
    Args:
        role: User role
        
    Returns:
        Set of permissions
    """
    return ROLE_PERMISSIONS.get(role, set())