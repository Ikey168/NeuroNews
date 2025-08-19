"""
API Key Management Routes for NeuroNews API - Issue #61.

Provides endpoints for generating, managing, and revoking API keys.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from src.api.auth.api_key_manager import APIKeyStatus, api_key_manager
from src.api.auth.jwt_auth import require_auth

router = APIRouter(prefix="/api/keys", tags=["api-keys"])


# Request/Response Models
class APIKeyGenerateRequest(BaseModel):
    """Request to generate a new API key."""

    name: str = Field(
        ...,
        description="Human-readable name for the API key",
        min_length=1,
        max_length=100,
    )
    expires_in_days: Optional[int] = Field(
        None, description="Days until expiration (default: 365)", ge=1, le=3650
    )
    permissions: Optional[List[str]] = Field(
        None, description="List of permissions for this key"
    )
    rate_limit: Optional[int] = Field(
        None, description="Rate limit in requests per minute", ge=1, le=10000
    )


class APIKeyResponse(BaseModel):
    """Response containing API key details."""

    key_id: str
    key_prefix: str
    name: str
    status: str
    created_at: str
    expires_at: Optional[str]
    last_used_at: Optional[str]
    usage_count: int
    permissions: Optional[List[str]]
    rate_limit: Optional[int]
    is_expired: bool


class APIKeyGenerateResponse(BaseModel):
    """Response for API key generation."""

    key_id: str
    api_key: str
    key_prefix: str
    name: str
    status: str
    created_at: str
    expires_at: Optional[str]
    permissions: Optional[List[str]]
    rate_limit: Optional[int]
    message: str


class APIKeyRevokeRequest(BaseModel):
    """Request to revoke an API key."""

    key_id: str = Field(..., description="ID of the key to revoke")


class APIKeyRenewRequest(BaseModel):
    """Request to renew an API key."""

    key_id: str = Field(..., description="ID of the key to renew")
    extends_days: Optional[int] = Field(
        None, description="Days to extend (default: 365)", ge=1, le=3650
    )


# Helper function to get user ID from auth
def get_user_id(user: dict = Depends(require_auth)) -> str:
    """Extract user ID from authenticated user."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user token")
    return user_id


@router.post("/generate", response_model=APIKeyGenerateResponse)
async def generate_api_key(
    request: APIKeyGenerateRequest, user_id: str = Depends(get_user_id)
):
    """
    Generate a new API key for the authenticated user.

    This endpoint fulfills the requirement: "Implement API /generate_api_key?user_id=xyz"

    Args:
        request: API key generation parameters
        user_id: Authenticated user ID

    Returns:
        New API key details (key value only shown once)
    """
    try:
        result = await api_key_manager.generate_api_key(
            user_id=user_id,
            name=request.name,
            expires_in_days=request.expires_in_days,
            permissions=request.permissions,
            rate_limit=request.rate_limit,
        )

        return APIKeyGenerateResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate API key: {str(e)}"
        )


@router.get("/generate_api_key", response_model=APIKeyGenerateResponse)
async def generate_api_key_query_param(
    user_id: str = Query(..., description="User ID for API key generation"),
    name: str = Query("Default API Key", description="Name for the API key"),
    expires_in_days: Optional[int] = Query(None, description="Days until expiration"),
    current_user: dict = Depends(require_auth),
):
    """
    Generate API key via query parameters (alternative endpoint).

    This specifically implements: "Implement API /generate_api_key?user_id=xyz"

    Args:
        user_id: User ID from query parameter
        name: Optional name for the key
        expires_in_days: Optional expiration period
        current_user: Authenticated user making request

    Returns:
        New API key details
    """
    # Verify the requesting user can generate keys for this user_id
    # Users can only generate keys for themselves unless they're admin
    requesting_user_id = current_user.get("sub")
    user_role = current_user.get("role", "").lower()

    if user_id != requesting_user_id and user_role not in ["admin", "administrator"]:
        raise HTTPException(
            status_code=403, detail="Can only generate API keys for your own account"
        )

    try:
        result = await api_key_manager.generate_api_key(
            user_id=user_id, name=name, expires_in_days=expires_in_days
        )

        return APIKeyGenerateResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate API key: {str(e)}"
        )


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(user_id: str = Depends(get_user_id)):
    """
    List all API keys for the authenticated user.

    Args:
        user_id: Authenticated user ID

    Returns:
        List of user's API keys (without actual key values)
    """
    try:
        keys = await api_key_manager.get_user_api_keys(user_id)
        return [APIKeyResponse(**key) for key in keys]

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve API keys: {str(e)}"
        )


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str = Path(..., description="API key ID"),
    user_id: str = Depends(get_user_id),
):
    """
    Get details of a specific API key.

    Args:
        key_id: API key ID
        user_id: Authenticated user ID

    Returns:
        API key details
    """
    try:
        # Get user's keys and find the specific one
        keys = await api_key_manager.get_user_api_keys(user_id)

        for key in keys:
            if key["key_id"] == key_id:
                return APIKeyResponse(**key)

        raise HTTPException(status_code=404, detail="API key not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve API key: {str(e)}"
        )


