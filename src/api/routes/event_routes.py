"""
Event Detection API Routes (Issue #31)

FastAPI routes for article clustering and event detection system.
Provides endpoints for accessing breaking news and event clusters.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.nlp.article_embedder import (ArticleEmbedder,
                                      get_redshift_connection_params)
from src.nlp.event_clusterer import EventClusterer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1", tags=["event-detection"])


# Pydantic models for request/response
class EventDetectionRequest(BaseModel):
    """Request model for manual event detection."""

    category: Optional[str] = Field(None, description="Category filter for articles")
    days_back: int = Field(7, ge=1, le=30, description="Days to look back for articles")
    max_articles: int = Field(
        100, ge=10, le=1000, description="Maximum articles to process"
    )
    clustering_method: str = Field(
        "kmeans", pattern="^(kmeans|dbscan)$", description="Clustering algorithm"
    )
    min_cluster_size: int = Field(
        3, ge=2, le=20, description="Minimum articles per cluster"
    )


class BreakingNewsResponse(BaseModel):
    """Response model for breaking news."""

    cluster_id: str
    cluster_name: str
    event_type: str
    category: str
    trending_score: float
    impact_score: float
    velocity_score: float
    cluster_size: int
    first_article_date: str
    last_article_date: str
    peak_activity_date: Optional[str]
    event_duration_hours: float
    sample_headlines: Optional[str]
    source_count: int
    avg_confidence: float


class EventClusterResponse(BaseModel):
    """Response model for event clusters."""

    cluster_id: str
    cluster_name: str
    event_type: str
    category: str
    cluster_size: int
    silhouette_score: float
    cohesion_score: float
    separation_score: float
    trending_score: float
    impact_score: float
    velocity_score: float
    significance_score: Optional[float]
    first_article_date: str
    last_article_date: str
    event_duration_hours: float
    primary_sources: List[str]
    geographic_focus: List[str]
    key_entities: List[str]
    status: str
    created_at: str


class ArticleInClusterResponse(BaseModel):
    """Response model for articles in a cluster."""

    article_id: str
    title: str
    source: str
    published_date: str
    assignment_confidence: float
    distance_to_centroid: float
    is_cluster_representative: bool
    contribution_score: float
    novelty_score: float


class EventDetectionStatsResponse(BaseModel):
    """Response model for event detection statistics."""

    articles_clustered: int
    clusters_created: int
    events_detected: int
    processing_time: float
    last_clustering_run: Optional[str]
    embedding_model: str
    clustering_method: str


# Dependency injection
async def get_embedder() -> ArticleEmbedder:
    """Get article embedder instance."""
    return ArticleEmbedder(
        model_name="all-MiniLM-L6-v2", conn_params=get_redshift_connection_params()
    )


async def get_clusterer() -> EventClusterer:
    """Get event clusterer instance."""
    return EventClusterer(
        conn_params=get_redshift_connection_params(),
        min_cluster_size=3,
        max_clusters=20,
    )


# API Routes


@router.get("/breaking_news", response_model=List[BreakingNewsResponse])
async def get_breaking_news(
    category: Optional[str] = Query(
        None, description="Filter by category (e.g., Technology, Politics)"
    ),
    hours_back: int = Query(
        24, ge=1, le=168, description="Hours to look back for events"
    ),
    limit: int = Query(
        10, ge=1, le=50, description="Maximum number of events to return"
    ),
    clusterer: EventClusterer = Depends(get_clusterer),
):
    """
    Get current breaking news events.

    This endpoint returns active breaking news events detected through
    article clustering. Events are ranked by trending score and impact.

    **Query Parameters:**
    - `category`: Filter by news category (Technology, Politics, Health, etc.)
    - `hours_back`: How far back to look for events (1-168 hours)
    - `limit`: Maximum number of events to return (1-50)

    **Example:**
    ```
    GET /api/v1/breaking_news?category=Technology&hours_back=12&limit=5
    ```
    """
    try:
        logger.info(
            f"Getting breaking news: category={category}, hours_back={hours_back}, limit={limit}"
        )

        events = await clusterer.get_breaking_news(
            category=category, hours_back=hours_back, limit=limit
        )

        if not events:
            return []

        # Convert to response model
        response_events = []
        for event in events:
            response_events.append(
                BreakingNewsResponse(
                    cluster_id=event["cluster_id"],
                    cluster_name=event["cluster_name"],
                    event_type=event["event_type"],
                    category=event["category"],
                    trending_score=float(event["trending_score"]),
                    impact_score=float(event["impact_score"]),
                    velocity_score=float(event["velocity_score"]),
                    cluster_size=int(event["cluster_size"]),
                    first_article_date=event["first_article_date"],
                    last_article_date=event["last_article_date"],
                    peak_activity_date=event.get("peak_activity_date"),
                    event_duration_hours=float(event["event_duration_hours"]),
                    sample_headlines=event.get("sample_headlines"),
                    source_count=int(event["source_count"]),
                    avg_confidence=float(event["avg_confidence"]),
                )
            )

        logger.info(f"Returned {len(response_events)} breaking news events")
        return response_events

    except Exception as e:
        logger.error(f"Error getting breaking news: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving breaking news: {str(e)}"
        )


@router.get("/events/clusters", response_model=List[EventClusterResponse])
async def get_event_clusters(
    category: Optional[str] = Query(None, description="Filter by category"),
    event_type: Optional[str] = Query(
        None, description="Filter by event type (breaking, trending, developing)"
    ),
    days_back: int = Query(7, ge=1, le=30, description="Days to look back"),
    limit: int = Query(20, ge=1, le=100, description="Maximum clusters to return"),
    min_significance: float = Query(
        0.0, ge=0.0, le=100.0, description="Minimum significance score"
    ),
):
    """
    Get all event clusters with detailed information.

    Returns comprehensive information about detected event clusters,
    including clustering metrics, significance scores, and metadata.

    **Query Parameters:**
    - `category`: Filter by news category
    - `event_type`: Filter by event type (breaking, trending, developing, ongoing)
    - `days_back`: How far back to look for clusters (1-30 days)
    - `limit`: Maximum number of clusters to return (1-100)
    - `min_significance`: Minimum significance score (0-100)
    """
    try:
        logger.info(
            f"Getting event clusters: category={category}, event_type={event_type}"
        )

        conn_params = get_redshift_connection_params()

        # Build query
        query = """
            SELECT 
                cluster_id, cluster_name, event_type, category, cluster_size,
                silhouette_score, cohesion_score, separation_score,
                trending_score, impact_score, velocity_score,
                first_article_date, last_article_date, event_duration_hours,
                primary_sources, geographic_focus, key_entities,
                status, created_at
            FROM event_clusters
            WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
            AND status = 'active'
        """
        params = [days_back]

        if category:
            query += " AND category = %s"
            params.append(category)

        if event_type:
            query += " AND event_type = %s"
            params.append(event_type)

        query += " ORDER BY trending_score DESC, impact_score DESC LIMIT %s"
        params.append(limit)

        import psycopg2
        from psycopg2.extras import RealDictCursor

        with psycopg2.connect(**conn_params) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

        # Convert to response model
        clusters = []
        for row in rows:
            # Calculate significance score
            significance_score = (
                float(row["trending_score"]) * 0.3
                + float(row["impact_score"]) * 0.4
                + float(row["velocity_score"]) * 0.2
                + (int(row["cluster_size"]) / 20) * 0.1
            )

            if significance_score < min_significance:
                continue

            # Parse JSON fields
            primary_sources = (
                json.loads(row["primary_sources"]) if row["primary_sources"] else []
            )
            geographic_focus = (
                json.loads(row["geographic_focus"]) if row["geographic_focus"] else []
            )
            key_entities = (
                json.loads(row["key_entities"]) if row["key_entities"] else []
            )

            clusters.append(
                EventClusterResponse(
                    cluster_id=row["cluster_id"],
                    cluster_name=row["cluster_name"],
                    event_type=row["event_type"],
                    category=row["category"],
                    cluster_size=int(row["cluster_size"]),
                    silhouette_score=float(row["silhouette_score"]),
                    cohesion_score=float(row["cohesion_score"]),
                    separation_score=float(row["separation_score"]),
                    trending_score=float(row["trending_score"]),
                    impact_score=float(row["impact_score"]),
                    velocity_score=float(row["velocity_score"]),
                    significance_score=significance_score,
                    first_article_date=row["first_article_date"].isoformat(),
                    last_article_date=row["last_article_date"].isoformat(),
                    event_duration_hours=float(row["event_duration_hours"]),
                    primary_sources=primary_sources,
                    geographic_focus=geographic_focus,
                    key_entities=key_entities,
                    status=row["status"],
                    created_at=row["created_at"].isoformat(),
                )
            )

        logger.info(f"Returned {len(clusters)} event clusters")
        return clusters

    except Exception as e:
        logger.error(f"Error getting event clusters: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving event clusters: {str(e)}"
        )


@router.get(
    "/events/{cluster_id}/articles", response_model=List[ArticleInClusterResponse]
)
async def get_articles_in_cluster(
    cluster_id: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum articles to return"),
):
    """
    Get all articles in a specific event cluster.

    Returns detailed information about articles assigned to the specified
    event cluster, including assignment confidence and contribution scores.

    **Path Parameters:**
    - `cluster_id`: Unique identifier of the event cluster

    **Query Parameters:**
    - `limit`: Maximum number of articles to return (1-200)
    """
    try:
        logger.info(f"Getting articles for cluster: {cluster_id}")

        conn_params = get_redshift_connection_params()

        import psycopg2
        from psycopg2.extras import RealDictCursor

        with psycopg2.connect(**conn_params) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT 
                        aca.article_id, a.title, a.source, a.published_date,
                        aca.assignment_confidence, aca.distance_to_centroid,
                        aca.is_cluster_representative, aca.contribution_score,
                        aca.novelty_score
                    FROM article_cluster_assignments aca
                    JOIN news_articles a ON aca.article_id = a.id
                    WHERE aca.cluster_id = %s
                    ORDER BY aca.assignment_confidence DESC, a.published_date DESC
                    LIMIT %s
                """,
                    (cluster_id, limit),
                )

                rows = cur.fetchall()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"Cluster {cluster_id} not found or has no articles",
            )

        # Convert to response model
        articles = []
        for row in rows:
            articles.append(
                ArticleInClusterResponse(
                    article_id=row["article_id"],
                    title=row["title"],
                    source=row["source"],
                    published_date=row["published_date"].isoformat(),
                    assignment_confidence=float(row["assignment_confidence"]),
                    distance_to_centroid=float(row["distance_to_centroid"]),
                    is_cluster_representative=bool(row["is_cluster_representative"]),
                    contribution_score=float(row["contribution_score"]),
                    novelty_score=float(row["novelty_score"]),
                )
            )

        logger.info(f"Returned {len(articles)} articles for cluster {cluster_id}")
        return articles

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting articles for cluster {cluster_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving articles: {str(e)}"
        )


