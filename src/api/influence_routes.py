"""
FastAPI routes for Influence & Network Analysis (Issue #40).

This module provides REST API endpoints for identifying key influencers
and performing network analysis on news entities.
"""

from datetime import datetime
from typing import List, Optional
import logging

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from src.knowledge_graph.graph_builder import GraphBuilder
from src.knowledge_graph.influence_network_analyzer import InfluenceNetworkAnalyzer

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/v1/influence", tags=["Influence Analysis"])


class InfluencerResponse(BaseModel):
    """Response model for influencer data."""
    rank: int
    entity_name: str
    entity_type: str
    influence_score: float
    normalized_score: float
    mention_count: int
    article_count: int
    avg_sentiment: float
    latest_mention: Optional[str]
    key_indicators: List[str]


class NetworkStatsResponse(BaseModel):
    """Response model for network statistics."""
    total_entities: int
    total_relationships: int
    articles_analyzed: int
    avg_connections_per_entity: float


class AnalysisPeriodResponse(BaseModel):
    """Response model for analysis period information."""
    days: int
    category: Optional[str]
    entity_types: Optional[List[str]]
    start_date: str
    end_date: str


class TopInfluencersResponse(BaseModel):
    """Response model for top influencers endpoint."""
    influencers: List[InfluencerResponse]
    algorithm: str
    analysis_period: AnalysisPeriodResponse
    network_stats: NetworkStatsResponse
    timestamp: str


class CategoryInfluencersResponse(BaseModel):
    """Response model for category-specific influencers."""
    category: str
    top_influencers: List[InfluencerResponse]
    analysis_summary: dict
    detailed_metrics: Optional[NetworkStatsResponse]
    category_insights: Optional[dict]


class PageRankEntityResponse(BaseModel):
    """Response model for PageRank entity ranking."""
    entity_name: str
    entity_type: str
    pagerank_score: float
    normalized_score: float
    total_mentions: int
    unique_articles: int
    avg_sentiment: float
    connection_count: int
    latest_mention: Optional[str]
    prominence_indicators: List[str]


class PageRankResponse(BaseModel):
    """Response model for PageRank analysis."""
    ranked_entities: List[PageRankEntityResponse]
    algorithm: str
    parameters: dict
    network_metrics: dict
    timestamp: str


class NetworkVisualizationNode(BaseModel):
    """Node model for network visualization."""
    id: str
    name: str
    type: str
    size: float
    color: str
    mentions: int
    sentiment: float
    tooltip: str


class NetworkVisualizationEdge(BaseModel):
    """Edge model for network visualization."""
    source: str
    target: str
    weight: float
    type: str


class NetworkVisualizationResponse(BaseModel):
    """Response model for network visualization data."""
    nodes: List[NetworkVisualizationNode]
    edges: List[NetworkVisualizationEdge]
    layout: dict
    metadata: dict


# Dependency to get the analyzer instance
async def get_influence_analyzer() -> InfluenceNetworkAnalyzer:
    """Get an instance of the InfluenceNetworkAnalyzer."""
    try:
        graph_builder = GraphBuilder()
        await graph_builder.connect()
        return InfluenceNetworkAnalyzer(graph_builder)
    except Exception as e:
        logger.error(f"Failed to initialize InfluenceNetworkAnalyzer: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize influence analysis service"
        )


