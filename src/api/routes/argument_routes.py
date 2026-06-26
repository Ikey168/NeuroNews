"""
Argument Mining API routes (Issues #90, #93, #95, #96, #97, #99, #102, #105).

GET  /api/v1/arguments/frames                    — aggregate frame distribution
GET  /api/v1/arguments/frames?document_id=       — frames for a specific document
GET  /api/v1/arguments/frames?source_type=       — aggregate filtered by source type
GET  /api/v1/arguments/frames?date_range=        — aggregate filtered by time window (7d/30d/90d)
GET  /api/v1/arguments/frames/source             — per-source frame distribution with concentrated-framing flag (#105)
GET  /api/v1/arguments/claims                    — query stored claims (includes factcheck fields)
GET  /api/v1/arguments/claims?unsourced_only=    — claims with no corroborating evidence
POST /api/v1/arguments/claims/extract            — run pipeline on a stored document
GET  /api/v1/arguments/claims/{id}               — single claim with evidence links + factcheck verdict
GET  /api/v1/arguments/claims/{id}/evidence      — evidence for a claim
POST /api/v1/arguments/claims/{id}/factcheck     — trigger on-demand fact-check (#97)
GET  /api/v1/arguments/stance/sources            — stance per (source, topic) from source_stances table (#99)
GET  /api/v1/arguments/stance/drift              — structured drift events + 7-bucket time series (#102)
GET  /api/v1/arguments/stance                    — stance distribution across topics
GET  /api/v1/arguments/positions                 — actor positions derived from claims
GET  /api/v1/arguments/controversy               — conflict pairs ranked by contradiction count
GET  /api/v1/arguments/controversy/graph         — force-directed graph: nodes=claims, edges=contradictions (#96)
GET  /api/v1/arguments/sources/ranking           — sources ranked by claim quality
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/arguments", tags=["arguments"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_date_cutoff(date_range: Optional[str]) -> Optional[str]:
    """Parse '7d', '30d', '90d' → ISO date cutoff string, or None."""
    if not date_range:
        return None
    dr = date_range.strip().lower()
    if dr.endswith("d"):
        try:
            from datetime import datetime, timezone, timedelta
            days = int(dr[:-1])
            return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        except ValueError:
            pass
    return None


def _classify_stance(supports: int, contradicts: int, confidence: float) -> str:
    """Map evidence counts + confidence to a 4-class stance label."""
    if confidence < 0.4:
        return "ambiguous"
    if contradicts > supports and contradicts > 0:
        return "critical"
    if supports > 0:
        return "supportive"
    return "neutral"


# ---------------------------------------------------------------------------
# Frames endpoint
# ---------------------------------------------------------------------------

@router.get("/frames")
async def get_frames(
    document_id: Optional[str] = Query(None, description="Return frames for this document"),
    source_type: Optional[str] = Query(None, description="Filter aggregate by source type"),
    date_range: Optional[str] = Query(None, description="Time window: 7d, 30d, 90d"),
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
    return await _aggregate_frames(conn, source_type=source_type, limit=limit, date_range=date_range)


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
    date_range: Optional[str] = None,
) -> Dict[str, Any]:
    """Return average frame scores across all (optionally filtered) documents."""
    import threading

    lock = getattr(conn, "_lock", None) or threading.Lock()
    cutoff = _parse_date_cutoff(date_range)

    conditions: list[str] = []
    params: list[Any] = []

    if source_type:
        conditions.append("source_type = ?")
        params.append(source_type)
    if cutoff:
        conditions.append("classified_at >= ?")
        params.append(cutoff)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    with lock:
        rows = conn.execute(
            f"""
            SELECT frame, AVG(score) AS avg_score, COUNT(DISTINCT document_id) AS n_docs
            FROM document_frames
            {where}
            GROUP BY frame
            ORDER BY avg_score DESC
            LIMIT ?
            """,
            params,
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
    unsourced_only: bool = Query(False, description="Return only claims with no evidence"),
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
    if unsourced_only:
        conditions.append(
            "claim_id NOT IN (SELECT DISTINCT claim_id FROM claim_evidence)"
        )

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with lock:
        rows = conn.execute(
            f"""
            SELECT claim_id, claim_text, document_id, source_type, confidence,
                   extracted_at, factcheck_verdict, factcheck_url, factcheck_publisher
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
            "factcheck_verdict": r[6],
            "factcheck_url": r[7],
            "factcheck_publisher": r[8],
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


