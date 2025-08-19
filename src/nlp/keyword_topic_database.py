"""
Database integration for keyword extraction and topic modeling (Issue #29).

This module handles storing extracted keywords and topics in AWS Redshift
and provides querying capabilities for topic-based search functionality.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.database.redshift_loader import ArticleRecord, RedshiftLoader
from src.nlp.keyword_topic_extractor import (ExtractionResult, KeywordResult,
                                             TopicResult)

logger = logging.getLogger(__name__)


class KeywordTopicDatabase:
    """Database operations for keyword and topic data."""

    def __init__(self, redshift_loader: Optional[RedshiftLoader] = None):
        """Initialize with Redshift connection."""
        self.db = redshift_loader

    async def store_extraction_results(
        self, results: List[ExtractionResult]
    ) -> Dict[str, Any]:
        """Store keyword and topic extraction results in database."""
        if not self.db:
            raise ValueError("Database connection not initialized")

        success_count = 0
        error_count = 0
        errors = []

        for result in results:
            try:
                await self._store_single_result(result)
                success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"Article {result.article_id}: {str(e)}")
                logger.error(
                    f"Error storing extraction result for {result.article_id}: {e}"
                )

        return {
            "success_count": success_count,
            "error_count": error_count,
            "total_processed": len(results),
            "errors": errors[:10],  # Limit error details
        }

    async def _store_single_result(self, result: ExtractionResult) -> None:
        """Store a single extraction result."""
        # Prepare keywords data as JSON
        keywords_data = [
            {"keyword": kw.keyword, "score": kw.score, "method": kw.method}
            for kw in result.keywords
        ]

        # Prepare topics data as JSON
        topics_data = []
        for topic in result.topics:
            topics_data.append(
                {
                    "topic_id": topic.topic_id,
                    "topic_name": topic.topic_name,
                    "topic_words": topic.topic_words,
                    "probability": topic.probability,
                    "coherence_score": topic.coherence_score,
                }
            )

        # Prepare dominant topic data
        dominant_topic_data = None
        if result.dominant_topic:
            dominant_topic_data = {
                "topic_id": result.dominant_topic.topic_id,
                "topic_name": result.dominant_topic.topic_name,
                "topic_words": result.dominant_topic.topic_words,
                "probability": result.dominant_topic.probability,
                "coherence_score": result.dominant_topic.coherence_score,
            }

        # Update the article record with keyword and topic data
        update_query = """
            UPDATE news_articles 
            SET 
                keywords = %s,
                topics = %s,
                dominant_topic = %s,
                extraction_method = %s,
                extraction_processed_at = %s,
                extraction_processing_time = %s
            WHERE id = %s
        """

        params = [
            json.dumps(keywords_data),
            json.dumps(topics_data),
            json.dumps(dominant_topic_data) if dominant_topic_data else None,
            result.extraction_method,
            result.processed_at,
            result.processing_time,
            result.article_id,
        ]

        await self.db.execute_query(update_query, params)

    async def get_articles_by_topic(
        self,
        topic_name: str,
        min_probability: float = 0.2,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get articles that match a specific topic."""
        if not self.db:
            raise ValueError("Database connection not initialized")

        # Query for articles with the specified topic
        query = """
            SELECT 
                id, url, title, source, published_date,
                keywords, topics, dominant_topic,
                extraction_method, extraction_processed_at
            FROM news_articles
            WHERE topics IS NOT NULL
                AND JSON_EXTRACT_PATH_TEXT(dominant_topic, 'topic_name') ILIKE %s
                AND CAST(JSON_EXTRACT_PATH_TEXT(dominant_topic, 'probability') AS FLOAT) >= %s
            ORDER BY published_date DESC
            LIMIT %s OFFSET %s
        """

        params = [f"%{topic_name}%", min_probability, limit, offset]
        results = await self.db.execute_query(query, params)

        articles = []
        for row in results:
            article = {
                "id": row[0],
                "url": row[1],
                "title": row[2],
                "source": row[3],
                "published_date": row[4].isoformat() if row[4] else None,
                "keywords": json.loads(row[5]) if row[5] else [],
                "topics": json.loads(row[6]) if row[6] else [],
                "dominant_topic": json.loads(row[7]) if row[7] else None,
                "extraction_method": row[8],
                "extraction_processed_at": row[9].isoformat() if row[9] else None,
            }
            articles.append(article)

        return articles

    async def get_articles_by_keyword(
        self, keyword: str, min_score: float = 0.1, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get articles that contain a specific keyword."""
        if not self.db:
            raise ValueError("Database connection not initialized")

        # Query for articles with the specified keyword
        query = """
            SELECT 
                id, url, title, source, published_date,
                keywords, topics, dominant_topic,
                extraction_method, extraction_processed_at
            FROM news_articles
            WHERE keywords IS NOT NULL
                AND JSON_EXTRACT_PATH_TEXT(keywords, '$[*].keyword') ILIKE %s
            ORDER BY published_date DESC
            LIMIT %s OFFSET %s
        """

        params = [f"%{keyword}%", limit, offset]
        results = await self.db.execute_query(query, params)

        articles = []
        for row in results:
            # Filter keywords to only include matches above threshold
            keywords = json.loads(row[5]) if row[5] else []
            filtered_keywords = [
                kw
                for kw in keywords
                if keyword.lower() in kw.get("keyword", "").lower()
                and kw.get("score", 0) >= min_score
            ]

            if (
                filtered_keywords
            ):  # Only include if keyword matches with sufficient score
                article = {
                    "id": row[0],
                    "url": row[1],
                    "title": row[2],
                    "source": row[3],
                    "published_date": row[4].isoformat() if row[4] else None,
                    "keywords": keywords,
                    "matched_keywords": filtered_keywords,
                    "topics": json.loads(row[6]) if row[6] else [],
                    "dominant_topic": json.loads(row[7]) if row[7] else None,
                    "extraction_method": row[8],
                    "extraction_processed_at": row[9].isoformat() if row[9] else None,
                }
                articles.append(article)

        return articles

    async def get_topic_statistics(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get topic distribution statistics for recent articles."""
        if not self.db:
            raise ValueError("Database connection not initialized")

        query = """
            SELECT 
                JSON_EXTRACT_PATH_TEXT(dominant_topic, 'topic_name') as topic_name,
                COUNT(*) as article_count,
                AVG(CAST(JSON_EXTRACT_PATH_TEXT(dominant_topic, 'probability') AS FLOAT)) as avg_probability,
                MIN(published_date) as earliest_article,
                MAX(published_date) as latest_article
            FROM news_articles
            WHERE dominant_topic IS NOT NULL
                AND published_date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY JSON_EXTRACT_PATH_TEXT(dominant_topic, 'topic_name')
            HAVING COUNT(*) >= 2
            ORDER BY article_count DESC
        """

        results = await self.db.execute_query(query, [days])

        topics = []
        for row in results:
            topic = {
                "topic_name": row[0],
                "article_count": int(row[1]),
                "avg_probability": float(row[2]) if row[2] else 0.0,
                "earliest_article": row[3].isoformat() if row[3] else None,
                "latest_article": row[4].isoformat() if row[4] else None,
                "percentage": 0.0,  # Will be calculated after getting total
            }
            topics.append(topic)

        # Calculate percentages
        total_articles = sum(topic["article_count"] for topic in topics)
        for topic in topics:
            topic["percentage"] = (
                (topic["article_count"] / total_articles * 100)
                if total_articles > 0
                else 0.0
            )

        return topics

    async def get_keyword_statistics(
        self, days: int = 30, min_frequency: int = 3
    ) -> List[Dict[str, Any]]:
        """Get keyword frequency statistics for recent articles."""
        if not self.db:
            raise ValueError("Database connection not initialized")

        # This is a complex query to extract and aggregate keywords from JSON
        query = """
            WITH keyword_counts AS (
                SELECT 
                    JSON_EXTRACT_PATH_TEXT(keyword_obj.value, 'keyword') as keyword,
                    CAST(JSON_EXTRACT_PATH_TEXT(keyword_obj.value, 'score') AS FLOAT) as score
                FROM news_articles
                CROSS JOIN JSON_ARRAY_ELEMENTS(CASE WHEN keywords IS NULL THEN '[]'::json ELSE keywords END) as keyword_obj(value)
                WHERE keywords IS NOT NULL
                    AND published_date >= CURRENT_DATE - INTERVAL '%s days'
                    AND JSON_EXTRACT_PATH_TEXT(keyword_obj.value, 'keyword') IS NOT NULL
            )
            SELECT 
                keyword,
                COUNT(*) as frequency,
                AVG(score) as avg_score,
                MIN(score) as min_score,
                MAX(score) as max_score
            FROM keyword_counts
            WHERE keyword IS NOT NULL AND keyword != ''
            GROUP BY keyword
            HAVING COUNT(*) >= %s
            ORDER BY frequency DESC, avg_score DESC
            LIMIT 100
        """

        results = await self.db.execute_query(query, [days, min_frequency])

        keywords = []
        for row in results:
            keyword = {
                "keyword": row[0],
                "frequency": int(row[1]),
                "avg_score": float(row[2]) if row[2] else 0.0,
                "min_score": float(row[3]) if row[3] else 0.0,
                "max_score": float(row[4]) if row[4] else 0.0,
            }
            keywords.append(keyword)

        return keywords

    async def search_articles_by_content_and_topics(
        self,
        search_term: str,
        topic_filter: Optional[str] = None,
        keyword_filter: Optional[str] = None,
        min_topic_probability: float = 0.1,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Advanced search combining content, topics, and keywords."""
        if not self.db:
            raise ValueError("Database connection not initialized")

        # Build dynamic query based on filters
        conditions = []
        params = []

        # Content search
        if search_term:
            conditions.append("(title ILIKE %s OR content ILIKE %s)")
            search_pattern = f"%{search_term}%"
            params.extend([search_pattern, search_pattern])

        # Topic filter
        if topic_filter:
            conditions.append(
                "JSON_EXTRACT_PATH_TEXT(dominant_topic, 'topic_name') ILIKE %s"
            )
            conditions.append(
                "CAST(JSON_EXTRACT_PATH_TEXT(dominant_topic, 'probability') AS FLOAT) >= %s"
            )
            params.extend([f"%{topic_filter}%", min_topic_probability])

        # Keyword filter
        if keyword_filter:
            conditions.append(
                "JSON_EXTRACT_PATH_TEXT(keywords, '$[*].keyword') ILIKE %s"
            )
            params.append(f"%{keyword_filter}%")

        # Base query
        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Count query
        count_query = f"""
            SELECT COUNT(*) 
            FROM news_articles
            WHERE {where_clause}
        """

        count_results = await self.db.execute_query(count_query, params)
        total_count = count_results[0][0] if count_results else 0

        # Main query
        main_query = f"""
            SELECT 
                id, url, title, content, source, published_date,
                keywords, topics, dominant_topic,
                extraction_method, extraction_processed_at,
                validation_score, content_quality
            FROM news_articles
            WHERE {where_clause}
            ORDER BY published_date DESC
            LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])
        results = await self.db.execute_query(main_query, params)

        articles = []
        for row in results:
            article = {
                "id": row[0],
                "url": row[1],
                "title": row[2],
                "content": (
                    row[3][:500] + "..." if len(row[3]) > 500 else row[3]
                ),  # Truncate content
                "source": row[4],
                "published_date": row[5].isoformat() if row[5] else None,
                "keywords": json.loads(row[6]) if row[6] else [],
                "topics": json.loads(row[7]) if row[7] else [],
                "dominant_topic": json.loads(row[8]) if row[8] else None,
                "extraction_method": row[9],
                "extraction_processed_at": row[10].isoformat() if row[10] else None,
                "validation_score": float(row[11]) if row[11] else None,
                "content_quality": row[12],
            }
            articles.append(article)

        return {
            "articles": articles,
            "total_count": total_count,
            "returned_count": len(articles),
            "has_more": (offset + len(articles)) < total_count,
            "search_params": {
                "search_term": search_term,
                "topic_filter": topic_filter,
                "keyword_filter": keyword_filter,
                "limit": limit,
                "offset": offset,
            },
        }


async def create_keyword_topic_db(
    redshift_config: Optional[Dict[str, str]] = None,
) -> KeywordTopicDatabase:
    """Factory function to create keyword topic database connection."""
    if not redshift_config:
        redshift_config = {
            "host": os.getenv("REDSHIFT_HOST"),
            "database": os.getenv("REDSHIFT_DB", "dev"),
            "user": os.getenv("REDSHIFT_USER", "admin"),
            "password": os.getenv("REDSHIFT_PASSWORD"),
        }

    # Validate required config
    if not redshift_config.get("host"):
        raise ValueError("REDSHIFT_HOST is required")

    db = RedshiftLoader(**redshift_config)
    await db.connect()

    return KeywordTopicDatabase(db)