@router.post("/revoke")
async def revoke_api_key(
    request: APIKeyRevokeRequest, user_id: str = Depends(get_user_id)
):
    """
    Revoke an API key.

    Args:
        request: Revoke request with key ID
        user_id: Authenticated user ID

    Returns:
        Success confirmation
    """
    try:
        success = await api_key_manager.revoke_api_key(user_id, request.key_id)

        if not success:
            raise HTTPException(
                status_code=404, detail="API key not found or not owned by user"
            )

        return {
            "message": f"API key {request.key_id} has been revoked",
            "key_id": request.key_id,
            "status": "revoked",
            "revoked_at": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to revoke API key: {str(e)}"
        )


@router.delete("/{key_id}")
async def delete_api_key(
    key_id: str = Path(..., description="API key ID to delete"),
    user_id: str = Depends(get_user_id),
):
    """
    Delete an API key permanently.

    Args:
        key_id: API key ID
        user_id: Authenticated user ID

    Returns:
        Success confirmation
    """
    try:
        success = await api_key_manager.delete_api_key(user_id, key_id)

        if not success:
            raise HTTPException(
                status_code=404, detail="API key not found or not owned by user"
            )

        return {
            "message": f"API key {key_id} has been deleted",
            "key_id": key_id,
            "status": "deleted",
            "deleted_at": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete API key: {str(e)}"
        )


@router.post("/renew")
async def renew_api_key(
    request: APIKeyRenewRequest, user_id: str = Depends(get_user_id)
):
    """
    Renew an API key by extending its expiration.

    Args:
        request: Renewal request with key ID and extension period
        user_id: Authenticated user ID

    Returns:
        Updated key information
    """
    try:
        result = await api_key_manager.renew_api_key(
            user_id=user_id, key_id=request.key_id, extends_days=request.extends_days
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to renew API key: {str(e)}"
        )


@router.get("/usage/stats")
async def get_api_key_usage_stats(user_id: str = Depends(get_user_id)):
    """
    Get usage statistics for user's API keys.

    Args:
        user_id: Authenticated user ID

    Returns:
        Usage statistics
    """
    try:
        keys = await api_key_manager.get_user_api_keys(user_id)

        total_keys = len(keys)
        active_keys = len([k for k in keys if k["status"] == "active"])
        expired_keys = len([k for k in keys if k["is_expired"]])
        total_usage = sum(k["usage_count"] for k in keys)

        # Get recent usage from metrics middleware
        from src.api.auth.api_key_middleware import api_key_metrics

        metrics = api_key_metrics.get_metrics()

        user_key_ids = [k["key_id"] for k in keys]
        user_requests = sum(
            count
            for key_id, count in metrics["request_counts"].items()
            if key_id in user_key_ids
        )

        return {
            "user_id": user_id,
            "summary": {
                "total_keys": total_keys,
                "active_keys": active_keys,
                "expired_keys": expired_keys,
                "revoked_keys": total_keys - active_keys - expired_keys,
                "total_usage": total_usage,
                "recent_requests": user_requests,
            },
            "keys": [
                {
                    "key_id": key["key_id"],
                    "name": key["name"],
                    "status": key["status"],
                    "usage_count": key["usage_count"],
                    "last_used_at": key["last_used_at"],
                }
                for key in keys
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get usage stats: {str(e)}"
        )


@router.get("/admin/metrics")
async def get_admin_api_key_metrics(current_user: dict = Depends(require_auth)):
    """
    Get system-wide API key metrics (admin only).

    Args:
        current_user: Authenticated user

    Returns:
        System-wide API key metrics
    """
    # Check admin privileges
    user_role = current_user.get("role", "").lower()
    if user_role not in ["admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")

    try:
        from src.api.auth.api_key_middleware import api_key_metrics

        metrics = api_key_metrics.get_metrics()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "api_key_metrics": metrics,
            "system_stats": {
                "total_api_requests": metrics["total_api_requests"],
                "active_api_keys": metrics["active_api_keys"],
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get admin metrics: {str(e)}"
        )


@router.post("/admin/cleanup")
async def cleanup_expired_keys(current_user: dict = Depends(require_auth)):
    """
    Clean up expired API keys (admin only).

    Args:
        current_user: Authenticated user

    Returns:
        Cleanup results
    """
    # Check admin privileges
    user_role = current_user.get("role", "").lower()
    if user_role not in ["admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")

    try:
        cleaned_count = await api_key_manager.cleanup_expired_keys()

        return {
            "message": f"Cleaned up {cleaned_count} expired API keys",
            "cleaned_count": cleaned_count,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to cleanup expired keys: {str(e)}"
        )


# Health check endpoint for API key system
@router.get("/health")
async def api_key_system_health():
    """
    Health check for the API key management system.

    Returns:
        System health status
    """
    try:
        # Check if DynamoDB is available
        dynamodb_status = "connected" if api_key_manager.store.table else "disconnected"

        return {
            "status": "healthy",
            "components": {
                "api_key_manager": "operational",
                "dynamodb": dynamodb_status,
                "key_generation": "operational",
            },
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
