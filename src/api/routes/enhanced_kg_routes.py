"""
Enhanced Knowledge Graph API Routes - Issue #37

This module provides comprehensive FastAPI endpoints for querying entity relationships
and event timelines from the knowledge graph. It integrates with the enhanced
knowledge graph populator from Issue #36 and provides advanced SPARQL/Gremlin
query capabilities.

Endpoints:
- /related_entities - Find entities related to a specified entity
- /event_timeline - Get chronological events for a topic
- /entity_details - Get detailed information about a specific entity
- /graph_search - Advanced graph search with custom filters
- /graph_analytics - Graph analytics and metrics
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

# Import enhanced knowledge graph components
try:
    from src.knowledge_graph.enhanced_graph_populator import (
        EnhancedKnowledgeGraphPopulator,
        create_enhanced_knowledge_graph_populator,
    )

    ENHANCED_KG_AVAILABLE = True
except ImportError:
    ENHANCED_KG_AVAILABLE = False

# Import configuration
try:
    from src.core.config import get_settings

    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/knowledge-graph", tags=["knowledge-graph"])

# Pydantic models for request/response validation


class EntityRelationshipQuery(BaseModel):
    """Request model for entity relationship queries."""

    entity_name: str = Field(
        ..., description="Name of the entity to find relationships for"
    )
    max_depth: int = Field(
        2, ge=1, le=5, description="Maximum relationship depth to traverse"
    )
    max_results: int = Field(
        50, ge=1, le=200, description="Maximum number of results to return"
    )
    relationship_types: Optional[List[str]] = Field(
        None, description="Filter by specific relationship types"
    )
    min_confidence: float = Field(
        0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    )
    include_context: bool = Field(
        True, description="Include relationship context information"
    )


class EventTimelineQuery(BaseModel):
    """Request model for event timeline queries."""

    topic: str = Field(..., description="Topic or entity to create timeline for")
    start_date: Optional[datetime] = Field(None, description="Start date for timeline")
    end_date: Optional[datetime] = Field(None, description="End date for timeline")
    max_events: int = Field(
        50, ge=1, le=200, description="Maximum number of events to return"
    )
    event_types: Optional[List[str]] = Field(
        None, description="Filter by specific event types"
    )
    include_articles: bool = Field(
        True, description="Include source articles in timeline"
    )


class GraphSearchQuery(BaseModel):
    """Request model for advanced graph search."""

    query_type: str = Field(
        ..., description="Type of search: 'entity', 'relationship', 'path'"
    )
    search_terms: List[str] = Field(..., description="Search terms or entity names")
    filters: Optional[Dict[str, Any]] = Field(
        {}, description="Additional search filters"
    )
    sort_by: str = Field(
        "relevance", description="Sort results by: relevance, date, confidence"
    )
    limit: int = Field(50, ge=1, le=200, description="Maximum number of results")


class RelatedEntity(BaseModel):
    """Response model for related entities."""

    entity_id: str
    entity_name: str
    entity_type: str
    relationship_type: str
    confidence: float
    context: Optional[str] = None
    source_articles: Optional[List[str]] = None
    properties: Optional[Dict[str, Any]] = None


class TimelineEvent(BaseModel):
    """Response model for timeline events."""

    event_id: str
    event_title: str
    event_date: datetime
    event_type: str
    description: str
    entities_involved: List[str]
    source_article_id: Optional[str] = None
    confidence: float
    metadata: Optional[Dict[str, Any]] = None


class EntityRelationshipResponse(BaseModel):
    """Response model for entity relationships."""

    query_entity: str
    total_results: int
    max_depth: int
    related_entities: List[RelatedEntity]
    execution_time: float
    timestamp: datetime


class EventTimelineResponse(BaseModel):
    """Response model for event timelines."""

    topic: str
    timeline_span: Dict[str, Optional[datetime]]
    total_events: int
    events: List[TimelineEvent]
    execution_time: float
    timestamp: datetime


# Dependency functions


async def get_enhanced_graph_populator() -> EnhancedKnowledgeGraphPopulator:
    """Dependency to get EnhancedKnowledgeGraphPopulator instance."""
    if not ENHANCED_KG_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Enhanced knowledge graph components not available"
        )

    try:
        # Get Neptune endpoint from configuration
        if CONFIG_AVAILABLE:
            settings = get_settings()
            neptune_endpoint = settings.NEPTUNE_ENDPOINT
        else:
            # Fallback to environment variable or default
            import os

            neptune_endpoint = os.getenv(
                "NEPTUNE_ENDPOINT",
                "wss://demo-cluster.neptune.amazonaws.com:8182/gremlin",
            )

        populator = create_enhanced_knowledge_graph_populator(neptune_endpoint)
        return populator

    except Exception as e:
        logger.error("Failed to create enhanced graph populator: {0}".format(e))
        raise HTTPException(
            status_code=503,
            detail="Knowledge graph service not available: {0}".format(str(e)),
        )


# API Endpoints


@router.get("/related_entities", response_model=EntityRelationshipResponse)
async def get_related_entities(
    entity: str = Query(..., description="Entity name to find relationships for"),
    max_depth: int = Query(2, ge=1, le=5, description="Maximum relationship depth"),
    max_results: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    relationship_types: Optional[str] = Query(
        None, description="Comma-separated relationship types to filter by"
    ),
    min_confidence: float = Query(
        0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
    include_context: bool = Query(True, description="Include relationship context"),
    populator: EnhancedKnowledgeGraphPopulator = Depends(get_enhanced_graph_populator),
) -> EntityRelationshipResponse:
    """
    Get entities related to a specified entity from the knowledge graph.

    This endpoint uses enhanced Gremlin queries to traverse the knowledge graph
    and find entities connected to the specified entity through various relationships.

    Example:
        GET /api/v1/knowledge-graph/related_entities?entity=Google&max_depth=2&max_results=20
    """
    start_time = datetime.now()

    try:
        logger.info("API request for related entities: {0}".format(entity))

        # Validate input
        if not entity or len(entity.strip()) < 2:
            raise HTTPException(
                status_code=400, detail="Entity name must be at least 2 characters long"
            )

        # Parse relationship types filter
        relationship_filter = None
        if relationship_types:
            relationship_filter = [rt.strip() for rt in relationship_types.split(",")]

        # Query enhanced knowledge graph
        query_result = await populator.query_entity_relationships(
            entity_name=entity,
            max_depth=max_depth,
            relationship_types=relationship_filter,
        )

        # Filter by confidence and format results
        related_entities = []
        for entity_info in query_result.get("related_entities", []):
            confidence = entity_info.get("confidence", 0.0)
            if confidence >= min_confidence:
                related_entity = RelatedEntity(
                    entity_id=entity_info.get("id", ""),
                    entity_name=entity_info.get("name", ""),
                    entity_type=entity_info.get("type", ""),
                    relationship_type=entity_info.get("relationship_type", "RELATED"),
                    confidence=confidence,
                    context=entity_info.get("context") if include_context else None,
                    source_articles=entity_info.get("source_articles", []),
                    properties=entity_info.get("properties", {}),
                )
                related_entities.append(related_entity)

        # Limit results
        related_entities = related_entities[:max_results]

        # Calculate execution time
        execution_time = (datetime.now() - start_time).total_seconds()

        response = EntityRelationshipResponse(
            query_entity=entity,
            total_results=len(related_entities),
            max_depth=max_depth,
            related_entities=related_entities,
            execution_time=execution_time,
            timestamp=datetime.utcnow(),
        )

        logger.info(
            "Successfully returned {0} related entities for {1}".format(
                len(related_entities), entity
            )
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error processing related entities request for {0}: {1}".format(
                entity, str(e)
            )
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve related entities: {0}".format(str(e)),
        )


@router.get("/event_timeline", response_model=EventTimelineResponse)
async def get_event_timeline(
    topic: str = Query(..., description="Topic or entity to create timeline for"),
    start_date: Optional[str] = Query(
        None, description="Start date (YYYY-MM-DD format)"
    ),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD format)"),
    max_events: int = Query(50, ge=1, le=200, description="Maximum number of events"),
    event_types: Optional[str] = Query(
        None, description="Comma-separated event types to filter by"
    ),
    include_articles: bool = Query(True, description="Include source articles"),
    populator: EnhancedKnowledgeGraphPopulator = Depends(get_enhanced_graph_populator),
) -> EventTimelineResponse:
    """
    Get chronological timeline of events related to a specific topic or entity.

    This endpoint queries the knowledge graph to find articles and events
    related to the specified topic, organized chronologically.

    Example:
        GET /api/v1/knowledge-graph/event_timeline?topic=AI%20Regulations&max_events=30
    """
    start_time = datetime.now()

    try:
        logger.info("API request for event timeline: {0}".format(topic))

        # Validate input
        if not topic or len(topic.strip()) < 2:
            raise HTTPException(
                status_code=400, detail="Topic must be at least 2 characters long"
            )

        # Parse date filters
        start_datetime = None
        end_datetime = None
        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD"
                )

        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD"
                )

        # Parse event types filter
        event_filter = None
        if event_types:
            event_filter = [et.strip() for et in event_types.split(",")]

        # Query timeline events using enhanced graph capabilities
        timeline_events = await _query_timeline_events(
            populator=populator,
            topic=topic,
            start_date=start_datetime,
            end_date=end_datetime,
            max_events=max_events,
            event_types=event_filter,
            include_articles=include_articles,
        )

        # Calculate execution time
        execution_time = (datetime.now() - start_time).total_seconds()

        # Determine timeline span
        timeline_span = {"start_date": start_datetime, "end_date": end_datetime}
        if timeline_events:
            actual_start = min(event.event_date for event in timeline_events)
            actual_end = max(event.event_date for event in timeline_events)
            if not start_datetime:
                timeline_span["start_date"] = actual_start
            if not end_datetime:
                timeline_span["end_date"] = actual_end

        response = EventTimelineResponse(
            topic=topic,
            timeline_span=timeline_span,
            total_events=len(timeline_events),
            events=timeline_events,
            execution_time=execution_time,
            timestamp=datetime.utcnow(),
        )

        logger.info(
            "Successfully returned {0} timeline events for {1}".format(
                len(timeline_events), topic
            )
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error processing event timeline request for {0}: {1}".format(topic, str(e))
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve event timeline: {0}".format(str(e)),
        )


@router.get("/entity_details/{entity_id}")
async def get_entity_details(
    entity_id: str = Path(..., description="Unique identifier of the entity"),
    include_relationships: bool = Query(
        True, description="Include relationship information"
    ),
    include_articles: bool = Query(True, description="Include source articles"),
    include_properties: bool = Query(True, description="Include entity properties"),
    populator: EnhancedKnowledgeGraphPopulator = Depends(get_enhanced_graph_populator),
) -> Dict[str, Any]:
    """
    Get detailed information about a specific entity including its properties,
    relationships, and source articles.

    Example:
        GET /api/v1/knowledge-graph/entity_details/google_inc_001
    """
    try:
        logger.info("API request for entity details: {0}".format(entity_id))

        # Query entity details using Gremlin
        entity_details = await _query_entity_details(
            populator=populator,
            entity_id=entity_id,
            include_relationships=include_relationships,
            include_articles=include_articles,
            include_properties=include_properties,
        )

        if not entity_details:
            raise HTTPException(
                status_code=404, detail=f"Entity with ID '{entity_id}' not found"
            )

        logger.info("Successfully returned details for entity {0}".format(entity_id))
        return entity_details

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error retrieving entity details for {0}: {1}".format(entity_id, str(e))
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve entity details: {0}".format(str(e)),
        )


@router.post("/graph_search")
async def advanced_graph_search(
    query: GraphSearchQuery,
    populator: EnhancedKnowledgeGraphPopulator = Depends(get_enhanced_graph_populator),
) -> Dict[str, Any]:
    """
    Perform advanced graph search with custom filters and parameters.

    Supports different query types:
    - 'entity': Search for entities by name or properties
    - 'relationship': Search for specific relationships
    - 'path': Find paths between entities

    Example POST body:
    {
        "query_type": "entity",
        "search_terms": ["artificial intelligence", "Google"],
        "filters": {"entity_type": "TECHNOLOGY"},
        "sort_by": "confidence",
        "limit": 20
    }
    """
    try:
        logger.info(
            "API request for advanced graph search: {0}".format(query.query_type)
        )

        # Validate query type
        valid_query_types = ["entity", "relationship", "path"]
        if query.query_type not in valid_query_types:
            raise HTTPException(
                status_code=400,
                detail="Invalid query_type. Must be one of: {0}".format(
                    valid_query_types
                ),
            )

        # Execute search based on query type
        search_results = await _execute_advanced_search(
            populator=populator,
            query_type=query.query_type,
            search_terms=query.search_terms,
            filters=query.filters,
            sort_by=query.sort_by,
            limit=query.limit,
        )

        response = {
            "query_type": query.query_type,
            "search_terms": query.search_terms,
            "total_results": len(search_results),
            "results": search_results,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(
            "Successfully returned {0} search results".format(len(search_results))
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing advanced graph search: {0}".format(str(e)))
        raise HTTPException(
            status_code=500, detail="Failed to execute graph search: {0}".format(str(e))
        )


@router.get("/graph_analytics")
async def get_graph_analytics(
    metric_type: str = Query(
        "overview", description="Type of analytics: overview, centrality, clustering"
    ),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    top_n: int = Query(10, ge=1, le=100, description="Number of top results to return"),
    populator: EnhancedKnowledgeGraphPopulator = Depends(get_enhanced_graph_populator),
) -> Dict[str, Any]:
    """
    Get analytics and metrics about the knowledge graph structure and content.

    Available metrics:
    - 'overview': General graph statistics
    - 'centrality': Most connected entities
    - 'clustering': Entity clusters and communities

    Example:
        GET /api/v1/knowledge-graph/graph_analytics?metric_type=centrality&top_n=20
    """
    try:
        logger.info("API request for graph analytics: {0}".format(metric_type))

        # Validate metric type
        valid_metrics = ["overview", "centrality", "clustering"]
        if metric_type not in valid_metrics:
            raise HTTPException(
                status_code=400,
                detail="Invalid metric_type. Must be one of: {0}".format(valid_metrics),
            )

        # Get graph analytics
        analytics_result = await _get_graph_analytics(
            populator=populator,
            metric_type=metric_type,
            entity_type=entity_type,
            top_n=top_n,
        )

        response = {
            "metric_type": metric_type,
            "entity_type_filter": entity_type,
            "analytics": analytics_result,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info("Successfully returned graph analytics for {0}".format(metric_type))
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing graph analytics request: {0}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve graph analytics: {0}".format(str(e)),
        )


@router.get("/sparql_query")
async def execute_sparql_query(
    query: str = Query(..., description="SPARQL query to execute"),
    format: str = Query("json", description="Response format: json, xml, turtle"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    populator: EnhancedKnowledgeGraphPopulator = Depends(get_enhanced_graph_populator),
) -> Dict[str, Any]:
    """
    Execute a SPARQL query against the knowledge graph.

    Note: This endpoint requires Neptune SPARQL endpoint configuration.

    Example:
        GET /api/v1/knowledge-graph/sparql_query?query=SELECT * WHERE { ?s ?p ?o } LIMIT 10
    """
    try:
        logger.info("API request for SPARQL query execution")

        # Validate SPARQL query
        if not query or len(query.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="SPARQL query must be at least 10 characters long",
            )

        # Execute SPARQL query using enhanced populator
        sparql_result = await populator.execute_sparql_query(query)

        response = {
            "query": query,
            "format": format,
            "limit": limit,
            "results": sparql_result,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info("Successfully executed SPARQL query")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error executing SPARQL query: {0}".format(str(e)))
        raise HTTPException(
            status_code=500, detail="Failed to execute SPARQL query: {0}".format(str(e))
        )


# Helper functions


async def _query_timeline_events(
    populator: EnhancedKnowledgeGraphPopulator,
    topic: str,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    max_events: int,
    event_types: Optional[List[str]],
    include_articles: bool,
) -> List[TimelineEvent]:
    """Query timeline events from the knowledge graph."""
    try:
        # Use Gremlin to find articles related to the topic
        gremlin_query = """
        g.V().hasLabel('Article')
             .or(
                 has('title', containing('{topic}')),
                 has('content', containing('{topic}'))
             )
        """

        # Add date filters if provided
        if start_date:
            gremlin_query += f".has('published_date', gte('{
                start_date.isoformat()}'))"
        if end_date:
            gremlin_query += f".has('published_date', lte('{
                end_date.isoformat()}'))"

        gremlin_query += (
            f".order().by('published_date', desc).limit({max_events}).valueMap(true)"
        )

        # Execute query using enhanced populator's graph builder
        results = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.V()
            .hasLabel("Article")
            .has("title", containing(topic))
            .order()
            .by("published_date", descending)
            .limit(max_events)
            .valueMap(True)
        )

        # Convert results to TimelineEvent objects
        timeline_events = []
        for i, article in enumerate(results):
            # Extract event information from article
            event_date_str = article.get("published_date", [""])[0]
            try:
                event_date = (
                    datetime.fromisoformat(event_date_str)
                    if event_date_str
                    else datetime.utcnow()
                )
            except ValueError:
                event_date = datetime.utcnow()

            # Get entities mentioned in the article
            entities_involved = await _get_article_entities(
                populator, article.get("id", [""])[0]
            )

            timeline_event = TimelineEvent(
                event_id=f"event_{i}_{article.get('id', [''])[0]}",
                event_title=article.get("title", ["Unknown Event"])[0],
                event_date=event_date,
                event_type="article",  # Could be enhanced with NLP classification
                description=(
                    article.get("content", [""])[0][:500] + "..."
                    if article.get("content")
                    else ""
                ),
                entities_involved=entities_involved,
                source_article_id=article.get("id", [""])[0],
                confidence=0.85,  # Could be calculated based on topic relevance
                metadata={
                    "author": article.get("author", [""])[0],
                    "source_url": article.get("source_url", [""])[0],
                    "category": article.get("category", [""])[0],
                },
            )
            timeline_events.append(timeline_event)

        return timeline_events

    except Exception as e:
        logger.error("Error querying timeline events: {0}".format(e))
        return []


async def _get_article_entities(
    populator: EnhancedKnowledgeGraphPopulator, article_id: str
) -> List[str]:
    """Get entities mentioned in a specific article."""
    try:
        # Query entities connected to the article
        results = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.V()
            .has("id", article_id)
            .out("MENTIONS_PERSON", "MENTIONS_ORG", "MENTIONS_TECH", "MENTIONS_POLICY")
            .values("normalized_form")
            .dedup()
            .limit(20)
        )

        return results or []

    except Exception as e:
        logger.debug("Error getting article entities: {0}".format(e))
        return []


async def _query_entity_details(
    populator: EnhancedKnowledgeGraphPopulator,
    entity_id: str,
    include_relationships: bool,
    include_articles: bool,
    include_properties: bool,
) -> Optional[Dict[str, Any]]:
    """Query detailed information about a specific entity."""
    try:
        # Get entity basic information
        entity_results = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.V().has("id", entity_id).valueMap(True)
        )

        if not entity_results:
            return None

        entity_data = entity_results[0]

        # Build response
        details = {
            "entity_id": entity_id,
            "entity_name": entity_data.get("normalized_form", ["Unknown"])[0],
            "entity_type": entity_data.get("entity_type", ["Unknown"])[0],
            "confidence": entity_data.get("confidence", [0.0])[0],
            "mention_count": entity_data.get("mention_count", [0])[0],
            "created_at": entity_data.get("created_at", [""])[0],
        }

        # Add properties if requested
        if include_properties:
            properties = {}
            for key, value in entity_data.items():
                if key not in ["id", "label", "normalized_form", "entity_type"]:
                    properties[key] = value[0] if value else None
            details["properties"] = properties

        # Add relationships if requested
        if include_relationships:
            relationships = await _get_entity_relationships(populator, entity_id)
            details["relationships"] = relationships

        # Add source articles if requested
        if include_articles:
            articles = await _get_entity_articles(populator, entity_id)
            details["source_articles"] = articles

        return details

    except Exception as e:
        logger.error("Error querying entity details: {0}".format(e))
        return None


async def _get_entity_relationships(
    populator: EnhancedKnowledgeGraphPopulator, entity_id: str
) -> List[Dict[str, Any]]:
    """Get relationships for a specific entity."""
    try:
        # Query outgoing relationships
        out_results = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.V()
            .has("id", entity_id)
            .outE()
            .project("type", "target", "properties")
            .by(T.label)
            .by(inV().valueMap("normalized_form", "entity_type"))
            .by(valueMap())
            .limit(50)
        )

        # Query incoming relationships
        in_results = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.V()
            .has("id", entity_id)
            .inE()
            .project("type", "source", "properties")
            .by(T.label)
            .by(outV().valueMap("normalized_form", "entity_type"))
            .by(valueMap())
            .limit(50)
        )

        relationships = []

        # Process outgoing relationships
        for rel in out_results:
            relationships.append(
                {
                    "direction": "outgoing",
                    "type": rel.get("type", "UNKNOWN"),
                    "target_entity": rel.get("target", {}),
                    "properties": rel.get("properties", {}),
                }
            )

        # Process incoming relationships
        for rel in in_results:
            relationships.append(
                {
                    "direction": "incoming",
                    "type": rel.get("type", "UNKNOWN"),
                    "source_entity": rel.get("source", {}),
                    "properties": rel.get("properties", {}),
                }
            )

        return relationships

    except Exception as e:
        logger.debug("Error getting entity relationships: {0}".format(e))
        return []


async def _get_entity_articles(
    populator: EnhancedKnowledgeGraphPopulator, entity_id: str
) -> List[Dict[str, Any]]:
    """Get articles that mention a specific entity."""
    try:
        results = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.V()
            .has("id", entity_id)
            .in_("MENTIONS_PERSON", "MENTIONS_ORG", "MENTIONS_TECH", "MENTIONS_POLICY")
            .valueMap("id", "title", "published_date", "author")
            .limit(20)
        )

        articles = []
        for article in results:
            articles.append(
                {
                    "article_id": article.get("id", [""])[0],
                    "title": article.get("title", [""])[0],
                    "published_date": article.get("published_date", [""])[0],
                    "author": article.get("author", [""])[0],
                }
            )

        return articles

    except Exception as e:
        logger.debug("Error getting entity articles: {0}".format(e))
        return []


async def _execute_advanced_search(
    populator: EnhancedKnowledgeGraphPopulator,
    query_type: str,
    search_terms: List[str],
    filters: Dict[str, Any],
    sort_by: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Execute advanced graph search based on query type."""
    try:
        if query_type == "entity":
            return await _search_entities(
                populator, search_terms, filters, sort_by, limit
            )
        elif query_type == "relationship":
            return await _search_relationships(
                populator, search_terms, filters, sort_by, limit
            )
        elif query_type == "path":
            return await _search_paths(populator, search_terms, filters, sort_by, limit)
        else:
            return []

    except Exception as e:
        logger.error("Error executing advanced search: {0}".format(e))
        return []


