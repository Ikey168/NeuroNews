"""
Snowflake ETL Processor for NeuroNews Pipeline (Issue #242)

This module implements an ETL process to store processed articles in Snowflake
using the snowflake-connector-python library. Adapts the existing Redshift
batch loading logic to use Snowflake's COPY INTO command for optimal performance.

Key Features:
- Native Snowflake connector with optimal performance
- COPY INTO command for efficient bulk loading
- VARIANT field support for JSON data
- Batch processing with error handling
- Schema management and initialization
- Connection pooling and transaction management
"""

import hashlib
import json
import logging
import os
import tempfile
import csv
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path

import snowflake.connector
from snowflake.connector import DictCursor
from snowflake.connector.pandas_tools import write_pandas
import pandas as pd

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class SnowflakeArticleRecord:
    """Structured representation of an article for Snowflake storage."""

    id: str
    url: str
    title: str
    content: str
    source: str
    published_date: Optional[datetime] = None
    scraped_at: datetime = None
    validation_score: Optional[float] = None
    content_quality: Optional[str] = None
    source_credibility: Optional[str] = None
    validation_flags: Optional[List[str]] = None
    validated_at: Optional[datetime] = None
    word_count: Optional[int] = None
    content_length: Optional[int] = None
    author: Optional[str] = None
    category: Optional[str] = None
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    entities: Optional[List[Dict]] = None
    keywords: Optional[List[Dict]] = None
    topics: Optional[List[Dict]] = None
    dominant_topic: Optional[Dict] = None
    extraction_method: Optional[str] = None
    extraction_processed_at: Optional[datetime] = None
    extraction_processing_time: Optional[float] = None

    def __post_init__(self):
        """Set default values after initialization."""
        if self.scraped_at is None:
            self.scraped_at = datetime.now(timezone.utc)

        # Generate ID if not provided
        if not self.id:
            self.id = self._generate_id()

        # Calculate metrics if not provided
        if self.word_count is None and self.content:
            self.word_count = len(self.content.split())

        if self.content_length is None and self.content:
            self.content_length = len(self.content)

    def _generate_id(self) -> str:
        """Generate a unique ID for the article based on URL and content."""
        content_hash = hashlib.md5(
            f"{self.url}{self.title}".encode()
        ).hexdigest()
        return f"article_{content_hash[:16]}"

    @classmethod
    def from_validated_article(cls, validated_data: Dict[str, Any]) -> "SnowflakeArticleRecord":
        """Create SnowflakeArticleRecord from data validation pipeline output."""
        # Parse validation flags from JSON if needed
        validation_flags = validated_data.get("validation_flags", [])
        if isinstance(validation_flags, str):
            try:
                validation_flags = json.loads(validation_flags)
            except json.JSONDecodeError:
                validation_flags = []

        # Parse datetime fields
        published_date = None
        if validated_data.get("published_date"):
            published_date = cls._parse_datetime(validated_data["published_date"])

        validated_at = None
        if validated_data.get("validated_at"):
            validated_at = cls._parse_datetime(validated_data["validated_at"])

        scraped_at = None
        if validated_data.get("scraped_at"):
            scraped_at = cls._parse_datetime(validated_data["scraped_at"])

        extraction_processed_at = None
        if validated_data.get("extraction_processed_at"):
            extraction_processed_at = cls._parse_datetime(validated_data["extraction_processed_at"])

        return cls(
            id=validated_data.get("id", ""),
            url=validated_data.get("url", ""),
            title=validated_data.get("title", ""),
            content=validated_data.get("content", ""),
            source=validated_data.get("source", ""),
            published_date=published_date,
            scraped_at=scraped_at,
            validation_score=validated_data.get("validation_score"),
            content_quality=validated_data.get("content_quality"),
            source_credibility=validated_data.get("source_credibility"),
            validation_flags=validation_flags,
            validated_at=validated_at,
            word_count=validated_data.get("word_count"),
            content_length=validated_data.get("content_length"),
            author=validated_data.get("author"),
            category=validated_data.get("category"),
            sentiment_score=validated_data.get("sentiment_score"),
            sentiment_label=validated_data.get("sentiment_label"),
            entities=validated_data.get("entities"),
            keywords=validated_data.get("keywords"),
            topics=validated_data.get("topics"),
            dominant_topic=validated_data.get("dominant_topic"),
            extraction_method=validated_data.get("extraction_method"),
            extraction_processed_at=extraction_processed_at,
            extraction_processing_time=validated_data.get("extraction_processing_time"),
        )

    @staticmethod
    def _parse_datetime(date_str: Union[str, datetime]) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if isinstance(date_str, datetime):
            return date_str

        if not date_str:
            return None

        # Try multiple datetime formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        logger.warning(f"Could not parse datetime: {date_str}")
        return None

    def to_snowflake_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary suitable for Snowflake insertion."""
        data = asdict(self)
        
        # Convert datetime objects to strings for JSON serialization
        for field in ['published_date', 'scraped_at', 'validated_at', 'extraction_processed_at']:
            if data[field]:
                data[field] = data[field].isoformat()
        
        # Ensure JSON fields are properly serialized
        json_fields = ['validation_flags', 'entities', 'keywords', 'topics', 'dominant_topic']
        for field in json_fields:
            if data[field] is not None:
                data[field] = json.dumps(data[field])
        
        return data


class SnowflakeETLProcessor:
    """Snowflake ETL processor for NeuroNews articles."""

    def __init__(
        self,
        account: str,
        user: str,
        password: Optional[str] = None,
        warehouse: str = "COMPUTE_WH",
        database: str = "NEURONEWS",
        schema: str = "PUBLIC",
        batch_size: int = 1000,
        role: Optional[str] = None,
    ):
        """
        Initialize SnowflakeETLProcessor.

        Args:
            account: Snowflake account identifier
            user: Username for authentication
            password: Password for authentication
            warehouse: Warehouse name
            database: Database name
            schema: Schema name
            batch_size: Number of records to process in each batch
            role: Role to use for connection
        """
        self._account = account
        self._user = user
        self._password = password or os.environ.get("SNOWFLAKE_PASSWORD")
        self._warehouse = warehouse
        self._database = database
        self._schema = schema
        self._role = role
        self._batch_size = batch_size

        if not self._password:
            raise ValueError(
                "Password must be provided or set in SNOWFLAKE_PASSWORD env var"
            )

        self._conn = None
        self._cursor = None

    def connect(self) -> None:
        """Establish connection to Snowflake."""
        if self._conn is None:
            try:
                conn_params = {
                    'account': self._account,
                    'user': self._user,
                    'password': self._password,
                    'warehouse': self._warehouse,
                    'database': self._database,
                    'schema': self._schema,
                }
                
                if self._role:
                    conn_params['role'] = self._role

                self._conn = snowflake.connector.connect(**conn_params)
                self._cursor = self._conn.cursor(DictCursor)
                
                logger.info(f"Connected to Snowflake account: {self._account}")
                logger.info(f"Using warehouse: {self._warehouse}, database: {self._database}, schema: {self._schema}")
                
            except Exception as e:
                logger.error(f"Failed to connect to Snowflake: {e}")
                raise

    def close(self) -> None:
        """Close database connection."""
        if self._cursor:
            self._cursor.close()
        if self._conn:
            self._conn.close()
            self._conn = None
            self._cursor = None
            logger.info("Disconnected from Snowflake")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type:
            self.rollback()
        self.close()

    def execute_query(self, query: str, params: Optional[List] = None) -> List:
        """Execute a query and return results."""
        try:
            if params:
                self._cursor.execute(query, params)
            else:
                self._cursor.execute(query)
                
            if self._cursor.description:  # SELECT query
                return self._cursor.fetchall()
            return []
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            if self._conn:
                self._conn.rollback()
            raise

    def commit(self) -> None:
        """Commit current transaction."""
        if self._conn:
            self._conn.commit()

    def rollback(self) -> None:
        """Rollback current transaction."""
        if self._conn:
            self._conn.rollback()

    def initialize_schema(self, schema_file: Optional[str] = None) -> None:
        """Initialize or update the Snowflake schema."""
        if schema_file is None:
            schema_file = os.path.join(os.path.dirname(__file__), "snowflake_schema.sql")

        try:
            with open(schema_file, "r") as f:
                schema_sql = f.read()

            # Execute schema statements
            statements = [
                stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()
            ]

            for statement in statements:
                if statement and not statement.lower().startswith('--'):
                    logger.debug(f"Executing schema statement: {statement[:100]}...")
                    self._cursor.execute(statement)

            self.commit()
            logger.info("Snowflake schema initialized successfully")

        except Exception as e:
            logger.error(f"Schema initialization failed: {e}")
            self.rollback()
            raise

    def load_single_article(
        self, article: Union[Dict[str, Any], SnowflakeArticleRecord]
    ) -> bool:
        """
        Load a single article into Snowflake.

        Args:
            article: Article data (dict or SnowflakeArticleRecord)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to SnowflakeArticleRecord if needed
            if isinstance(article, dict):
                record = SnowflakeArticleRecord.from_validated_article(article)
            else:
                record = article

            # Check if article already exists
            if self._article_exists(record.id):
                logger.debug(f"Article {record.id} already exists, skipping")
                return False

            # Insert article using MERGE for upsert behavior
            data = record.to_snowflake_dict()
            
            merge_query = """
            MERGE INTO news_articles AS target
            USING (SELECT 
                %(id)s as id, %(url)s as url, %(title)s as title, %(content)s as content,
                %(source)s as source, %(published_date)s::TIMESTAMP_NTZ as published_date,
                %(scraped_at)s::TIMESTAMP_NTZ as scraped_at, %(validation_score)s as validation_score,
                %(content_quality)s as content_quality, %(source_credibility)s as source_credibility,
                PARSE_JSON(%(validation_flags)s) as validation_flags,
                %(validated_at)s::TIMESTAMP_NTZ as validated_at, %(word_count)s as word_count,
                %(content_length)s as content_length, %(author)s as author, %(category)s as category,
                %(sentiment_score)s as sentiment_score, %(sentiment_label)s as sentiment_label,
                PARSE_JSON(%(entities)s) as entities, PARSE_JSON(%(keywords)s) as keywords,
                PARSE_JSON(%(topics)s) as topics, PARSE_JSON(%(dominant_topic)s) as dominant_topic,
                %(extraction_method)s as extraction_method,
                %(extraction_processed_at)s::TIMESTAMP_NTZ as extraction_processed_at,
                %(extraction_processing_time)s as extraction_processing_time
            ) AS source
            ON target.id = source.id
            WHEN NOT MATCHED THEN
                INSERT (id, url, title, content, source, published_date, scraped_at,
                       validation_score, content_quality, source_credibility, validation_flags,
                       validated_at, word_count, content_length, author, category,
                       sentiment_score, sentiment_label, entities, keywords, topics, dominant_topic,
                       extraction_method, extraction_processed_at, extraction_processing_time)
                VALUES (source.id, source.url, source.title, source.content, source.source,
                       source.published_date, source.scraped_at, source.validation_score,
                       source.content_quality, source.source_credibility, source.validation_flags,
                       source.validated_at, source.word_count, source.content_length, source.author,
                       source.category, source.sentiment_score, source.sentiment_label, source.entities,
                       source.keywords, source.topics, source.dominant_topic, source.extraction_method,
                       source.extraction_processed_at, source.extraction_processing_time)
            """

            self._cursor.execute(merge_query, data)
            self.commit()
            
            logger.debug(f"Successfully loaded article: {record.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to load article {record.id if isinstance(record, SnowflakeArticleRecord) else 'unknown'}: {e}")
            self.rollback()
            return False

    def load_articles_batch(
        self,
        articles: List[Union[Dict[str, Any], SnowflakeArticleRecord]],
        use_copy_into: bool = True,
        skip_duplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Load multiple articles in batches using COPY INTO for optimal performance.

        Args:
            articles: List of article data (dicts or SnowflakeArticleRecords)
            use_copy_into: Whether to use COPY INTO command (recommended for large batches)
            skip_duplicates: Whether to skip articles that already exist

        Returns:
            Dictionary with loading statistics
        """
        if not articles:
            return {
                "total_articles": 0,
                "loaded_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "success_rate": 100.0,
                "processing_time_seconds": 0,
                "articles_per_second": 0,
                "errors": [],
            }

        start_time = datetime.now()
        total_articles = len(articles)
        loaded_count = failed_count = skipped_count = 0
        errors = []

        try:
            logger.info(f"Starting batch load of {total_articles} articles")

            # Process articles in chunks
            for i in range(0, total_articles, self._batch_size):
                batch = articles[i : i + self._batch_size]
                logger.info(f"Processing batch {i // self._batch_size + 1}: {len(batch)} articles")

                try:
                    if use_copy_into and len(batch) > 10:  # Use COPY INTO for larger batches
                        batch_stats = self._process_batch_copy_into(batch, skip_duplicates)
                    else:
                        batch_stats = self._process_batch_individual(batch, skip_duplicates)

                    loaded_count += batch_stats["loaded"]
                    failed_count += batch_stats["failed"] 
                    skipped_count += batch_stats["skipped"]
                    errors.extend(batch_stats.get("errors", []))

                except Exception as e:
                    logger.error(f"Batch processing failed: {e}")
                    failed_count += len(batch)
                    errors.append(f"Batch {i // self._batch_size + 1} failed: {str(e)}")

            processing_time = (datetime.now() - start_time).total_seconds()

            stats = {
                "total_articles": total_articles,
                "loaded_count": loaded_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "success_rate": (
                    (loaded_count / total_articles * 100) if total_articles > 0 else 0
                ),
                "processing_time_seconds": processing_time,
                "articles_per_second": (
                    total_articles / processing_time if processing_time > 0 else 0
                ),
                "errors": errors[:10],  # Limit to first 10 errors
            }

            logger.info(
                f"Batch load completed: {loaded_count}/{total_articles} articles loaded "
                f"({stats['success_rate']:.1f}% success rate)"
            )

            return stats

        except Exception as e:
            logger.error(f"Batch load failed: {e}")
            self.rollback()
            raise

    def _process_batch_copy_into(
        self, batch: List[Union[Dict[str, Any], SnowflakeArticleRecord]], skip_duplicates: bool
    ) -> Dict[str, int]:
        """Process batch using Snowflake's COPY INTO command for optimal performance."""
        loaded = failed = skipped = 0
        errors = []

        try:
            # Convert all articles to records
            records = []
            for article in batch:
                try:
                    if isinstance(article, dict):
                        record = SnowflakeArticleRecord.from_validated_article(article)
                    else:
                        record = article
                    records.append(record)
                except Exception as e:
                    failed += 1
                    errors.append(f"Failed to convert article: {e}")

            if not records:
                return {"loaded": 0, "failed": failed, "skipped": 0, "errors": errors}

            # Create temporary CSV file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as tmp_file:
                tmp_path = tmp_file.name
                writer = csv.writer(tmp_file, quoting=csv.QUOTE_ALL)
                
                # Write header
                headers = [
                    'id', 'url', 'title', 'content', 'source', 'published_date', 'scraped_at',
                    'validation_score', 'content_quality', 'source_credibility', 'validation_flags',
                    'validated_at', 'word_count', 'content_length', 'author', 'category',
                    'sentiment_score', 'sentiment_label', 'entities', 'keywords', 'topics',
                    'dominant_topic', 'extraction_method', 'extraction_processed_at', 'extraction_processing_time'
                ]
                writer.writerow(headers)
                
                # Write data
                for record in records:
                    data = record.to_snowflake_dict()
                    row = [data.get(field, '') for field in headers]
                    writer.writerow(row)

            try:
                # Upload file to Snowflake internal stage
                stage_name = f"@~/news_articles_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                
                self._cursor.execute(f"PUT file://{tmp_path} {stage_name}")
                
                # Use COPY INTO with staging table for duplicate handling
                if skip_duplicates:
                    # Clear staging table
                    self._cursor.execute("TRUNCATE news_articles_staging")
                    
                    # Copy into staging table
                    copy_query = f"""
                    COPY INTO news_articles_staging
                    FROM {stage_name}
                    FILE_FORMAT = (TYPE = 'CSV' FIELD_OPTIONALLY_ENCLOSED_BY = '"' SKIP_HEADER = 1)
                    ON_ERROR = 'CONTINUE'
                    """
                    
                    result = self._cursor.execute(copy_query)
                    copy_result = self._cursor.fetchall()
                    
                    # Move from staging to main table (excluding duplicates)
                    merge_query = """
                    MERGE INTO news_articles AS target
                    USING news_articles_staging AS source
                    ON target.id = source.id
                    WHEN NOT MATCHED THEN
                        INSERT (id, url, title, content, source, published_date, scraped_at,
                               validation_score, content_quality, source_credibility, validation_flags,
                               validated_at, word_count, content_length, author, category,
                               sentiment_score, sentiment_label, entities, keywords, topics, dominant_topic,
                               extraction_method, extraction_processed_at, extraction_processing_time)
                        VALUES (source.id, source.url, source.title, source.content, source.source,
                               source.published_date, source.scraped_at, source.validation_score,
                               source.content_quality, source.source_credibility, source.validation_flags,
                               source.validated_at, source.word_count, source.content_length, source.author,
                               source.category, source.sentiment_score, source.sentiment_label, source.entities,
                               source.keywords, source.topics, source.dominant_topic, source.extraction_method,
                               source.extraction_processed_at, source.extraction_processing_time)
                    """
                    
                    self._cursor.execute(merge_query)
                    loaded = self._cursor.rowcount
                    skipped = len(records) - loaded
                    
                else:
                    # Direct copy into main table
                    copy_query = f"""
                    COPY INTO news_articles
                    FROM {stage_name}
                    FILE_FORMAT = (TYPE = 'CSV' FIELD_OPTIONALLY_ENCLOSED_BY = '"' SKIP_HEADER = 1)
                    ON_ERROR = 'CONTINUE'
                    """
                    
                    result = self._cursor.execute(copy_query)
                    copy_result = self._cursor.fetchall()
                    loaded = len([r for r in copy_result if r[1] == 'LOADED'])
                    failed += len([r for r in copy_result if r[1] != 'LOADED'])

                # Clean up stage file
                self._cursor.execute(f"REMOVE {stage_name}")
                
                self.commit()

            finally:
                # Clean up temporary file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            return {
                "loaded": loaded,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
            }

        except Exception as e:
            logger.error(f"COPY INTO batch processing failed: {e}")
            self.rollback()
            return {"loaded": 0, "failed": len(batch), "skipped": 0, "errors": [str(e)]}

    def _process_batch_individual(
        self, batch: List[Union[Dict[str, Any], SnowflakeArticleRecord]], skip_duplicates: bool
    ) -> Dict[str, int]:
        """Process batch by inserting articles individually."""
        loaded = failed = skipped = 0
        errors = []

        for article in batch:
            try:
                if self.load_single_article(article):
                    loaded += 1
                else:
                    skipped += 1 if skip_duplicates else (failed := failed + 1)
            except Exception as e:
                failed += 1
                errors.append(str(e))

        return {
            "loaded": loaded,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
        }

    def _article_exists(self, article_id: str) -> bool:
        """Check if article already exists in database."""
        query = "SELECT 1 FROM news_articles WHERE id = ? LIMIT 1"
        result = self.execute_query(query, [article_id])
        return len(result) > 0

    def get_article_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about stored articles."""
        stats_queries = {
            "total_articles": "SELECT COUNT(*) FROM news_articles",
            "by_source_credibility": """
                SELECT source_credibility, COUNT(*) as count
                FROM news_articles
                GROUP BY source_credibility
                ORDER BY count DESC
            """,
            "by_content_quality": """
                SELECT content_quality, COUNT(*) as count
                FROM news_articles
                GROUP BY content_quality
                ORDER BY count DESC
            """,
            "avg_validation_score": """
                SELECT AVG(validation_score) as avg_score,
                       MIN(validation_score) as min_score,
                       MAX(validation_score) as max_score
                FROM news_articles
                WHERE validation_score IS NOT NULL
            """,
            "recent_articles": """
                SELECT COUNT(*) as recent_count
                FROM news_articles
                WHERE scraped_at >= DATEADD(day, -7, CURRENT_DATE())
            """,
            "top_sources": """
                SELECT source, COUNT(*) as count
                FROM news_articles
                GROUP BY source
                ORDER BY count DESC
                LIMIT 10
            """,
        }

        stats = {}

        for stat_name, query in stats_queries.items():
            try:
                result = self.execute_query(query)
                if stat_name == "total_articles":
                    stats[stat_name] = result[0][0] if result else 0
                elif stat_name in ["avg_validation_score", "recent_articles"]:
                    stats[stat_name] = dict(result[0]) if result else {}
                else:
                    stats[stat_name] = [dict(row) for row in result]
            except Exception as e:
                logger.error(f"Failed to get {stat_name}: {e}")
                stats[stat_name] = None

        return stats

    def get_articles_paginated(
        self,
        page: int = 1,
        per_page: int = 50,
        min_score: Optional[float] = None,
        sentiment: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Tuple[List[Dict], Dict]:
        """
        Get paginated articles with optional filtering.

        Args:
            page: Page number (1-based)
            per_page: Articles per page (1-100)
            min_score: Minimum sentiment score filter
            sentiment: Sentiment label filter ('positive', 'negative', 'neutral')
            category: Category filter

        Returns:
            Tuple containing:
            1. List of article dictionaries
            2. Pagination metadata dictionary
        """
        if page < 1:
            raise ValueError("Page number must be >= 1")
        if per_page < 1 or per_page > 100:
            raise ValueError("Items per page must be between 1 and 100")

        conditions = []
        params = []

        if min_score is not None:
            conditions.append("sentiment_score >= ?")
            params.append(min_score)

        if sentiment:
            conditions.append("sentiment_label = ?")
            params.append(sentiment.upper())

        if category:
            conditions.append("category = ?")
            params.append(category)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        count_query = f"SELECT COUNT(*) FROM news_articles WHERE {where_clause}"
        result = self.execute_query(count_query, params)
        total = result[0][0]

        # Calculate pagination
        offset = (page - 1) * per_page
        pages = (total + per_page - 1) // per_page  # Ceiling division

        # Get paginated results
        query = f"""
            SELECT id, title, url, published_date, category, source,
                   sentiment_score, sentiment_label
            FROM news_articles
            WHERE {where_clause}
            ORDER BY published_date DESC
            LIMIT ? OFFSET ?
        """
        params.extend([per_page, offset])

        results = self.execute_query(query, params)

        articles = []
        for row in results:
            articles.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "url": row[2],
                    "published_date": row[3].isoformat() if row[3] else None,
                    "category": row[4],
                    "source": row[5],
                    "sentiment": {
                        "score": float(row[6]) if row[6] else None,
                        "label": row[7],
                    },
                }
            )

        pagination = {
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

        return articles, pagination

    def delete_article(self, article_id: str) -> bool:
        """Delete an article from Snowflake."""
        query = "DELETE FROM news_articles WHERE id = ?"
        self._cursor.execute(query, [article_id])
        deleted = self._cursor.rowcount > 0
        self.commit()
        return deleted

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on Snowflake connection and schema."""
        health_status = {
            "connection": False,
            "schema_valid": False,
            "tables_exist": False,
            "sample_query": False,
            "errors": []
        }

        try:
            # Test connection
            self.execute_query("SELECT CURRENT_VERSION()")
            health_status["connection"] = True

            # Test schema
            self.execute_query(f"USE SCHEMA {self._database}.{self._schema}")
            health_status["schema_valid"] = True

            # Test table existence
            tables = ["news_articles", "article_summaries", "event_clusters"]
            for table in tables:
                self.execute_query(f"DESCRIBE TABLE {table}")
            health_status["tables_exist"] = True

            # Test sample query
            self.execute_query("SELECT COUNT(*) FROM news_articles LIMIT 1")
            health_status["sample_query"] = True

        except Exception as e:
            health_status["errors"].append(str(e))

        return health_status