@router.get(
    "/top_influencers",
    response_model=TopInfluencersResponse,
    summary="Get Top Influencers",
    description="Identify key influencers and entities using network analysis algorithms"
)
async def get_top_influencers(
    category: Optional[str] = Query(
        None, 
        description="Filter by news category (Politics, Technology, Business, etc.)",
        example="Politics"
    ),
    entity_types: Optional[List[str]] = Query(
        None,
        description="Filter by entity types (Person, Organization, Technology, etc.)",
        example=["Person", "Organization"]
    ),
    time_window_days: int = Query(
        30,
        ge=1,
        le=365,
        description="Time window for analysis in days",
        example=30
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Maximum number of influencers to return",
        example=20
    ),
    algorithm: str = Query(
        "pagerank",
        regex="^(pagerank|centrality|hybrid)$",
        description="Algorithm to use for influence calculation",
        example="pagerank"
    ),
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> TopInfluencersResponse:
    """
    Get top influencers using specified analysis algorithm.
    
    This endpoint implements comprehensive influence analysis to identify
    key entities and influencers in news content. It supports multiple
    algorithms and filtering options.
    
    **Algorithms:**
    - `pagerank`: PageRank-style algorithm considering entity relationships
    - `centrality`: Network centrality-based analysis
    - `hybrid`: Combination of multiple algorithms for best results
    
    **Categories:**
    - Politics, Technology, Business, Health, Sports, Entertainment, etc.
    
    **Entity Types:**
    - Person, Organization, Technology, Event, Location, Policy, etc.
    """
    try:
        logger.info(f"Getting top influencers: category={category}, algorithm={algorithm}")
        
        result = await analyzer.identify_key_influencers(
            category=category,
            entity_types=entity_types,
            time_window_days=time_window_days,
            limit=limit,
            algorithm=algorithm
        )
        
        return TopInfluencersResponse(**result)
        
    except Exception as e:
        logger.error(f"Error in get_top_influencers: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze influencers: {str(e)}"
        )


@router.get(
    "/category/{category}",
    response_model=CategoryInfluencersResponse,
    summary="Get Top Influencers by Category",
    description="Get top influencers for a specific news category"
)
async def get_top_influencers_by_category(
    category: str = Query(
        ...,
        description="News category to analyze",
        example="Politics"
    ),
    time_window_days: int = Query(
        30,
        ge=1,
        le=365,
        description="Time window for analysis in days",
        example=30
    ),
    limit: int = Query(
        15,
        ge=1,
        le=50,
        description="Number of top influencers to return",
        example=15
    ),
    include_metrics: bool = Query(
        True,
        description="Whether to include detailed metrics and insights",
        example=True
    ),
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> CategoryInfluencersResponse:
    """
    Get top influencers for a specific category.
    
    This endpoint is specifically designed for category-based analysis,
    as requested in the issue requirements for `/top_influencers?category=Politics`.
    
    **Supported Categories:**
    - Politics: Political figures, parties, policies
    - Technology: Tech companies, products, executives
    - Business: Companies, executives, market entities
    - Health: Medical institutions, researchers, policies
    - Sports: Athletes, teams, organizations
    - Entertainment: Celebrities, studios, media companies
    
    **Response includes:**
    - Ranked list of top influencers
    - Category-specific insights and trends
    - Detailed network metrics (if requested)
    - Analysis summary with timeframe and methodology
    """
    try:
        logger.info(f"Getting top influencers for category: {category}")
        
        result = await analyzer.get_top_influencers_by_category(
            category=category,
            time_window_days=time_window_days,
            limit=limit,
            include_metrics=include_metrics
        )
        
        return CategoryInfluencersResponse(**result)
        
    except Exception as e:
        logger.error(f"Error in get_top_influencers_by_category: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze category influencers: {str(e)}"
        )


@router.get(
    "/pagerank",
    response_model=PageRankResponse,
    summary="Entity PageRank Analysis",
    description="Rank entity importance using PageRank-style algorithm"
)
async def get_pagerank_analysis(
    category: Optional[str] = Query(
        None,
        description="Filter by news category",
        example="Technology"
    ),
    entity_type: Optional[str] = Query(
        None,
        description="Filter by entity type",
        example="Organization"
    ),
    damping_factor: float = Query(
        0.85,
        ge=0.1,
        le=0.9,
        description="PageRank damping factor",
        example=0.85
    ),
    max_iterations: int = Query(
        100,
        ge=10,
        le=1000,
        description="Maximum iterations for convergence",
        example=100
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Number of top entities to return",
        example=20
    ),
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> PageRankResponse:
    """
    Rank entity importance using PageRank-style algorithm.
    
    This endpoint implements a modified PageRank algorithm specifically
    designed for news entity networks. The algorithm considers:
    
    **Ranking Factors:**
    - Entity mention frequency across articles
    - Relationship strength and types between entities
    - Temporal decay for recent importance
    - Article sentiment and prominence
    - Network connectivity patterns
    
    **Parameters:**
    - `damping_factor`: Probability of continuing random walk (0.1-0.9)
    - `max_iterations`: Maximum iterations before convergence timeout
    - Entity and category filters for focused analysis
    
    **Algorithm Details:**
    The PageRank score represents the probability that a random walker
    following entity relationships will visit a particular entity.
    Higher scores indicate more central and influential entities.
    """
    try:
        logger.info(f"Running PageRank analysis: category={category}, type={entity_type}")
        
        result = await analyzer.rank_entity_importance_pagerank(
            category=category,
            entity_type=entity_type,
            damping_factor=damping_factor,
            max_iterations=max_iterations,
            limit=limit
        )
        
        return PageRankResponse(**result)
        
    except Exception as e:
        logger.error(f"Error in get_pagerank_analysis: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run PageRank analysis: {str(e)}"
        )


@router.get(
    "/network/visualization",
    response_model=NetworkVisualizationResponse,
    summary="Generate Network Visualization Data",
    description="Generate data for interactive network visualization of entities"
)
async def get_network_visualization(
    entity_ids: List[str] = Query(
        ...,
        description="List of entity IDs to visualize",
        example=["entity1", "entity2", "entity3"]
    ),
    include_relationships: bool = Query(
        True,
        description="Whether to include relationship data",
        example=True
    ),
    max_connections: int = Query(
        50,
        ge=1,
        le=200,
        description="Maximum connections to include per entity",
        example=50
    ),
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> NetworkVisualizationResponse:
    """
    Generate data for network visualization of entities.
    
    This endpoint provides structured data for creating interactive
    network visualizations showing entity relationships and influence.
    
    **Visualization Elements:**
    - **Nodes**: Entities with size based on influence score
    - **Edges**: Relationships with weight based on connection strength
    - **Layout**: Force-directed positioning hints
    - **Colors**: Entity type-based color coding
    - **Tooltips**: Detailed entity information on hover
    
    **Use Cases:**
    - Interactive network graphs for web applications
    - Influence network analysis dashboards
    - Entity relationship exploration tools
    - Political/tech ecosystem mapping
    
    **Output Format:**
    Compatible with popular visualization libraries like D3.js,
    Cytoscape.js, and vis.js for web-based network graphs.
    """
    try:
        logger.info(f"Generating network visualization for {len(entity_ids)} entities")
        
        if len(entity_ids) > 100:
            raise HTTPException(
                status_code=400,
                detail="Too many entities requested. Maximum is 100 entities."
            )
        
        result = await analyzer.generate_network_visualization_data(
            entity_ids=entity_ids,
            include_relationships=include_relationships,
            max_connections=max_connections
        )
        
        return NetworkVisualizationResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_network_visualization: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate network visualization: {str(e)}"
        )


@router.get(
    "/health",
    summary="Health Check",
    description="Check the health status of the influence analysis service"
)
async def health_check(
    analyzer: InfluenceNetworkAnalyzer = Depends(get_influence_analyzer)
) -> dict:
    """
    Health check endpoint for the influence analysis service.
    
    Verifies that the service is running and can connect to
    the knowledge graph database.
    """
    try:
        # Simple health check - verify graph connection
        test_query = analyzer.g.V().limit(1)
        await analyzer._execute_traversal(test_query)
        
        return {
            "status": "healthy",
            "service": "influence_network_analysis",
            "timestamp": datetime.utcnow().isoformat(),
            "features": [
                "top_influencers",
                "pagerank_analysis", 
                "category_analysis",
                "network_visualization"
            ]
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Service unhealthy: {str(e)}"
        )


# Additional utility endpoints

@router.get(
    "/categories",
    summary="Get Available Categories",
    description="Get list of available news categories for analysis"
)
async def get_available_categories() -> dict:
    """Get list of available news categories."""
    return {
        "categories": [
            {
                "name": "Politics",
                "description": "Political news, figures, parties, and policies",
                "entity_types": ["Person", "Organization", "Policy", "Event"]
            },
            {
                "name": "Technology", 
                "description": "Tech companies, products, and industry news",
                "entity_types": ["Organization", "Technology", "Person", "Event"]
            },
            {
                "name": "Business",
                "description": "Business news, companies, and market analysis",
                "entity_types": ["Organization", "Person", "Event", "Policy"]
            },
            {
                "name": "Health",
                "description": "Health and medical news, research, and policies",
                "entity_types": ["Organization", "Person", "Policy", "Technology"]
            },
            {
                "name": "Sports",
                "description": "Sports news, athletes, teams, and events", 
                "entity_types": ["Person", "Organization", "Event", "Location"]
            },
            {
                "name": "Entertainment",
                "description": "Entertainment industry news and personalities",
                "entity_types": ["Person", "Organization", "Event", "Technology"]
            }
        ],
        "total": 6
    }


@router.get(
    "/entity_types", 
    summary="Get Available Entity Types",
    description="Get list of available entity types for filtering"
)
async def get_available_entity_types() -> dict:
    """Get list of available entity types."""
    return {
        "entity_types": [
            {
                "name": "Person",
                "description": "Individual people (politicians, executives, etc.)",
                "color": "#FF6B6B"
            },
            {
                "name": "Organization", 
                "description": "Companies, institutions, and organizations",
                "color": "#4ECDC4"
            },
            {
                "name": "Technology",
                "description": "Technologies, products, and platforms",
                "color": "#45B7D1"
            },
            {
                "name": "Event",
                "description": "News events, conferences, and incidents",
                "color": "#96CEB4"
            },
            {
                "name": "Location",
                "description": "Geographic locations and places",
                "color": "#FFEAA7"
            },
            {
                "name": "Policy",
                "description": "Policies, legislation, and regulations",
                "color": "#DDA0DD"
            }
        ],
        "total": 6
    }
