"""
Knowledge Graph streaming-update routes — Issue #42.

Exposes the live state of the in-process knowledge graph that is updated
by background tasks every time a document is ingested:

  GET /kg/connections/emerging   — new edges added since a given timestamp
  GET /kg/topics/evolving        — entities with a recent burst of new edges
  GET /kg/stats                  — current node/triple counts
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/kg", tags=["knowledge-graph-stream"])


def _load_updater():
    from src.knowledge_graph.kg_updater import (
        get_emerging_connections,
        get_evolving_topics,
        get_store_stats,
    )
    return get_emerging_connections, get_evolving_topics, get_store_stats


@router.get("/connections/emerging", response_model=List[Dict[str, Any]])
async def emerging_connections(
    since: str = Query(
        None,
        description=(
            "ISO-8601 UTC timestamp. Returns connections added after this point. "
            "Defaults to 1 hour ago."
        ),
        example="2025-01-01T00:00:00Z",
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of connections to return"),
):
    """
    Return knowledge-graph edges (triples) that were added since *since*.

    Each item describes one new connection: the two entities it links, the
    relation type, which document triggered it, and the exact timestamp it
    was recorded.

    Use this endpoint to watch for newly discovered relationships as documents
    are ingested in real time.
    """
    get_emerging_connections, _, _ = _load_updater()

    if since is None:
        since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid ISO-8601 timestamp: {since!r}. "
                       "Expected format: 2025-01-01T00:00:00Z",
            )

    return get_emerging_connections(since=since_dt, limit=limit)


@router.get("/topics/evolving", response_model=List[Dict[str, Any]])
async def evolving_topics(
    window_minutes: int = Query(
        60,
        ge=1,
        le=1440,
        description="Look-back window in minutes (default: 60, max: 1440 = 24 h)",
    ),
    top_n: int = Query(20, ge=1, le=100, description="Maximum number of topics to return"),
):
    """
    Return entities ranked by how many new connections they accumulated in the
    last *window_minutes* minutes.

    A high ``new_connections`` count means many recently ingested documents
    mention this entity — it is an actively evolving topic right now.  The
    ``source_docs`` list shows which documents drove the activity.
    """
    _, get_evolving_topics, _ = _load_updater()
    return get_evolving_topics(window_seconds=window_minutes * 60, top_n=top_n)


@router.get("/stats", response_model=Dict[str, Any])
async def kg_stats():
    """
    Return current knowledge-graph statistics: total node and triple counts,
    number of background-update events recorded since startup, and live status.
    """
    _, _, get_store_stats = _load_updater()
    return get_store_stats()
