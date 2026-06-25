"""
Argument Mining API routes (Issue #90, #95).

GET  /api/v1/arguments/frames              — aggregate frame distribution
GET  /api/v1/arguments/frames?document_id= — frames for a specific document
GET  /api/v1/arguments/frames?source_type= — aggregate filtered by source type
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/arguments", tags=["arguments"])


# ---------------------------------------------------------------------------
# Frames endpoint
# ---------------------------------------------------------------------------

@router.get("/frames")
async def get_frames(
    document_id: Optional[str] = Query(None, description="Return frames for this document"),
    source_type: Optional[str] = Query(None, description="Filter aggregate by source type"),
    limit: int = Query(50, ge=1, le=500, description="Max rows for aggregate queries"),
) -> Dict[str, Any]:
    """
    Return narrative frame scores.

    - With `document_id`: look up pre-computed scores in `document_frames`; if
      absent, classify the document on-the-fly from `news_articles` content.
    - Without `document_id`: return average scores across all documents,
      optionally filtered by `source_type`.
    """
    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()

    if document_id:
        return await _frames_for_document(conn, document_id)
    return await _aggregate_frames(conn, source_type=source_type, limit=limit)


async def _frames_for_document(conn, document_id: str) -> Dict[str, Any]:
    """Return per-frame scores for one document, classifying on-the-fly if needed."""
    import threading

    lock = getattr(conn, "_lock", None) or threading.Lock()

    # Check pre-computed scores first
    with lock:
        rows = conn.execute(
            "SELECT frame, score, source_type FROM document_frames WHERE document_id = ?",
            [document_id],
        ).fetchall()

    if rows:
        frames = {r[0]: round(r[1], 4) for r in rows}
        source_type = rows[0][2]
        dominant = max(frames, key=frames.__getitem__)
        return {
            "document_id": document_id,
            "source_type": source_type,
            "frames": frames,
            "dominant": dominant,
            "source": "precomputed",
        }

    # Not in cache — try to classify on-the-fly from news_articles
    with lock:
        article = conn.execute(
            "SELECT id, title, content, source FROM news_articles WHERE id = ? LIMIT 1",
            [document_id],
        ).fetchone()

    if not article:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found in document_frames or news_articles",
        )

    doc_id, title, content = article[0], article[1], article[2]

    try:
        from src.argument_mining.frames import get_frame_classifier
        fc = get_frame_classifier()
        from services.ingest.common.document_model import Document
        import time
        doc = Document(
            document_id=doc_id,
            source_type="news",
            language="en",
            ingested_at=int(time.time() * 1000),
            title=title,
            content=content,
        )
        prediction = fc.predict(doc)
        return {
            "document_id": document_id,
            "source_type": prediction.source_type,
            "frames": {f: round(s, 4) for f, s in prediction.frames.items()},
            "dominant": prediction.dominant,
            "source": "live",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Frame classification failed: {exc}")


async def _aggregate_frames(
    conn,
    source_type: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    """Return average frame scores across all (optionally filtered) documents."""
    import threading

    lock = getattr(conn, "_lock", None) or threading.Lock()

    if source_type:
        with lock:
            rows = conn.execute(
                """
                SELECT frame, AVG(score) AS avg_score, COUNT(DISTINCT document_id) AS n_docs
                FROM document_frames
                WHERE source_type = ?
                GROUP BY frame
                ORDER BY avg_score DESC
                """,
                [source_type],
            ).fetchall()
    else:
        with lock:
            rows = conn.execute(
                """
                SELECT frame, AVG(score) AS avg_score, COUNT(DISTINCT document_id) AS n_docs
                FROM document_frames
                GROUP BY frame
                ORDER BY avg_score DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()

    if not rows:
        # No pre-computed data — classify a sample and return live estimates
        return await _aggregate_live(conn, source_type=source_type)

    total_docs = rows[0][2] if rows else 0
    distribution = {r[0]: round(r[1], 4) for r in rows}
    dominant = max(distribution, key=distribution.__getitem__) if distribution else "other"
    return {
        "distribution": distribution,
        "dominant": dominant,
        "total_documents": total_docs,
        "source_type_filter": source_type,
        "source": "precomputed",
    }


async def _aggregate_live(conn, source_type: Optional[str]) -> Dict[str, Any]:
    """Classify a sample of news_articles and return aggregate frame distribution."""
    import threading
    import time

    lock = getattr(conn, "_lock", None) or threading.Lock()

    with lock:
        rows = conn.execute(
            "SELECT id, title, content FROM news_articles LIMIT 20"
        ).fetchall()

    if not rows:
        from src.argument_mining.dataset import FRAME_LABELS
        return {
            "distribution": {f: 0.0 for f in FRAME_LABELS},
            "dominant": "other",
            "total_documents": 0,
            "source_type_filter": source_type,
            "source": "live",
        }

    try:
        from src.argument_mining.frames import get_frame_classifier, FRAME_LABELS
        from services.ingest.common.document_model import Document

        fc = get_frame_classifier()
        totals: Dict[str, float] = {f: 0.0 for f in FRAME_LABELS}
        for doc_id, title, content in rows:
            doc = Document(
                document_id=doc_id,
                source_type="news",
                language="en",
                ingested_at=int(time.time() * 1000),
                title=title,
                content=content,
            )
            pred = fc.predict(doc)
            for frame, score in pred.frames.items():
                totals[frame] = totals.get(frame, 0.0) + score

        n = len(rows)
        distribution = {f: round(totals[f] / n, 4) for f in FRAME_LABELS}
        dominant = max(distribution, key=distribution.__getitem__)
        return {
            "distribution": distribution,
            "dominant": dominant,
            "total_documents": n,
            "source_type_filter": source_type,
            "source": "live",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Live frame classification failed: {exc}")
