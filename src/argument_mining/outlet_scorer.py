"""
Outlet transparency scoring — issue #116.

Scores each outlet across three dimensions:

  1. frame_diversity   — Shannon entropy over the outlet's 7-frame distribution
                         (0 = all one frame, 1 = perfectly balanced coverage)
  2. attribution_rate  — fraction of detected claims that have an attributed source
                         (0 = nothing attributed, 1 = all claims attributed)
  3. stance_neutrality — entropy of the outlet's aggregate stance distribution
                         across contested topics (0 = all one stance, 1 = perfectly
                         balanced supportive/critical/neutral/ambiguous)

  composite_score = mean(frame_diversity, attribution_rate, stance_neutrality)

Scores are computed per outlet and stored as weekly snapshots in
``outlet_scores`` so sparklines can be drawn from the history.

Public API
----------
  compute_outlet_scores(conn, date_range="90d") -> List[OutletScoreRow]
  store_scores(rows, conn) -> None
  run_scorer_batch(conn, lock, date_range?, date_override?) -> dict
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

FRAME_LABELS = ["economic", "security", "humanitarian", "legal",
                 "political", "scientific", "other"]

_EPS = 1e-9  # avoid log(0)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class OutletScoreRow:
    source: str
    source_type: str
    score_date: str                   # ISO-8601 Monday of the current week
    frame_diversity: float            # 0–1
    attribution_rate: float           # 0–1
    stance_neutrality: float          # 0–1
    composite_score: float            # mean of the three
    doc_count: int
    claim_count: int
    computed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _week_date(override: Optional[str] = None) -> str:
    if override:
        return override
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def _date_cutoff(date_range: str) -> str:
    mapping = {"7d": 7, "14d": 14, "30d": 30, "90d": 90, "180d": 180, "365d": 365}
    days = mapping.get(date_range, 90)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    return cutoff


def _shannon_entropy(counts: Dict[str, float], n_bins: int) -> float:
    """Normalised Shannon entropy ∈ [0, 1] for a dict of scores/counts."""
    total = sum(counts.values())
    if total < _EPS:
        return 0.0
    entropy = 0.0
    for v in counts.values():
        p = v / total
        if p > _EPS:
            entropy -= p * math.log(p)
    return entropy / math.log(n_bins)


# ---------------------------------------------------------------------------
# Per-dimension extractors
# ---------------------------------------------------------------------------

def _frame_diversity(conn, source: str, source_type: str, cutoff: str) -> tuple[float, int]:
    """Return (diversity_score 0-1, doc_count)."""
    if source_type == "news":
        rows = conn.execute("""
            SELECT df.frame, AVG(df.score) AS avg_score,
                   COUNT(DISTINCT df.document_id) AS doc_count
            FROM document_frames df
            JOIN news_articles n ON df.document_id = n.id
            WHERE n.source = ? AND n.publish_date >= ?
            GROUP BY df.frame
        """, [source, cutoff]).fetchall()
    else:
        rows = conn.execute("""
            SELECT frame, AVG(score) AS avg_score,
                   COUNT(DISTINCT document_id) AS doc_count
            FROM document_frames
            WHERE source_type = ? AND classified_at >= ?
            GROUP BY frame
        """, [source_type, cutoff]).fetchall()

    if not rows:
        return 0.0, 0

    frame_scores = {r[0]: float(r[1]) for r in rows}
    doc_count = max(int(r[2]) for r in rows)
    diversity = _shannon_entropy(frame_scores, n_bins=len(FRAME_LABELS))
    return round(diversity, 4), doc_count


def _attribution_rate(conn, source: str, source_type: str, cutoff: str) -> tuple[float, int]:
    """Return (attribution_rate 0-1, total_claim_count)."""
    if source_type == "news":
        row = conn.execute("""
            SELECT
                COUNT(*)                                       AS total,
                COUNT(*) FILTER (WHERE c.attributed = true)   AS attributed
            FROM argument_claims c
            JOIN news_articles n ON c.document_id = n.id
            WHERE n.source = ? AND c.extracted_at >= ?
        """, [source, cutoff]).fetchone()
    else:
        row = conn.execute("""
            SELECT
                COUNT(*)                                     AS total,
                COUNT(*) FILTER (WHERE attributed = true)   AS attributed
            FROM argument_claims
            WHERE source_type = ? AND extracted_at >= ?
        """, [source_type, cutoff]).fetchone()

    total = int(row[0]) if row and row[0] else 0
    attributed = int(row[1]) if row and row[1] else 0
    rate = round(attributed / total, 4) if total > 0 else 0.0
    return rate, total


def _stance_neutrality(conn, source: str, source_type: str) -> float:
    """Return neutrality_score 0-1 from stance distribution in source_stances."""
    rows = conn.execute("""
        SELECT stance, SUM(document_count) AS n
        FROM source_stances
        WHERE source = ? AND source_type = ?
        GROUP BY stance
    """, [source, source_type]).fetchall()

    if not rows:
        # No stance data — return midpoint rather than penalising the outlet
        return 0.5

    stance_counts = {r[0]: float(r[1]) for r in rows}
    # Ensure all four labels are present (with 0 if absent)
    for lbl in ("supportive", "critical", "neutral", "ambiguous"):
        stance_counts.setdefault(lbl, 0.0)

    return round(_shannon_entropy(stance_counts, n_bins=4), 4)


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

def compute_outlet_scores(
    conn,
    date_range: str = "90d",
    score_date: Optional[str] = None,
) -> List[OutletScoreRow]:
    """
    Compute transparency scores for every outlet that has frame data.

    Returns one OutletScoreRow per (source, source_type) pair.
    Outlets with fewer than 3 documents are excluded.
    """
    cutoff = _date_cutoff(date_range)
    week = _week_date(score_date)
    ts = datetime.now(timezone.utc).isoformat()

    # Enumerate outlets from document_frames (same approach as outlet_clustering)
    news_outlets = conn.execute("""
        SELECT DISTINCT n.source AS source, 'news' AS source_type
        FROM document_frames df
        JOIN news_articles n ON df.document_id = n.id
        WHERE n.source IS NOT NULL AND n.publish_date >= ?
    """, [cutoff]).fetchall()

    other_outlets = conn.execute("""
        SELECT DISTINCT source_type AS source, source_type
        FROM document_frames
        WHERE source_type != 'news' AND classified_at >= ?
    """, [cutoff]).fetchall()

    results: List[OutletScoreRow] = []
    for src, src_type in list(news_outlets) + list(other_outlets):
        try:
            diversity, doc_count = _frame_diversity(conn, src, src_type, cutoff)
            if doc_count < 3:
                continue
            attr_rate, claim_count = _attribution_rate(conn, src, src_type, cutoff)
            neutrality = _stance_neutrality(conn, src, src_type)
            composite = round((diversity + attr_rate + neutrality) / 3.0, 4)

            results.append(OutletScoreRow(
                source=src,
                source_type=src_type,
                score_date=week,
                frame_diversity=diversity,
                attribution_rate=attr_rate,
                stance_neutrality=neutrality,
                composite_score=composite,
                doc_count=doc_count,
                claim_count=claim_count,
                computed_at=ts,
            ))
        except Exception as e:
            logger.debug("scorer: skipping %s/%s: %s", src, src_type, e)

    results.sort(key=lambda r: -r.composite_score)
    return results


def store_scores(rows: List[OutletScoreRow], conn) -> None:
    """Upsert scores into ``outlet_scores`` (INSERT OR REPLACE keyed by source+type+date)."""
    for r in rows:
        conn.execute("""
            INSERT OR REPLACE INTO outlet_scores
                (source, source_type, score_date,
                 frame_diversity, attribution_rate, stance_neutrality,
                 composite_score, doc_count, claim_count, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [r.source, r.source_type, r.score_date,
              r.frame_diversity, r.attribution_rate, r.stance_neutrality,
              r.composite_score, r.doc_count, r.claim_count, r.computed_at])


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_scorer_batch(
    conn, lock,
    date_range: str = "90d",
    date_override: Optional[str] = None,
) -> dict:
    """
    Compute + persist weekly transparency scores for all outlets.

    Idempotent — re-running in the same week overwrites that week's row.

    Returns a summary dict for API/MCP responses.
    """
    try:
        with lock:
            rows = compute_outlet_scores(conn, date_range=date_range,
                                         score_date=date_override)
    except Exception as e:
        return {"error": f"score computation failed: {e}"}

    if not rows:
        return {"outlets_scored": 0, "score_date": _week_date(date_override),
                "message": "no outlets with sufficient frame data"}

    try:
        with lock:
            store_scores(rows, conn)
    except Exception as e:
        return {"error": f"store failed: {e}"}

    return {
        "outlets_scored": len(rows),
        "score_date":     _week_date(date_override),
        "top_outlet":     rows[0].source if rows else None,
        "top_composite":  rows[0].composite_score if rows else None,
    }
