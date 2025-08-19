"""
FastAPI routes for keyword extraction and topic modeling (Issue #29).

This module provides API endpoints for:
- Topic-based article search
- Keyword-based article search
- Topic and keyword statistics
- Advanced search combining multiple filters
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.nlp.keyword_topic_database import KeywordTopicDatabase, create_keyword_topic_db

router = APIRouter(prefix="/topics", tags=["topics", "keywords"])


async def get_keyword_topic_db() -> KeywordTopicDatabase:
    """Dependency to get keyword topic database connection."""
    try:
        return await create_keyword_topic_db()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Database connection error: {str(e)}"
        )


@router.get("/articles")
async def get_articles_by_topic(
    topic: str = Query(..., description="Topic name to search for"),
    min_probability: float = Query(
        0.2, ge=0.0, le=1.0, description="Minimum topic probability"
    ),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of articles to return"
    ),
    offset: int = Query(0, ge=0, description="Number of articles to skip"),
    db: KeywordTopicDatabase = Depends(get_keyword_topic_db),
) -> Dict[str, Any]:
    """
    Get articles that match a specific topic.

    This endpoint implements the topic-based search API requirement from Issue #29.

    Args:
        topic: Topic name to search for (case-insensitive)
        min_probability: Minimum probability threshold for topic matching
        limit: Maximum number of articles to return (1-200)
        offset: Number of articles to skip for pagination
        db: Database connection (injected)

    Returns:
        Dict containing:
        - articles: List of matching articles with topic information
        - total_count: Total number of matching articles
        - search_params: Parameters used for the search
    """
    try:
        articles = await db.get_articles_by_topic(
            topic_name=topic,
            min_probability=min_probability,
            limit=limit,
            offset=offset,
        )

        return {
            "articles": articles,
            "total_count": len(articles),
            "search_params": {
                "topic": topic,
                "min_probability": min_probability,
                "limit": limit,
                "offset": offset,
            },
            "has_more": len(articles) == limit,  # Simplified check
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving articles by topic: {str(e)}"
        )


@router.get("/keywords/articles")
async def get_articles_by_keyword(
    keyword: str = Query(..., description="Keyword to search for"),
    min_score: float = Query(0.1, ge=0.0, le=1.0, description="Minimum keyword score"),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of articles to return"
    ),
    offset: int = Query(0, ge=0, description="Number of articles to skip"),
    db: KeywordTopicDatabase = Depends(get_keyword_topic_db),
) -> Dict[str, Any]:
    """
    Get articles that contain a specific keyword.

    Args:
        keyword: Keyword to search for (case-insensitive)
        min_score: Minimum keyword score threshold
        limit: Maximum number of articles to return (1-200)
        offset: Number of articles to skip for pagination
        db: Database connection (injected)

    Returns:
        Dict containing articles with keyword information
    """
    try:
        articles = await db.get_articles_by_keyword(
            keyword=keyword, min_score=min_score, limit=limit, offset=offset
        )

        return {
            "articles": articles,
            "total_count": len(articles),
            "search_params": {
                "keyword": keyword,
                "min_score": min_score,
                "limit": limit,
                "offset": offset,
            },
            "has_more": len(articles) == limit,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving articles by keyword: {str(e)}"
        )


@router.get("/statistics")
async def get_topic_statistics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: KeywordTopicDatabase = Depends(get_keyword_topic_db),
) -> Dict[str, Any]:
    """
    Get topic distribution statistics for recent articles.

    Args:
        days: Number of days to look back (1-365)
        db: Database connection (injected)

    Returns:
        Dict with topic statistics and distribution
    """
    try:
        topics = await db.get_topic_statistics(days=days)

        return {
            "topics": topics,
            "analysis_period": {
                "days": days,
                "end_date": datetime.now().isoformat(),
                "start_date": (datetime.now() - timedelta(days=days)).isoformat(),
            },
            "total_topics": len(topics),
            "total_articles": sum(topic["article_count"] for topic in topics),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving topic statistics: {str(e)}"
        )


@router.get("/keywords/statistics")
async def get_keyword_statistics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    min_frequency: int = Query(3, ge=1, description="Minimum keyword frequency"),
    db: KeywordTopicDatabase = Depends(get_keyword_topic_db),
) -> Dict[str, Any]:
    """
    Get keyword frequency statistics for recent articles.

    Args:
        days: Number of days to look back (1-365)
        min_frequency: Minimum frequency for keywords to be included
        db: Database connection (injected)

    Returns:
        Dict with keyword frequency statistics
    """
    try:
        keywords = await db.get_keyword_statistics(
            days=days, min_frequency=min_frequency
        )

        return {
            "keywords": keywords,
            "analysis_period": {
                "days": days,
                "end_date": datetime.now().isoformat(),
                "start_date": (datetime.now() - timedelta(days=days)).isoformat(),
            },
            "total_keywords": len(keywords),
            "min_frequency": min_frequency,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving keyword statistics: {str(e)}"
        )


@router.get("/search")
async def advanced_search(
    search_term: Optional[str] = Query(
        None, description="Text to search in title and content"
    ),
    topic: Optional[str] = Query(None, description="Filter by topic name"),
    keyword: Optional[str] = Query(None, description="Filter by keyword"),
    min_topic_probability: float = Query(
        0.1, ge=0.0, le=1.0, description="Minimum topic probability"
    ),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of articles to return"
    ),
    offset: int = Query(0, ge=0, description="Number of articles to skip"),
    db: KeywordTopicDatabase = Depends(get_keyword_topic_db),
) -> Dict[str, Any]:
    """
    Advanced search combining content, topics, and keywords.

    This endpoint provides comprehensive search functionality that can filter
    articles by content, topics, and keywords simultaneously.

    Args:
        search_term: Text to search in article title and content
        topic: Filter by topic name (case-insensitive)
        keyword: Filter by keyword (case-insensitive)
        min_topic_probability: Minimum probability for topic matching
        limit: Maximum number of articles to return (1-200)
        offset: Number of articles to skip for pagination
        db: Database connection (injected)

    Returns:
        Dict containing search results with metadata
    """
    try:
        # Validate that at least one search parameter is provided
        if not any([search_term, topic, keyword]):
            raise HTTPException(
                status_code=400,
                detail="At least one search parameter (search_term, topic, or keyword) must be provided",
            )

        results = await db.search_articles_by_content_and_topics(
            search_term=search_term,
            topic_filter=topic,
            keyword_filter=keyword,
            min_topic_probability=min_topic_probability,
            limit=limit,
            offset=offset,
        )

        return results

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error performing advanced search: {str(e)}"
        )


@router.get("/trending")
async def get_trending_topics(
    days: int = Query(7, ge=1, le=30, description="Number of days for trend analysis"),
    min_articles: int = Query(
        5, ge=1, description="Minimum articles for trending topics"
    ),
    db: KeywordTopicDatabase = Depends(get_keyword_topic_db),
) -> Dict[str, Any]:
    """
    Get trending topics based on recent article frequency.

    Args:
        days: Number of days to analyze for trends
        min_articles: Minimum number of articles for a topic to be considered trending
        db: Database connection (injected)

    Returns:
        Dict with trending topics and metadata
    """
    try:
        topics = await db.get_topic_statistics(days=days)

        # Filter topics by minimum article count and sort by frequency
        trending_topics = [
            topic for topic in topics if topic["article_count"] >= min_articles
        ]

        # Sort by article count (frequency) and average probability
        trending_topics.sort(
            key=lambda x: (x["article_count"], x["avg_probability"]), reverse=True
        )

        return {
            "trending_topics": trending_topics[:20],  # Top 20 trending topics
            "analysis_period": {
                "days": days,
                "end_date": datetime.now().isoformat(),
                "start_date": (datetime.now() - timedelta(days=days)).isoformat(),
            },
            "criteria": {
                "min_articles": min_articles,
                "total_topics_found": len(topics),
                "trending_topics_count": len(trending_topics),
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving trending topics: {str(e)}"
        )


@router.get("/keywords/trending")
async def get_trending_keywords(
    days: int = Query(7, ge=1, le=30, description="Number of days for trend analysis"),
    min_frequency: int = Query(
        10, ge=1, description="Minimum frequency for trending keywords"
    ),
    db: KeywordTopicDatabase = Depends(get_keyword_topic_db),
) -> Dict[str, Any]:
    """
    Get trending keywords based on recent frequency and scores.

    Args:
        days: Number of days to analyze for trends
        min_frequency: Minimum frequency for keywords to be considered trending
        db: Database connection (injected)

    Returns:
        Dict with trending keywords and metadata
    """
    try:
        keywords = await db.get_keyword_statistics(
            days=days, min_frequency=min_frequency
        )

        # Sort by frequency and average score
        trending_keywords = sorted(
            keywords, key=lambda x: (x["frequency"], x["avg_score"]), reverse=True
        )[
            :50
        ]  # Top 50 trending keywords

        return {
            "trending_keywords": trending_keywords,
            "analysis_period": {
                "days": days,
                "end_date": datetime.now().isoformat(),
                "start_date": (datetime.now() - timedelta(days=days)).isoformat(),
            },
            "criteria": {
                "min_frequency": min_frequency,
                "total_keywords_found": len(keywords),
                "trending_keywords_count": len(trending_keywords),
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving trending keywords: {str(e)}"
        )
