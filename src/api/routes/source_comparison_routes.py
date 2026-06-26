"""
Multi-source news comparison endpoints — Issue #46.

GET /compare_sources?topic=AI+Regulation&limit=10&days=90
GET /sources/trustworthiness?source_type=news&date_range=30d
GET /sources/{source}/profile
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["source-comparison"])


def _get_conn():
    from src.database.local_analytics_connector import get_shared_connection
    return get_shared_connection()


@router.get("/compare_sources")
async def compare_sources(
    topic: str = Query(..., min_length=1, description="Topic keyword to compare across sources"),
    limit: int = Query(10, ge=1, le=50, description="Max number of sources to return"),
    days: int = Query(90, ge=1, le=365, description="Look-back window in days"),
) -> Dict[str, Any]:
    """
    Compare how different media outlets cover the same topic.

    Returns per-source article counts, average sentiment, sentiment
    distribution, outlet trust scores (when available), editorial cluster,
    and per-topic stance — plus a cross-source summary.
    """
    try:
        from src.nlp.source_comparator import compare_sources as _compare
        conn = _get_conn()
        return _compare(topic=topic, conn=conn, limit=limit, days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources/trustworthiness")
async def list_trustworthiness(
    source_type: Optional[str] = Query(None, description="Filter by source type (e.g. 'news')"),
    date_range: str = Query("30d", description="Score date range: 30d, 90d, or all"),
) -> Dict[str, Any]:
    """
    List all sources with their latest transparency / bias trust scores.

    Scores come from the outlet-scoring pipeline (frame_diversity,
    attribution_rate, stance_neutrality, composite_score). Returns an empty
    list when the scoring job has not yet been run.
    """
    valid_ranges = {"30d", "90d", "all"}
    if date_range not in valid_ranges:
        raise HTTPException(
            status_code=422,
            detail=f"date_range must be one of {sorted(valid_ranges)}",
        )
    try:
        from src.nlp.source_comparator import list_source_trustworthiness
        conn = _get_conn()
        rows = list_source_trustworthiness(
            conn=conn,
            source_type=source_type,
            date_range=date_range,
        )
        return {"sources": rows, "count": len(rows), "date_range": date_range}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources/{source}/profile")
async def source_profile(
    source: str,
) -> Dict[str, Any]:
    """
    Return a full profile for one named source: article volume, average
    sentiment, trust scores, editorial cluster, and per-topic stances.
    """
    try:
        from src.nlp.source_comparator import get_source_profile
        conn = _get_conn()
        return get_source_profile(source=source, conn=conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
