"""
Alert condition detection against the local DuckDB warehouse.

Three condition types
---------------------
breaking_news    — articles matching the topic published in the last 15 min
                   with negative or strongly negative sentiment
sentiment_shift  — avg sentiment over last 1h vs previous 1h exceeds threshold
new_event        — at least 3 new articles on the same source in the last 30 min
                   (proxy for a breaking cluster forming)

Each check returns a dict with keys: triggered (bool), title, body.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from src.database.local_analytics_connector import get_shared_connection, _LOCK


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def check_breaking_news(topic: str) -> Dict[str, Any]:
    """Articles matching topic published in the last 15 min with negative sentiment."""
    cutoff = _now() - timedelta(minutes=15)
    pattern = f"%{topic}%"
    conn = get_shared_connection()
    with _LOCK:
        rows = conn.execute(
            """SELECT title, source, sentiment_score
               FROM news_articles
               WHERE (title ILIKE ? OR category ILIKE ?)
                 AND publish_date >= ?
                 AND sentiment_score < -0.1
               ORDER BY publish_date DESC LIMIT 5""",
            [pattern, pattern, cutoff],
        ).fetchall()

    if not rows:
        return {"triggered": False, "title": "", "body": ""}

    headlines = "\n".join(f"• {r[0]} ({r[1]}, score {r[2]:+.2f})" for r in rows)
    return {
        "triggered": True,
        "title": f"Breaking: {len(rows)} negative article(s) on '{topic}'",
        "body": f"New negative coverage detected in the last 15 minutes:\n\n{headlines}",
    }


def check_sentiment_shift(topic: str, threshold: float = 0.15) -> Dict[str, Any]:
    """Sentiment shifted by more than `threshold` between the last two 1-hour windows."""
    now = _now()
    h1_start = now - timedelta(hours=1)
    h2_start = now - timedelta(hours=2)
    pattern = f"%{topic}%"
    conn = get_shared_connection()

    with _LOCK:
        r_recent = conn.execute(
            """SELECT AVG(sentiment_score) FROM news_articles
               WHERE (title ILIKE ? OR category ILIKE ?)
                 AND publish_date >= ? AND publish_date < ?""",
            [pattern, pattern, h1_start, now],
        ).fetchone()
        r_prev = conn.execute(
            """SELECT AVG(sentiment_score) FROM news_articles
               WHERE (title ILIKE ? OR category ILIKE ?)
                 AND publish_date >= ? AND publish_date < ?""",
            [pattern, pattern, h2_start, h1_start],
        ).fetchone()

    avg_recent = r_recent[0] if r_recent and r_recent[0] is not None else None
    avg_prev = r_prev[0] if r_prev and r_prev[0] is not None else None

    if avg_recent is None or avg_prev is None:
        return {"triggered": False, "title": "", "body": ""}

    delta = avg_recent - avg_prev
    if abs(delta) < threshold:
        return {"triggered": False, "title": "", "body": ""}

    direction = "worsened" if delta < 0 else "improved"
    return {
        "triggered": True,
        "title": f"Sentiment {direction} for '{topic}': {delta:+.3f}",
        "body": (
            f"Sentiment on '{topic}' has {direction} significantly.\n\n"
            f"  Previous hour avg: {avg_prev:+.3f}\n"
            f"  Last hour avg:     {avg_recent:+.3f}\n"
            f"  Delta:             {delta:+.3f}"
        ),
    }


def check_new_event(topic: str) -> Dict[str, Any]:
    """3+ articles from the same source on the topic in the last 30 min — cluster forming."""
    cutoff = _now() - timedelta(minutes=30)
    pattern = f"%{topic}%"
    conn = get_shared_connection()

    with _LOCK:
        rows = conn.execute(
            """SELECT source, COUNT(*) AS n
               FROM news_articles
               WHERE (title ILIKE ? OR category ILIKE ?)
                 AND publish_date >= ?
               GROUP BY source HAVING COUNT(*) >= 3
               ORDER BY n DESC LIMIT 3""",
            [pattern, pattern, cutoff],
        ).fetchall()

    if not rows:
        return {"triggered": False, "title": "", "body": ""}

    sources = ", ".join(f"{r[0]} ({r[1]} articles)" for r in rows)
    return {
        "triggered": True,
        "title": f"New event cluster forming: '{topic}'",
        "body": (
            f"Multiple sources are publishing rapidly on '{topic}':\n\n"
            f"{sources}\n\n"
            "This may indicate a breaking event or policy update."
        ),
    }


def run_all_checks(topic: str, alert_type: str, threshold: float | None) -> Dict[str, Any]:
    """Run the appropriate check for a rule's alert_type."""
    if alert_type == "breaking_news":
        return check_breaking_news(topic)
    if alert_type == "sentiment_shift":
        return check_sentiment_shift(topic, threshold=threshold or 0.15)
    if alert_type == "new_event":
        return check_new_event(topic)
    return {"triggered": False, "title": "", "body": ""}
