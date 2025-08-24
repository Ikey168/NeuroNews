"""
Database integration for AI-powered article summaries.

This module handles the storage and retrieval of AI-generated summaries
in Redshift, including schema management, caching, and performance optimization.

Features:
- Redshift schema management for summaries
- Efficient storage and retrieval
- Caching mechanisms
- Batch operations
- Performance monitoring

Author: NeuroNews Development Team
Created: August 2025
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psycopg2

from .ai_summarizer import (
    Summary,
    SummaryLength,
    create_summary_hash,
)

logger = logging.getLogger(__name__)


@dataclass
class SummaryRecord:
    """Database record for a summary."""

    id: Optional[int] = None
    article_id: str = ""
    content_hash: str = ""
    summary_text: str = ""
    summary_length: str = ""
    model_used: str = ""
    confidence_score: float = 0.0
    processing_time: float = 0.0
    word_count: int = 0
    sentence_count: int = 0
    compression_ratio: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SummaryDatabase:
    """
    Database manager for AI-generated article summaries.

    Handles storage, retrieval, and management of summaries in Redshift
    with advanced caching and performance optimization.
    """

    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize the summary database manager.

        Args:
            connection_params: Database connection parameters
        """
        self.connection_params = connection_params
        self.table_name = "article_summaries"

        # Performance metrics
        self.metrics = {
            "queries_executed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_query_time": 0.0,
            "average_query_time": 0.0,
        }

        # Simple in-memory cache
        self._cache: Dict[str, SummaryRecord] = {}
        self._cache_timeout = 3600  # 1 hour
        self._cache_timestamps: Dict[str, datetime] = {}

        logger.info("SummaryDatabase initialized")

    def _get_connection(self):
        """Get database connection."""
        return psycopg2.connect(**self.connection_params)

    def _update_metrics(self, query_time: float, cache_hit: bool = False):
        """Update performance metrics."""
        self.metrics["queries_executed"] += 1
        self.metrics["total_query_time"] += query_time
        self.metrics["average_query_time"] = (
            self.metrics["total_query_time"] / self.metrics["queries_executed"]
        )

        if cache_hit:
            self.metrics["cache_hits"] += 1
        else:
            self.metrics["cache_misses"] += 1

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in self._cache_timestamps:
            return False

        timestamp = self._cache_timestamps[cache_key]
        return datetime.now() - timestamp < timedelta(seconds=self._cache_timeout)

    def _cache_get(self, cache_key: str) -> Optional[SummaryRecord]:
        """Get item from cache if valid."""
        if cache_key in self._cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        # Remove expired entry
        if cache_key in self._cache:
            del self._cache[cache_key]
            del self._cache_timestamps[cache_key]

        return None

    def _cache_set(self, cache_key: str, record: SummaryRecord):
        """Set item in cache."""
        self._cache[cache_key] = record
        self._cache_timestamps[cache_key] = datetime.now()

    async def create_table(self):
        """Create the summaries table if it doesn't exist."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            id BIGINT IDENTITY(1,1) PRIMARY KEY,
            article_id VARCHAR(255) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            summary_text TEXT NOT NULL,
            summary_length VARCHAR(50) NOT NULL,
            model_used VARCHAR(255) NOT NULL,
            confidence_score DECIMAL(5,4),
            processing_time DECIMAL(10,4),
            word_count INTEGER,
            sentence_count INTEGER,
            compression_ratio DECIMAL(5,4),
            created_at TIMESTAMP DEFAULT GETDATE(),
            updated_at TIMESTAMP DEFAULT GETDATE()
        );

        -- Create indexes for performance
        CREATE INDEX IF NOT EXISTS idx_article_summaries_article_id
        ON {self.table_name} (article_id);

        CREATE INDEX IF NOT EXISTS idx_article_summaries_content_hash
        ON {self.table_name} (content_hash);

        CREATE INDEX IF NOT EXISTS idx_article_summaries_length
        ON {self.table_name} (summary_length);

        CREATE INDEX IF NOT EXISTS idx_article_summaries_created_at
        ON {self.table_name} (created_at);
        """

        start_time = time.time()

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(create_sql)
                    conn.commit()

            query_time = time.time() - start_time
            self._update_metrics(query_time)

            logger.info(
                "Table {0} created/verified in {1}s".format(self.table_name, query_time)
            )

        except Exception as e:
            logger.error(
                "Failed to create table {0}: {1}".format(self.table_name, str(e))
            )
            raise

    async def store_summary(
        self, article_id: str, original_text: str, summary: Summary
    ) -> int:
        """
        Store a generated summary in the database.

        Args:
            article_id: Unique identifier for the article
            original_text: Original article text (for hash generation)
            summary: Generated Summary object

        Returns:
            Database ID of the stored summary
        """
        content_hash = create_summary_hash(original_text, summary.length, summary.model)

        # Check if summary already exists
        existing = await self.get_summary_by_hash(content_hash)
        if existing:
            logger.info("Summary already exists for hash {0}".format(content_hash))
            return existing.id

        insert_sql = """
        INSERT INTO {self.table_name} (
            article_id, content_hash, summary_text, summary_length,
            model_used, confidence_score, processing_time, word_count,
            sentence_count, compression_ratio
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """

        start_time = time.time()

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        insert_sql,
                        (
                            article_id,
                            content_hash,
                            summary.text,
                            summary.length.value,
                            summary.model.value,
                            summary.confidence_score,
                            summary.processing_time,
                            summary.word_count,
                            summary.sentence_count,
                            summary.compression_ratio,
                        ),
                    )

                    summary_id = cursor.fetchone()[0]
                    conn.commit()

            query_time = time.time() - start_time
            self._update_metrics(query_time)

            # Cache the record
            record = SummaryRecord(
                id=summary_id,
                article_id=article_id,
                content_hash=content_hash,
                summary_text=summary.text,
                summary_length=summary.length.value,
                model_used=summary.model.value,
                confidence_score=summary.confidence_score,
                processing_time=summary.processing_time,
                word_count=summary.word_count,
                sentence_count=summary.sentence_count,
                compression_ratio=summary.compression_ratio,
                created_at=datetime.now(),
            )

            cache_key = "hash:{0}".format(content_hash)
            self._cache_set(cache_key, record)

            logger.info(
                "Summary stored with ID {0} in {1:.2f}s".format(summary_id, query_time)
            )
            return summary_id

        except Exception as e:
            logger.error("Failed to store summary: {0}".format(str(e)))
            raise

    async def get_summary_by_hash(self, content_hash: str) -> Optional[SummaryRecord]:
        """
        Get a summary by its content hash.

        Args:
            content_hash: Hash of the content and parameters

        Returns:
            SummaryRecord if found, None otherwise
        """
        cache_key = "hash:{0}".format(content_hash)

        # Check cache first
        cached = self._cache_get(cache_key)
        if cached:
            self._update_metrics(0, cache_hit=True)
            return cached

        select_sql = """
        SELECT id, article_id, content_hash, summary_text, summary_length,
               model_used, confidence_score, processing_time, word_count,
               sentence_count, compression_ratio, created_at, updated_at
        FROM {self.table_name}
        WHERE content_hash = %s
        ORDER BY created_at DESC
        LIMIT 1;
        """

        start_time = time.time()

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(select_sql, (content_hash,))
                    row = cursor.fetchone()

            query_time = time.time() - start_time
            self._update_metrics(query_time, cache_hit=False)

            if row:
                record = SummaryRecord(
                    id=row[0],
                    article_id=row[1],
                    content_hash=row[2],
                    summary_text=row[3],
                    summary_length=row[4],
                    model_used=row[5],
                    confidence_score=float(row[6]) if row[6] else 0.0,
                    processing_time=float(row[7]) if row[7] else 0.0,
                    word_count=row[8],
                    sentence_count=row[9],
                    compression_ratio=float(row[10]) if row[10] else 0.0,
                    created_at=row[11],
                    updated_at=row[12],
                )

                # Cache the result
                self._cache_set(cache_key, record)

                return record

            return None

        except Exception as e:
            logger.error(
                "Failed to get summary by hash {0}: {1}".format(content_hash, str(e))
            )
            raise

    async def get_summaries_by_article(self, article_id: str) -> List[SummaryRecord]:
        """
        Get all summaries for an article.

        Args:
            article_id: Unique identifier for the article

        Returns:
            List of SummaryRecord objects
        """
        cache_key = "article:{0}".format(article_id)

        # Check cache first
        cached = self._cache_get(cache_key)
        if cached:
            self._update_metrics(0, cache_hit=True)
            return [cached] if cached else []

        select_sql = """
        SELECT id, article_id, content_hash, summary_text, summary_length,
               model_used, confidence_score, processing_time, word_count,
               sentence_count, compression_ratio, created_at, updated_at
        FROM {self.table_name}
        WHERE article_id = %s
        ORDER BY created_at DESC;
        """

        start_time = time.time()

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(select_sql, (article_id,))
                    rows = cursor.fetchall()

            query_time = time.time() - start_time
            self._update_metrics(query_time, cache_hit=False)

            records = []
            for row in rows:
                record = SummaryRecord(
                    id=row[0],
                    article_id=row[1],
                    content_hash=row[2],
                    summary_text=row[3],
                    summary_length=row[4],
                    model_used=row[5],
                    confidence_score=float(row[6]) if row[6] else 0.0,
                    processing_time=float(row[7]) if row[7] else 0.0,
                    word_count=row[8],
                    sentence_count=row[9],
                    compression_ratio=float(row[10]) if row[10] else 0.0,
                    created_at=row[11],
                    updated_at=row[12],
                )
                records.append(record)

            return records

        except Exception as e:
            logger.error(
                "Failed to get summaries for article {0}: {1}".format(
                    article_id, str(e)
                )
            )
            raise

    async def get_summary_by_article_and_length(
        self, article_id: str, length: SummaryLength
    ) -> Optional[SummaryRecord]:
        """
        Get a specific summary by article ID and length.

        Args:
            article_id: Unique identifier for the article
            length: Desired summary length

        Returns:
            SummaryRecord if found, None otherwise
        """
        cache_key = "article:{0}:length:{1}".format(article_id, length.value)

        # Check cache first
        cached = self._cache_get(cache_key)
        if cached:
            self._update_metrics(0, cache_hit=True)
            return cached

        select_sql = """
        SELECT id, article_id, content_hash, summary_text, summary_length,
               model_used, confidence_score, processing_time, word_count,
               sentence_count, compression_ratio, created_at, updated_at
        FROM {self.table_name}
        WHERE article_id = %s AND summary_length = %s
        ORDER BY created_at DESC
        LIMIT 1;
        """

        start_time = time.time()

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(select_sql, (article_id, length.value))
                    row = cursor.fetchone()

            query_time = time.time() - start_time
            self._update_metrics(query_time, cache_hit=False)

            if row:
                record = SummaryRecord(
                    id=row[0],
                    article_id=row[1],
                    content_hash=row[2],
                    summary_text=row[3],
                    summary_length=row[4],
                    model_used=row[5],
                    confidence_score=float(row[6]) if row[6] else 0.0,
                    processing_time=float(row[7]) if row[7] else 0.0,
                    word_count=row[8],
                    sentence_count=row[9],
                    compression_ratio=float(row[10]) if row[10] else 0.0,
                    created_at=row[11],
                    updated_at=row[12],
                )

                # Cache the result
                self._cache_set(cache_key, record)

                return record

            return None

        except Exception as e:
            logger.error(
                "Failed to get summary for article {0} with length {1}: {2}".format(
                    article_id, length.value, str(e)
                )
            )
            raise

    async def delete_summaries_by_article(self, article_id: str) -> int:
        """
        Delete all summaries for an article.

        Args:
            article_id: Unique identifier for the article

        Returns:
            Number of deleted records
        """
        delete_sql = """
        DELETE FROM {self.table_name}
        WHERE article_id = %s;
        """

        start_time = time.time()

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(delete_sql, (article_id,))
                    deleted_count = cursor.rowcount
                    conn.commit()

            query_time = time.time() - start_time
            self._update_metrics(query_time)

            # Clear cache entries for this article
            keys_to_remove = [
                key
                for key in self._cache.keys()
                if key.startswith("article:{0}".format(article_id))
            ]
            for key in keys_to_remove:
                del self._cache[key]
                if key in self._cache_timestamps:
                    del self._cache_timestamps[key]

            logger.info(
                "Deleted {0} summaries for article {1} in {2:.2f}s".format(
                    deleted_count, article_id, query_time
                )
            )
            return deleted_count

        except Exception as e:
            logger.error(
                "Failed to delete summaries for article {0}: {1}".format(
                    article_id, str(e)
                )
            )
            raise

    async def get_summary_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about stored summaries.

        Returns:
            Dictionary with summary statistics
        """
        stats_sql = """
        SELECT
            COUNT(*) as total_summaries,
            COUNT(DISTINCT article_id) as unique_articles,
            AVG(confidence_score) as avg_confidence,
            AVG(processing_time) as avg_processing_time,
            AVG(word_count) as avg_word_count,
            AVG(compression_ratio) as avg_compression_ratio,
            summary_length,
            COUNT(*) as length_count
        FROM {self.table_name}
        GROUP BY summary_length

        UNION ALL

        SELECT
            COUNT(*) as total_summaries,
            COUNT(DISTINCT article_id) as unique_articles,
            AVG(confidence_score) as avg_confidence,
            AVG(processing_time) as avg_processing_time,
            AVG(word_count) as avg_word_count,
            AVG(compression_ratio) as avg_compression_ratio,
            'total' as summary_length,
            COUNT(*) as length_count
        FROM {self.table_name};
        """

        start_time = time.time()

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(stats_sql)
                    rows = cursor.fetchall()

            query_time = time.time() - start_time
            self._update_metrics(query_time)

            stats = {}
            for row in rows:
                length = row[6]
                stats[length] = {
                    "total_summaries": row[0],
                    "unique_articles": row[1],
                    "avg_confidence": float(row[2]) if row[2] else 0.0,
                    "avg_processing_time": float(row[3]) if row[3] else 0.0,
                    "avg_word_count": float(row[4]) if row[4] else 0.0,
                    "avg_compression_ratio": float(row[5]) if row[5] else 0.0,
                    "count": row[7],
                }

            # Add cache statistics
            stats["cache"] = {
                "cache_size": len(self._cache),
                "cache_hits": self.metrics["cache_hits"],
                "cache_misses": self.metrics["cache_misses"],
                "hit_rate": (
                    self.metrics["cache_hits"]
                    / max(1, self.metrics["cache_hits"] + self.metrics["cache_misses"])
                ),
            }

            return stats

        except Exception as e:
            logger.error("Failed to get summary statistics: {0}".format(str(e)))
            raise

    def clear_cache(self):
        """Clear the in-memory cache."""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Summary database cache cleared")

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get database performance metrics."""
        return self.metrics.copy()


# Utility functions for database setup
def get_snowflake_connection_params() -> Dict[str, Any]:
    """
    Get Snowflake connection parameters from environment variables.

    Returns:
        Dictionary with connection parameters
    """
    import os

    return {
        "account": os.getenv("SNOWFLAKE_ACCOUNT", "test-account"),
        "user": os.getenv("SNOWFLAKE_USER", "admin"),
        "password": os.getenv("SNOWFLAKE_PASSWORD", "password"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "ANALYTICS_WH"),
        "database": os.getenv("SNOWFLAKE_DATABASE", "NEURONEWS"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
    }


async def setup_summary_database():
    """Set up the summary database with proper schema."""
    connection_params = get_snowflake_connection_params()
    db = SummaryDatabase(connection_params)
    await db.create_table()
    return db
