"""
Derived analytics views over the local DuckDB warehouse.

The event-clustering, trending-topics and breaking-news subsystems are normally
backed by separate stores (an ML clusterer over Redshift/Postgres, a keyword
topic database, …). For a local, zero-service setup those aren't available, so
this module synthesizes equivalent, data-driven results directly from the
seeded ``news_articles`` table: articles are grouped by their leading title word
into "topics"/"clusters" and simple trending / impact / velocity scores are
derived from group size and recency.

The returned dict shapes match what the API route response models expect.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.database.local_analytics_connector import LocalAnalyticsConnector


async def _grouped_topics(
    days: int, category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Group recent articles by leading title word into topic aggregates."""
    db = LocalAnalyticsConnector()
    db.connect()

    cutoff = datetime.now() - timedelta(days=days)
    recent_cutoff = datetime.now() - timedelta(hours=24)

    conditions = ["publish_date >= %s", "LENGTH(SPLIT_PART(title, ' ', 1)) > 3"]
    params: List[Any] = [cutoff]
    if category:
        conditions.append("category = %s")
        params.append(category)
    where_clause = " AND ".join(conditions)

    # recent_cutoff is the first bound parameter (used inside the SUM CASE).
    query = """
        SELECT
            UPPER(SPLIT_PART(title, ' ', 1)) AS topic,
            COUNT(*) AS cnt,
            AVG(sentiment_score) AS avg_sent,
            MIN(publish_date) AS first_date,
            MAX(publish_date) AS last_date,
            COUNT(DISTINCT source) AS source_count,
            STRING_AGG(DISTINCT source, '||') AS sources,
            arg_max(category, publish_date) AS category,
            arg_max(title, publish_date) AS headline,
            STRING_AGG(title, ' | ') AS sample_titles,
            SUM(CASE WHEN publish_date >= %s THEN 1 ELSE 0 END) AS recent_cnt
        FROM news_articles
        WHERE {where_clause}
        GROUP BY UPPER(SPLIT_PART(title, ' ', 1))
        ORDER BY cnt DESC
    """.format(
        where_clause=where_clause
    )

    rows = await db.execute_query(query, [recent_cutoff, *params])
    db.disconnect()

    topics: List[Dict[str, Any]] = []
    for r in rows:
        (
            topic,
            cnt,
            avg_sent,
            first_date,
            last_date,
            source_count,
            sources,
            cat,
            headline,
            sample_titles,
            recent_cnt,
        ) = r
        cnt = int(cnt)
        recent_cnt = int(recent_cnt or 0)
        recent_fraction = recent_cnt / cnt if cnt else 0.0
        duration_hours = (
            (last_date - first_date).total_seconds() / 3600.0
            if first_date and last_date
            else 0.0
        )
        topics.append(
            {
                "topic": topic,
                "cnt": cnt,
                "avg_sent": float(avg_sent or 0.0),
                "first_date": first_date,
                "last_date": last_date,
                "source_count": int(source_count or 0),
                "sources": (sources or "").split("||") if sources else [],
                "category": cat or "General",
                "headline": headline or topic,
                "sample_titles": (sample_titles or "").split(" | ")[:3],
                "recent_fraction": recent_fraction,
                "duration_hours": round(duration_hours, 1),
                "trending_score": round(min(100.0, cnt * 5 + recent_fraction * 20), 2),
                "impact_score": round(min(100.0, cnt * 6.0), 2),
                "velocity_score": round(recent_fraction, 3),
            }
        )
    return topics


def _event_type(t: Dict[str, Any]) -> str:
    if t["recent_fraction"] >= 0.5:
        return "breaking"
    if t["recent_fraction"] > 0.0:
        return "developing"
    return "trending"


async def get_trending_topics(days: int = 7) -> List[Dict[str, Any]]:
    """Trending topics in the shape expected by /topics/trending."""
    topics = await _grouped_topics(days)
    max_cnt = max((t["cnt"] for t in topics), default=1)
    return [
        {
            "topic": t["topic"],
            "topic_name": t["topic"],
            "article_count": t["cnt"],
            "avg_probability": round(t["cnt"] / max_cnt, 3),
            "avg_sentiment": round(t["avg_sent"], 3),
            "growth_rate": round(t["recent_fraction"], 3),
        }
        for t in topics
    ]


async def get_event_clusters(
    days_back: int = 7,
    category: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Event clusters in the shape expected by /api/v1/events/clusters."""
    topics = await _grouped_topics(days_back, category=category)
    clusters: List[Dict[str, Any]] = []
    now_iso = datetime.now().isoformat()
    for t in topics:
        etype = _event_type(t)
        if event_type and etype != event_type:
            continue
        clusters.append(
            {
                "cluster_id": "cl-{0}".format(t["topic"].lower()),
                "cluster_name": t["headline"],
                "event_type": etype,
                "category": t["category"],
                "cluster_size": t["cnt"],
                "silhouette_score": 0.5,
                "cohesion_score": 0.6,
                "separation_score": 0.5,
                "trending_score": t["trending_score"],
                "impact_score": t["impact_score"],
                "velocity_score": t["velocity_score"],
                "significance_score": round(
                    t["trending_score"] * 0.3 + t["impact_score"] * 0.4, 2
                ),
                "first_article_date": t["first_date"].isoformat(),
                "last_article_date": t["last_date"].isoformat(),
                "event_duration_hours": t["duration_hours"],
                "primary_sources": t["sources"],
                "geographic_focus": [],
                "key_entities": [t["topic"].title()],
                "status": "active",
                "created_at": now_iso,
            }
        )
    return clusters[:limit]


async def get_breaking_news(
    hours_back: int = 24,
    category: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Breaking news in the shape expected by /api/v1/breaking_news."""
    days = max(1, (hours_back + 23) // 24)
    topics = await _grouped_topics(days, category=category)
    # Most active topics first.
    topics.sort(key=lambda t: t["trending_score"], reverse=True)
    events: List[Dict[str, Any]] = []
    for t in topics[:limit]:
        events.append(
            {
                "cluster_id": "bn-{0}".format(t["topic"].lower()),
                "cluster_name": t["headline"],
                "event_type": _event_type(t),
                "category": t["category"],
                "trending_score": t["trending_score"],
                "impact_score": t["impact_score"],
                "velocity_score": t["velocity_score"],
                "cluster_size": t["cnt"],
                "first_article_date": t["first_date"].isoformat(),
                "last_article_date": t["last_date"].isoformat(),
                "peak_activity_date": t["last_date"].isoformat(),
                "event_duration_hours": t["duration_hours"],
                "sample_headlines": " | ".join(t["sample_titles"]),
                "source_count": t["source_count"],
                "avg_confidence": 0.8,
            }
        )
    return events