@router.post("/events/detect", response_model=EventDetectionStatsResponse)
async def trigger_event_detection(
    request: EventDetectionRequest,
    embedder: ArticleEmbedder = Depends(get_embedder),
    clusterer: EventClusterer = Depends(get_clusterer),
):
    """
    Manually trigger event detection on recent articles.

    This endpoint processes recent articles, generates embeddings if needed,
    and performs clustering to detect new events. Useful for testing or
    manual event detection runs.

    **Request Body:**
    ```json
    {
        "category": "Technology",
        "days_back": 3,
        "max_articles": 50,
        "clustering_method": "kmeans",
        "min_cluster_size": 3
    }
    ```
    """
    try:
        logger.info(f"Triggering event detection: {request}")

        # Update clusterer settings
        clusterer.min_cluster_size = request.min_cluster_size
        clusterer.clustering_method = request.clustering_method

        # Get embeddings for clustering
        embeddings_data = await embedder.get_embeddings_for_clustering(
            limit=request.max_articles,
            category_filter=request.category,
            days_back=request.days_back,
        )

        if not embeddings_data:
            raise HTTPException(
                status_code=404,
                detail=f"No articles found for clustering with the specified criteria",
            )

        logger.info(f"Found {len(embeddings_data)} articles with embeddings")

        # Detect events
        events = await clusterer.detect_events(embeddings_data, request.category)

        # Get statistics
        clusterer_stats = clusterer.get_statistics()
        embedder_stats = embedder.get_statistics()

        response = EventDetectionStatsResponse(
            articles_clustered=clusterer_stats["articles_clustered"],
            clusters_created=clusterer_stats["clusters_created"],
            events_detected=clusterer_stats["events_detected"],
            processing_time=clusterer_stats["processing_time"],
            last_clustering_run=clusterer_stats["last_clustering_run"],
            embedding_model=embedder_stats["model_name"],
            clustering_method=request.clustering_method,
        )

        logger.info(f"Event detection completed: {response}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in event detection: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error in event detection: {str(e)}"
        )


