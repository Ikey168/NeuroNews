"""
API Rate Limiting Routes (Issue #59)

Provides endpoints for checking and managing API rate limits.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.auth.jwt_auth import require_auth
from src.api.middleware.rate_limit_middleware import (
    RateLimitConfig,
    RateLimitStore,
    SuspiciousActivityDetector,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["rate-limits"])


# Response Models
class UserLimitsResponse(BaseModel):
    """Response model for user API limits."""

    user_id: str
    tier: str
    limits: Dict[str, int]
    current_usage: Dict[str, int]
    remaining: Dict[str, int]
    reset_times: Dict[str, str]
    concurrent_requests: int
    max_concurrent: int


class SuspiciousActivityResponse(BaseModel):
    """Response model for suspicious activity alerts."""

    user_id: str
    alerts: List[str]
    timestamp: str
    details: Dict[str, Any]


class UsageStatisticsResponse(BaseModel):
    """Response model for usage statistics."""

    total_requests: int
    unique_users: int
    tier_distribution: Dict[str, int]
    top_endpoints: List[Dict[str, Any]]
    suspicious_activities: int
    rate_limit_violations: int


class TierUpgradeResponse(BaseModel):
    """Response model for tier upgrade information."""

    current_tier: str
    available_tiers: List[Dict[str, Any]]
    upgrade_benefits: Dict[str, List[str]]


# Global instances (would be dependency injected in production)
rate_limit_store = RateLimitStore()
rate_limit_config = RateLimitConfig()
suspicious_detector = SuspiciousActivityDetector(rate_limit_store, rate_limit_config)


@router.get("/api_limits", response_model=UserLimitsResponse)
async def get_api_limits(
    user_id: str = Query(..., description="User ID to check limits for"),
    current_user: dict = Depends(require_auth),
):
    """
    Get API rate limits and current usage for a user.

    Args:
        user_id: The user ID to check limits for
        current_user: Current authenticated user

    Returns:
        User's rate limits, current usage, and remaining quota

    Raises:
        HTTPException: If user not found or access denied
    """
    # Authorization check - users can only see their own limits, admins can see any
    if current_user.get("user_id") != user_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Get user tier (in production, this would come from database)
        user_tier_name = await _get_user_tier(user_id)
        user_tier = _get_tier_config(user_tier_name)

        # Get current usage
        current_usage = await rate_limit_store.get_request_counts(user_id)

        # Calculate remaining requests
        remaining = {
            "minute": max(0, user_tier.requests_per_minute - current_usage["minute"]),
            "hour": max(0, user_tier.requests_per_hour - current_usage["hour"]),
            "day": max(0, user_tier.requests_per_day - current_usage["day"]),
        }

        # Calculate reset times
        now = datetime.now()
        reset_times = {
            "minute": (
                now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            ).isoformat(),
            "hour": (
                now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            ).isoformat(),
            "day": (
                now.replace(hour=0, minute=0, second=0, microsecond=0)
                + timedelta(days=1)
            ).isoformat(),
        }

        # Get concurrent request info
        concurrent_requests = 0
        if rate_limit_store.use_redis:
            try:
                concurrent_requests = (
                    await rate_limit_store._get_concurrent_count_redis(user_id)
                )
            except:
                pass
        else:
            concurrent_requests = rate_limit_store.memory_store[user_id]["concurrent"]

        return UserLimitsResponse(
            user_id=user_id,
            tier=user_tier.name,
            limits={
                "requests_per_minute": user_tier.requests_per_minute,
                "requests_per_hour": user_tier.requests_per_hour,
                "requests_per_day": user_tier.requests_per_day,
                "burst_limit": user_tier.burst_limit,
                "concurrent_requests": user_tier.concurrent_requests,
            },
            current_usage=current_usage,
            remaining=remaining,
            reset_times=reset_times,
            concurrent_requests=concurrent_requests,
            max_concurrent=user_tier.concurrent_requests,
        )

    except Exception as e:
        logger.error(f"Error getting API limits for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/api_limits/suspicious_activity", response_model=List[SuspiciousActivityResponse]
)
async def get_suspicious_activity(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    current_user: dict = Depends(require_auth),
):
    """
    Get suspicious activity alerts (admin only).

    Args:
        hours: Number of hours to look back
        current_user: Current authenticated user

    Returns:
        List of suspicious activity alerts

    Raises:
        HTTPException: If user is not admin
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Get recent alerts
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_alerts = [
            alert
            for alert in suspicious_detector.alerts
            if datetime.fromisoformat(alert["timestamp"]) > cutoff_time
        ]

        return [
            SuspiciousActivityResponse(
                user_id=alert["user_id"],
                alerts=alert["alerts"],
                timestamp=alert["timestamp"],
                details={
                    "ip_address": alert["ip_address"],
                    "endpoint": alert["endpoint"],
                },
            )
            for alert in recent_alerts
        ]

    except Exception as e:
        logger.error(f"Error getting suspicious activity: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api_limits/usage_statistics", response_model=UsageStatisticsResponse)