# ---------------------------------------------------------------------------
# Single claim detail (#95)
# ---------------------------------------------------------------------------

@router.get("/claims/{claim_id}")
async def get_claim(claim_id: str) -> Dict[str, Any]:
    """Return a single claim with its evidence links and factcheck verdict."""
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    with lock:
        row = conn.execute(
            """
            SELECT claim_id, claim_text, document_id, source_type, confidence,
                   extracted_at, factcheck_verdict, factcheck_url, factcheck_publisher
            FROM argument_claims WHERE claim_id = ?
            """,
            [claim_id],
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    with lock:
        ev_rows = conn.execute(
            """
            SELECT evidence_id, evidence_text, evidence_document_id,
                   evidence_source_type, relation, similarity_score, found_at
            FROM claim_evidence WHERE claim_id = ?
            ORDER BY similarity_score DESC
            """,
            [claim_id],
        ).fetchall()

    return {
        "claim_id": row[0],
        "claim_text": row[1],
        "document_id": row[2],
        "source_type": row[3],
        "confidence": round(row[4], 4) if row[4] is not None else None,
        "extracted_at": row[5],
        "factcheck_verdict": row[6],
        "factcheck_url": row[7],
        "factcheck_publisher": row[8],
        "evidence": [
            {
                "evidence_id": e[0],
                "evidence_text": e[1],
                "evidence_document_id": e[2],
                "evidence_source_type": e[3],
                "relation": e[4],
                "similarity_score": round(e[5], 6) if e[5] is not None else None,
                "found_at": e[6],
            }
            for e in ev_rows
        ],
        "evidence_count": len(ev_rows),
    }


# ---------------------------------------------------------------------------
# On-demand fact-check endpoint (#97)
# ---------------------------------------------------------------------------

@router.post("/claims/{claim_id}/factcheck")
async def factcheck_claim(claim_id: str) -> Dict[str, Any]:
    """
    Trigger an on-demand fact-check for a single claim via Google Fact Check Tools.

    Requires GOOGLE_FACTCHECK_API_KEY in the environment.  Returns 503 when the
    key is not configured.  Results are cached in argument_claims so repeated
    calls for the same claim are fast.
    """
    import threading
    import os

    from src.database.local_analytics_connector import get_shared_connection
    from src.argument_mining.factcheck import lookup_claim, store_result

    if not os.getenv("GOOGLE_FACTCHECK_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_FACTCHECK_API_KEY is not configured on this server.",
        )

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    with lock:
        row = conn.execute(
            "SELECT claim_text FROM argument_claims WHERE claim_id = ?",
            [claim_id],
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    result = lookup_claim(row[0])
    if result is None:
        raise HTTPException(status_code=502, detail="Fact Check Tools API returned no result")

    store_result(conn, lock, claim_id, result)

    return {
        "claim_id": claim_id,
        "factcheck_verdict": result.verdict,
        "factcheck_url": result.url,
        "factcheck_publisher": result.publisher,
        "textual_rating": result.textual_rating,
        "checked_at": result.checked_at,
    }


# ---------------------------------------------------------------------------
# Stance endpoints (#95, #99)
# ---------------------------------------------------------------------------

@router.get("/stance/sources")
async def get_stance_by_source(
    topic: Optional[str] = Query(None, description="Filter by topic/category keyword"),
    source: Optional[str] = Query(None, description="Filter by publication source name"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    date_range: Optional[str] = Query(None, description="Time window: 7d, 30d, 90d"),
    limit: int = Query(30, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Return stance breakdown (supportive/critical/neutral/ambiguous) per source and topic,
    aggregated from the `source_stances` table populated by the nightly stance aggregation job.

    Falls back to deriving stances from `argument_claims` when the table is empty.
    """
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    cutoff = _parse_date_cutoff(date_range)
    where_parts: list[str] = []
    params: list[Any] = []

    if topic:
        where_parts.append("topic ILIKE ?")
        params.append(f"%{topic}%")
    if source:
        where_parts.append("source ILIKE ?")
        params.append(f"%{source}%")
    if source_type:
        where_parts.append("source_type = ?")
        params.append(source_type)
    if cutoff:
        where_parts.append("window_start >= ?")
        params.append(cutoff)

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    params.append(limit)

    with lock:
        rows = conn.execute(
            f"""
            SELECT
                source, source_type, topic,
                SUM(CASE WHEN stance = 'supportive' THEN document_count ELSE 0 END) AS supportive,
                SUM(CASE WHEN stance = 'critical'   THEN document_count ELSE 0 END) AS critical,
                SUM(CASE WHEN stance = 'neutral'    THEN document_count ELSE 0 END) AS neutral,
                SUM(CASE WHEN stance = 'ambiguous'  THEN document_count ELSE 0 END) AS ambiguous,
                SUM(document_count)                                                  AS total,
                AVG(confidence)                                                      AS confidence,
                MAX(window_start)                                                    AS window_start,
                MAX(window_end)                                                      AS window_end
            FROM source_stances
            {where}
            GROUP BY source, source_type, topic
            ORDER BY total DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    if not rows:
        return await _stance_sources_from_claims(conn, lock, topic, source_type, limit)

    sources_data = [
        {
            "source": r[0],
            "source_type": r[1],
            "topic": r[2],
            "supportive": int(r[3]),
            "critical": int(r[4]),
            "neutral": int(r[5]),
            "ambiguous": int(r[6]),
            "total": int(r[7]),
            "confidence": round(float(r[8]), 4) if r[8] is not None else None,
            "document_count": int(r[7]),
            "window_start": r[9],
            "window_end": r[10],
        }
        for r in rows
    ]
    return {"sources": sources_data, "count": len(sources_data)}


async def _stance_sources_from_claims(
    conn, lock, topic: Optional[str], source_type: Optional[str], limit: int
) -> Dict[str, Any]:
    """Fallback: derive per-source stances from argument_claims when source_stances is empty."""
    where_parts = ["1=1"]
    params: list[Any] = []
    if source_type:
        where_parts.append("c.source_type = ?")
        params.append(source_type)
    if topic:
        where_parts.append("n.category ILIKE ?")
        params.append(f"%{topic}%")
    params.append(limit * 4)

    with lock:
        rows = conn.execute(
            f"""
            WITH ev AS (
                SELECT claim_id,
                       SUM(CASE WHEN relation = 'supports'    THEN 1 ELSE 0 END) AS sup,
                       SUM(CASE WHEN relation = 'contradicts' THEN 1 ELSE 0 END) AS con
                FROM claim_evidence
                GROUP BY claim_id
            )
            SELECT
                COALESCE(n.source, c.source_type) AS source_name,
                c.source_type,
                COALESCE(n.category, 'general')   AS topic,
                c.confidence,
                COALESCE(ev.sup, 0)               AS sup,
                COALESCE(ev.con, 0)               AS con
            FROM argument_claims c
            LEFT JOIN news_articles n ON c.document_id = n.id
            LEFT JOIN ev             ON c.claim_id     = ev.claim_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY n.publish_date DESC NULLS LAST
            LIMIT ?
            """,
            params,
        ).fetchall()

    agg: dict[tuple, dict[str, Any]] = {}
    for source_name, stype, t, conf, sup, con in rows:
        key = (source_name, stype, t)
        if key not in agg:
            agg[key] = {"supportive": 0, "critical": 0, "neutral": 0, "ambiguous": 0, "total": 0}
        stance = _classify_stance(int(sup), int(con), float(conf or 0))
        agg[key][stance] += 1
        agg[key]["total"] += 1

    result = [
        {
            "source": k[0],
            "source_type": k[1],
            "topic": k[2],
            "supportive": v["supportive"],
            "critical": v["critical"],
            "neutral": v["neutral"],
            "ambiguous": v["ambiguous"],
            "total": v["total"],
            "confidence": None,
            "document_count": v["total"],
            "window_start": None,
            "window_end": None,
        }
        for k, v in sorted(agg.items(), key=lambda x: -x[1]["total"])
    ]
    return {"sources": result[:limit], "count": len(result)}


def _load_claim_stance_rows(conn, lock, source_type: Optional[str], source: Optional[str],
                             topic: Optional[str], cutoff: Optional[str]) -> list:
    """Load claims with derived stance labels from the DuckDB warehouse."""
    where_parts = ["1=1"]
    params: list[Any] = []

    if source_type:
        where_parts.append("c.source_type = ?")
        params.append(source_type)
    if source:
        where_parts.append("n.source ILIKE ?")
        params.append(f"%{source}%")
    if topic:
        where_parts.append("n.category ILIKE ?")
        params.append(f"%{topic}%")
    if cutoff:
        where_parts.append("n.publish_date >= ?")
        params.append(cutoff)

    query = f"""
    WITH evidence_counts AS (
        SELECT claim_id,
               SUM(CASE WHEN relation = 'supports'    THEN 1 ELSE 0 END) AS sup,
               SUM(CASE WHEN relation = 'contradicts' THEN 1 ELSE 0 END) AS con
        FROM claim_evidence
        GROUP BY claim_id
    )
    SELECT
        COALESCE(n.category, 'general') AS topic,
        c.source_type,
        c.confidence,
        c.extracted_at,
        COALESCE(ec.sup, 0)             AS sup,
        COALESCE(ec.con, 0)             AS con
    FROM argument_claims c
    LEFT JOIN news_articles n  ON c.document_id = n.id
    LEFT JOIN evidence_counts ec ON c.claim_id  = ec.claim_id
    WHERE {' AND '.join(where_parts)}
    """

    with lock:
        return conn.execute(query, params).fetchall()


@router.get("/stance/drift")
async def get_stance_drift(
    source: Optional[str] = Query(None, description="Filter by publication source name"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    topic: Optional[str] = Query(None, description="Filter by topic/category keyword"),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    """
    Return stance drift data for (source, topic).

    Primary response: structured drift events from `stance_drift_events` (populated
    nightly by the drift detection job — issue #102).

    Also returns a 7-bucket supportive-ratio time series derived from claim rows
    for the sparkline in the Stance panel (backward compat).
    """
    import threading
    from datetime import datetime

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    # ── Structured drift events from the dedicated table ─────────────────────
    events = _load_drift_events(conn, lock, source=source, source_type=source_type,
                                topic=topic, limit=limit)

    # ── Legacy 7-bucket time-series (sparkline) ───────────────────────────────
    rows = _load_claim_stance_rows(conn, lock, source_type, source, topic, cutoff=None)

    def _parse_ts(s: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    timed = [(r[3], r[2], int(r[4]), int(r[5])) for r in rows if r[3]]
    drift: list[float] = []
    periods: list[str] = []

    if timed:
        ts_objs = [_parse_ts(r[0]) for r in timed]
        valid = [(ts, r[1], r[2], r[3]) for ts, r in zip(ts_objs, timed) if ts is not None]
        if valid:
            t_min = min(v[0] for v in valid)
            t_max = max(v[0] for v in valid)
            span = max((t_max - t_min).total_seconds(), 1)
            n_buckets = 7
            buckets: list[dict] = [{"supportive": 0, "total": 0} for _ in range(n_buckets)]
            periods = [
                (t_min + (t_max - t_min) * (i / n_buckets)).strftime("%Y-%m-%d")
                for i in range(n_buckets)
            ]
            for ts, confidence, sup, con in valid:
                frac = (ts - t_min).total_seconds() / span
                idx = min(n_buckets - 1, int(frac * n_buckets))
                buckets[idx]["total"] += 1
                if _classify_stance(sup, con, float(confidence or 0)) == "supportive":
                    buckets[idx]["supportive"] += 1
            drift = [
                round(b["supportive"] / b["total"], 3) if b["total"] > 0 else 0.0
                for b in buckets
            ]

    return {
        "events": events,
        "drift": drift,
        "periods": periods,
        "topic": topic,
        "source": source,
        "source_type": source_type,
        "count": len(events),
    }


def _load_drift_events(
    conn,
    lock,
    *,
    source: Optional[str],
    source_type: Optional[str],
    topic: Optional[str],
    limit: int,
) -> list[dict]:
    """Query stance_drift_events filtered by source/source_type/topic."""
    conditions = []
    params: list = []
    if source:
        conditions.append("source = ?")
        params.append(source)
    if source_type:
        conditions.append("source_type = ?")
        params.append(source_type)
    if topic:
        conditions.append("topic = ?")
        params.append(topic)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    try:
        with lock:
            rows = conn.execute(
                f"""
                SELECT source, source_type, topic, from_stance, to_stance,
                       confidence_delta, detected_at, window_pair
                FROM stance_drift_events
                {where}
                ORDER BY window_pair DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
    except Exception:
        return []

    return [
        {
            "source": r[0],
            "source_type": r[1],
            "topic": r[2],
            "from_stance": r[3],
            "to_stance": r[4],
            "confidence_delta": r[5],
            "detected_at": r[6],
            "window_pair": r[7],
        }
        for r in rows
    ]


@router.get("/stance")
async def get_stance(
    topic: Optional[str] = Query(None, description="Filter by topic keyword (matches news category)"),
    source: Optional[str] = Query(None, description="Filter by publication source name"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    date_range: Optional[str] = Query(None, description="Time window: 7d, 30d, 90d"),
    limit: int = Query(20, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Return stance distribution (supportive/critical/neutral/ambiguous) across topics,
    derived from claim confidence and cross-corpus evidence relations.
    """
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    cutoff = _parse_date_cutoff(date_range)
    rows = _load_claim_stance_rows(conn, lock, source_type, source, topic, cutoff)

    by_topic: dict[str, Any] = {}

    for row in rows:
        cat, src_type, confidence, extracted_at, sup, con = row
        if cat not in by_topic:
            by_topic[cat] = {
                "supportive": 0, "critical": 0, "neutral": 0, "ambiguous": 0,
                "by_source": {}, "extracted_ats": [],
            }
        entry: Any = by_topic[cat]
        stance = _classify_stance(int(sup), int(con), float(confidence or 0))
        entry[stance] += 1
        if src_type not in entry["by_source"]:
            entry["by_source"][src_type] = {"supportive": 0, "critical": 0, "neutral": 0, "ambiguous": 0}
        entry["by_source"][src_type][stance] += 1
        if extracted_at:
            entry["extracted_ats"].append(extracted_at)

    def _total(d: Any) -> int:
        return d["supportive"] + d["critical"] + d["neutral"] + d["ambiguous"]

    result = []
    for topic_name, data in sorted(by_topic.items(), key=lambda x: -_total(x[1])):
        total = data["supportive"] + data["critical"] + data["neutral"] + data["ambiguous"]
        # Simple 7-point drift: interpolate supportive ratio across extracted_at range
        n_ts = len(data["extracted_ats"])
        base = round(data["supportive"] / max(total, 1), 2)
        drift = [base] * 7 if n_ts else []
        result.append({
            "topic": topic_name,
            "supportive": data["supportive"],
            "critical": data["critical"],
            "neutral": data["neutral"],
            "ambiguous": data["ambiguous"],
            "total": total,
            "drift": drift,
            "by_source": {k: dict(v) for k, v in data["by_source"].items()},
        })

    return {"stances": result[:limit], "count": len(result)}


# ---------------------------------------------------------------------------
# Frames/source endpoint (#95, enhanced by #105)
# ---------------------------------------------------------------------------

_CONCENTRATED_THRESHOLD = 0.60  # single frame dominance above this → concentrated framing flag


@router.get("/frames/source")
async def get_frames_by_source(
    source: Optional[str] = Query(None, description="Filter by publication source name"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    topic: Optional[str] = Query(None, description="Filter by topic/category keyword"),
    date_range: Optional[str] = Query(None, description="Time window: 7d, 30d, 90d"),
    limit: int = Query(20, ge=1, le=200, description="Max number of sources to return"),
) -> Dict[str, Any]:
    """
    Return frame distribution aggregated per publication source, across all content types (#105).

    Each entry includes:
    - source: publication name (falls back to source_type for non-news when no name is available)
    - source_type: content type (news/blog/paper/transcript/book/note)
    - frames: avg score per frame label
    - doc_count: number of documents classified
    - dominant: highest-scoring frame
    - concentrated: True when any single frame avg_score > 60% (editorial framing signal)
    - concentrated_frame: name of the concentrated frame, or null
    """
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    cutoff = _parse_date_cutoff(date_range)

    # ── news branch: join news_articles for source names ──────────────────────
    news_where: list[str] = ["n.source IS NOT NULL"]
    news_params: list[Any] = []
    if source_type and source_type != "news":
        news_where.append("1=0")  # exclude news entirely when filtering for non-news
    elif source_type == "news":
        pass  # include all news
    if source:
        news_where.append("n.source ILIKE ?")
        news_params.append(f"%{source}%")
    if topic:
        news_where.append("n.category ILIKE ?")
        news_params.append(f"%{topic}%")
    if cutoff:
        news_where.append("n.publish_date >= ?")
        news_params.append(cutoff)

    # ── non-news branch: fall back to source_type as source name ─────────────
    # (doc source names for non-news are available in source_stances when populated)
    other_where: list[str] = ["df.source_type != 'news'"]
    other_params: list[Any] = []
    if source_type and source_type != "news":
        other_where.append("df.source_type = ?")
        other_params.append(source_type)
    elif source_type == "news":
        other_where.append("1=0")  # exclude non-news when filtering for news only
    if cutoff:
        other_where.append("df.classified_at >= ?")
        other_params.append(cutoff)

    news_where_clause = " AND ".join(news_where)
    other_where_clause = " AND ".join(other_where)

    with lock:
        news_rows = conn.execute(
            f"""
            SELECT n.source,
                   'news'            AS source_type,
                   df.frame,
                   AVG(df.score)                  AS avg_score,
                   COUNT(DISTINCT df.document_id) AS doc_count
            FROM document_frames df
            JOIN news_articles n ON df.document_id = n.id
            WHERE {news_where_clause}
            GROUP BY n.source, df.frame
            """,
            news_params,
        ).fetchall()

        other_rows = conn.execute(
            f"""
            SELECT df.source_type      AS source,
                   df.source_type,
                   df.frame,
                   AVG(df.score)                  AS avg_score,
                   COUNT(DISTINCT df.document_id) AS doc_count
            FROM document_frames df
            WHERE {other_where_clause}
            GROUP BY df.source_type, df.frame
            """,
            other_params,
        ).fetchall()

    by_source: dict[str, Any] = {}
    for row in list(news_rows) + list(other_rows):
        src, src_type, frame, avg_score, doc_count = row
        key = f"{src_type}::{src}"
        if key not in by_source:
            by_source[key] = {"source": src, "source_type": src_type, "frames": {}, "doc_count": 0}
        entry_s: Any = by_source[key]
        entry_s["frames"][frame] = round(float(avg_score), 4)
        entry_s["doc_count"] = max(entry_s["doc_count"], int(doc_count))

    result = []
    for data in sorted(by_source.values(), key=lambda x: -x["doc_count"]):
        frames = data["frames"]
        dominant = max(frames, key=frames.__getitem__) if frames else "other"
        top_score = frames.get(dominant, 0.0)
        concentrated = top_score > _CONCENTRATED_THRESHOLD
        result.append({
            "source": data["source"],
            "source_type": data["source_type"],
            "frames": frames,
            "doc_count": data["doc_count"],
            "dominant": dominant,
            "concentrated": concentrated,
            "concentrated_frame": dominant if concentrated else None,
        })

    # Apply name-based filter after aggregation (handles fallback source names)
    if source:
        result = [r for r in result if source.lower() in r["source"].lower()]

    return {"sources": result[:limit], "count": len(result)}


# ---------------------------------------------------------------------------
# Positions endpoint (#95)
# ---------------------------------------------------------------------------

@router.get("/positions")
async def get_positions(
    actor: Optional[str] = Query(None, description="Filter by actor/source name"),
    topic: Optional[str] = Query(None, description="Filter by topic/category keyword"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    """
    Return actor policy positions derived from argument claims.
    Actor = the news/content source; position = the claim text;
    stance is inferred from supporting/contradicting evidence.
    """
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    where_parts: list[str] = []
    params: list[Any] = []

    if source_type:
        where_parts.append("c.source_type = ?")
        params.append(source_type)
    if actor:
        where_parts.append("n.source ILIKE ?")
        params.append(f"%{actor}%")
    if topic:
        where_parts.append("n.category ILIKE ?")
        params.append(f"%{topic}%")

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    params.append(limit)

    with lock:
        rows = conn.execute(
            f"""
            WITH evidence_counts AS (
                SELECT claim_id,
                       SUM(CASE WHEN relation = 'supports'    THEN 1 ELSE 0 END) AS sup,
                       SUM(CASE WHEN relation = 'contradicts' THEN 1 ELSE 0 END) AS con
                FROM claim_evidence
                GROUP BY claim_id
            )
            SELECT
                COALESCE(n.source, c.source_type)   AS actor,
                c.claim_text                        AS position,
                COALESCE(n.category, 'general')     AS topic,
                c.source_type,
                c.document_id,
                n.publish_date,
                c.confidence,
                COALESCE(ec.sup, 0)                 AS sup,
                COALESCE(ec.con, 0)                 AS con
            FROM argument_claims c
            LEFT JOIN news_articles n    ON c.document_id = n.id
            LEFT JOIN evidence_counts ec ON c.claim_id   = ec.claim_id
            {where_clause}
            ORDER BY n.publish_date DESC NULLS LAST, c.confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    positions = []
    for row in rows:
        actor_name, pos_text, topic_name, src_type, doc_id, pub_date, confidence, sup, con = row
        internal_stance = _classify_stance(int(sup), int(con), float(confidence or 0))
        pos_stance = "for" if internal_stance == "supportive" else (
            "against" if internal_stance == "critical" else "neutral"
        )
        positions.append({
            "actor": actor_name or src_type,
            "position": pos_text,
            "stance": pos_stance,
            "date": str(pub_date) if pub_date else "",
            "source_type": src_type,
            "document_id": doc_id,
            "topic": topic_name,
        })

    return {"positions": positions, "count": len(positions)}


# ---------------------------------------------------------------------------
# Controversy endpoint (#95)
# ---------------------------------------------------------------------------

@router.get("/controversy")
async def get_controversy(
    topic: Optional[str] = Query(None, description="Filter by topic/category keyword"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    date_range: Optional[str] = Query(None, description="Time window: 7d, 30d, 90d"),
    limit: int = Query(20, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Return conflict pairs where one source's claim is contradicted by a different source's
    evidence. Intensity is normalized to [0, 1] within the result set.
    """
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    cutoff = _parse_date_cutoff(date_range)
    where_parts = [
        "e.relation = 'contradicts'",
        "n1.source IS NOT NULL",
        "n2.source IS NOT NULL",
        "n1.source != n2.source",
    ]
    params: list[Any] = []

    if source_type:
        where_parts.append("c.source_type = ?")
        params.append(source_type)
    if topic:
        where_parts.append("n1.category ILIKE ?")
        params.append(f"%{topic}%")
    if cutoff:
        where_parts.append("n1.publish_date >= ?")
        params.append(cutoff)

    params.append(limit * 3)  # over-fetch for normalisation

    with lock:
        rows = conn.execute(
            f"""
            SELECT
                n1.source                        AS actor_a,
                n2.source                        AS actor_b,
                COALESCE(n1.category, 'general') AS topic,
                COUNT(*)                         AS contradiction_count,
                COUNT(DISTINCT n2.id)            AS source_count
            FROM claim_evidence e
            JOIN argument_claims c   ON e.claim_id            = c.claim_id
            JOIN news_articles n1    ON c.document_id          = n1.id
            JOIN news_articles n2    ON e.evidence_document_id = n2.id
            WHERE {' AND '.join(where_parts)}
            GROUP BY n1.source, n2.source, COALESCE(n1.category, 'general')
            ORDER BY contradiction_count DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    if not rows:
        return {"conflicts": [], "count": 0}

    max_count = max(r[3] for r in rows)
    conflicts = [
        {
            "actor_a": r[0],
            "actor_b": r[1],
            "topic": r[2],
            "intensity": round(r[3] / max_count, 2),
            "source_count": r[4],
        }
        for r in rows[:limit]
    ]

    return {"conflicts": conflicts, "count": len(conflicts)}


# ---------------------------------------------------------------------------
# Controversy graph endpoint (#96)
# ---------------------------------------------------------------------------

@router.get("/controversy/graph")
async def get_controversy_graph(
    topic: Optional[str] = Query(None, description="Filter by topic/category keyword"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    date_range: Optional[str] = Query(None, description="Time window: 7d, 30d, 90d"),
    limit: int = Query(60, ge=1, le=300),
) -> Dict[str, Any]:
    """
    Return a force-directed graph of contested claims.

    Nodes are individual claims involved in cross-source contradictions.
    Edges are claim_evidence rows where relation='contradicts' and the two
    claims come from different source outlets.

    Node fields:  id, label, source, source_type, topic, date, claim_text, confidence
    Edge fields:  source, target, severity (similarity_score ∈ [0,1]), relation
    """
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    cutoff = _parse_date_cutoff(date_range)
    conditions: list[str] = [
        "e.relation = 'contradicts'",
        "n1.source IS NOT NULL",
        "n2.source IS NOT NULL",
        "n1.source != n2.source",
    ]
    params: list[Any] = []

    if source_type:
        conditions.append("(c1.source_type = ? OR c2.source_type = ?)")
        params.extend([source_type, source_type])
    if topic:
        conditions.append("(n1.category ILIKE ? OR n2.category ILIKE ?)")
        params.extend([f"%{topic}%", f"%{topic}%"])
    if cutoff:
        conditions.append("(n1.publish_date >= ? OR n2.publish_date >= ?)")
        params.extend([cutoff, cutoff])

    params.append(limit)

    with lock:
        rows = conn.execute(
            f"""
            SELECT
                c1.claim_id                          AS claim_id_a,
                c1.claim_text                        AS text_a,
                c1.source_type                       AS source_type_a,
                c1.confidence                        AS confidence_a,
                c1.extracted_at                      AS date_a,
                COALESCE(n1.source, c1.source_type)  AS source_a,
                COALESCE(n1.category, 'general')     AS topic_a,
                c1.document_id                       AS doc_id_a,
                c2.claim_id                          AS claim_id_b,
                c2.claim_text                        AS text_b,
                c2.source_type                       AS source_type_b,
                c2.confidence                        AS confidence_b,
                c2.extracted_at                      AS date_b,
                COALESCE(n2.source, c2.source_type)  AS source_b,
                COALESCE(n2.category, 'general')     AS topic_b,
                c2.document_id                       AS doc_id_b,
                COALESCE(e.similarity_score, 0.5)    AS severity
            FROM claim_evidence e
            JOIN argument_claims c1 ON e.claim_id             = c1.claim_id
            JOIN argument_claims c2 ON e.evidence_document_id = c2.document_id
            LEFT JOIN news_articles n1 ON c1.document_id       = n1.id
            LEFT JOIN news_articles n2 ON c2.document_id       = n2.id
            WHERE {' AND '.join(conditions)}
            ORDER BY severity DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    nodes: dict[str, Any] = {}
    edges: list[dict[str, Any]] = []

    for r in rows:
        (
            cid_a, txt_a, stype_a, conf_a, date_a, src_a, topic_a, doc_a,
            cid_b, txt_b, stype_b, conf_b, date_b, src_b, topic_b, doc_b,
            severity,
        ) = r
        if cid_a not in nodes:
            nodes[cid_a] = {
                "id": cid_a, "label": src_a, "source": src_a,
                "source_type": stype_a, "topic": topic_a,
                "date": str(date_a) if date_a else None,
                "claim_text": txt_a,
                "confidence": float(conf_a) if conf_a is not None else 0.5,
                "document_id": doc_a,
            }
        if cid_b not in nodes:
            nodes[cid_b] = {
                "id": cid_b, "label": src_b, "source": src_b,
                "source_type": stype_b, "topic": topic_b,
                "date": str(date_b) if date_b else None,
                "claim_text": txt_b,
                "confidence": float(conf_b) if conf_b is not None else 0.5,
                "document_id": doc_b,
            }
        edges.append({
            "source": cid_a,
            "target": cid_b,
            "severity": round(float(severity), 3),
            "relation": "contradicts",
        })

    node_list = list(nodes.values())
    return {"nodes": node_list, "edges": edges, "node_count": len(node_list), "edge_count": len(edges)}


# ---------------------------------------------------------------------------
# Sources ranking endpoint (#95)
# ---------------------------------------------------------------------------

@router.get("/sources/ranking")
async def get_sources_ranking(
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Rank content sources by claim count, average confidence, and evidence citation frequency."""
    import threading

    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()

    where_parts: list[str] = []
    params: list[Any] = []

    if source_type:
        where_parts.append("c.source_type = ?")
        params.append(source_type)

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    params.append(limit)

    with lock:
        rows = conn.execute(
            f"""
            SELECT
                COALESCE(n.source, c.source_type)    AS source_name,
                c.source_type,
                COUNT(DISTINCT c.claim_id)           AS claim_count,
                ROUND(AVG(c.confidence), 4)          AS avg_confidence,
                COUNT(e.evidence_id)                 AS evidence_citations
            FROM argument_claims c
            LEFT JOIN news_articles n  ON c.document_id = n.id
            LEFT JOIN claim_evidence e ON c.claim_id    = e.claim_id
            {where_clause}
            GROUP BY COALESCE(n.source, c.source_type), c.source_type
            ORDER BY claim_count DESC, avg_confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    sources = [
        {
            "source": r[0],
            "source_type": r[1],
            "claim_count": r[2],
            "avg_confidence": float(r[3]) if r[3] is not None else 0.0,
            "evidence_citations": r[4],
        }
        for r in rows
    ]

    return {"sources": sources, "count": len(sources)}
