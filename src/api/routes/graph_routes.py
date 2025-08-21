"""
FastAPI routes for knowledge graph queries.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from gremlin_python.process.traversal import (  # Predicates and T tokens (like T.label)
    P,
    T,
)

from src.knowledge_graph.graph_builder import GraphBuilder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/graph", tags=["knowledge-graph"])

# Global variable to hold the GraphBuilder instance
graph_builder_instance: Optional[GraphBuilder] = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # app parameter is conventional for lifespan
    global graph_builder_instance
    logger.info("Application startup: Initializing GraphBuilder...")
    NEPTUNE_ENDPOINT = os.getenv("NEPTUNE_ENDPOINT", "ws://localhost:8182/gremlin")
    graph_builder_instance = GraphBuilder(NEPTUNE_ENDPOINT)
    try:
        await graph_builder_instance.connect()
        logger.info("GraphBuilder connected successfully.")
    except Exception as e:
        logger.error("GraphBuilder failed to connect during startup: {0}".format(e))
        graph_builder_instance = None

    yield

    logger.info("Application shutdown: Closing GraphBuilder connection...")
    if (
        graph_builder_instance
        and hasattr(graph_builder_instance, "close")
        and callable(graph_builder_instance.close)
    ):
        try:
            await graph_builder_instance.close()
            logger.info("GraphBuilder connection closed successfully.")
        except Exception as e:
            logger.error("Error during GraphBuilder close: {0}".format(e))
    elif graph_builder_instance:
        logger.warning(
            "GraphBuilder instance does not have a callable close method or was None initially."
        )
    else:
        logger.info("GraphBuilder instance was None, no close action needed.")


async def get_graph() -> GraphBuilder:
    if graph_builder_instance is None:
        logger.error("GraphBuilder instance is not available (was None after startup).")
        raise HTTPException(
            status_code=503,
            detail="Graph database service not available (not initialized).",
        )

    if not hasattr(graph_builder_instance, "g") or graph_builder_instance.g is None:
        logger.error(
            "GraphBuilder's traversal source 'g' is not initialized on the instance."
        )
        try:
            logger.info("Attempting to reconnect GraphBuilder...")
            await graph_builder_instance.connect()
            if (
                not hasattr(graph_builder_instance, "g")
                or graph_builder_instance.g is None
            ):
                raise ConnectionError(
                    "Failed to re-establish graph connection (g still None)."
                )
            logger.info("GraphBuilder reconnected successfully.")
        except Exception as e:
            logger.error("Failed to reconnect GraphBuilder: {0}".format(e))
            raise HTTPException(
                status_code=503,
                detail="Graph database service not available (reconnect failed: {0}).".format(
                    e
                ),
            )
    return graph_builder_instance


@router.get("/related_entities")
async def get_related_entities(
    entity: str = Query(..., description="Entity name to find relationships for"),
    entity_type: Optional[str] = Query(
        None, description="Type of entity (Organization, Person, Event)"
    ),
    max_depth: int = Query(2, description="Maximum relationship depth to traverse"),
    relationship_types: Optional[List[str]] = Query(
        None, description="Filter by relationship types"
    ),
    graph: GraphBuilder = Depends(get_graph),
) -> Dict[str, Any]:
    try:
        g = graph.g

        query = g.V()
        if entity_type:
            query = query.hasLabel(entity_type)
        query = query.has("name", entity)

        path_query = query
        for i in range(max_depth):
            if relationship_types:
                path_query = path_query.bothE(*relationship_types).otherV().simplePath()
            else:
                path_query = path_query.both().simplePath()
            if (
                i < max_depth - 1
            ):  # Avoid dedup on the very last step if only properties are needed
                path_query = path_query.dedup()

        final_traversal = path_query.dedup().valueMap(
            True
        )  # valueMap(True) includes id, label, properties
        results = await graph._execute_traversal(final_traversal)

        formatted_results = {
            "entity": entity,
            "related_entities": [
                {
                    "name": (
                        r.get(
                            "name", r.get("orgName", r.get("eventName", ["Unknown"]))
                        )[0]
                        if isinstance(
                            r.get(
                                "name",
                                r.get("orgName", r.get("eventName", ["Unknown"])),
                            ),
                            list,
                        )
                        and r.get(
                            "name", r.get("orgName", r.get("eventName", ["Unknown"]))
                        )
                        else r.get(
                            "name", r.get("orgName", r.get("eventName", "Unknown"))
                        )
                    ),
                    # T.label is a Gremlin token, valueMap(True) should provide
                    # it.
                    "type": r.get(T.label, "Unknown") if T.label in r else "Unknown",
                    "properties": {
                        k: v[0] if isinstance(v, list) and len(v) == 1 else v
                        for k, v in r.items()
                        if k not in [T.id, T.label]
                    },
                }
                for r in results
            ],
        }
        return formatted_results

    except ConnectionError as ce:
        logger.error("Connection error in get_related_entities: {0}".format(str(ce)))
        raise HTTPException(
            status_code=503,
            detail="Graph database connection error: {0}".format(str(ce)),
        )
    except Exception as e:
        logger.error(
            f"Error getting related entities for '{entity}': {str(e)}"
        )
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail="Internal server error: {0}".format(str(e)),
        )


@router.get("/event_timeline")
async def get_event_timeline(
    topic: str = Query(..., description="Topic to create timeline for"),
    start_date: Optional[datetime] = Query(None, description="Start date for timeline"),
    end_date: Optional[datetime] = Query(None, description="End date for timeline"),
    graph: GraphBuilder = Depends(get_graph),
) -> Dict[str, Any]:
    try:
        g = graph.g
        query = g.V().hasLabel("Event").has("keywords", P.eq(topic))

        if start_date:
            query = query.has("startDate", P.gte(start_date.isoformat()))
        if end_date:
            # For lte on date, ensure the time component covers the whole day if only date is given
            # Assuming end_date from query is already a specific datetime
            query = query.has("startDate", P.lte(end_date.isoformat()))

        projected_query = (
            query.project("event_name", "date", "location")
            .by("eventName")
            .by("startDate")
            .by("location")
        )  # Ensure these are the correct property names

        results = await graph._execute_traversal(projected_query)

        timeline = {
            "topic": topic,
            "events": [
                {
                    "name": r.get("event_name", "Unknown Event"),
                    "date": r.get("date", "Unknown Date"),
                    "location": r.get("location", "Unknown Location"),
                }
                for r in results
            ],
        }
        return timeline

    except ConnectionError as ce:
        logger.error("Connection error in get_event_timeline: {0}".format(str(ce)))
        raise HTTPException(
            status_code=503,
            detail="Graph database connection error: {0}".format(str(ce)),
        )
    except Exception as e:
        logger.error(
            f"Error getting event timeline for topic '{topic}': {
                str(e)}"
        )
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail="Internal server error: {0}".format(str(e)),
        )


@router.get("/health")
async def health_check(graph: GraphBuilder = Depends(get_graph)) -> Dict[str, str]:
    try:
        await graph._execute_traversal(graph.g.V().limit(1))
        return {"status": "healthy"}
    except ConnectionError as ce:
        logger.error("Health check failed due to connection error: {0}".format(str(ce)))
        raise HTTPException(
            status_code=503,
            detail="Graph database connection error: {0}".format(str(ce)),
        )
    except Exception as e:
        logger.error("Health check failed: {0}".format(str(e)))
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=503,
            detail="Graph database connection failed: {0}".format(str(e)),
        )
