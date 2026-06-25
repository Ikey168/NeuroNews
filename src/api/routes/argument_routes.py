"""
Argument Mining API routes (Issues #90, #93, #95).

GET  /api/v1/arguments/frames              — aggregate frame distribution
GET  /api/v1/arguments/frames?document_id= — frames for a specific document
GET  /api/v1/arguments/frames?source_type= — aggregate filtered by source type
GET  /api/v1/arguments/claims              — query stored claims
POST /api/v1/arguments/claims/extract      — run pipeline on a stored document
GET  /api/v1/arguments/claims/{claim_id}/evidence — evidence for a claim
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


# ---------------------------------------------------------------------------
# Claims endpoints (#93)
# ---------------------------------------------------------------------------

@router.get("/claims")
async def get_claims(
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    topic: Optional[str] = Query(None, description="Full-text filter on claim text"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
) -> Dict[str, Any]:
    """Query stored argument claims, filterable by document, source type, or keyword topic."""
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    conditions: list[str] = []
    params: list[Any] = []

    if document_id:
        conditions.append("document_id = ?")
        params.append(document_id)
    if source_type:
        conditions.append("source_type = ?")
        params.append(source_type)
    if topic:
        conditions.append("claim_text ILIKE ?")
        params.append(f"%{topic}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with lock:
        rows = conn.execute(
            f"""
            SELECT claim_id, claim_text, document_id, source_type, confidence, extracted_at
            FROM argument_claims
            {where}
            ORDER BY confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    claims = [
        {
            "claim_id": r[0],
            "claim_text": r[1],
            "document_id": r[2],
            "source_type": r[3],
            "confidence": round(r[4], 4) if r[4] is not None else None,
            "extracted_at": r[5],
        }
        for r in rows
    ]
    return {"claims": claims, "count": len(claims)}


@router.post("/claims/extract")
async def extract_claims_for_document(
    document_id: str = Query(..., description="ID of a document already in news_articles"),
    source_type: str = Query("news", description="Source type label"),
) -> Dict[str, Any]:
    """Run the claim+evidence pipeline on a stored document and persist results."""
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    with lock:
        row = conn.execute(
            "SELECT id, title, content FROM news_articles WHERE id = ? LIMIT 1",
            [document_id],
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")

    doc_id, title, content = row[0], row[1], row[2]
    if not content:
        raise HTTPException(status_code=422, detail="Document has no content to process")

    try:
        import time
        from services.ingest.common.document_model import Document
        from src.argument_mining.evidence import run_pipeline

        doc = Document(
            document_id=doc_id,
            source_type=source_type,
            language="en",
            ingested_at=int(time.time() * 1000),
            title=title,
            content=content,
        )
        claims, evidence = run_pipeline(doc, conn)
        return {
            "document_id": doc_id,
            "source_type": source_type,
            "claims_extracted": len(claims),
            "evidence_found": len(evidence),
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "claim_text": c.claim_text,
                    "confidence": round(c.confidence, 4),
                }
                for c in claims
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}")


@router.get("/claims/{claim_id}/evidence")
async def get_evidence(
    claim_id: str,
    relation: Optional[str] = Query(None, description="Filter by 'supports' or 'contradicts'"),
    limit: int = Query(20, ge=1, le=200),
) -> Dict[str, Any]:
    """Return stored evidence records for a given claim."""
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    conditions = ["claim_id = ?"]
    params: list[Any] = [claim_id]

    if relation:
        if relation not in ("supports", "contradicts"):
            raise HTTPException(status_code=422, detail="relation must be 'supports' or 'contradicts'")
        conditions.append("relation = ?")
        params.append(relation)

    params.append(limit)
    with lock:
        rows = conn.execute(
            f"""
            SELECT evidence_id, evidence_text, evidence_document_id,
                   evidence_source_type, relation, similarity_score, found_at
            FROM claim_evidence
            WHERE {' AND '.join(conditions)}
            ORDER BY similarity_score DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    # Verify the claim exists (return 404 rather than empty list for unknown IDs)
    if not rows:
        with lock:
            exists = conn.execute(
                "SELECT 1 FROM argument_claims WHERE claim_id = ? LIMIT 1",
                [claim_id],
            ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    evidence = [
        {
            "evidence_id": r[0],
            "evidence_text": r[1],
            "evidence_document_id": r[2],
            "evidence_source_type": r[3],
            "relation": r[4],
            "similarity_score": round(r[5], 6) if r[5] is not None else None,
            "found_at": r[6],
        }
        for r in rows
    ]
    return {"claim_id": claim_id, "evidence": evidence, "count": len(evidence)}
