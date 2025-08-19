"""
API Routes for Knowledge Graph Related Entities

This module provides FastAPI endpoints for querying entity relationships
and knowledge graph data populated from NLP processing.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.config import get_settings
from src.knowledge_graph.nlp_populator import (
    KnowledgeGraphPopulator,
    get_entity_relationships,
)

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1", tags=["knowledge-graph"])

# Get configuration
settings = get_settings()


async def get_graph_populator() -> KnowledgeGraphPopulator:
    """Dependency to get KnowledgeGraphPopulator instance."""
    return KnowledgeGraphPopulator(neptune_endpoint=settings.NEPTUNE_ENDPOINT)


@router.get("/related_entities")
async def get_related_entities_endpoint(
    entity_name: str = Query(
        ..., description="Name of the entity to find relationships for"
    ),
    max_results: int = Query(
        10, ge=1, le=100, description="Maximum number of related entities to return"
    ),
    include_confidence: bool = Query(
        True, description="Include confidence scores in results"
    ),
    min_confidence: float = Query(
        0.0,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for relationships",
    ),
    populator: KnowledgeGraphPopulator = Depends(get_graph_populator),
) -> Dict[str, Any]:
    """
    Get entities related to a specified entity from the knowledge graph.

    This endpoint returns entities that have relationships with the specified entity,
    based on NLP-extracted data and knowledge graph connections.

    Args:
        entity_name: Name of the entity to find relationships for
        max_results: Maximum number of related entities to return (1-100)
        include_confidence: Whether to include confidence scores
        min_confidence: Minimum confidence threshold for filtering results

    Returns:
        Dictionary containing related entities and metadata

    Raises:
        HTTPException: If entity is not found or processing fails
    """
    try:
        logger.info(f"API request for related entities: {entity_name}")

        # Validate input
        if not entity_name or len(entity_name.strip()) < 2:
            raise HTTPException(
                status_code=400, detail="Entity name must be at least 2 characters long"
            )

        # Get related entities from knowledge graph
        related_entities = await populator.get_related_entities(
            entity_name=entity_name, max_results=max_results
        )

        # Filter by confidence if specified
        if min_confidence > 0.0:
            related_entities = [
                entity
                for entity in related_entities
                if entity.get("confidence", 0.0) >= min_confidence
            ]

        # Remove confidence scores if not requested
        if not include_confidence:
            for entity in related_entities:
                entity.pop("confidence", None)

        # Prepare response
        response = {
            "query_entity": entity_name,
            "total_results": len(related_entities),
            "max_results_requested": max_results,
            "min_confidence_threshold": (
                min_confidence if min_confidence > 0.0 else None
            ),
            "related_entities": related_entities,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success",
        }

        logger.info(
            f"Successfully returned {len(related_entities)} related entities for {entity_name}"
        )
        return response

    except Exception as e:
        logger.error(
            f"Error processing related entities request for {entity_name}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve related entities: {str(e)}"
        )
    finally:
        await populator.close()


@router.get("/entity_details/{entity_id}")
async def get_entity_details(
    entity_id: str,
    include_relationships: bool = Query(
        True, description="Include relationship information"
    ),
    include_articles: bool = Query(True, description="Include source articles"),
    populator: KnowledgeGraphPopulator = Depends(get_graph_populator),
) -> Dict[str, Any]:
    """
    Get detailed information about a specific entity.

    Args:
        entity_id: Unique identifier of the entity
        include_relationships: Whether to include relationship data
        include_articles: Whether to include source article information

    Returns:
        Dictionary containing entity details and metadata

    Raises:
        HTTPException: If entity is not found or processing fails
    """
    try:
        logger.info(f"API request for entity details: {entity_id}")

        # Find entity in graph
        entity = await populator._find_entity(entity_id)
        if not entity:
            raise HTTPException(
                status_code=404, detail=f"Entity with ID {entity_id} not found"
            )

        response = {
            "entity_id": entity_id,
            "entity_name": entity.get("text", ""),
            "entity_type": entity.get("entity_type", ""),
            "normalized_form": entity.get("normalized_form", ""),
            "mention_count": entity.get("mention_count", 0),
            "first_seen": entity.get("first_seen", ""),
            "confidence": entity.get("confidence", 0.0),
            "timestamp": datetime.utcnow().isoformat(),
        }

        if include_relationships:
            related_entities = await populator.get_related_entities(
                entity.get("normalized_form", ""), max_results=50
            )
            response["relationships"] = related_entities

        if include_articles:
            # Get source articles (placeholder - would need implementation in graph_builder)
            response["source_articles"] = entity.get("source_articles", [])

        logger.info(f"Successfully returned details for entity {entity_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting entity details for {entity_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve entity details: {str(e)}"
        )
    finally:
        await populator.close()


@router.post("/populate_article")
async def populate_article_endpoint(
    article_data: Dict[str, Any],
    populator: KnowledgeGraphPopulator = Depends(get_graph_populator),
) -> Dict[str, Any]:
    """
    Populate the knowledge graph with entities and relationships from an article.

    Args:
        article_data: Dictionary containing article information
                     Required fields: id, title, content
                     Optional fields: published_date

    Returns:
        Dictionary containing processing statistics

    Raises:
        HTTPException: If article data is invalid or processing fails
    """
    try:
        logger.info(f"API request to populate article: {article_data.get('id')}")

        # Validate required fields
        required_fields = ["id", "title", "content"]
        for field in required_fields:
            if field not in article_data or not article_data[field]:
                raise HTTPException(
                    status_code=400, detail=f"Missing required field: {field}"
                )

        # Parse published date if provided
        published_date = None
        if "published_date" in article_data and article_data["published_date"]:
            try:
                published_date = datetime.fromisoformat(
                    article_data["published_date"].replace("Z", "+00:00")
                )
            except ValueError:
                logger.warning(
                    f"Invalid published_date format: {article_data['published_date']}"
                )

        # Process article
        stats = await populator.populate_from_article(
            article_id=article_data["id"],
            title=article_data["title"],
            content=article_data["content"],
            published_date=published_date,
        )

        logger.info(f"Successfully populated article {article_data['id']}")
        return {
            "status": "success",
            "processing_stats": stats,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error populating article {article_data.get('id')}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to populate article: {str(e)}"
        )
    finally:
        await populator.close()


@router.post("/batch_populate")
async def batch_populate_articles_endpoint(
    articles: List[Dict[str, Any]],
    populator: KnowledgeGraphPopulator = Depends(get_graph_populator),
) -> Dict[str, Any]:
    """
    Populate the knowledge graph with multiple articles in batch.

    Args:
        articles: List of article dictionaries

    Returns:
        Dictionary containing batch processing statistics

    Raises:
        HTTPException: If processing fails
    """
    try:
        logger.info(f"API request for batch population of {len(articles)} articles")

        if not articles:
            raise HTTPException(
                status_code=400, detail="No articles provided for batch processing"
            )

        if len(articles) > 100:
            raise HTTPException(
                status_code=400,
                detail="Batch size too large. Maximum 100 articles per batch.",
            )

        # Process articles in batch
        batch_stats = await populator.batch_populate_articles(articles)

        logger.info(f"Successfully completed batch processing")
        return {
            "status": "success",
            "batch_stats": batch_stats,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch article population: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to process batch: {str(e)}"
        )
    finally:
        await populator.close()


@router.get("/knowledge_graph_stats")
async def get_knowledge_graph_stats(
    populator: KnowledgeGraphPopulator = Depends(get_graph_populator),
) -> Dict[str, Any]:
    """
    Get statistics about the knowledge graph population.

    Returns:
        Dictionary containing graph statistics
    """
    try:
        logger.info("API request for knowledge graph statistics")

        # Get graph statistics (placeholder - would need implementation in graph_builder)
        stats = {
            "total_entities": 0,  # Would query from Neptune
            "total_relationships": 0,  # Would query from Neptune
            "total_articles": 0,  # Would query from Neptune
            "entity_types": {},  # Would aggregate from Neptune
            "relationship_types": {},  # Would aggregate from Neptune
            "last_updated": datetime.utcnow().isoformat(),
            "status": "success",
        }

        # This would be implemented with actual Neptune queries
        # For now, return placeholder structure

        logger.info("Successfully returned knowledge graph statistics")
        return stats

    except Exception as e:
        logger.error(f"Error getting knowledge graph statistics: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve statistics: {str(e)}"
        )
    finally:
        await populator.close()


@router.get("/search_entities")
async def search_entities(
    query: str = Query(..., description="Search query for entities"),
    entity_types: Optional[List[str]] = Query(
        None, description="Filter by entity types"
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    populator: KnowledgeGraphPopulator = Depends(get_graph_populator),
) -> Dict[str, Any]:
    """
    Search for entities in the knowledge graph by text query.

    Args:
        query: Search query string
        entity_types: Optional list of entity types to filter by
        limit: Maximum number of results to return

    Returns:
        Dictionary containing search results
    """
    try:
        logger.info(f"API request to search entities: {query}")

        if len(query.strip()) < 2:
            raise HTTPException(
                status_code=400,
                detail="Search query must be at least 2 characters long",
            )

        # Search entities (placeholder - would need implementation in graph_builder)
        # This would perform text search across entity names and normalized forms
        results = []  # Would query from Neptune with text search

        response = {
            "query": query,
            "entity_types_filter": entity_types,
            "total_results": len(results),
            "results": results,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success",
        }

        logger.info(f"Successfully returned {len(results)} search results for: {query}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching entities for query {query}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to search entities: {str(e)}"
        )
    finally:
        await populator.close()
