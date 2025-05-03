"""
FastAPI routes for knowledge graph queries.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.knowledge_graph.graph_builder import GraphBuilder
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/graph", tags=["knowledge-graph"])

# Initialize graph connection
graph = GraphBuilder(os.getenv('NEPTUNE_ENDPOINT'))

@router.get("/related_entities")
async def get_related_entities(
    entity: str = Query(..., description="Entity name to find relationships for"),
    entity_type: Optional[str] = Query(None, description="Type of entity (Organization, Person, Event)"),
    max_depth: int = Query(2, description="Maximum relationship depth to traverse"),
    relationship_types: Optional[List[str]] = Query(None, description="Filter by relationship types")
) -> Dict[str, Any]:
    """
    Get entities related to the specified entity through various relationships.
    
    Example: /graph/related_entities?entity=Google&entity_type=Organization&max_depth=2
    """
    try:
        # Build base query
        g = graph.g
        
        # Start with the entity
        query = g.V()
        
        if entity_type:
            query = query.hasLabel(entity_type)
        
        query = query.has('name', entity).aggregate('start')
        
        # Build relationship traversal
        for _ in range(max_depth):
            if relationship_types:
                query = query.outE(*relationship_types).inV()
            else:
                query = query.out()
            
            query = query.dedup()
        
        # Project results
        results = query.project(
            'entity', 'type', 'relationships', 'articles'
        ).by(
            __.valueMap(True)
        ).by(
            __.label()
        ).by(
            __.outE().group().by(__.label()).by(__.count())
        ).by(
            __.in_('MENTIONS_ORG', 'MENTIONS_PERSON', 'COVERS_EVENT')
            .hasLabel('Article')
            .valueMap('headline', 'publishDate')
            .fold()
        ).toList()
        
        # Format response
        formatted_results = {
            "entity": entity,
            "related_entities": [
                {
                    "name": r['entity'].get('name', r['entity'].get('orgName', r['entity'].get('eventName', 'Unknown')))[0],
                    "type": r['type'],
                    "relationship_counts": r['relationships'],
                    "mentioned_in": [
                        {
                            "headline": article['headline'][0],
                            "date": article['publishDate'][0].isoformat()
                        }
                        for article in r['articles']
                    ]
                }
                for r in results
            ]
        }
        
        return formatted_results
        
    except Exception as e:
        logger.error(f"Error getting related entities: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/event_timeline")
async def get_event_timeline(
    topic: str = Query(..., description="Topic to create timeline for"),
    start_date: Optional[datetime] = Query(None, description="Start date for timeline"),
    end_date: Optional[datetime] = Query(None, description="End date for timeline"),
    include_related: bool = Query(True, description="Include related events")
) -> Dict[str, Any]:
    """
    Get a timeline of events related to a specific topic.
    
    Example: /graph/event_timeline?topic=AI Regulation&start_date=2024-01-01
    """
    try:
        g = graph.g
        
        # Build base query for events with the topic
        query = g.V().hasLabel('Event').has('keywords', topic)
        
        # Add date filters if provided
        if start_date:
            query = query.has('startDate', P.gte(start_date))
        if end_date:
            query = query.has('startDate', P.lte(end_date))
        
        # Get event details and related entities
        results = query.project(
            'event', 'date', 'location', 'organizations', 'people', 'articles'
        ).by(
            'eventName'
        ).by(
            'startDate'
        ).by(
            'location'
        ).by(
            __.in_('HOSTED', 'SPONSORED')
            .hasLabel('Organization')
            .valueMap('orgName', 'orgType')
            .fold()
        ).by(
            __.in_('PARTICIPATED_IN', 'ORGANIZED')
            .hasLabel('Person')
            .valueMap('name', 'title')
            .fold()
        ).by(
            __.in_('COVERS_EVENT')
            .hasLabel('Article')
            .valueMap('headline', 'publishDate', 'url')
            .fold()
        ).toList()
        
        # Format timeline
        timeline = {
            "topic": topic,
            "events": [
                {
                    "name": r['event'],
                    "date": r['date'].isoformat(),
                    "location": r['location'],
                    "organizations": [
                        {
                            "name": org['orgName'][0],
                            "type": org['orgType'][0]
                        }
                        for org in r['organizations']
                    ],
                    "people": [
                        {
                            "name": person['name'][0],
                            "title": person['title'][0]
                        }
                        for person in r['people']
                    ],
                    "coverage": [
                        {
                            "headline": article['headline'][0],
                            "date": article['publishDate'][0].isoformat(),
                            "url": article['url'][0]
                        }
                        for article in r['articles']
                    ]
                }
                for r in results
            ]
        }
        
        # Sort events by date
        timeline["events"].sort(key=lambda x: x["date"])
        
        return timeline
        
    except Exception as e:
        logger.error(f"Error getting event timeline: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Check the health of the graph database connection.
    """
    try:
        # Try a simple query to verify connection
        graph.g.V().limit(1).toList()
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="Graph database connection failed")