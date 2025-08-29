"""
FastAPI routes for graph-based search and trending topics (Issue #39).

This module provides endpoints for:
- Semantic search for related news using knowledge graph
- Graph-based trending topics analysis
- Performance-optimized query caching
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse

from src.knowledge_graph.graph_builder import GraphBuilder
from src.knowledge_graph.graph_search_service import GraphBasedSearchService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/graph/search", tags=["graph-search", "trending"])

# Global variables for service instances
search_service_instance: Optional[GraphBasedSearchService] = None
graph_builder_instance: Optional[GraphBuilder] = None


async def get_graph_builder() -> GraphBuilder:
    """Dependency to get graph builder instance."""
    global graph_builder_instance
    
    if graph_builder_instance is None:
        import os
        neptune_endpoint = os.getenv("NEPTUNE_ENDPOINT", "ws://localhost:8182/gremlin")
        graph_builder_instance = GraphBuilder(neptune_endpoint)
        try:
            await graph_builder_instance.connect()
            logger.info("Graph builder connected successfully for search service")
        except Exception as e:
            logger.error(f"Failed to connect graph builder: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Graph database service not available: {str(e)}"
            )
    
    if not hasattr(graph_builder_instance, "g") or graph_builder_instance.g is None:
        try:
            await graph_builder_instance.connect()
        except Exception as e:
            logger.error(f"Failed to reconnect graph builder: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail="Graph database connection failed"
            )
    
    return graph_builder_instance


async def get_search_service() -> GraphBasedSearchService:
    """Dependency to get graph search service instance."""
    global search_service_instance
    
    graph_builder = await get_graph_builder()
    
    if search_service_instance is None:
        search_service_instance = GraphBasedSearchService(graph_builder)
        logger.info("Graph search service initialized")
    
    return search_service_instance


@router.get("/semantic")
async def semantic_search_news(
    query: str = Query(..., description="Search term or entity name"),
    entity_types: Optional[List[str]] = Query(
        None, 
        description="Filter by entity types (Organization, Person, Technology, Event, etc.)"
    ),
    relationship_depth: int = Query(
        2, 
        ge=1, 
        le=3, 
        description="Relationship traversal depth (1-3)"
    ),
    limit: int = Query(
        20, 
        ge=1, 
        le=100, 
        description="Maximum number of articles to return"
    ),
    include_sentiment: bool = Query(
        True, 
        description="Include sentiment analysis in results"
    ),
    search_service: GraphBasedSearchService = Depends(get_search_service)
) -> Dict[str, Any]:
    """
    Perform semantic search for related news using knowledge graph relationships.
    
    This endpoint implements the semantic search requirement from Issue #39,
    allowing users to find news articles that are semantically related through
    entity relationships in the knowledge graph.
    
    **Key Features:**
    - Graph-based relationship traversal for finding related content
    - Multi-entity type search across organizations, people, technologies, events
    - Relevance scoring based on graph connections and content similarity
    - Configurable search depth and result filtering
    
    **Example Queries:**
    - "OpenAI" → finds articles about OpenAI and related companies/people
    - "quantum computing" → finds articles about quantum tech and related entities
    - "Elon Musk" → finds articles about Musk and connected organizations/events
    """
    try:
        logger.info(f"Semantic search request: {query}")
        
        # Validate entity types if provided
        valid_entity_types = {
            "Organization", "Person", "Technology", "Event", 
            "Location", "Policy", "Article"
        }
        
        if entity_types:
            invalid_types = set(entity_types) - valid_entity_types
            if invalid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid entity types: {invalid_types}. "
                           f"Valid types: {valid_entity_types}"
                )
        
        # Perform semantic search
        results = await search_service.semantic_search_related_news(
            query_term=query,
            entity_types=entity_types,
            relationship_depth=relationship_depth,
            limit=limit,
            include_sentiment=include_sentiment
        )
        
        # Add API metadata
        results["api_info"] = {
            "endpoint": "/graph/search/semantic",
            "version": "1.0.0",
            "response_time": datetime.utcnow().isoformat()
        }
        
        logger.info(
            f"Semantic search completed: {results.get('total_found', 0)} articles found"
        )
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in semantic search endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error in semantic search: {str(e)}"
        )


@router.get("/trending_topics")
async def get_trending_topics_graph(
    category: Optional[str] = Query(
        None, 
        description="Category filter (Technology, Politics, Business, Health, etc.)"
    ),
    time_window_hours: int = Query(
        24, 
        ge=1, 
        le=168, 
        description="Time window for trend analysis in hours (1-168)"
    ),
    min_connections: int = Query(
        3, 
        ge=1, 
        le=20, 
        description="Minimum graph connections for trending topics"
    ),
    limit: int = Query(
        20, 
        ge=1, 
        le=50, 
        description="Maximum number of trending topics to return"
    ),
    search_service: GraphBasedSearchService = Depends(get_search_service)
) -> Dict[str, Any]:
    """
    Query trending topics based on graph relationships and temporal analysis.
    
    This endpoint implements the trending topics requirement from Issue #39,
    analyzing the knowledge graph to identify topics that are trending based on:
    - Recent mention frequency in articles
    - Graph connectivity and relationship strength  
    - Entity co-occurrence patterns
    - Temporal velocity and acceleration
    
    **Key Features:**
    - Graph-based trend detection using entity relationships
    - Multi-factor trending scores (mentions, connections, velocity, sentiment)
    - Category-specific trending analysis
    - Configurable time windows and connection thresholds
    
    **Categories:**
    - Technology: AI, quantum computing, semiconductors, etc.
    - Politics: Elections, policies, government, etc.
    - Business: Markets, companies, mergers, etc.
    - Health: Medical breakthroughs, regulations, etc.
    """
    try:
        logger.info(f"Trending topics request: category={category}, window={time_window_hours}h")
        
        # Validate category if provided
        valid_categories = {
            "Technology", "Politics", "Business", "Health", 
            "Science", "Sports", "Entertainment", "World"
        }
        
        if category and category not in valid_categories:
            logger.warning(f"Unknown category '{category}', proceeding anyway")
        
        # Perform trending analysis
        results = await search_service.query_trending_topics_by_graph(
            category=category,
            time_window_hours=time_window_hours,
            min_connections=min_connections,
            limit=limit
        )
        
        # Add API metadata
        results["api_info"] = {
            "endpoint": "/graph/search/trending_topics",
            "version": "1.0.0",
            "response_time": datetime.utcnow().isoformat(),
            "valid_categories": list(valid_categories)
        }
        
        trending_count = len(results.get("trending_topics", []))
        logger.info(f"Trending topics analysis completed: {trending_count} topics found")
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in trending topics endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error in trending analysis: {str(e)}"
        )


@router.post("/cache/frequent_queries")
async def cache_frequent_queries(
    background_tasks: BackgroundTasks,
    queries: List[str] = Query(..., description="List of frequent search queries to cache"),
    cache_duration_hours: int = Query(
        6, 
        ge=1, 
        le=24, 
        description="Cache duration in hours"
    ),
    search_service: GraphBasedSearchService = Depends(get_search_service)
) -> Dict[str, Any]:
    """
    Cache frequent queries for performance optimization.
    
    This endpoint implements the caching requirement from Issue #39,
    pre-computing and caching results for frequently searched terms
    to improve API response times.
    
    **Features:**
    - Background processing for non-blocking cache operations
    - Configurable cache duration
    - Batch processing of multiple queries
    - Cache statistics and monitoring
    
    **Usage:**
    POST with a list of frequently searched terms. The system will
    pre-compute semantic search and trending analysis results.
    """
    try:
        logger.info(f"Cache request for {len(queries)} queries")
        
        # Validate input
        if not queries:
            raise HTTPException(
                status_code=400,
                detail="At least one query must be provided"
            )
        
        if len(queries) > 50:
            raise HTTPException(
                status_code=400,
                detail="Maximum 50 queries can be cached at once"
            )
        
        # Start background caching task
        background_tasks.add_task(
            search_service.cache_frequent_queries,
            queries,
            cache_duration_hours
        )
        
        response = {
            "status": "accepted",
            "message": "Caching operation started in background",
            "queries_to_cache": queries,
            "cache_duration_hours": cache_duration_hours,
            "estimated_completion_minutes": len(queries) * 0.5,  # Rough estimate
            "timestamp": datetime.utcnow().isoformat(),
            "api_info": {
                "endpoint": "/graph/search/cache/frequent_queries",
                "version": "1.0.0"
            }
        }
        
        logger.info(f"Background caching started for {len(queries)} queries")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in cache endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error in cache operation: {str(e)}"
        )


@router.get("/trending_topics/category/{category}")
async def get_trending_topics_by_category(
    category: str,
    time_window_hours: int = Query(
        24, 
        ge=1, 
        le=168, 
        description="Time window for trend analysis in hours"
    ),
    min_connections: int = Query(
        3, 
        ge=1, 
        description="Minimum graph connections"
    ),
    limit: int = Query(
        20, 
        ge=1, 
        le=50, 
        description="Maximum results"
    ),
    search_service: GraphBasedSearchService = Depends(get_search_service)
) -> Dict[str, Any]:
    """
    Get trending topics for a specific category.
    
    This is a convenience endpoint that implements the category-specific
    trending analysis mentioned in Issue #39: "Integrate with API 
    /trending_topics?category=Technology"
    
    **Path Parameters:**
    - category: The news category (Technology, Politics, Business, etc.)
    
    **Popular Categories:**
    - Technology: AI, quantum computing, semiconductors, startups
    - Politics: Elections, legislation, government, international relations  
    - Business: Markets, earnings, mergers, economic indicators
    - Health: Medical research, pharmaceuticals, public health
    """
    try:
        # Capitalize category for consistency
        category = category.title()
        
        logger.info(f"Category-specific trending request: {category}")
        
        # Use the main trending analysis with category filter
        results = await search_service.query_trending_topics_by_graph(
            category=category,
            time_window_hours=time_window_hours,
            min_connections=min_connections,
            limit=limit
        )
        
        # Add category-specific metadata
        results["api_info"] = {
            "endpoint": f"/graph/search/trending_topics/category/{category}",
            "category": category,
            "version": "1.0.0",
            "response_time": datetime.utcnow().isoformat()
        }
        
        return results
        
    except Exception as e:
        logger.error(f"Error in category trending endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/health")
async def health_check(
    search_service: GraphBasedSearchService = Depends(get_search_service)
) -> Dict[str, str]:
    """Health check for graph search service."""
    try:
        # Test basic graph connectivity
        test_query = search_service.g.V().limit(1)
        await search_service._execute_traversal(test_query)
        
        return {
            "status": "healthy",
            "service": "graph-search",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Graph search health check failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Graph search service unhealthy: {str(e)}"
        )


@router.get("/stats")
async def get_search_stats(
    search_service: GraphBasedSearchService = Depends(get_search_service)
) -> Dict[str, Any]:
    """Get statistics about the graph search service and knowledge graph."""
    try:
        # Get basic graph statistics
        stats_queries = {
            "total_articles": search_service.g.V().hasLabel("Article").count(),
            "total_organizations": search_service.g.V().hasLabel("Organization").count(),
            "total_people": search_service.g.V().hasLabel("Person").count(),
            "total_technologies": search_service.g.V().hasLabel("Technology").count(),
            "total_events": search_service.g.V().hasLabel("Event").count(),
            "total_relationships": search_service.g.E().count()
        }
        
        stats = {}
        for name, query in stats_queries.items():
            try:
                result = await search_service._execute_traversal(query)
                stats[name] = result[0] if result else 0
            except:
                stats[name] = 0
        
        return {
            "graph_statistics": stats,
            "service_info": {
                "status": "operational",
                "features": [
                    "semantic_search",
                    "trending_analysis", 
                    "query_caching",
                    "category_filtering"
                ],
                "max_relationship_depth": 3,
                "max_results_per_query": 100
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting search stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving statistics: {str(e)}"
        )
