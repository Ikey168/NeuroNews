"""
FastAPI routes for sentiment analysis and sentiment trends.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth.jwt_auth import require_auth
from src.database.local_analytics_connector import LocalAnalyticsConnector

router = APIRouter(prefix="/news_sentiment", tags=["sentiment"])


async def get_db():
    """Dependency to get an analytics warehouse connection (local DuckDB)."""
    db = LocalAnalyticsConnector()
    try:
        db.connect()
        yield db
    finally:
        db.disconnect()


@router.get("/heatmap")
async def get_sentiment_heatmap(
    days: int = Query(14, ge=1, le=60, description="Number of days to cover"),
    max_topics: int = Query(6, ge=1, le=12, description="Maximum category rows"),
    _user: dict = Depends(require_auth),
) -> Dict[str, Any]:
    """Category x day average-sentiment heatmap derived from the warehouse."""
    try:
        from src.database.local_warehouse_views import (
            get_sentiment_heatmap as warehouse_heatmap,
        )

        return await warehouse_heatmap(days=days, max_topics=max_topics)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error building sentiment heatmap: {0}".format(str(e)),
        )


@router.get("")
async def get_sentiment_trends(
    topic: Optional[str] = Query(None, description="Topic to filter articles by"),
    start_date: Optional[datetime] = Query(
        None, description="Start date for sentiment analysis"
    ),
    end_date: Optional[datetime] = Query(
        None, description="End date for sentiment analysis"
    ),
    source: Optional[str] = Query(None, description="News source to filter by"),
    group_by: str = Query("day", description="Group by: day, week, month"),
    db: LocalAnalyticsConnector = Depends(get_db),
    _user: dict = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Get sentiment trends for news articles with optional filtering by topic.

    This endpoint implements the requirement from Issue #28:
    /news_sentiment?topic=AI to fetch sentiment trends.

    Args:
        topic: Topic to search for in article titles and content
        start_date: Filter articles from this date (defaults to 30 days ago)
        end_date: Filter articles until this date (defaults to today)
        source: Filter by specific news source
        group_by: How to group sentiment data (day, week, month)
        db: Database connection (injected)

    Returns:
        Dict containing:
        - sentiment_trends: Time-series sentiment data
        - overall_sentiment: Aggregated sentiment statistics
        - article_count: Number of articles analyzed
        - topic_filter: The topic that was filtered (if any)
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Build the WHERE clause conditions
        conditions = ["publish_date >= %s", "publish_date <= %s"]
        params = [start_date, end_date]

        # Add topic filter if provided
        if topic:
            conditions.append("(title ILIKE %s OR content ILIKE %s)")
            topic_pattern = "%{0}%".format(topic)
            params.extend([topic_pattern, topic_pattern])

        # Add source filter if provided
        if source:
            conditions.append("source = %s")
            params.append(source)

        # Add condition to only include articles with sentiment data
        conditions.append("sentiment_label IS NOT NULL")

        # Build the where clause
        where_clause = " AND ".join(conditions)

        # Determine date grouping based on group_by parameter
        if group_by == "week":
            date_trunc = "DATE_TRUNC('week', publish_date)"
        elif group_by == "month":
            date_trunc = "DATE_TRUNC('month', publish_date)"
        else:  # default to day
            date_trunc = "DATE_TRUNC('day', publish_date)"

        # Query for sentiment trends over time
        trends_query = """
            SELECT
                {date_trunc} as period,
                sentiment_label,
                COUNT(*) as article_count,
                AVG(sentiment_score) as avg_sentiment_score,
                MIN(sentiment_score) as min_sentiment_score,
                MAX(sentiment_score) as max_sentiment_score
            FROM news_articles
            WHERE {where_clause}
            GROUP BY {date_trunc}, sentiment_label
            ORDER BY period, sentiment_label
        """.format(
            date_trunc=date_trunc, where_clause=where_clause
        )

        trends_results = await db.execute_query(trends_query, params)

        # Query for overall sentiment statistics
        overall_query = """
            SELECT
                sentiment_label,
                COUNT(*) as count,
                AVG(sentiment_score) as avg_score,
                COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
            FROM news_articles
            WHERE {where_clause}
            GROUP BY sentiment_label
            ORDER BY count DESC
        """.format(
            where_clause=where_clause
        )

        overall_results = await db.execute_query(overall_query, params)

        # Query for total article count
        count_query = """
            SELECT COUNT(*) as total_articles
            FROM news_articles
            WHERE {where_clause}
        """.format(
            where_clause=where_clause
        )

        count_results = await db.execute_query(count_query, params)
        total_articles = count_results[0][0] if count_results else 0

        # Format trends data
        sentiment_trends = {}
        for row in trends_results:
            period_str = row[0].isoformat()
            sentiment = row[1]

            if period_str not in sentiment_trends:
                sentiment_trends[period_str] = {"date": period_str, "sentiments": {}}

            sentiment_trends[period_str]["sentiments"][sentiment.lower()] = {
                "count": int(row[2]),
                "avg_score": float(row[3]) if row[3] else 0.0,
                "min_score": float(row[4]) if row[4] else 0.0,
                "max_score": float(row[5]) if row[5] else 0.0,
            }

        # Format overall sentiment data
        overall_sentiment = {}
        for row in overall_results:
            sentiment = row[0].lower()
            overall_sentiment[sentiment] = {
                "count": int(row[1]),
                "avg_score": float(row[2]) if row[2] else 0.0,
                "percentage": float(row[3]) if row[3] else 0.0,
            }

        return {
            "sentiment_trends": list(sentiment_trends.values()),
            "overall_sentiment": overall_sentiment,
            "article_count": total_articles,
            "topic_filter": topic,
            "date_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "group_by": group_by,
            "source_filter": source,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving sentiment trends: {0}".format(str(e)),
        )


@router.get("/summary")
async def get_sentiment_summary(
    topic: Optional[str] = Query(None, description="Topic to filter articles by"),
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
    db: LocalAnalyticsConnector = Depends(get_db),
    _user: dict = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Get a summary of sentiment analysis for recent articles.

    Args:
        topic: Optional topic filter
        days: Number of days to analyze (1-365)
        db: Database connection (injected)

    Returns:
        Dict with sentiment summary statistics
    """
    try:
        start_date = datetime.now() - timedelta(days=days)

        conditions = ["publish_date >= %s", "sentiment_label IS NOT NULL"]
        params = [start_date]

        if topic:
            conditions.append("(title ILIKE %s OR content ILIKE %s)")
            topic_pattern = "%{0}%".format(topic)
            params.extend([topic_pattern, topic_pattern])

        where_clause = " AND ".join(conditions)

        query = """
            SELECT
                sentiment_label,
                COUNT(*) as count,
                AVG(sentiment_score) as avg_score,
                STDDEV(sentiment_score) as score_stddev
            FROM news_articles
            WHERE {where_clause}
            GROUP BY sentiment_label
            ORDER BY count DESC
        """.format(
            where_clause=where_clause
        )

        results = await db.execute_query(query, params)

        total_articles = sum(row[1] for row in results)

        sentiment_summary = {
            "summary": {},
            "total_articles": total_articles,
            "days_analyzed": days,
            "topic_filter": topic,
        }

        for row in results:
            sentiment = row[0].lower()
            count = int(row[1])
            avg_score = float(row[2]) if row[2] else 0.0
            stddev = float(row[3]) if row[3] else 0.0
            percentage = (count / total_articles * 100) if total_articles > 0 else 0.0

            sentiment_summary["summary"][sentiment] = {
                "count": count,
                "percentage": round(percentage, 2),
                "avg_score": round(avg_score, 3),
                "score_stddev": round(stddev, 3),
            }

        return sentiment_summary

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving sentiment summary: {0}".format(str(e)),
        )


@router.get("/topics")
async def get_topic_sentiment_analysis(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    min_articles: int = Query(5, ge=1, description="Minimum articles per topic"),
    db: LocalAnalyticsConnector = Depends(get_db),
    _user: dict = Depends(require_auth),
) -> List[Dict[str, Any]]:
    """
    Get sentiment analysis broken down by detected topics/keywords.

    Args:
        days: Number of days to analyze
        min_articles: Minimum number of articles required for a topic to be included
        db: Database connection (injected)

    Returns:
        List of topics with their sentiment statistics
    """
    try:
        # Keyword-based topic sentiment from the local warehouse (significant
        # terms, not the first word of each title).
        from src.database.local_warehouse_views import get_topic_sentiment

        topic_list = await get_topic_sentiment(
            days=days, min_articles=min_articles, max_topics=12
        )

        # Add percentage breakdown per sentiment label.
        for topic_data in topic_list:
            total = topic_data["total_articles"] or 1
            for sentiment_data in topic_data["sentiments"].values():
                sentiment_data["percentage"] = round(
                    sentiment_data["count"] / total * 100, 2
                )

        return topic_list

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving topic sentiment analysis: {0}".format(str(e)),
        )