async def _search_entities(
    populator: EnhancedKnowledgeGraphPopulator,
    search_terms: List[str],
    filters: Dict[str, Any],
    sort_by: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Search for entities by terms and filters."""
    try:
        # Build search query
        base_query = populator.graph_builder.g.V()

        # Apply entity type filter
        if "entity_type" in filters:
            base_query = base_query.has("entity_type", filters["entity_type"])

        # Apply search terms (search in normalized_form)
        if search_terms:
            term_filters = []
            for term in search_terms:
                term_filters.append(f"has('normalized_form', containing('{term}'))")

            # Combine with OR logic
            search_query = base_query
            for i, term in enumerate(search_terms):
                if i == 0:
                    search_query = search_query.has("normalized_form", containing(term))
                else:
                    search_query = search_query.or_(
                        has("normalized_form", containing(term))
                    )
        else:
            search_query = base_query

        # Apply sorting
        if sort_by == "confidence":
            search_query = search_query.order().by("confidence", desc)
        elif sort_by == "date":
            search_query = search_query.order().by("created_at", desc)
        else:  # relevance (default)
            search_query = search_query.order().by("mention_count", desc)

        # Execute query
        results = await populator.graph_builder._execute_traversal(
            search_query.limit(limit).valueMap(True)
        )

        # Format results
        entities = []
        for entity in results:
            entities.append(
                {
                    "entity_id": entity.get("id", [""])[0],
                    "entity_name": entity.get("normalized_form", [""])[0],
                    "entity_type": entity.get("entity_type", [""])[0],
                    "confidence": entity.get("confidence", [0.0])[0],
                    "mention_count": entity.get("mention_count", [0])[0],
                    "properties": {
                        k: v[0] if v else None
                        for k, v in entity.items()
                        if k not in ["id", "label"]
                    },
                }
            )

        return entities

    except Exception as e:
        logger.error("Error searching entities: {0}".format(e))
        return []


async def _search_relationships(
    populator: EnhancedKnowledgeGraphPopulator,
    search_terms: List[str],
    filters: Dict[str, Any],
    sort_by: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Search for relationships by terms and filters."""
    try:
        # This is a simplified implementation
        # In practice, you'd want more sophisticated relationship searching
        results = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.E()
            .limit(limit)
            .project("type", "source", "target", "properties")
            .by(T.label)
            .by(outV().valueMap("normalized_form"))
            .by(inV().valueMap("normalized_form"))
            .by(valueMap())
        )

        relationships = []
        for rel in results:
            relationships.append(
                {
                    "relationship_type": rel.get("type", "UNKNOWN"),
                    "source_entity": rel.get("source", {}),
                    "target_entity": rel.get("target", {}),
                    "properties": rel.get("properties", {}),
                }
            )

        return relationships

    except Exception as e:
        logger.error("Error searching relationships: {0}".format(e))
        return []