@router.get("/events/categories", response_model=List[Dict[str, Any]])
async def get_trending_categories():
    """
    Get trending categories with event statistics.

    Returns statistics about active events grouped by category,
    showing which categories are most active.
    """
    try:
        conn_params = get_redshift_connection_params()

        import psycopg2
        from psycopg2.extras import RealDictCursor

        with psycopg2.connect(**conn_params) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM trending_events_by_category
                    ORDER BY avg_trending_score DESC
                    LIMIT 20
                """
                )

                rows = cur.fetchall()

        # Convert to response format
        categories = []
        for row in rows:
            categories.append(
                {
                    "category": row["category"],
                    "active_events": int(row["active_events"]),
                    "total_articles": int(row["total_articles"]),
                    "avg_trending_score": float(row["avg_trending_score"]),
                    "avg_impact_score": float(row["avg_impact_score"]),
                    "max_trending_score": float(row["max_trending_score"]),
                    "top_events": (
                        row["top_events"].split(" | ") if row["top_events"] else []
                    ),
                }
            )

        logger.info(f"Returned trending data for {len(categories)} categories")
        return categories

    except Exception as e:
        logger.error(f"Error getting trending categories: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving trending categories: {str(e)}"
        )


@router.get("/events/stats", response_model=Dict[str, Any])
async def get_event_detection_stats():
    """
    Get overall event detection system statistics.

    Returns comprehensive statistics about the event detection system,
    including processing metrics and system health indicators.
    """
    try:
        conn_params = get_redshift_connection_params()

        import psycopg2
        from psycopg2.extras import RealDictCursor

        with psycopg2.connect(**conn_params) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get overall statistics
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total_clusters,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active_clusters,
                        AVG(cluster_size) as avg_cluster_size,
                        AVG(trending_score) as avg_trending_score,
                        AVG(impact_score) as avg_impact_score,
                        MAX(trending_score) as max_trending_score,
                        COUNT(CASE WHEN event_type = 'breaking' THEN 1 END) as breaking_events,
                        COUNT(CASE WHEN event_type = 'trending' THEN 1 END) as trending_events
                    FROM event_clusters
                    WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                """
                )

                cluster_stats = cur.fetchone()

                # Get embedding statistics
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total_embeddings,
                        COUNT(DISTINCT embedding_model) as unique_models,
                        AVG(embedding_quality_score) as avg_quality_score,
                        AVG(processing_time) as avg_processing_time
                    FROM article_embeddings
                    WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                """
                )

                embedding_stats = cur.fetchone()

                # Get assignment statistics
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total_assignments,
                        AVG(assignment_confidence) as avg_confidence,
                        COUNT(CASE WHEN is_cluster_representative THEN 1 END) as representative_articles
                    FROM article_cluster_assignments
                    WHERE assigned_at >= CURRENT_DATE - INTERVAL '30 days'
                """
                )

                assignment_stats = cur.fetchone()

        # Combine statistics
        stats = {
            "cluster_statistics": {
                "total_clusters": int(cluster_stats["total_clusters"] or 0),
                "active_clusters": int(cluster_stats["active_clusters"] or 0),
                "avg_cluster_size": float(cluster_stats["avg_cluster_size"] or 0),
                "avg_trending_score": float(cluster_stats["avg_trending_score"] or 0),
                "avg_impact_score": float(cluster_stats["avg_impact_score"] or 0),
                "max_trending_score": float(cluster_stats["max_trending_score"] or 0),
                "breaking_events": int(cluster_stats["breaking_events"] or 0),
                "trending_events": int(cluster_stats["trending_events"] or 0),
            },
            "embedding_statistics": {
                "total_embeddings": int(embedding_stats["total_embeddings"] or 0),
                "unique_models": int(embedding_stats["unique_models"] or 0),
                "avg_quality_score": float(embedding_stats["avg_quality_score"] or 0),
                "avg_processing_time": float(
                    embedding_stats["avg_processing_time"] or 0
                ),
            },
            "assignment_statistics": {
                "total_assignments": int(assignment_stats["total_assignments"] or 0),
                "avg_confidence": float(assignment_stats["avg_confidence"] or 0),
                "representative_articles": int(
                    assignment_stats["representative_articles"] or 0
                ),
            },
            "system_info": {
                "last_updated": datetime.now().isoformat(),
                "time_period": "30 days",
                "version": "1.0",
            },
        }

        logger.info("Retrieved event detection system statistics")
        return stats

    except Exception as e:
        logger.error(f"Error getting event detection stats: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving statistics: {str(e)}"
        )


# Add router to main app
def add_event_detection_routes(app):
    """Add event detection routes to FastAPI app."""
    app.include_router(router)
