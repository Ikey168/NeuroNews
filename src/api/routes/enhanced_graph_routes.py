"""
Enhanced Knowledge Graph API Routes
Issue #75: Deploy Knowledge Graph API in Kubernetes

This module provides optimized FastAPI routes for the Knowledge Graph API
with caching, performance monitoring, and real-time execution capabilities.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.graph.optimized_api import OptimizedGraphAPI, create_optimized_graph_api

logger = logging.getLogger(__name__)

# Global instance for the optimized graph API
optimized_graph_api: Optional[OptimizedGraphAPI] = None


# Pydantic models for request/response validation
class RelatedEntitiesRequest(BaseModel):
    entity: str = Field(
        ..., min_length=1, description="Entity name to find relationships for"
    )
    entity_type: Optional[str] = Field(
        None, description="Type of entity (Organization, Person, Event)"
    )
    max_depth: int = Field(
        2, ge=1, le=5, description="Maximum relationship depth to traverse"
    )
    relationship_types: Optional[List[str]] = Field(
        None, description="Filter by relationship types"
    )
    use_cache: bool = Field(True, description="Whether to use caching")


class EventTimelineRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="Topic to create timeline for")
    start_date: Optional[datetime] = Field(None, description="Start date for timeline")
    end_date: Optional[datetime] = Field(None, description="End date for timeline")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of events")
    use_cache: bool = Field(True, description="Whether to use caching")


class EntitySearchRequest(BaseModel):
    search_term: str = Field(..., min_length=2, description="Term to search for")
    entity_types: Optional[List[str]] = Field(
        None, description="Filter by entity types"
    )
    limit: int = Field(50, ge=1, le=500, description="Maximum number of results")
    use_cache: bool = Field(True, description="Whether to use caching")


class CacheManagementRequest(BaseModel):
    pattern: Optional[str] = Field(
        None, description="Pattern to match for cache clearing"
    )
    force: bool = Field(False, description="Force cache clearing without confirmation")


@asynccontextmanager
async def lifespan_manager(app):
    """Application lifespan manager for graph API initialization."""
    global optimized_graph_api

    logger.info("Initializing optimized Knowledge Graph API...")

    try:
        # Get Neptune endpoint from environment
        neptune_endpoint = os.getenv("NEPTUNE_ENDPOINT", "wss://localhost:8182/gremlin")

        # Create optimized graph API
        optimized_graph_api = create_optimized_graph_api(neptune_endpoint)

        # Initialize the API (includes Redis connection)
        await optimized_graph_api.initialize()

        # Connect to Neptune
        await optimized_graph_api.graph.connect()

        logger.info("Optimized Knowledge Graph API initialized successfully")

    except Exception as e:
        logger.error("Failed to initialize optimized graph API: {0}".format(e))
        optimized_graph_api = None

    # Yield control to the application
    yield

    # Cleanup on shutdown
    logger.info("Shutting down optimized Knowledge Graph API...")
    if optimized_graph_api:
        try:
            await optimized_graph_api.close()
            await optimized_graph_api.graph.close()
            logger.info("Optimized graph API closed successfully")
        except Exception as e:
            logger.error("Error during graph API shutdown: {0}".format(e))


# Create router with enhanced configuration
router = APIRouter(
    prefix="/api/v2/graph",
    tags=["knowledge-graph-v2"],
    responses={
        404: {"description": "Entity not found"},
        500: {"description": "Internal server error"},
        503: {"description": "Service unavailable"},
    },
)


async def get_optimized_graph() -> OptimizedGraphAPI:
    """Dependency to get the optimized graph API instance."""
    if optimized_graph_api is None:
        logger.error("Optimized graph API not initialized")
        raise HTTPException(
            status_code=503, detail="Knowledge Graph API service not available"
        )

    return optimized_graph_api


@router.get(
    "/related-entities",
    summary="Get Related Entities",
    description="Find entities related to a given entity with caching and optimization",
)
async def get_related_entities_v2(
    entity: str = Query(..., description="Entity name to find relationships for"),
    entity_type: Optional[str] = Query(
        None, description="Type of entity (Organization, Person, Event)"
    ),
    max_depth: int = Query(
        2, ge=1, le=5, description="Maximum relationship depth to traverse"
    ),
    relationship_types: Optional[str] = Query(
        None, description="Comma-separated relationship types"
    ),
    use_cache: bool = Query(True, description="Whether to use caching"),
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Get entities related to the specified entity with advanced caching and optimization.

    This endpoint provides:
    - Redis-based result caching for frequently accessed queries
    - Query optimization with configurable depth limits
    - Real-time performance monitoring
    - Automatic retry logic for failed queries
    """
    try:
        # Parse relationship types if provided
        parsed_relationship_types = None
        if relationship_types:
            parsed_relationship_types = [
                rt.strip() for rt in relationship_types.split(",")
            ]

        # Execute optimized query
        result = await graph_api.get_related_entities_optimized(
            entity=entity,
            entity_type=entity_type,
            max_depth=max_depth,
            relationship_types=parsed_relationship_types,
            use_cache=use_cache,
        )

        # Add metadata
        result["metadata"] = {
            "api_version": "v2",
            "cache_used": use_cache,
            "query_timestamp": datetime.now().isoformat(),
            "optimized": True,
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in get_related_entities_v2: {0}".format(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/related-entities",
    summary="Get Related Entities (POST)",
    description="Find related entities using POST request with full parameter validation",
)
async def get_related_entities_v2_post(
    request: RelatedEntitiesRequest,
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Get related entities using POST request with comprehensive request validation.
    """
    try:
        result = await graph_api.get_related_entities_optimized(
            entity=request.entity,
            entity_type=request.entity_type,
            max_depth=request.max_depth,
            relationship_types=request.relationship_types,
            use_cache=request.use_cache,
        )

        result["metadata"] = {
            "api_version": "v2",
            "request_method": "POST",
            "cache_used": request.use_cache,
            "query_timestamp": datetime.now().isoformat(),
            "optimized": True,
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in get_related_entities_v2_post: {0}".format(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/event-timeline",
    summary="Get Event Timeline",
    description="Create optimized timeline of events for a given topic",
)
async def get_event_timeline_v2(
    topic: str = Query(..., description="Topic to create timeline for"),
    start_date: Optional[str] = Query(
        None, description="Start date (ISO format: YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None, description="End date (ISO format: YYYY-MM-DD)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events"),
    use_cache: bool = Query(True, description="Whether to use caching"),
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Get an optimized timeline of events related to a specific topic.

    Features:
    - Date range filtering with validation
    - Result limiting and pagination support
    - Redis caching for frequent timeline queries
    - Performance optimization for large datasets
    """
    try:
        # Parse dates if provided
        parsed_start_date = None
        parsed_end_date = None

        if start_date:
            try:
                parsed_start_date = datetime.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD"
                )

        if end_date:
            try:
                parsed_end_date = datetime.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD"
                )

        # Validate date range
        if (
            parsed_start_date
            and parsed_end_date
            and parsed_start_date > parsed_end_date
        ):
            raise HTTPException(
                status_code=400, detail="start_date must be before end_date"
            )

        # Execute optimized query
        result = await graph_api.get_event_timeline_optimized(
            topic=topic,
            start_date=parsed_start_date,
            end_date=parsed_end_date,
            limit=limit,
            use_cache=use_cache,
        )

        # Add metadata
        result["metadata"] = {
            "api_version": "v2",
            "cache_used": use_cache,
            "query_timestamp": datetime.now().isoformat(),
            "optimized": True,
            "limit": limit,
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in get_event_timeline_v2: {0}".format(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/event-timeline",
    summary="Get Event Timeline (POST)",
    description="Create event timeline using POST request with validation",
)
async def get_event_timeline_v2_post(
    request: EventTimelineRequest,
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Get event timeline using POST request with comprehensive validation.
    """
    try:
        # Validate date range
        if (
            request.start_date
            and request.end_date
            and request.start_date > request.end_date
        ):
            raise HTTPException(
                status_code=400, detail="start_date must be before end_date"
            )

        result = await graph_api.get_event_timeline_optimized(
            topic=request.topic,
            start_date=request.start_date,
            end_date=request.end_date,
            limit=request.limit,
            use_cache=request.use_cache,
        )

        result["metadata"] = {
            "api_version": "v2",
            "request_method": "POST",
            "cache_used": request.use_cache,
            "query_timestamp": datetime.now().isoformat(),
            "optimized": True,
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in get_event_timeline_v2_post: {0}".format(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/search",
    summary="Search Entities",
    description="Search for entities with caching and relevance scoring",
)
async def search_entities_v2(
    q: str = Query(..., min_length=2, description="Search term"),
    types: Optional[str] = Query(
        None, description="Comma-separated entity types to filter by"
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of results"),
    use_cache: bool = Query(True, description="Whether to use caching"),
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Search for entities by name or properties with optimization and relevance scoring.

    Features:
    - Full-text search across entity names and properties
    - Entity type filtering
    - Relevance scoring for better result ranking
    - Redis caching for frequent searches
    - Performance optimization for large datasets
    """
    try:
        # Parse entity types if provided
        parsed_types = None
        if types:
            parsed_types = [t.strip() for t in types.split(",")]

        # Execute optimized search
        result = await graph_api.search_entities_optimized(
            search_term=q, entity_types=parsed_types, limit=limit, use_cache=use_cache
        )

        # Add metadata
        result["metadata"] = {
            "api_version": "v2",
            "cache_used": use_cache,
            "query_timestamp": datetime.now().isoformat(),
            "optimized": True,
            "limit": limit,
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in search_entities_v2: {0}".format(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/search",
    summary="Search Entities (POST)",
    description="Search entities using POST request with validation",
)
async def search_entities_v2_post(
    request: EntitySearchRequest,
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Search entities using POST request with comprehensive validation.
    """
    try:
        result = await graph_api.search_entities_optimized(
            search_term=request.search_term,
            entity_types=request.entity_types,
            limit=request.limit,
            use_cache=request.use_cache,
        )

        result["metadata"] = {
            "api_version": "v2",
            "request_method": "POST",
            "cache_used": request.use_cache,
            "query_timestamp": datetime.now().isoformat(),
            "optimized": True,
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in search_entities_v2_post: {0}".format(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/stats",
    summary="API Statistics",
    description="Get caching and performance statistics for the Knowledge Graph API",
)
async def get_api_stats(
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Get comprehensive statistics about the Knowledge Graph API performance and caching.

    Returns:
    - Cache hit rates and performance metrics
    - Query performance statistics
    - Configuration information
    - Redis connection status
    """
    try:
        stats = await graph_api.get_cache_stats()

        # Add API-specific metadata
        stats["api_info"] = {
            "version": "v2",
            "uptime": "Runtime information would go here",
            "endpoints": [
                "/related-entities",
                "/event-timeline",
                "/search",
                "/stats",
                "/health",
                "/cache/clear",
            ],
        }

        return stats

    except Exception as e:
        logger.error("Error getting API stats: {0}".format(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve API statistics")


@router.get(
    "/health",
    summary="Health Check",
    description="Comprehensive health check for the Knowledge Graph API",
)
async def health_check_v2(
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Perform comprehensive health check including Neptune, Redis, and API status.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "api_version": "v2",
        "components": {},
    }

    overall_healthy = True

    # Check Neptune connection
    try:
        await graph_api.graph._execute_traversal(graph_api.graph.g.V().limit(1))
        health_status["components"]["neptune"] = {
            "status": "healthy",
            "message": "Neptune connection successful",
        }
    except Exception as e:
        health_status["components"]["neptune"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_healthy = False

    # Check Redis connection
    try:
        if graph_api.redis_client:
            await graph_api.redis_client.ping()
            health_status["components"]["redis"] = {
                "status": "healthy",
                "message": "Redis connection successful",
            }
        else:
            health_status["components"]["redis"] = {
                "status": "disabled",
                "message": "Redis not configured, using memory cache",
            }
    except Exception as e:
        health_status["components"]["redis"] = {"status": "unhealthy", "error": str(e)}
        # Redis failure is not critical since we have memory cache fallback

    # Check API performance
    try:
        stats = await graph_api.get_cache_stats()
        error_rate = stats["performance"]["error_rate"]

        if error_rate > 0.1:  # More than 10% error rate
            health_status["components"]["api"] = {
                "status": "degraded",
                "error_rate": error_rate,
                "message": "High error rate detected",
            }
        else:
            health_status["components"]["api"] = {
                "status": "healthy",
                "error_rate": error_rate,
                "message": "API performing normally",
            }
    except Exception as e:
        health_status["components"]["api"] = {"status": "unknown", "error": str(e)}

    # Set overall status
    if not overall_healthy:
        health_status["status"] = "unhealthy"
        return JSONResponse(status_code=503, content=health_status)

    return health_status


@router.delete(
    "/cache",
    summary="Clear Cache",
    description="Clear cached results with optional pattern matching",
)
async def clear_cache_v2(
    pattern: Optional[str] = Query(
        None, description="Pattern to match for selective clearing"
    ),
    force: bool = Query(False, description="Force clearing without confirmation"),
    background_tasks: BackgroundTasks = None,
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Clear cached results from Redis and memory cache.

    Parameters:
    - pattern: Optional pattern to match cache keys for selective clearing
    - force: Force clearing without additional confirmation
    """
    try:
        # Perform cache clearing
        result = await graph_api.clear_cache(pattern=pattern)

        # Add operation metadata
        result["metadata"] = {
            "api_version": "v2",
            "operation": "cache_clear",
            "timestamp": datetime.now().isoformat(),
            "forced": force,
        }

        logger.info(f"Cache cleared: {result['cleared_entries']} entries")
        return result

    except Exception as e:
        logger.error("Error clearing cache: {0}".format(e))
        raise HTTPException(status_code=500, detail="Failed to clear cache")


@router.post(
    "/cache/clear",
    summary="Clear Cache (POST)",
    description="Clear cache using POST request with validation",
)
async def clear_cache_v2_post(
    request: CacheManagementRequest,
    background_tasks: BackgroundTasks,
    graph_api: OptimizedGraphAPI = Depends(get_optimized_graph),
) -> Dict[str, Any]:
    """
    Clear cache using POST request with comprehensive validation.
    """
    try:
        result = await graph_api.clear_cache(pattern=request.pattern)

        result["metadata"] = {
            "api_version": "v2",
            "request_method": "POST",
            "operation": "cache_clear",
            "timestamp": datetime.now().isoformat(),
            "forced": request.force,
        }

        logger.info(
            f"Cache cleared via POST: {
                result['cleared_entries']} entries"
        )
        return result

    except Exception as e:
        logger.error("Error clearing cache via POST: {0}".format(e))
        raise HTTPException(status_code=500, detail="Failed to clear cache")


# Note: Exception handlers should be added at the FastAPI app level, not router level
# These would be registered in the main app.py file


# Export the lifespan manager for app initialization
__all__ = ["router", "lifespan_manager"]
