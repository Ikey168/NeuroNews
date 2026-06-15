"""
API routes for local dashboard management (Issue #49).

This module exposes a small REST surface over the local, file-based dashboard
backend in src.dashboards.quicksight_service. It no longer depends on AWS
QuickSight or boto3; all operations read/write local JSON definition files.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.dashboards.quicksight_service import (
    DashboardType,
    LocalDashboardConfig,
    LocalDashboardService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/dashboards",
    tags=["dashboards"],
    responses={404: {"description": "Not found"}},
)


def get_dashboard_service() -> LocalDashboardService:
    """Construct a local dashboard service from environment configuration."""
    return LocalDashboardService(LocalDashboardConfig.from_env())


@router.post("/setup")
async def setup_dashboards():
    """Set up the local dashboard backend (data source, datasets, analyses,
    dashboards)."""
    service = get_dashboard_service()
    return await service.setup_dashboard_resources()


@router.post("/layouts/{layout_type}")
async def create_dashboard_layout(layout_type: str):
    """Create a dashboard layout for a specific insight type."""
    try:
        layout = DashboardType(layout_type)
    except ValueError:
        valid = ", ".join(t.value for t in DashboardType)
        raise HTTPException(
            status_code=400,
            detail="Invalid layout type '{0}'. Valid types: {1}".format(
                layout_type, valid
            ),
        )

    service = get_dashboard_service()
    result = await service.create_dashboard_layout(layout)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


@router.get("/")
async def list_dashboards():
    """List all local NeuroNews dashboards."""
    service = get_dashboard_service()
    return await service.get_dashboard_info()


@router.get("/{dashboard_id}")
async def get_dashboard(dashboard_id: str):
    """Get information about a specific local dashboard."""
    service = get_dashboard_service()
    result = await service.get_dashboard_info(dashboard_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.delete("/{dashboard_id}")
async def delete_dashboard(dashboard_id: str):
    """Delete a local dashboard definition."""
    service = get_dashboard_service()
    result = await service.delete_dashboard(dashboard_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.post("/refresh")
async def setup_real_time_updates():
    """Configure local refresh schedules for datasets."""
    service = get_dashboard_service()
    return await service.setup_real_time_updates()


@router.get("/validate/setup")
async def validate_setup(dashboard_id: Optional[str] = Query(default=None)):
    """Validate the local dashboard setup and resources."""
    service = get_dashboard_service()
    return await service.validate_setup()
