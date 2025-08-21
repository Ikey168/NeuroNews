"""
API routes for AWS QuickSight Dashboard management - TEMPORARILY DISABLED

This module is temporarily disabled due to syntax errors in quicksight_service.py
TODO: Fix quicksight_service.py and restore this functionality
"""

from fastapi import APIRouter

# Create empty router for now
router = APIRouter(
    prefix="/api/v1/dashboards",
    tags=["dashboards"],
    responses={404: {"description": "Not found"}},
)

# All endpoints are temporarily disabled
# Original implementation will be restored after fixing quicksight_service.py syntax errors
