"""
API routes for AWS QuickSight Dashboard management.

This module provides REST API endpoints for Issue #49:
Develop AWS QuickSight Dashboard for News Insights.

Endpoints:
- POST /api/v1/dashboards/setup - Set up QuickSight resources
- GET /api/v1/dashboards - List all dashboards
- POST /api/v1/dashboards/layout/{layout_type} - Create specific dashboard layout
- PUT /api/v1/dashboards/refresh - Set up real-time updates
- GET /api/v1/dashboards/validate - Validate setup
- GET /api/v1/dashboards/{dashboard_id} - Get specific dashboard info
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from src.dashboards.quicksight_service import (
    DashboardType,
    QuickSightConfig,
    QuickSightDashboardService,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/v1/dashboards",
    tags=["dashboards"],
    responses={404: {"description": "Not found"}},
)

# Global service instance
_quicksight_service: Optional[QuickSightDashboardService] = None


# Pydantic models for requests and responses


class QuickSightSetupRequest(BaseModel):
    """Request model for QuickSight setup."""

    aws_account_id: str = Field(..., description="AWS Account ID")
    region: str = Field(default="us-east-1", description="AWS Region")
    redshift_host: Optional[str] = Field(None, description="Redshift cluster endpoint")
    redshift_database: str = Field(
        default="neuronews", description="Redshift database name"
    )
    redshift_username: Optional[str] = Field(None, description="Redshift username")
    redshift_password: Optional[str] = Field(None, description="Redshift password")


class DashboardLayoutRequest(BaseModel):
    """Request model for creating dashboard layouts."""

    layout_type: str = Field(..., description="Dashboard layout type")
    custom_filters: Optional[List[Dict[str, Any]]] = Field(
        None, description="Custom filters"
    )
    refresh_schedule: Optional[str] = Field("hourly", description="Refresh schedule")


class QuickSightSetupResponse(BaseModel):
    """Response model for QuickSight setup."""

    success: bool
    data_source_created: bool
    datasets_created: List[str]
    analyses_created: List[str]
    dashboards_created: List[str]
    errors: List[str]


class DashboardInfo(BaseModel):
    """Dashboard information model."""

    id: str
    name: str
    url: str
    last_updated: datetime
    created_time: datetime
    status: Optional[str] = None


class DashboardListResponse(BaseModel):
    """Response model for dashboard list."""

    success: bool
    dashboards: List[DashboardInfo]
    total_count: int


class DashboardLayoutResponse(BaseModel):
    """Response model for dashboard layout creation."""

    success: bool
    dashboard_id: Optional[str] = None
    dashboard_url: Optional[str] = None
    error: Optional[str] = None


class ValidationResponse(BaseModel):
    """Response model for setup validation."""

    success: bool
    data_source_valid: bool
    datasets_valid: List[str]
    analyses_valid: List[str]
    dashboards_valid: List[str]
    overall_valid: bool
    errors: List[str]


class RefreshSetupResponse(BaseModel):
    """Response model for refresh setup."""

    success: bool
    refresh_schedules: List[Dict[str, Any]]
    update_frequency: str
    error: Optional[str] = None


# Dependency functions


async def get_quicksight_service() -> QuickSightDashboardService:
    """Get or create QuickSight service instance."""
    global _quicksight_service

    if _quicksight_service is None:
        try:
            _quicksight_service = QuickSightDashboardService()
            logger.info("QuickSight service initialized")
        except Exception as e:
            logger.error("Failed to initialize QuickSight service: {0}".format(e))
            raise HTTPException(
                status_code=503, detail="QuickSight service not available"
            )

    return _quicksight_service


# API Endpoints


@router.post(
    "/setup",
    response_model=QuickSightSetupResponse,
    summary="Set up QuickSight Resources",
    description="""
    Set up AWS QuickSight for interactive visualization.

    This endpoint implements the first requirement of Issue #49:
    "Set up AWS QuickSight for interactive visualization."

    Creates:
    - Redshift data source connection
    - Datasets for different analysis types
    - Base analyses and visualizations
    - Comprehensive dashboard
    """,
)
async def setup_quicksight_resources(
    setup_request: QuickSightSetupRequest,
    service: QuickSightDashboardService = Depends(get_quicksight_service),
):
    """Set up QuickSight resources for news insights."""
    try:
        logger.info("API request to set up QuickSight resources")

        # Update service configuration
        config = QuickSightConfig(
            aws_account_id=setup_request.aws_account_id,
            region=setup_request.region,
            redshift_host=setup_request.redshift_host,
            redshift_database=setup_request.redshift_database,
            redshift_username=setup_request.redshift_username,
            redshift_password=setup_request.redshift_password,
        )

        # Reinitialize service with new config
        global _quicksight_service
        _quicksight_service = QuickSightDashboardService(config)

        # Set up resources
        result = await service.setup_quicksight_resources()

        logger.info("QuickSight setup completed successfully")
        return QuickSightSetupResponse(**result)

    except Exception as e:
        logger.error("Failed to set up QuickSight resources: {0}".format(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to set up QuickSight resources: {0}".format(str(e)),
        )


@router.get(
    "",
    response_model=DashboardListResponse,
    summary="List Dashboards",
    description="Get list of all NeuroNews dashboards in QuickSight.",
)
async def list_dashboards(
    service: QuickSightDashboardService = Depends(get_quicksight_service),
):
    """List all NeuroNews dashboards."""
    try:
        logger.info("API request to list dashboards")

        result = await service.get_dashboard_info()

        if not result["success"]:
            raise HTTPException(
                status_code=500, detail=result.get("error", "Failed to list dashboards")
            )

        dashboards = [
            DashboardInfo(
                id=dashboard["id"],
                name=dashboard["name"],
                url=dashboard["url"],
                last_updated=dashboard["last_updated"],
                created_time=dashboard["created_time"],
            )
            for dashboard in result["dashboards"]
        ]

        return DashboardListResponse(
            success=True, dashboards=dashboards, total_count=result["total_count"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list dashboards: {0}".format(e))
        raise HTTPException(
            status_code=500, detail="Failed to list dashboards: {0}".format(str(e))
        )


@router.post(
    "/layout/{layout_type}",
    response_model=DashboardLayoutResponse,
    summary="Create Dashboard Layout",
    description="""
    Create a dashboard layout for specific insights.

    This implements the second requirement of Issue #49:
    "Create a dashboard layout for trending topics by sentiment,
    knowledge graph entity relationships, event timeline analysis."

    Supported layout types:
    - sentiment_trends: Trending topics by sentiment
    - entity_relationships: Knowledge graph entity relationships
    - event_timeline: Event timeline analysis
    - comprehensive: All insights combined
    """,
)
async def create_dashboard_layout(
    layout_type: str = Path(..., description="Dashboard layout type"),
    layout_request: DashboardLayoutRequest = None,
    service: QuickSightDashboardService = Depends(get_quicksight_service),
):
    """Create specific dashboard layout."""
    try:
        logger.info("API request to create dashboard layout: {0}".format(layout_type))

        # Validate layout type
        try:
            dashboard_type = DashboardType(layout_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid layout type: {0}. Supported types: {1}".format(
                    layout_type, [t.value for t in DashboardType]
                ]),
            )

        # Create dashboard layout
        result = await service.create_dashboard_layout(dashboard_type)

        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to create dashboard layout"),
            )

        logger.info("Successfully created {0} dashboard layout".format(layout_type))
        return DashboardLayoutResponse(
            success=True,
            dashboard_id=result["dashboard_id"],
            dashboard_url=result["dashboard_url"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to create dashboard layout {0}: {1}".format(layout_type, e)
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to create dashboard layout: {0}".format(str(e)),
        )


@router.put(
    "/refresh",
    response_model=RefreshSetupResponse,
    summary="Set up Real-time Updates",
    description="""
    Implement real-time updates from Redshift.

    This implements the fourth requirement of Issue #49:
    "Implement real-time updates from Redshift."

    Sets up automatic refresh schedules for all datasets to ensure
    dashboards show the latest data from the Redshift data warehouse.
    """,
)
async def setup_real_time_updates(
    refresh_frequency: str = Query(
        "hourly", description="Refresh frequency (hourly, daily, weekly)"
    ),
    service: QuickSightDashboardService = Depends(get_quicksight_service),
):
    """Set up real-time updates from Redshift."""
    try:
        logger.info("API request to set up real-time updates")

        # Validate refresh frequency
        valid_frequencies = ["hourly", "daily", "weekly"]
        if refresh_frequency not in valid_frequencies:
            raise HTTPException(
                status_code=400,
                detail="Invalid refresh frequency: {0}. Supported: {1}".format(
                    refresh_frequency, valid_frequencies
                ),
            )

        # Set up real-time updates
        result = await service.setup_real_time_updates()

        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to set up real-time updates"),
            )

        logger.info("Real-time updates set up successfully")
        return RefreshSetupResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to set up real-time updates: {0}".format(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to set up real-time updates: {0}".format(str(e)),
        )


@router.get(
    "/validate",
    response_model=ValidationResponse,
    summary="Validate Setup",
    description="""
    Validate QuickSight setup and resources.

    Checks the status of:
    - Data source connection
    - Created datasets
    - Analysis objects
    - Dashboard availability

    Returns comprehensive validation results.
    """,
)
async def validate_quicksight_setup(
    service: QuickSightDashboardService = Depends(get_quicksight_service),
):
    """Validate QuickSight setup and resources."""
    try:
        logger.info("API request to validate QuickSight setup")

        result = await service.validate_setup()

        logger.info(
            f"Validation completed: {
                'Success' if result['overall_valid'] else 'Issues found'}"
        )
        return ValidationResponse(**result)

    except Exception as e:
        logger.error("Failed to validate setup: {0}".format(e))
        raise HTTPException(
            status_code=500, detail="Failed to validate setup: {0}".format(str(e))
        )


@router.get(
    "/health",
    summary="Health Check",
    description="Health check endpoint for QuickSight dashboard service.",
)
async def health_check():
    """Health check for QuickSight dashboard service."""
    try:
        # Simple health check - don't try to access service
        return {
            "status": "healthy",
            "service": "quicksight-dashboard",
            "timestamp": datetime.now().isoformat(),
            "issue": "49",
            "description": "AWS QuickSight Dashboard for News Insights",
        }
    except Exception as e:
        logger.error("Health check failed: {0}".format(e))
        raise HTTPException(status_code=503, detail="Service unhealthy")


@router.get(
    "/{dashboard_id}",
    response_model=Dict[str, Any],
    summary="Get Dashboard Info",
    description="Get detailed information about a specific dashboard.",
)
async def get_dashboard_info(
    dashboard_id: str = Path(..., description="Dashboard ID"),
    service: QuickSightDashboardService = Depends(get_quicksight_service),
):
    """Get information about a specific dashboard."""
    try:
        logger.info("API request to get dashboard info: {0}".format(dashboard_id))

        result = await service.get_dashboard_info(dashboard_id)

        if not result["success"]:
            raise HTTPException(
                status_code=404, detail="Dashboard not found: {0}".format(dashboard_id)
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get dashboard info for {0}: {1}".format(dashboard_id, e)
        )
        raise HTTPException(
            status_code=500, detail="Failed to get dashboard info: {0}".format(str(e))
        )