async def get_usage_statistics(current_user: dict = Depends(require_auth)):
    """
    Get API usage statistics (admin only).

    Args:
        current_user: Current authenticated user

    Returns:
        Overall API usage statistics

    Raises:
        HTTPException: If user is not admin
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # In production, this would query the database for statistics
        # For now, return mock data
        return UsageStatisticsResponse(
            total_requests=125430,
            unique_users=1247,
            tier_distribution={"free": 1100, "premium": 120, "enterprise": 27},
            top_endpoints=[
                {"endpoint": "/news/articles", "requests": 45230},
                {"endpoint": "/graph/entities", "requests": 23450},
                {"endpoint": "/api/v1/breaking-news", "requests": 15670},
                {"endpoint": "/sentiment/trends", "requests": 12890},
                {"endpoint": "/topics/trending", "requests": 8760},
            ],
            suspicious_activities=len(suspicious_detector.alerts),
            rate_limit_violations=342,
        )

    except Exception as e:
        logger.error(f"Error getting usage statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api_limits/tier_info", response_model=TierUpgradeResponse)
async def get_tier_info(current_user: dict = Depends(require_auth)):
    """
    Get information about available tiers and upgrade benefits.

    Args:
        current_user: Current authenticated user

    Returns:
        Information about user tiers and upgrade benefits
    """
    try:
        user_id = current_user.get("user_id", current_user.get("id"))
        current_tier = await _get_user_tier(user_id)

        available_tiers = [
            {
                "name": "free",
                "price": 0,
                "requests_per_day": rate_limit_config.FREE_TIER.requests_per_day,
                "concurrent_requests": rate_limit_config.FREE_TIER.concurrent_requests,
            },
            {
                "name": "premium",
                "price": 29,
                "requests_per_day": rate_limit_config.PREMIUM_TIER.requests_per_day,
                "concurrent_requests": rate_limit_config.PREMIUM_TIER.concurrent_requests,
            },
            {
                "name": "enterprise",
                "price": 199,
                "requests_per_day": rate_limit_config.ENTERPRISE_TIER.requests_per_day,
                "concurrent_requests": rate_limit_config.ENTERPRISE_TIER.concurrent_requests,
            },
        ]

        upgrade_benefits = {
            "premium": [
                "20x more daily requests",
                "3x more concurrent connections",
                "Priority support",
                "Advanced analytics",
            ],
            "enterprise": [
                "500x more daily requests",
                "17x more concurrent connections",
                "Dedicated support",
                "Custom integrations",
                "SLA guarantees",
            ],
        }

        return TierUpgradeResponse(
            current_tier=current_tier,
            available_tiers=available_tiers,
            upgrade_benefits=upgrade_benefits,
        )

    except Exception as e:
        logger.error(f"Error getting tier info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api_limits/reset")
async def reset_user_limits(
    user_id: str = Query(..., description="User ID to reset limits for"),
    current_user: dict = Depends(require_auth),
):
    """
    Reset rate limits for a user (admin only).

    Args:
        user_id: The user ID to reset limits for
        current_user: Current authenticated user

    Returns:
        Success message

    Raises:
        HTTPException: If user is not admin
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Reset rate limits
        if rate_limit_store.use_redis:
            await _reset_user_limits_redis(user_id)
        else:
            _reset_user_limits_memory(user_id)

        logger.info(
            f"Rate limits reset for user {user_id} by admin {current_user.get('user_id')}"
        )

        return {"message": f"Rate limits reset successfully for user {user_id}"}

    except Exception as e:
        logger.error(f"Error resetting limits for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api_limits/health")
async def health_check():
    """
    Health check endpoint for rate limiting system.

    Returns:
        Health status of rate limiting components
    """
    health_status = {
        "status": "healthy",
        "store_backend": "redis" if rate_limit_store.use_redis else "memory",
        "timestamp": datetime.now().isoformat(),
    }

    # Test store connectivity
    try:
        if rate_limit_store.use_redis:
            await rate_limit_store.redis_client.ping()
            health_status["redis_connection"] = "connected"
        else:
            health_status["memory_store"] = "active"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["error"] = str(e)

    return health_status


# Helper functions
async def _get_user_tier(user_id: str) -> str:
    """Get user tier from database (mock implementation)."""
    # In production, this would query the user database
    # For demo purposes, return based on user_id pattern
    if user_id.startswith("enterprise_"):
        return "enterprise"
    elif user_id.startswith("premium_"):
        return "premium"
    else:
        return "free"


def _get_tier_config(tier_name: str):
    """Get tier configuration."""
    tier_map = {
        "free": rate_limit_config.FREE_TIER,
        "premium": rate_limit_config.PREMIUM_TIER,
        "enterprise": rate_limit_config.ENTERPRISE_TIER,
    }
    return tier_map.get(tier_name, rate_limit_config.FREE_TIER)


async def _reset_user_limits_redis(user_id: str):
    """Reset user limits in Redis."""
    import time

    now = time.time()

    keys_to_delete = [
        f"rate_limit:{user_id}:minute:{int(now // 60)}",
        f"rate_limit:{user_id}:hour:{int(now // 3600)}",
        f"rate_limit:{user_id}:day:{int(now // 86400)}",
        f"concurrent:{user_id}",
    ]

    for key in keys_to_delete:
        await rate_limit_store.redis_client.delete(key)


def _reset_user_limits_memory(user_id: str):
    """Reset user limits in memory."""
    if user_id in rate_limit_store.memory_store:
        rate_limit_store.memory_store[user_id] = {
            "requests": [],
            "concurrent": 0,
            "metrics": [],
        }
