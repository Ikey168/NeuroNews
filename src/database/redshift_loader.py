"""
Enhanced RedshiftLoader for NeuroNews ETL Pipeline.

This module implements an ETL process to store processed articles in AWS Redshift
with support for batch uploads, data validation integration, and schema management.

Issue #22: Store Processed Articles in AWS Redshift
- Define news_articles schema in Redshift
- Implement ETL process (src/database/redshift_loader.py)
- Convert raw JSON articles to structured format before ingestion
- Enable batch uploads for efficiency
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import psycopg2
import psycopg2.extras

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class ArticleRecord:
    """Structured representation of an article for Redshift storage."""

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
    keywords: Optional[List[str]] = None

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
            "{0}{1}".format(self.url, self.title).encode()
        ).hexdigest()
        return "article_{0}".format(content_hash[:16])

    @classmethod
    def from_validated_article(cls, validated_data: Dict[str, Any]) -> "ArticleRecord":
        """Create ArticleRecord from data validation pipeline output."""
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
            "%Y-%m-%dT%H:%M:%S.%",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        logger.warning("Could not parse datetime: {0}".format(date_str))
        return None


class RedshiftETLProcessor:
    """Enhanced Redshift ETL processor for NeuroNews articles."""

    def __init__(
        self,
        host: str,
        database: str = "dev",
        user: str = "admin",
        password: Optional[str] = None,
        batch_size: int = 1000,
    ):
        """
        Initialize RedshiftETLProcessor.

        Args:
            host: Redshift cluster endpoint
            database: Database name
            user: Username for authentication
            password: Password for authentication
            batch_size: Number of records to process in each batch
        """
        self._host = host
        self._database = database
        self._user = user
        self._password = password or os.environ.get("REDSHIFT_PASSWORD")
        self._batch_size = batch_size

        if not self._password:
            raise ValueError(
                "Password must be provided or set in REDSHIFT_PASSWORD env var"
            )

        self._conn = None
        self._cursor = None

    def connect(self) -> None:
        """Establish connection to Redshift."""
        if self._conn is None:
            try:
                self._conn = psycopg2.connect(
                    host=self._host,
                    database=self._database,
                    user=self._user,
                    password=self._password,
                    port=5439,  # Default Redshift port
                )
                self._conn.autocommit = False
                self._cursor = self._conn.cursor(
                    cursor_factory=psycopg2.extras.DictCursor
                )
                logger.info("Connected to Redshift cluster: {0}".format(self._host))
            except Exception as e:
                logger.error("Failed to connect to Redshift: {0}".format(e))
                raise

    def close(self) -> None:
        """Close database connection."""
        if self._cursor:
            self._cursor.close()
        if self._conn:
            self._conn.close()
            self._conn = None
            self._cursor = None
            logger.info("Disconnected from Redshift")

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
            self._cursor.execute(query, params or [])
            if self._cursor.description:  # SELECT query
                return self._cursor.fetchall()
            return []
        except Exception as e:
            logger.error("Query execution failed: {0}".format(e))
            logger.error("Query: {0}".format(query))
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
        """Initialize or update the Redshift schema."""
        if schema_file is None:
            schema_file = os.path.join(os.path.dirname(__file__), "redshift_schema.sql")

        try:
            with open(schema_file, "r") as f:
                schema_sql = f.read()

            # Execute schema statements
            statements = [
                stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()
            ]

            for statement in statements:
                if statement:
                    logger.debug(
                        "Executing schema statement: {0}...".format(statement[:100])
                    )
                    self._cursor.execute(statement)

            self.commit()
            logger.info("Schema initialized successfully")

        except Exception as e:
            logger.error("Schema initialization failed: {0}".format(e))
            self.rollback()
            raise

    def load_single_article(
        self, article: Union[Dict[str, Any], ArticleRecord]
    ) -> bool:
        """
        Load a single article into Redshift.

        Args:
            article: Article data (dict or ArticleRecord)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to ArticleRecord if needed
            if isinstance(article, dict):
                record = ArticleRecord.from_validated_article(article)
            else:
                record = article

            # Check if article already exists
            if self._article_exists(record.id):
                logger.warning("Article {0} already exists, skipping".format(record.id))
                return False

            # Insert article
            query = """
                INSERT INTO news_articles (
                    id, url, title, content, source, published_date, scraped_at,
                    validation_score, content_quality, source_credibility, validation_flags,
                    validated_at, word_count, content_length, author, category,
                    sentiment_score, sentiment_label, entities, keywords
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """

            params = [
                record.id,
                record.url,
                record.title,
                record.content,
                record.source,
                record.published_date,
                record.scraped_at,
                record.validation_score,
                record.content_quality,
                record.source_credibility,
                (
                    json.dumps(record.validation_flags)
                    if record.validation_flags
                    else None
                ),
                record.validated_at,
                record.word_count,
                record.content_length,
                record.author,
                record.category,
                record.sentiment_score,
                record.sentiment_label,
                json.dumps(record.entities) if record.entities else None,
                json.dumps(record.keywords) if record.keywords else None,
            ]

            self.execute_query(query, params)
            self.commit()
            logger.debug("Successfully loaded article: {0}".format(record.id))
            return True

        except Exception as e:
            logger.error("Failed to load article: {0}".format(e))
            self.rollback()
            return False

    def batch_load_articles(
        self,
        articles: List[Union[Dict[str, Any], ArticleRecord]],
        use_staging: bool = True,
    ) -> Dict[str, Any]:
        """
        Load multiple articles in batches for efficiency.

        Args:
            articles: List of article data (dicts or ArticleRecords)
            use_staging: Whether to use staging table for atomic batch loads

        Returns:
            Dictionary with batch load statistics
        """
        start_time = datetime.now()
        total_articles = len(articles)
        loaded_count = 0
        failed_count = 0
        skipped_count = 0
        errors = []

        try:
            # Process articles in batches
            for i in range(0, total_articles, self._batch_size):
                batch = articles[i: i + self._batch_size]
                batch_result = self._process_batch(batch, use_staging)

                loaded_count += batch_result["loaded"]
                failed_count += batch_result["failed"]
                skipped_count += batch_result["skipped"]
                errors.extend(batch_result["errors"])

                batch_num = i // self._batch_size + 1
                logger.info(
                    "Processed batch {0}: {1} loaded, {2} failed".format(
                        batch_num, batch_result["loaded"], batch_result["failed"]
                    )
                )

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
                "Batch load completed: {0}/{1} articles loaded ({2:.1f}% success rate)".format(
                    loaded_count, total_articles, stats["success_rate"]
                )
            )

            return stats

        except Exception as e:
            logger.error("Batch load failed: {0}".format(e))
            self.rollback()
            raise

    def _process_batch(
        self, batch: List[Union[Dict[str, Any], ArticleRecord]], use_staging: bool
    ) -> Dict[str, int]:
        """Process a single batch of articles."""
        loaded = failed = skipped = 0
        errors = []

        if use_staging:
            # Use staging table for atomic batch insert
            return self._process_batch_staging(batch)
        else:
            # Process articles one by one
            for article in batch:
                try:
                    if self.load_single_article(article):
                        loaded += 1
                    else:
                        skipped += 1
                except Exception as e:
                    failed += 1
                    errors.append(str(e))

        return {
            "loaded": loaded,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
        }

    def _process_batch_staging(
        self, batch: List[Union[Dict[str, Any], ArticleRecord]]
    ) -> Dict[str, int]:
        """Process batch using staging table for better performance."""
        loaded = failed = skipped = 0
        errors = []

        try:
            # Clear staging table
            self.execute_query("TRUNCATE news_articles_staging")

            # Prepare batch data
            records = []
            for article in batch:
                try:
                    if isinstance(article, dict):
                        record = ArticleRecord.from_validated_article(article)
                    else:
                        record = article
                    records.append(record)
                except Exception as e:
                    failed += 1
                    errors.append("Failed to convert article: {0}".format(e))

            if not records:
                return {"loaded": 0, "failed": failed, "skipped": 0, "errors": errors}

            # Bulk insert into staging
            values_list = []
            params_list = []

            for record in records:
                values_list.append(
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                )
                params_list.extend(
                    [
                        record.id,
                        record.url,
                        record.title,
                        record.content,
                        record.source,
                        record.published_date,
                        record.scraped_at,
                        record.validation_score,
                        record.content_quality,
                        record.source_credibility,
                        (
                            json.dumps(record.validation_flags)
                            if record.validation_flags
                            else None
                        ),
                        record.validated_at,
                        record.word_count,
                        record.content_length,
                        record.author,
                        record.category,
                        record.sentiment_score,
                        record.sentiment_label,
                        json.dumps(record.entities) if record.entities else None,
                        json.dumps(record.keywords) if record.keywords else None,
                    ]
                )

            staging_query = """
                INSERT INTO news_articles_staging (
                    id, url, title, content, source, published_date, scraped_at,
                    validation_score, content_quality, source_credibility, validation_flags,
                    validated_at, word_count, content_length, author, category,
                    sentiment_score, sentiment_label, entities, keywords
                ) VALUES {', '.join(values_list)}
            """

            self.execute_query(staging_query, params_list)

            # Move from staging to main table (excluding duplicates)
            merge_query = """
                INSERT INTO news_articles
                SELECT s.* FROM news_articles_staging s
                LEFT JOIN news_articles m ON s.id = m.id
                WHERE m.id IS NULL
            """

            self.execute_query(merge_query)
            loaded = self._cursor.rowcount
            skipped = len(records) - loaded

            self.commit()

            return {
                "loaded": loaded,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
            }

        except Exception as e:
            logger.error("Staging batch processing failed: {0}".format(e))
            self.rollback()
            return {"loaded": 0, "failed": len(batch), "skipped": 0, "errors": [str(e)]}

    def _article_exists(self, article_id: str) -> bool:
        """Check if article already exists in database."""
        query = "SELECT 1 FROM news_articles WHERE id = %s LIMIT 1"
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
                WHERE scraped_at >= CURRENT_DATE - INTERVAL '7 days'
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
                if stat_name in ["total_articles", "recent_articles"]:
                    stats[stat_name] = result[0][0] if result else 0
                elif stat_name == "avg_validation_score":
                    if result and result[0][0] is not None:
                        stats[stat_name] = {
                            "average": float(result[0][0]),
                            "minimum": float(result[0][1]),
                            "maximum": float(result[0][2]),
                        }
                    else:
                        stats[stat_name] = {"average": 0, "minimum": 0, "maximum": 0}
                else:
                    stats[stat_name] = [dict(row) for row in result]
            except Exception as e:
                logger.error("Failed to get {0}: {1}".format(stat_name, e))
                stats[stat_name] = None

        return stats

    def process_validation_pipeline_output(
        self, validation_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Process output from the data validation pipeline and load into Redshift.

        Args:
            validation_results: List of validated article data from pipeline

        Returns:
            Processing statistics
        """
        logger.info(
            "Processing {0} validated articles for Redshift storage".format(
                len(validation_results)
            )
        )

        # Filter out invalid results
        valid_articles = [
            result
            for result in validation_results
            if result
            and isinstance(result, dict)
            and result.get("title")
            and result.get("content")
        ]

        if len(valid_articles) != len(validation_results):
            logger.warning(
                "Filtered out {0} invalid articles".format(
                    len(validation_results) - len(valid_articles)
                )
            )

        if not valid_articles:
            logger.warning("No valid articles to process")
            return {
                "total_articles": len(validation_results),
                "loaded_count": 0,
                "failed_count": len(validation_results),
                "skipped_count": 0,
                "success_rate": 0,
                "errors": ["No valid articles found"],
            }

        # Batch load the valid articles
        return self.batch_load_articles(valid_articles)


# Legacy class for backward compatibility
class RedshiftLoader(RedshiftETLProcessor):
    """Legacy RedshiftLoader class - deprecated, use RedshiftETLProcessor instead."""

    def __init__(self, *args, **kwargs):
        logger.warning("RedshiftLoader is deprecated, use RedshiftETLProcessor instead")
        super().__init__(*args, **kwargs)

    async def execute_query(self, query: str, params: Optional[List] = None) -> List:
        """Execute a query and return results."""
        self._cursor.execute(query, params or [])
        return self._cursor.fetchall()

    async def get_latest_articles(
        self,
        page: int = 1,
        per_page: int = 10,
        min_score: float = None,
        sentiment: str = None,
        category: str = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Fetch latest news articles with pagination and optional filtering.

        Args:
            page: Page number (1-based)
            per_page: Number of items per page
            min_score: Optional minimum sentiment score filter
            sentiment: Optional sentiment label filter (POSITIVE/NEGATIVE/NEUTRAL)
            category: Optional category filter

        Returns:
            Tuple containing:
            1. List of article dictionaries
            2. Pagination metadata dictionary with:
               - total: Total number of matching articles
               - page: Current page number
               - per_page: Items per page
               - pages: Total number of pages
        """
        if page < 1:
            raise ValueError("Page number must be >= 1")
        if per_page < 1 or per_page > 100:
            raise ValueError("Items per page must be between 1 and 100")

        conditions = []
        params = []

        if min_score is not None:
            conditions.append("sentiment_score >= %s")
            params.append(min_score)

        if sentiment:
            conditions.append("sentiment_label = %s")
            params.append(sentiment.upper())

        if category:
            conditions.append("category = %s")
            params.append(category)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        count_query = "SELECT COUNT(*) FROM news_articles WHERE {0}".format(
            where_clause
        )
        result = await self.execute_query(count_query, params)
        total = result[0][0]

        # Calculate pagination
        offset = (page - 1) * per_page
        pages = (total + per_page - 1) // per_page  # Ceiling division

        # Get paginated results
        query = """
            SELECT id, title, url, publish_date, category, source,
                   sentiment_score, sentiment_label
            FROM news_articles
            WHERE {where_clause}
            ORDER BY publish_date DESC
            LIMIT %s OFFSET %s
        """
        params.extend([per_page, offset])

        results = await self.execute_query(query, params)

        articles = []
        for row in results:
            articles.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "url": row[2],
                    "publish_date": row[3].isoformat() if row[3] else None,
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

    async def load_article(self, article_data: Dict[str, Any]) -> None:
        """Load a single article into Redshift."""
        required_fields = ["id", "title", "url", "content"]
        missing = [f for f in required_fields if f not in article_data]
        if missing:
            raise ValueError("Missing required fields: {0}".format(", ".join(missing)))

        query = """
            INSERT INTO news_articles (
                id, title, url, content, publish_date,
                source, category, sentiment_score, sentiment_label
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        params = [
            article_data["id"],
            article_data["title"],
            article_data["url"],
            article_data["content"],
            article_data.get("publish_date"),
            article_data.get("source"),
            article_data.get("category"),
            article_data.get("sentiment_score"),
            article_data.get("sentiment_label"),
        ]

        await self.execute_query(query, params)
        self._conn.commit()

    async def delete_article(self, article_id: str) -> bool:
        """Delete an article from Redshift."""
        query = "DELETE FROM news_articles WHERE id = %s"
        self._cursor.execute(query, [article_id])
        deleted = self._cursor.rowcount > 0
        self._conn.commit()
        return deleted
