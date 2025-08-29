"""
FastAPI routes for Influence & Network Analysis (Issue #40).

Provides REST API endpoints for identifying key influencers, ranking entities,
and visualizing network relationships in political and tech news.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, Any
import logging

from src.knowledge_graph.graph_builder import GraphBuilder
from src.knowledge_graph.influence_network_analyzer import InfluenceNetworkAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/influence", tags=["influence-analysis"])

# Global variables for service instances
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
            logger.info("Graph builder connected successfully for influence analysis")
        except Exception as e:
            logger.error(f"Failed to connect graph builder: {str(e)}")
            # For demo purposes, create a mock instance
            from unittest.mock import Mock
            graph_builder_instance = Mock()
    
    return graph_builder_instance


def get_influence_analyzer(
    graph_builder=Depends(get_graph_builder)
) -> InfluenceNetworkAnalyzer:
    """Dependency to get influence analyzer instance."""
    return InfluenceNetworkAnalyzer(graph_builder)


@router.get("/top_influencers")
async def get_top_influencers(
    category: str = Query(..., description="Category to analyze (Politics, Technology, etc.)"),
    time_window_days: int = Query(30, description="Time window for analysis in days", ge=1, le=365),
    algorithm: str = Query("combined", description="Ranking algorithm", 
                          regex="^(influence|pagerank|combined)$"),
    limit: int = Query(15, description="Maximum influencers to return", ge=1, le=100),
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> Dict[str, Any]:
    """
    Get top influencers for a specific category.
    
    This is the main API endpoint requested in Issue #40:
    /top_influencers?category=Politics
    
    Args:
        category: Category to analyze (Politics, Technology, etc.)
        time_window_days: Time window for analysis
        algorithm: Ranking algorithm (influence, pagerank, combined)
        limit: Maximum influencers to return
        
    Returns:
        JSON response with ranked influencers and analysis metadata
        
    Raises:
        HTTPException: If analysis fails or invalid parameters
    """
    try:
        logger.info(f"API request: top influencers for {category} using {algorithm}")
        
        result = await analyzer.get_top_influencers_by_category(
            category=category,
            time_window_days=time_window_days,
            algorithm=algorithm,
            limit=limit
        )
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No influencers found for category: {category}"
            )
        
        # Add API metadata
        result["api_info"] = {
            "endpoint": "/api/v1/influence/top_influencers",
            "method": "GET",
            "version": "1.0"
        }
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in top_influencers API: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/key_influencers")
async def identify_key_influencers(
    category: Optional[str] = Query(None, description="Category filter"),
    time_window_days: int = Query(30, description="Time window for analysis in days", ge=1, le=365),
    min_mentions: int = Query(5, description="Minimum mentions required", ge=1),
    limit: int = Query(20, description="Maximum influencers to return", ge=1, le=100),
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> Dict[str, Any]:
    """
    Identify key influencers using influence-based metrics.
    
    Args:
        category: Optional category filter
        time_window_days: Time window for analysis
        min_mentions: Minimum mentions required
        limit: Maximum influencers to return
        
    Returns:
        JSON response with identified influencers and metrics
    """
    try:
        logger.info(f"API request: key influencers for category={category}")
        
        result = await analyzer.identify_key_influencers(
            category=category,
            time_window_days=time_window_days,
            min_mentions=min_mentions,
            limit=limit
        )
        
        result["api_info"] = {
            "endpoint": "/api/v1/influence/key_influencers",
            "method": "GET",
            "version": "1.0"
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error in key_influencers API: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/pagerank")
async def rank_entities_pagerank(
    category: Optional[str] = Query(None, description="Category filter"),
    iterations: int = Query(20, description="PageRank iterations", ge=5, le=100),
    damping_factor: float = Query(0.85, description="PageRank damping factor", ge=0.1, le=1.0),
    limit: int = Query(20, description="Maximum entities to return", ge=1, le=100),
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> Dict[str, Any]:
    """
    Rank entity importance using PageRank algorithm.
    
    Args:
        category: Optional category filter
        iterations: Number of PageRank iterations
        damping_factor: PageRank damping factor
        limit: Maximum entities to return
        
    Returns:
        JSON response with PageRank-ranked entities
    """
    try:
        logger.info(f"API request: PageRank for category={category}")
        
        result = await analyzer.rank_entity_importance_pagerank(
            category=category,
            iterations=iterations,
            damping_factor=damping_factor,
            limit=limit
        )
        
        result["api_info"] = {
            "endpoint": "/api/v1/influence/pagerank",
            "method": "GET",
            "version": "1.0"
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error in pagerank API: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/network_visualization")
async def visualize_entity_networks(
    central_entity: str = Query(..., description="Central entity for network visualization"),
    max_depth: int = Query(2, description="Maximum relationship depth", ge=1, le=4),
    min_connection_strength: float = Query(0.1, description="Minimum connection strength", 
                                         ge=0.0, le=1.0),
    limit: int = Query(50, description="Maximum nodes in network", ge=5, le=200),
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> Dict[str, Any]:
    """
    Generate network visualization data for entity relationships.
    
    Args:
        central_entity: Central entity to build network around
        max_depth: Maximum relationship depth
        min_connection_strength: Minimum connection strength
        limit: Maximum nodes in network
        
    Returns:
        JSON response with network visualization data (nodes and edges)
    """
    try:
        logger.info(f"API request: network visualization for {central_entity}")
        
        result = await analyzer.visualize_entity_networks(
            central_entity=central_entity,
            max_depth=max_depth,
            min_connection_strength=min_connection_strength,
            limit=limit
        )
        
        if not result["nodes"]:
            raise HTTPException(
                status_code=404,
                detail=f"Entity '{central_entity}' not found or has no network connections"
            )
        
        result["api_info"] = {
            "endpoint": "/api/v1/influence/network_visualization",
            "method": "GET",
            "version": "1.0"
        }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in network_visualization API: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/influence_metrics/{entity_name}")
async def get_entity_influence_metrics(
    entity_name: str,
    time_window_days: int = Query(30, description="Time window for analysis in days", ge=1, le=365),
    include_network: bool = Query(True, description="Include network analysis"),
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> Dict[str, Any]:
    """
    Get detailed influence metrics for a specific entity.
    
    Args:
        entity_name: Name of the entity to analyze
        time_window_days: Time window for analysis
        include_network: Whether to include network analysis
        
    Returns:
        JSON response with detailed entity influence metrics
    """
    try:
        logger.info(f"API request: influence metrics for {entity_name}")
        
        # Get influence analysis
        influence_result = await analyzer.identify_key_influencers(
            category=None,
            time_window_days=time_window_days,
            min_mentions=1,
            limit=1000
        )
        
        # Find the specific entity
        entity_metrics = None
        for influencer in influence_result.get("influencers", []):
            if influencer["entity"].lower() == entity_name.lower():
                entity_metrics = influencer
                break
        
        if not entity_metrics:
            raise HTTPException(
                status_code=404,
                detail=f"Entity '{entity_name}' not found or has insufficient mentions"
            )
        
        result = {
            "entity": entity_name,
            "metrics": entity_metrics,
            "analysis_period": influence_result.get("analysis_period", {}),
            "api_info": {
                "endpoint": f"/api/v1/influence/influence_metrics/{entity_name}",
                "method": "GET",
                "version": "1.0"
            }
        }
        
        # Include network visualization if requested
        if include_network:
            try:
                network_result = await analyzer.visualize_entity_networks(
                    central_entity=entity_name,
                    max_depth=2,
                    limit=30
                )
                result["network"] = network_result
            except Exception as e:
                logger.warning(f"Could not generate network for {entity_name}: {str(e)}")
                result["network"] = {"error": "Network data unavailable"}
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in influence_metrics API: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/categories")
async def get_available_categories(
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> Dict[str, Any]:
    """
    Get list of available categories for influence analysis.
    
    Returns:
        JSON response with available categories and their entity counts
    """
    try:
        logger.info("API request: available categories")
        
        # Mock categories for now - would query actual data
        categories = {
            "Politics": {
                "description": "Political entities, parties, and figures",
                "estimated_entities": 150,
                "sample_entities": ["Democratic Party", "Republican Party", "Joe Biden", "Congress"]
            },
            "Technology": {
                "description": "Tech companies, platforms, and innovations",
                "estimated_entities": 200,
                "sample_entities": ["Apple", "Google", "Meta", "AI", "Machine Learning"]
            },
            "Economics": {
                "description": "Economic entities, markets, and financial institutions",
                "estimated_entities": 100,
                "sample_entities": ["Federal Reserve", "Wall Street", "Stock Market", "Inflation"]
            },
            "Healthcare": {
                "description": "Healthcare organizations, policies, and medical topics",
                "estimated_entities": 80,
                "sample_entities": ["CDC", "FDA", "Medicare", "COVID-19"]
            },
            "Environment": {
                "description": "Environmental organizations, policies, and climate topics",
                "estimated_entities": 60,
                "sample_entities": ["EPA", "Climate Change", "Green Energy", "Paris Agreement"]
            }
        }
        
        return {
            "categories": categories,
            "total_categories": len(categories),
            "recommendation": "Use 'Politics' or 'Technology' for best results",
            "api_info": {
                "endpoint": "/api/v1/influence/categories",
                "method": "GET",
                "version": "1.0"
            }
        }
        
    except Exception as e:
        logger.error(f"Error in categories API: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for influence analysis service.
    
    Returns:
        JSON response with service health status
    """
    return {
        "service": "Influence & Network Analysis",
        "status": "healthy",
        "version": "1.0",
        "endpoints": [
            "/top_influencers",
            "/key_influencers", 
            "/pagerank",
            "/network_visualization",
            "/influence_metrics/{entity_name}",
            "/categories"
        ],
        "description": "REST API for identifying key influencers and analyzing entity networks"
    }
