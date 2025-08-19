"""
RBAC Management API Routes for Issue #60.

Provides endpoints for managing roles and permissions in the system.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth.jwt_auth import require_auth
from src.api.rbac.rbac_system import Permission, UserRole, rbac_manager

router = APIRouter(prefix="/api/rbac", tags=["rbac"])


# Request/Response Models
class UserRoleUpdate(BaseModel):
    """Request to update a user's role."""

    user_id: str = Field(..., description="User ID to update")
    new_role: UserRole = Field(..., description="New role to assign")


class RoleInfo(BaseModel):
    """Information about a role."""

    name: str
    description: str
    permissions: List[str]
    permission_count: int


class UserPermissionInfo(BaseModel):
    """User permission information."""

    user_id: str
    role: str
    permissions: List[str]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AccessCheckRequest(BaseModel):
    """Request to check access for a user."""

    user_role: UserRole
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    path: str = Field(..., description="API endpoint path")


class AccessCheckResponse(BaseModel):
    """Response for access check."""

    has_access: bool
    user_role: str
    endpoint: str
    required_permissions: List[str]
    user_permissions: List[str]
    minimum_required_role: str


# Admin-only dependency
async def require_admin(user: dict = Depends(require_auth)) -> dict:
    """Ensure user has admin role."""
    if user.get("role", "").lower() not in ["admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


@router.get("/roles", response_model=Dict[str, RoleInfo])
async def get_all_roles(_: dict = Depends(require_auth)):
    """
    Get information about all system roles.

    Returns:
        Dictionary of role information
    """
    try:
        role_summary = rbac_manager.get_role_summary()

        return {
            role_name: RoleInfo(
                name=info["name"],
                description=info["description"],
                permissions=info["permissions"],
                permission_count=info["permission_count"],
            )
            for role_name, info in role_summary.items()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve roles: {str(e)}"
        )


@router.get("/roles/{role_name}", response_model=RoleInfo)
async def get_role_info(role_name: str, _: dict = Depends(require_auth)):
    """
    Get detailed information about a specific role.

    Args:
        role_name: Name of the role to query

    Returns:
        Detailed role information
    """
    try:
        role = UserRole(role_name.lower())
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Role '{role_name}' not found")

    try:
        role_summary = rbac_manager.get_role_summary()
        role_info = role_summary[role.value]

        return RoleInfo(
            name=role_info["name"],
            description=role_info["description"],
            permissions=role_info["permissions"],
            permission_count=role_info["permission_count"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve role information: {str(e)}"
        )


@router.post("/users/{user_id}/role", response_model=Dict[str, Any])
async def update_user_role(
    user_id: str, role_update: UserRoleUpdate, admin_user: dict = Depends(require_admin)
):
    """
    Update a user's role (Admin only).

    Args:
        user_id: ID of user to update
        role_update: New role information
        admin_user: Admin user making the request

    Returns:
        Success confirmation
    """
    try:
        # Store updated permissions in DynamoDB
        success = await rbac_manager.store_user_permissions(
            role_update.user_id, role_update.new_role
        )

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to update user role in database"
            )

        return {
            "message": f"Successfully updated user {user_id} to role {role_update.new_role.value}",
            "user_id": user_id,
            "new_role": role_update.new_role.value,
            "updated_by": admin_user.get("sub"),
            "updated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update user role: {str(e)}"
        )


@router.get("/users/{user_id}/permissions", response_model=UserPermissionInfo)
async def get_user_permissions(
    user_id: str, current_user: dict = Depends(require_auth)
):
    """
    Get user's current permissions.

    Args:
        user_id: ID of user to query
        current_user: Current authenticated user

    Returns:
        User permission information
    """
    # Users can only view their own permissions unless they're admin
    if current_user.get("sub") != user_id and current_user.get(
        "role", ""
    ).lower() not in ["admin", "administrator"]:
        raise HTTPException(
            status_code=403, detail="Can only view your own permissions"
        )

    try:
        # Try to get from DynamoDB first
        db_permissions = await rbac_manager.get_user_role_from_db(user_id)

        if db_permissions:
            user_role = db_permissions
        else:
            # Fallback to token role if not in DB
            if current_user.get("sub") == user_id:
                try:
                    user_role = UserRole(current_user.get("role", "free").lower())
                except ValueError:
                    user_role = UserRole.FREE
            else:
                raise HTTPException(
                    status_code=404, detail="User permissions not found"
                )

        # Get permissions for the role
        permissions = rbac_manager.permission_manager.get_role_permissions(user_role)

        return UserPermissionInfo(
            user_id=user_id,
            role=user_role.value,
            permissions=[p.value for p in permissions],
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve user permissions: {str(e)}"
        )


@router.post("/check-access", response_model=AccessCheckResponse)
async def check_access(
    access_request: AccessCheckRequest, _: dict = Depends(require_auth)
):
    """
    Check if a role has access to a specific endpoint.

    Args:
        access_request: Access check parameters

    Returns:
        Access check result
    """
    try:
        has_access = rbac_manager.has_access(
            access_request.user_role, access_request.method, access_request.path
        )

        required_permissions = rbac_manager.get_endpoint_permissions(
            access_request.method, access_request.path
        )

        user_permissions = rbac_manager.permission_manager.get_role_permissions(
            access_request.user_role
        )

        # Find minimum required role
        minimum_role = "none"
        for role in [UserRole.FREE, UserRole.PREMIUM, UserRole.ADMIN]:
            if rbac_manager.has_access(
                role, access_request.method, access_request.path
            ):
                minimum_role = role.value
                break

        return AccessCheckResponse(
            has_access=has_access,
            user_role=access_request.user_role.value,
            endpoint=f"{access_request.method} {access_request.path}",
            required_permissions=[p.value for p in required_permissions],
            user_permissions=[p.value for p in user_permissions],
            minimum_required_role=minimum_role,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check access: {str(e)}")


@router.get("/permissions", response_model=List[str])
async def get_all_permissions(_: dict = Depends(require_auth)):
    """
    Get list of all system permissions.

    Returns:
        List of permission names
    """
    try:
        return [permission.value for permission in Permission]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve permissions: {str(e)}"
        )


@router.get("/endpoint-permissions")
async def get_endpoint_permissions(
    method: str = Query(..., description="HTTP method"),
    path: str = Query(..., description="API endpoint path"),
    _: dict = Depends(require_auth),
):
    """
    Get required permissions for a specific endpoint.

    Args:
        method: HTTP method
        path: API endpoint path

    Returns:
        Required permissions for the endpoint
    """
    try:
        required_permissions = rbac_manager.get_endpoint_permissions(method, path)

        return {
            "endpoint": f"{method} {path}",
            "required_permissions": [p.value for p in required_permissions],
            "permission_count": len(required_permissions),
            "public_endpoint": len(required_permissions) == 0,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get endpoint permissions: {str(e)}"
        )


@router.get("/metrics", response_model=Dict[str, Any])
async def get_rbac_metrics(admin_user: dict = Depends(require_admin)):
    """
    Get RBAC system metrics (Admin only).

    Args:
        admin_user: Admin user making the request

    Returns:
        RBAC metrics and statistics
    """
    try:
        from src.api.rbac.rbac_middleware import rbac_metrics

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "rbac_metrics": rbac_metrics.get_metrics(),
            "role_summary": rbac_manager.get_role_summary(),
            "total_permissions": len([p for p in Permission]),
            "total_roles": len([r for r in UserRole]),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve RBAC metrics: {str(e)}"
        )


@router.delete("/users/{user_id}/permissions")
async def delete_user_permissions(
    user_id: str, admin_user: dict = Depends(require_admin)
):
    """
    Delete user permissions from DynamoDB (Admin only).

    Args:
        user_id: ID of user whose permissions to delete
        admin_user: Admin user making the request

    Returns:
        Success confirmation
    """
    try:
        success = await rbac_manager.permission_store.delete_user_permissions(user_id)

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to delete user permissions"
            )

        return {
            "message": f"Successfully deleted permissions for user {user_id}",
            "user_id": user_id,
            "deleted_by": admin_user.get("sub"),
            "deleted_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete user permissions: {str(e)}"
        )
