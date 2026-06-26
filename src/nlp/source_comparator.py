"""
Multi-source news comparison engine — Issue #46.

Compares how different media outlets cover the same topic by aggregating
article-level sentiment, outlet trust scores, editorial cluster, and
per-topic stances from the analytics warehouse.

Entry points:
  compare_sources(topic, conn, limit, days) -> dict
  list_source_trustworthiness(conn, source_type, date_range) -> list[dict]
  get_source_profile(source, conn) -> dict
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dominant_sentiment(pos: int, neg: int, neu: int) -> str:
    m = max(pos, neg, neu)
    if m == 0:
        return "neutral"
    if pos == m:
        return "positive"
    if neg == m:
        return "negative"
    return "neutral"


def _safe_float(v: Any) -> Optional[float]:
    try:
        return round(float(v), 4) if v is not None else None
    except (TypeError, ValueError):
        return None


def _date_cutoff_expr(days: int) -> str:
    return f"CURRENT_TIMESTAMP - INTERVAL '{days} days'"


# ---------------------------------------------------------------------------
# Article-level coverage query (sync, raw duckdb connection)
# ---------------------------------------------------------------------------

def _fetch_coverage(
    topic: str,
    conn: Any,
    limit: int,
    days: int,
) -> List[Dict[str, Any]]:
    """Return per-source article counts and sentiment aggregates."""
    sql = f"""
        SELECT
            source,
            COUNT(*)                                                   AS article_count,
            AVG(sentiment_score)                                       AS avg_sentiment,
            SUM(CASE WHEN sentiment_label = 'positive' THEN 1 ELSE 0 END) AS positive_count,
            SUM(CASE WHEN sentiment_label = 'negative' THEN 1 ELSE 0 END) AS negative_count,
            SUM(CASE WHEN sentiment_label = 'neutral'  THEN 1 ELSE 0 END) AS neutral_count,
            MAX(category)                                              AS category
        FROM news_articles
        WHERE (title ILIKE ? OR content ILIKE ?)
          AND publish_date >= {_date_cutoff_expr(days)}
        GROUP BY source
        ORDER BY article_count DESC
        LIMIT ?
    """
    pattern = f"%{topic}%"
    rows = conn.execute(sql, [pattern, pattern, limit]).fetchall()
    return [
        {
            "source": r[0],
            "article_count": r[1],
            "avg_sentiment": _safe_float(r[2]),
            "positive_count": r[3] or 0,
            "negative_count": r[4] or 0,
            "neutral_count": r[5] or 0,
            "category": r[6],
        }
        for r in rows
    ]


def _fetch_outlet_scores(sources: List[str], conn: Any) -> Dict[str, Dict[str, Any]]:
    """Return latest outlet trust scores keyed by source name."""
    if not sources:
        return {}
    placeholders = ", ".join("?" * len(sources))
    sql = f"""
        SELECT DISTINCT ON (source)
            source,
            frame_diversity,
            attribution_rate,
            stance_neutrality,
            composite_score
        FROM outlet_scores
        WHERE source IN ({placeholders})
        ORDER BY source, score_date DESC
    """
    rows = conn.execute(sql, sources).fetchall()
    return {
        r[0]: {
            "frame_diversity": _safe_float(r[1]),
            "attribution_rate": _safe_float(r[2]),
            "stance_neutrality": _safe_float(r[3]),
            "composite_score": _safe_float(r[4]),
        }
        for r in rows
    }


def _fetch_clusters(sources: List[str], conn: Any) -> Dict[str, Dict[str, Any]]:
    """Return editorial cluster info keyed by source name."""
    if not sources:
        return {}
    placeholders = ", ".join("?" * len(sources))
    sql = f"""
        SELECT source, cluster_id, cluster_label, dominant_frame
        FROM outlet_clusters
        WHERE source IN ({placeholders})
    """
    rows = conn.execute(sql, sources).fetchall()
    return {
        r[0]: {
            "cluster_id": r[1],
            "cluster_label": r[2],
            "dominant_frame": r[3],
        }
        for r in rows
    }


def _fetch_stances(topic: str, sources: List[str], conn: Any) -> Dict[str, Dict[str, Any]]:
    """Return the most recent per-topic stance keyed by source name."""
    if not sources:
        return {}
    placeholders = ", ".join("?" * len(sources))
    sql = f"""
        SELECT DISTINCT ON (source)
            source, stance, confidence
        FROM source_stances
        WHERE source IN ({placeholders}) AND topic ILIKE ?
        ORDER BY source, computed_at DESC
    """
    rows = conn.execute(sql, sources + [f"%{topic}%"]).fetchall()
    return {
        r[0]: {"stance": r[1], "stance_confidence": _safe_float(r[2])}
        for r in rows
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare_sources(
    topic: str,
    conn: Any,
    limit: int = 10,
    days: int = 90,
) -> Dict[str, Any]:
    """
    Compare how different outlets cover *topic*.

    Args:
        topic:  Substring matched against title and content (case-insensitive).
        conn:   Raw DuckDB connection (``get_shared_connection()``).
        limit:  Maximum number of sources to return (ordered by article count).
        days:   Look-back window in days.

    Returns a dict with keys: topic, days, total_articles, sources_found,
    comparison (list), summary.
    """
    topic = topic.strip()
    if not topic:
        return {
            "topic": topic,
            "days": days,
            "total_articles": 0,
            "sources_found": 0,
            "comparison": [],
            "summary": {},
        }

    coverage = _fetch_coverage(topic, conn, limit, days)
    if not coverage:
        return {
            "topic": topic,
            "days": days,
            "total_articles": 0,
            "sources_found": 0,
            "comparison": [],
            "summary": {},
        }

    sources = [r["source"] for r in coverage]
    total_articles = sum(r["article_count"] for r in coverage)

    scores = _fetch_outlet_scores(sources, conn)
    clusters = _fetch_clusters(sources, conn)
    stances = _fetch_stances(topic, sources, conn)

    comparison = []
    for r in coverage:
        src = r["source"]
        pos = r["positive_count"]
        neg = r["negative_count"]
        neu = r["neutral_count"]
        coverage_pct = round(r["article_count"] / max(total_articles, 1) * 100, 1)
        sentiment = r["avg_sentiment"]

        comparison.append({
            "source": src,
            "article_count": r["article_count"],
            "coverage_share_pct": coverage_pct,
            "avg_sentiment": sentiment,
            "dominant_sentiment": _dominant_sentiment(pos, neg, neu),
            "sentiment_distribution": {
                "positive": pos,
                "negative": neg,
                "neutral": neu,
            },
            "trust_scores": scores.get(src),
            "cluster": clusters.get(src),
            "stance": stances.get(src, {}).get("stance"),
            "stance_confidence": stances.get(src, {}).get("stance_confidence"),
        })

    # Summary across sources
    def _attr(key: str, default: Any = None):
        return [c[key] for c in comparison if c[key] is not None]

    sentiments = _attr("avg_sentiment")
    trusts = [
        c["trust_scores"]["composite_score"]
        for c in comparison
        if c["trust_scores"] and c["trust_scores"].get("composite_score") is not None
    ]
    stances_found = sorted({c["stance"] for c in comparison if c["stance"]})

    summary: Dict[str, Any] = {
        "highest_coverage_source": comparison[0]["source"] if comparison else None,
        "stance_spread": stances_found,
    }
    if sentiments:
        summary["most_positive_source"] = max(
            comparison, key=lambda c: c["avg_sentiment"] or -math.inf
        )["source"]
        summary["most_negative_source"] = min(
            comparison, key=lambda c: c["avg_sentiment"] or math.inf
        )["source"]
    if trusts:
        summary["most_trusted_source"] = max(
            (c for c in comparison if c["trust_scores"] and c["trust_scores"].get("composite_score") is not None),
            key=lambda c: c["trust_scores"]["composite_score"],
        )["source"]

    return {
        "topic": topic,
        "days": days,
        "total_articles": total_articles,
        "sources_found": len(comparison),
        "comparison": comparison,
        "summary": summary,
    }


def list_source_trustworthiness(
    conn: Any,
    source_type: Optional[str] = None,
    date_range: str = "30d",
) -> List[Dict[str, Any]]:
    """
    List all sources with their latest trust scores.

    Args:
        conn:         Raw DuckDB connection.
        source_type:  Optional filter (e.g. "news", "blog").
        date_range:   "30d" / "90d" / "all" — oldest score_date to include.
    """
    where_clauses: List[str] = []
    params: List[Any] = []
    if date_range != "all":
        days = int(date_range.rstrip("d"))
        # computed_at is a VARCHAR timestamp — cast it for comparison
        where_clauses.append(
            f"TRY_CAST(computed_at AS TIMESTAMP) >= {_date_cutoff_expr(days)}"
        )
    if source_type:
        where_clauses.append("source_type = ?")
        params.append(source_type)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = f"""
        SELECT DISTINCT ON (source)
            source,
            source_type,
            frame_diversity,
            attribution_rate,
            stance_neutrality,
            composite_score,
            doc_count,
            score_date
        FROM outlet_scores
        {where_sql}
        ORDER BY source, score_date DESC
    """
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "source": r[0],
            "source_type": r[1],
            "frame_diversity": _safe_float(r[2]),
            "attribution_rate": _safe_float(r[3]),
            "stance_neutrality": _safe_float(r[4]),
            "composite_score": _safe_float(r[5]),
            "doc_count": r[6],
            "score_date": r[7],
        }
        for r in rows
    ]


def get_source_profile(source: str, conn: Any) -> Dict[str, Any]:
    """
    Return a full profile for one source: article stats, trust scores,
    cluster, stances.
    """
    # Article stats
    stats_sql = """
        SELECT
            COUNT(*)                    AS total_articles,
            AVG(sentiment_score)        AS avg_sentiment,
            MIN(publish_date)           AS first_seen,
            MAX(publish_date)           AS last_seen,
            MAX(category)               AS category
        FROM news_articles
        WHERE source = ?
    """
    s = conn.execute(stats_sql, [source]).fetchone()

    # Trust scores (latest row)
    scores_sql = """
        SELECT frame_diversity, attribution_rate, stance_neutrality, composite_score
        FROM outlet_scores
        WHERE source = ?
        ORDER BY score_date DESC
        LIMIT 1
    """
    sc = conn.execute(scores_sql, [source]).fetchone()

    # Cluster
    cluster_sql = """
        SELECT cluster_id, cluster_label, dominant_frame, pca_x, pca_y
        FROM outlet_clusters
        WHERE source = ?
        LIMIT 1
    """
    cl = conn.execute(cluster_sql, [source]).fetchone()

    # Stances
    stances_sql = """
        SELECT topic, stance, confidence, document_count
        FROM source_stances
        WHERE source = ?
        ORDER BY computed_at DESC
        LIMIT 20
    """
    st_rows = conn.execute(stances_sql, [source]).fetchall()

    return {
        "source": source,
        "total_articles": s[0] if s else 0,
        "avg_sentiment": _safe_float(s[1]) if s else None,
        "first_seen": str(s[2]) if s and s[2] else None,
        "last_seen": str(s[3]) if s and s[3] else None,
        "category": s[4] if s else None,
        "trust_scores": {
            "frame_diversity": _safe_float(sc[0]),
            "attribution_rate": _safe_float(sc[1]),
            "stance_neutrality": _safe_float(sc[2]),
            "composite_score": _safe_float(sc[3]),
        } if sc else None,
        "cluster": {
            "cluster_id": cl[0],
            "cluster_label": cl[1],
            "dominant_frame": cl[2],
            "pca_x": _safe_float(cl[3]),
            "pca_y": _safe_float(cl[4]),
        } if cl else None,
        "stances": [
            {
                "topic": r[0],
                "stance": r[1],
                "confidence": _safe_float(r[2]),
                "document_count": r[3],
            }
            for r in st_rows
        ],
    }
