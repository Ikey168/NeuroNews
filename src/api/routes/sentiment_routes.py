"""
FastAPI routes for sentiment analysis and sentiment trends.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
from src.database.redshift_loader import RedshiftLoader

router = APIRouter(prefix="/news_sentiment", tags=["sentiment"])

async def get_db():
    """Dependency to get database connection."""
    host = os.getenv("REDSHIFT_HOST")
    if not host:
        raise HTTPException(
            status_code=500,
            detail="REDSHIFT_HOST environment variable not set"
        )
    
    db = RedshiftLoader(
        host=host,
        database=os.getenv("REDSHIFT_DB", "dev"),
        user=os.getenv("REDSHIFT_USER", "admin"),
        password=os.getenv("REDSHIFT_PASSWORD")
    )
    try:
        await db.connect()
        yield db
    finally:
        await db.close()

@router.get("")
async def get_sentiment_trends(
    topic: Optional[str] = Query(None, description="Topic to filter articles by"),
    start_date: Optional[datetime] = Query(None, description="Start date for sentiment analysis"),
    end_date: Optional[datetime] = Query(None, description="End date for sentiment analysis"),
    source: Optional[str] = Query(None, description="News source to filter by"),
    group_by: str = Query("day", description="Group by: day, week, month"),
    db: RedshiftLoader = Depends(get_db)
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
            topic_pattern = f"%{topic}%"
            params.extend([topic_pattern, topic_pattern])
        
        # Add source filter if provided
        if source:
            conditions.append("source = %s")
            params.append(source)
        
        # Add condition to only include articles with sentiment data
        conditions.append("sentiment_label IS NOT NULL")
        
        where_clause = " AND ".join(conditions)
        
        # Determine date grouping based on group_by parameter
        if group_by == "week":
            date_trunc = "DATE_TRUNC('week', publish_date)"
        elif group_by == "month":
            date_trunc = "DATE_TRUNC('month', publish_date)"
        else:  # default to day
            date_trunc = "DATE_TRUNC('day', publish_date)"
        
        # Query for sentiment trends over time
        trends_query = f"""
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
        """
        
        trends_results = await db.execute_query(trends_query, params)
        
        # Query for overall sentiment statistics
        overall_query = f"""
            SELECT 
                sentiment_label,
                COUNT(*) as count,
                AVG(sentiment_score) as avg_score,
                COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
            FROM news_articles
            WHERE {where_clause}
            GROUP BY sentiment_label
            ORDER BY count DESC
        """
        
        overall_results = await db.execute_query(overall_query, params)
        
        # Query for total article count
        count_query = f"""
            SELECT COUNT(*) as total_articles
            FROM news_articles
            WHERE {where_clause}
        """
        
        count_results = await db.execute_query(count_query, params)
        total_articles = count_results[0][0] if count_results else 0
        
        # Format trends data
        sentiment_trends = {}
        for row in trends_results:
            period_str = row[0].isoformat()
            sentiment = row[1]
            
            if period_str not in sentiment_trends:
                sentiment_trends[period_str] = {
                    "date": period_str,
                    "sentiments": {}
                }
            
            sentiment_trends[period_str]["sentiments"][sentiment.lower()] = {
                "count": int(row[2]),
                "avg_score": float(row[3]) if row[3] else 0.0,
                "min_score": float(row[4]) if row[4] else 0.0,
                "max_score": float(row[5]) if row[5] else 0.0
            }
        
        # Format overall sentiment data
        overall_sentiment = {}
        for row in overall_results:
            sentiment = row[0].lower()
            overall_sentiment[sentiment] = {
                "count": int(row[1]),
                "avg_score": float(row[2]) if row[2] else 0.0,
                "percentage": float(row[3]) if row[3] else 0.0
            }
        
        return {
            "sentiment_trends": list(sentiment_trends.values()),
            "overall_sentiment": overall_sentiment,
            "article_count": total_articles,
            "topic_filter": topic,
            "date_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "group_by": group_by,
            "source_filter": source
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving sentiment trends: {str(e)}"
        )

@router.get("/summary")
async def get_sentiment_summary(
    topic: Optional[str] = Query(None, description="Topic to filter articles by"),
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
    db: RedshiftLoader = Depends(get_db)
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
            topic_pattern = f"%{topic}%"
            params.extend([topic_pattern, topic_pattern])
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                sentiment_label,
                COUNT(*) as count,
                AVG(sentiment_score) as avg_score,
                STDDEV(sentiment_score) as score_stddev
            FROM news_articles
            WHERE {where_clause}
            GROUP BY sentiment_label
            ORDER BY count DESC
        """
        
        results = await db.execute_query(query, params)
        
        total_articles = sum(row[1] for row in results)
        
        sentiment_summary = {
            "summary": {},
            "total_articles": total_articles,
            "days_analyzed": days,
            "topic_filter": topic
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
                "score_stddev": round(stddev, 3)
            }
        
        return sentiment_summary
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving sentiment summary: {str(e)}"
        )

@router.get("/topics")
async def get_topic_sentiment_analysis(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    min_articles: int = Query(5, ge=1, description="Minimum articles per topic"),
    db: RedshiftLoader = Depends(get_db)
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
        start_date = datetime.now() - timedelta(days=days)
        
        # This is a simplified topic extraction - in production you might want
        # to use more sophisticated NLP techniques or pre-computed topic tags
        query = """
            SELECT 
                UPPER(SPLIT_PART(title, ' ', 1)) as topic_word,
                sentiment_label,
                COUNT(*) as article_count,
                AVG(sentiment_score) as avg_sentiment
            FROM news_articles
            WHERE publish_date >= %s 
                AND sentiment_label IS NOT NULL
                AND LENGTH(SPLIT_PART(title, ' ', 1)) > 3
            GROUP BY UPPER(SPLIT_PART(title, ' ', 1)), sentiment_label
            HAVING COUNT(*) >= %s
            ORDER BY article_count DESC
        """
        
        results = await db.execute_query(query, [start_date, min_articles])
        
        # Group results by topic
        topics = {}
        for row in results:
            topic = row[0]
            sentiment = row[1].lower()
            count = int(row[2])
            avg_score = float(row[3]) if row[3] else 0.0
            
            if topic not in topics:
                topics[topic] = {
                    "topic": topic,
                    "total_articles": 0,
                    "sentiments": {}
                }
            
            topics[topic]["total_articles"] += count
            topics[topic]["sentiments"][sentiment] = {
                "count": count,
                "avg_score": round(avg_score, 3)
            }
        
        # Convert to list and calculate percentages
        topic_list = []
        for topic_data in topics.values():
            total = topic_data["total_articles"]
            for sentiment_data in topic_data["sentiments"].values():
                sentiment_data["percentage"] = round(sentiment_data["count"] / total * 100, 2)
            topic_list.append(topic_data)
        
        # Sort by total articles descending
        topic_list.sort(key=lambda x: x["total_articles"], reverse=True)
        
        return topic_list
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving topic sentiment analysis: {str(e)}"
        )