async def _search_paths(
    populator: EnhancedKnowledgeGraphPopulator,
    search_terms: List[str],
    filters: Dict[str, Any],
    sort_by: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Search for paths between entities."""
    try:
        if len(search_terms) < 2:
            return []

        # Find paths between first two search terms
        source_term = search_terms[0]
        target_term = search_terms[1]
        max_path_length = filters.get("max_path_length", 4)

        # This is a simplified path search
        # In practice, you'd want more sophisticated path finding algorithms
        results = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.V()
            .has("normalized_form", source_term)
            .repeat(bothE().otherV().simplePath())
            .until(has("normalized_form", target_term))
            .limit(max_path_length)
            .path()
            .limit(limit)
        )

        paths = []
        for i, path in enumerate(results):
            paths.append(
                {
                    "path_id": "path_{0}".format(i),
                    "source": source_term,
                    "target": target_term,
                    "length": len(path) - 1,
                    "nodes": [str(node) for node in path],
                }
            )

        return paths

    except Exception as e:
        logger.error("Error searching paths: {0}".format(e))
        return []


async def _get_graph_analytics(
    populator: EnhancedKnowledgeGraphPopulator,
    metric_type: str,
    entity_type: Optional[str],
    top_n: int,
) -> Dict[str, Any]:
    """Get graph analytics and metrics."""
    try:
        if metric_type == "overview":
            return await _get_overview_analytics(populator, entity_type)
        elif metric_type == "centrality":
            return await _get_centrality_analytics(populator, entity_type, top_n)
        elif metric_type == "clustering":
            return await _get_clustering_analytics(populator, entity_type, top_n)
        else:
            return {}

    except Exception as e:
        logger.error("Error getting graph analytics: {0}".format(e))
        return {}


async def _get_overview_analytics(
    populator: EnhancedKnowledgeGraphPopulator, entity_type: Optional[str]
) -> Dict[str, Any]:
    """Get overview analytics of the graph."""
    try:
        # Get basic counts
        vertex_count_query = populator.graph_builder.g.V()
        if entity_type:
            vertex_count_query = vertex_count_query.has("entity_type", entity_type)

        vertex_count = await populator.graph_builder._execute_traversal(
            vertex_count_query.count()
        )
        edge_count = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.E().count()
        )

        # Get entity type distribution
        type_distribution = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.V().groupCount().by("entity_type")
        )

        return {
            "total_vertices": vertex_count[0] if vertex_count else 0,
            "total_edges": edge_count[0] if edge_count else 0,
            "entity_type_distribution": (
                type_distribution[0] if type_distribution else {}
            ),
            "analysis_date": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Error getting overview analytics: {0}".format(e))
        return {}


async def _get_centrality_analytics(
    populator: EnhancedKnowledgeGraphPopulator, entity_type: Optional[str], top_n: int
) -> Dict[str, Any]:
    """Get centrality analytics (most connected entities)."""
    try:
        # Get entities with highest degree centrality (most connections)
        centrality_query = populator.graph_builder.g.V()
        if entity_type:
            centrality_query = centrality_query.has("entity_type", entity_type)

        results = await populator.graph_builder._execute_traversal(
            centrality_query.project("entity", "degree")
            .by(valueMap("normalized_form", "entity_type"))
            .by(bothE().count())
            .order()
            .by(select("degree"), desc)
            .limit(top_n)
        )

        centrality_data = []
        for result in results:
            entity_info = result.get("entity", {})
            centrality_data.append(
                {
                    "entity_name": entity_info.get("normalized_form", ["Unknown"])[0],
                    "entity_type": entity_info.get("entity_type", ["Unknown"])[0],
                    "degree_centrality": result.get("degree", 0),
                }
            )

        return {
            "top_central_entities": centrality_data,
            "metric": "degree_centrality",
            "top_n": top_n,
        }

    except Exception as e:
        logger.error("Error getting centrality analytics: {0}".format(e))
        return {}


async def _get_clustering_analytics(
    populator: EnhancedKnowledgeGraphPopulator, entity_type: Optional[str], top_n: int
) -> Dict[str, Any]:
    """Get clustering analytics."""
    try:
        # This is a simplified clustering analysis
        # In practice, you'd want more sophisticated community detection
        # algorithms

        # Get densely connected entity groups
        results = await populator.graph_builder._execute_traversal(
            populator.graph_builder.g.V().has("entity_type", entity_type)
            if entity_type
            else populator.graph_builder.g.V()
            .bothE()
            .groupCount()
            .by(otherV().values("entity_type"))
            .order(local)
            .by(values, desc)
            .limit(local, top_n)
        )

        return {
            "entity_type_clusters": results[0] if results else {},
            "analysis_method": "entity_type_grouping",
            "top_n": top_n,
        }

    except Exception as e:
        logger.error("Error getting clustering analytics: {0}".format(e))
        return {}


# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check endpoint for the knowledge graph API."""
    try:
        return {
            "status": "healthy",
            "service": "knowledge-graph-api",
            "enhanced_kg_available": ENHANCED_KG_AVAILABLE,
            "config_available": CONFIG_AVAILABLE,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="Service unhealthy: {0}".format(str(e)),
        )
