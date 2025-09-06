"""
Administrative Panel API Routes.

Provides endpoints for system administration, configuration management,
user management, and monitoring.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth.jwt_auth import require_auth
from src.database.snowflake_analytics_connector import SnowflakeAnalyticsConnector

router = APIRouter(prefix="/admin", tags=["admin"])


class SystemHealthResponse(BaseModel):
    """Response model for system health check."""
    
    status: str
    timestamp: str
    database_status: str
    api_status: str
    services: Dict[str, Any]
    metrics: Dict[str, Any]


class UserManagementRequest(BaseModel):
    """Request model for user management operations."""
    
    user_id: str = Field(..., description="User ID")
    action: str = Field(..., description="Action: activate, deactivate, delete")
    reason: Optional[str] = Field(None, description="Reason for action")


class SystemConfigUpdate(BaseModel):
    """Request model for system configuration updates."""
    
    setting_key: str = Field(..., description="Configuration setting key")
    setting_value: Any = Field(..., description="New value for setting")
    category: Optional[str] = Field(None, description="Configuration category")


# Admin-only dependency
async def require_admin(user: dict = Depends(require_auth)) -> dict:
    """Ensure user has admin role."""
    if user.get("role", "").lower() not in ["admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


async def get_db():
    """Dependency to get database connection."""
    account = os.getenv("SNOWFLAKE_ACCOUNT")
    if not account:
        raise HTTPException(
            status_code=500, detail="SNOWFLAKE_ACCOUNT environment variable not set"
        )

    db = SnowflakeAnalyticsConnector(
        account=account,
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        database=os.getenv("SNOWFLAKE_DATABASE", "NEURONEWS"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "ANALYTICS_WH"),
    )
    try:
        db.connect()
        yield db
    finally:
        db.disconnect()


@router.get("/health", response_model=SystemHealthResponse)
async def get_system_health(
    admin_user: dict = Depends(require_admin),
    db: SnowflakeAnalyticsConnector = Depends(get_db),
):
    """
    Get comprehensive system health status.
    
    Returns database connectivity, API status, and service metrics.
    """
    try:
        # Check database health
        db_status = "healthy"
        try:
            await db.execute_query("SELECT 1", [])
        except Exception:
            db_status = "unhealthy"
        
        # Get basic metrics
        metrics_query = """
            SELECT 
                COUNT(*) as total_articles,
                COUNT(DISTINCT source) as unique_sources,
                COUNT(DISTINCT category) as unique_categories,
                MAX(publish_date) as latest_article_date
            FROM news_articles
            WHERE publish_date >= CURRENT_DATE - INTERVAL '7 days'
        """
        
        metrics_results = await db.execute_query(metrics_query, [])
        metrics_row = metrics_results[0] if metrics_results else [0, 0, 0, None]
        
        services = {
            "database": {
                "status": db_status,
                "type": "snowflake",
                "last_checked": datetime.utcnow().isoformat()
            },
            "api": {
                "status": "healthy",
                "uptime": "active",  # Would be calculated from actual uptime
                "last_checked": datetime.utcnow().isoformat()
            }
        }
        
        metrics = {
            "total_articles_7d": int(metrics_row[0]),
            "unique_sources": int(metrics_row[1]),
            "unique_categories": int(metrics_row[2]),
            "latest_article_date": metrics_row[3].isoformat() if metrics_row[3] else None
        }
        
        overall_status = "healthy" if db_status == "healthy" else "degraded"
        
        return SystemHealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat(),
            database_status=db_status,
            api_status="healthy",
            services=services,
            metrics=metrics
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving system health: {}".format(str(e))
        )


@router.get("/users")
async def get_user_list(
    limit: int = Query(100, ge=1, le=1000, description="Maximum users to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    status_filter: Optional[str] = Query(None, description="Filter by user status"),
    admin_user: dict = Depends(require_admin),
    db: SnowflakeAnalyticsConnector = Depends(get_db),
):
    """
    Get list of system users with their activity status.
    """
    try:
        # This would typically query a users table
        # For now, return mock admin data as this is a testing implementation
        users = [
            {
                "user_id": "admin-001",
                "username": "admin",
                "email": "admin@neuronews.com",
                "role": "admin",
                "status": "active",
                "last_login": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }
        ]
        
        return {
            "users": users,
            "total_count": len(users),
            "returned_count": len(users),
            "offset": offset,
            "has_more": False
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving user list: {}".format(str(e))
        )


@router.post("/users/manage")
async def manage_user(
    request: UserManagementRequest,
    admin_user: dict = Depends(require_admin),
):
    """
    Perform user management operations (activate, deactivate, delete).
    """
    try:
        if request.action not in ["activate", "deactivate", "delete"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid action. Must be: activate, deactivate, or delete"
            )
        
        # Mock implementation - would typically update user status in database
        return {
            "message": "User {} successfully {}d".format(request.user_id, request.action),
            "user_id": request.user_id,
            "action": request.action,
            "reason": request.reason,
            "performed_by": admin_user.get("sub"),
            "performed_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error managing user: {}".format(str(e))
        )


@router.get("/system/stats")
async def get_system_statistics(
    days_back: int = Query(30, ge=1, le=365, description="Days to look back"),
    admin_user: dict = Depends(require_admin),
    db: SnowflakeAnalyticsConnector = Depends(get_db),
):
    """
    Get comprehensive system usage statistics.
    """
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        # Article statistics
        article_stats_query = """
            SELECT 
                COUNT(*) as total_articles,
                COUNT(DISTINCT source) as unique_sources,
                COUNT(DISTINCT category) as unique_categories,
                AVG(CASE WHEN sentiment_score IS NOT NULL THEN sentiment_score END) as avg_sentiment
            FROM news_articles
            WHERE publish_date >= %s AND publish_date <= %s
        """
        
        article_results = await db.execute_query(
            article_stats_query, [start_date, end_date]
        )
        article_row = article_results[0] if article_results else [0, 0, 0, 0]
        
        # Category breakdown
        category_query = """
            SELECT category, COUNT(*) as count
            FROM news_articles
            WHERE publish_date >= %s AND publish_date <= %s
              AND category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
            LIMIT 10
        """
        
        category_results = await db.execute_query(
            category_query, [start_date, end_date]
        )
        
        # Source breakdown
        source_query = """
            SELECT source, COUNT(*) as count
            FROM news_articles
            WHERE publish_date >= %s AND publish_date <= %s
              AND source IS NOT NULL
            GROUP BY source
            ORDER BY count DESC
            LIMIT 10
        """
        
        source_results = await db.execute_query(
            source_query, [start_date, end_date]
        )
        
        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days_back
            },
            "article_stats": {
                "total_articles": int(article_row[0]),
                "unique_sources": int(article_row[1]),
                "unique_categories": int(article_row[2]),
                "avg_sentiment": float(article_row[3]) if article_row[3] else None
            },
            "top_categories": [
                {"category": row[0], "count": int(row[1])}
                for row in category_results
            ],
            "top_sources": [
                {"source": row[0], "count": int(row[1])}
                for row in source_results
            ],
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving system statistics: {}".format(str(e))
        )


@router.post("/system/config")
async def update_system_config(
    config_update: SystemConfigUpdate,
    admin_user: dict = Depends(require_admin),
):
    """
    Update system configuration settings.
    """
    try:
        # Mock implementation - would typically update configuration in database/cache
        return {
            "message": "Configuration setting updated successfully",
            "setting_key": config_update.setting_key,
            "old_value": "previous_value",  # Would get from actual config
            "new_value": config_update.setting_value,
            "category": config_update.category,
            "updated_by": admin_user.get("sub"),
            "updated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error updating configuration: {}".format(str(e))
        )


@router.get("/system/config")
async def get_system_config(
    category: Optional[str] = Query(None, description="Filter by configuration category"),
    admin_user: dict = Depends(require_admin),
):
    """
    Get current system configuration settings.
    """
    try:
        # Mock configuration - would typically come from database/config service
        config = {
            "database": {
                "connection_timeout": 30,
                "max_connections": 100,
                "retry_attempts": 3
            },
            "api": {
                "rate_limit_requests_per_minute": 1000,
                "max_request_size_mb": 10,
                "enable_caching": True
            },
            "system": {
                "maintenance_mode": False,
                "debug_logging": False,
                "backup_frequency_hours": 24
            }
        }
        
        if category:
            if category in config:
                return {category: config[category]}
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Configuration category '{}' not found".format(category)
                )
        
        return {
            "configuration": config,
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving configuration: {}".format(str(e))
        )


@router.post("/system/maintenance")
async def toggle_maintenance_mode(
    enabled: bool = Query(..., description="Enable/disable maintenance mode"),
    message: Optional[str] = Query(None, description="Maintenance message"),
    admin_user: dict = Depends(require_admin),
):
    """
    Enable or disable system maintenance mode.
    """
    try:
        # Mock implementation - would typically update system state
        return {
            "message": "Maintenance mode {} successfully".format(
                "enabled" if enabled else "disabled"
            ),
            "maintenance_enabled": enabled,
            "maintenance_message": message,
            "changed_by": admin_user.get("sub"),
            "changed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error toggling maintenance mode: {}".format(str(e))
        )


@router.get("/logs")
async def get_system_logs(
    level: str = Query("ERROR", description="Log level filter"),
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum logs to return"),
    admin_user: dict = Depends(require_admin),
):
    """
    Get recent system logs for monitoring and debugging.
    """
    try:
        # Mock logs - would typically come from logging service
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        logs = [
            {
                "timestamp": datetime.utcnow().isoformat(),
                "level": level,
                "component": "api.routes.news",
                "message": "Database query executed successfully",
                "request_id": "req-12345",
                "user_id": "user-67890"
            }
        ]
        
        return {
            "logs": logs,
            "total_count": len(logs),
            "level_filter": level,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours
            },
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving system logs: {}".format(str(e))
        )