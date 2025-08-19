"""
Redshift Storage Pipeline for Scrapy Integration - Issue #22

This pipeline automatically stores validated articles in AWS Redshift
as part of the scraping workflow.
"""

import logging
import os
# Add src to path for imports
import sys
from typing import Any, Dict, Optional

from scrapy import Spider
from scrapy.exceptions import DropItem

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from database.redshift_loader import RedshiftETLProcessor

logger = logging.getLogger(__name__)


class RedshiftStoragePipeline:
    """
    Scrapy pipeline for storing validated articles in AWS Redshift.

    This pipeline should be placed after the data validation pipelines
    to ensure only high-quality, validated articles are stored.
    """

    def __init__(
        self,
        redshift_host: str,
        redshift_database: str = "dev",
        redshift_user: str = "admin",
        redshift_password: Optional[str] = None,
        batch_size: int = 100,
        auto_commit: bool = True,
    ):
        """
        Initialize Redshift storage pipeline.

        Args:
            redshift_host: Redshift cluster endpoint
            redshift_database: Database name
            redshift_user: Username for authentication
            redshift_password: Password (or will use REDSHIFT_PASSWORD env var)
            batch_size: Number of articles to batch before committing
            auto_commit: Whether to auto-commit batches
        """
        self.redshift_host = redshift_host
        self.redshift_database = redshift_database
        self.redshift_user = redshift_user
        self.redshift_password = redshift_password
        self.batch_size = batch_size
        self.auto_commit = auto_commit

        self.etl_processor = None
        self.batch_articles = []
        self.stats = {
            "processed_count": 0,
            "stored_count": 0,
            "failed_count": 0,
            "batch_count": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline from Scrapy crawler settings."""
        settings = crawler.settings

        return cls(
            redshift_host=settings.get("REDSHIFT_HOST"),
            redshift_database=settings.get("REDSHIFT_DATABASE", "dev"),
            redshift_user=settings.get("REDSHIFT_USER", "admin"),
            redshift_password=settings.get("REDSHIFT_PASSWORD"),
            batch_size=settings.getint("REDSHIFT_BATCH_SIZE", 100),
            auto_commit=settings.getbool("REDSHIFT_AUTO_COMMIT", True),
        )

    def open_spider(self, spider: Spider):
        """Initialize Redshift connection when spider opens."""
        try:
            # Validate required configuration
            if not self.redshift_host:
                raise ValueError("REDSHIFT_HOST must be configured")

            # Initialize ETL processor
            self.etl_processor = RedshiftETLProcessor(
                host=self.redshift_host,
                database=self.redshift_database,
                user=self.redshift_user,
                password=self.redshift_password,
                batch_size=self.batch_size,
            )

            # Connect to Redshift
            self.etl_processor.connect()
            spider.logger.info(f"Connected to Redshift cluster: {self.redshift_host}")

            # Initialize schema if needed
            try:
                self.etl_processor.initialize_schema()
                spider.logger.info("Redshift schema initialized")
            except Exception as e:
                spider.logger.warning(
                    f"Schema initialization failed (may already exist): {e}"
                )

        except Exception as e:
            spider.logger.error(f"Failed to initialize Redshift connection: {e}")
            spider.logger.error("Articles will not be stored in Redshift")
            self.etl_processor = None

    def process_item(self, item: Dict[str, Any], spider: Spider) -> Dict[str, Any]:
        """
        Process and store article item in Redshift.

        Args:
            item: Article item from Scrapy
            spider: Scrapy spider instance

        Returns:
            The processed item

        Raises:
            DropItem: If storage fails and drop_on_error is True
        """
        if not self.etl_processor:
            spider.logger.warning("Redshift not available, skipping storage")
            return item

        self.stats["processed_count"] += 1

        try:
            # Ensure item has required validation metadata
            if not self._is_validated_item(item):
                spider.logger.warning(
                    f"Item missing validation metadata: {item.get('url', 'Unknown')}"
                )
                # Add basic validation metadata if missing
                self._add_basic_validation_metadata(item)

            # Add to batch
            self.batch_articles.append(dict(item))

            # Process batch if it's full or auto_commit is disabled
            if len(self.batch_articles) >= self.batch_size:
                self._process_batch(spider)

            spider.logger.debug(
                f"Article queued for Redshift storage: {item.get('url', 'Unknown')}"
            )
            return item

        except Exception as e:
            self.stats["failed_count"] += 1
            spider.logger.error(f"Failed to queue article for Redshift: {e}")

            # Optionally drop item on storage failure
            if spider.settings.getbool("REDSHIFT_DROP_ON_ERROR", False):
                raise DropItem(f"Redshift storage failed: {e}")

            return item

    def close_spider(self, spider: Spider):
        """Process remaining batch and close connection when spider closes."""
        try:
            # Process any remaining articles in batch
            if self.batch_articles and self.etl_processor:
                self._process_batch(spider, final=True)

            # Log final statistics
            spider.logger.info(
                f"""
=== Redshift Storage Pipeline Statistics ===
Processed: {self.stats['processed_count']} articles
Stored: {self.stats['stored_count']} articles
Failed: {self.stats['failed_count']} articles
Batches: {self.stats['batch_count']} batches
Success Rate: {(self.stats['stored_count'] / max(1, self.stats['processed_count'])) * 100:.1f}%
==========================================
"""
            )

            # Store stats in spider stats
            spider.crawler.stats.set_value(
                "redshift_processed_count", self.stats["processed_count"]
            )
            spider.crawler.stats.set_value(
                "redshift_stored_count", self.stats["stored_count"]
            )
            spider.crawler.stats.set_value(
                "redshift_failed_count", self.stats["failed_count"]
            )
            spider.crawler.stats.set_value(
                "redshift_success_rate",
                (self.stats["stored_count"] / max(1, self.stats["processed_count"]))
                * 100,
            )

        except Exception as e:
            spider.logger.error(f"Error during Redshift pipeline cleanup: {e}")

        finally:
            # Close Redshift connection
            if self.etl_processor:
                try:
                    self.etl_processor.close()
                    spider.logger.info("Redshift connection closed")
                except Exception as e:
                    spider.logger.error(f"Error closing Redshift connection: {e}")

    def _process_batch(self, spider: Spider, final: bool = False):
        """Process the current batch of articles."""
        if not self.batch_articles:
            return

        try:
            batch_size = len(self.batch_articles)
            spider.logger.info(f"Processing Redshift batch: {batch_size} articles")

            # Load batch into Redshift
            load_stats = self.etl_processor.batch_load_articles(
                self.batch_articles, use_staging=True
            )

            # Update statistics
            self.stats["stored_count"] += load_stats["loaded_count"]
            self.stats["failed_count"] += load_stats["failed_count"]
            self.stats["batch_count"] += 1

            spider.logger.info(
                f"Batch processed: {load_stats['loaded_count']}/{batch_size} stored, "
                f"{load_stats['skipped_count']} skipped, {load_stats['failed_count']} failed"
            )

            # Log errors if any
            if load_stats.get("errors"):
                for error in load_stats["errors"][:3]:  # Log first 3 errors
                    spider.logger.error(f"Batch processing error: {error}")

            # Clear batch
            self.batch_articles.clear()

        except Exception as e:
            spider.logger.error(f"Failed to process Redshift batch: {e}")
            self.stats["failed_count"] += len(self.batch_articles)
            self.batch_articles.clear()

    def _is_validated_item(self, item: Dict[str, Any]) -> bool:
        """Check if item has been processed by validation pipeline."""
        validation_fields = [
            "validation_score",
            "content_quality",
            "source_credibility",
            "validated_at",
        ]

        return any(field in item for field in validation_fields)

    def _add_basic_validation_metadata(self, item: Dict[str, Any]):
        """Add basic validation metadata if missing."""
        from datetime import datetime

        # Add minimal validation metadata
        if "validation_score" not in item:
            item["validation_score"] = 50.0  # Default score

        if "content_quality" not in item:
            # Basic quality assessment based on content length
            content_length = len(item.get("content", ""))
            if content_length > 1000:
                item["content_quality"] = "medium"
            elif content_length > 200:
                item["content_quality"] = "low"
            else:
                item["content_quality"] = "poor"

        if "source_credibility" not in item:
            item["source_credibility"] = "unknown"

        if "validated_at" not in item:
            item["validated_at"] = datetime.now().isoformat()

        if "validation_flags" not in item:
            item["validation_flags"] = ["unvalidated"]


class RedshiftAnalyticsPipeline:
    """
    Pipeline for storing analytics-focused article data in Redshift.

    This pipeline can run alongside RedshiftStoragePipeline to create
    denormalized views optimized for analytics queries.
    """

    def __init__(self, redshift_host: str, analytics_table: str = "article_analytics"):
        """
        Initialize analytics pipeline.

        Args:
            redshift_host: Redshift cluster endpoint
            analytics_table: Name of analytics table
        """
        self.redshift_host = redshift_host
        self.analytics_table = analytics_table
        self.etl_processor = None
        self.analytics_batch = []

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline from Scrapy crawler settings."""
        return cls(
            redshift_host=crawler.settings.get("REDSHIFT_HOST"),
            analytics_table=crawler.settings.get(
                "REDSHIFT_ANALYTICS_TABLE", "article_analytics"
            ),
        )

    def open_spider(self, spider: Spider):
        """Initialize analytics connection."""
        if not self.redshift_host:
            spider.logger.warning(
                "REDSHIFT_HOST not configured, analytics pipeline disabled"
            )
            return

        try:
            self.etl_processor = RedshiftETLProcessor(host=self.redshift_host)
            self.etl_processor.connect()
            spider.logger.info("Redshift analytics pipeline initialized")
        except Exception as e:
            spider.logger.error(f"Failed to initialize analytics pipeline: {e}")
            self.etl_processor = None

    def process_item(self, item: Dict[str, Any], spider: Spider) -> Dict[str, Any]:
        """Process item for analytics storage."""
        if not self.etl_processor:
            return item

        try:
            # Extract analytics-relevant fields
            analytics_record = self._extract_analytics_data(item)
            self.analytics_batch.append(analytics_record)

            # Process batch if full
            if len(self.analytics_batch) >= 50:  # Smaller batch for analytics
                self._process_analytics_batch(spider)

        except Exception as e:
            spider.logger.error(f"Analytics processing failed: {e}")

        return item

    def close_spider(self, spider: Spider):
        """Process remaining analytics batch."""
        if self.analytics_batch and self.etl_processor:
            self._process_analytics_batch(spider, final=True)

        if self.etl_processor:
            self.etl_processor.close()

    def _extract_analytics_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract analytics-relevant data from article item."""
        return {
            "article_id": item.get("id"),
            "source": item.get("source"),
            "publish_date": item.get("published_date"),
            "scraped_date": item.get("scraped_at"),
            "word_count": item.get("word_count", 0),
            "validation_score": item.get("validation_score"),
            "content_quality": item.get("content_quality"),
            "source_credibility": item.get("source_credibility"),
            "category": item.get("category"),
            "sentiment_score": item.get("sentiment_score"),
            "has_author": bool(item.get("author")),
            "title_length": len(item.get("title", "")),
            "url_domain": self._extract_domain(item.get("url", "")),
        }

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse

            return urlparse(url).netloc.lower()
        except:
            return "unknown"

    def _process_analytics_batch(self, spider: Spider, final: bool = False):
        """Process analytics batch."""
        if not self.analytics_batch:
            return

        try:
            # Insert analytics records (implementation depends on analytics table schema)
            spider.logger.info(
                f"Processing analytics batch: {len(self.analytics_batch)} records"
            )
            # Implementation would insert into analytics table
            self.analytics_batch.clear()

        except Exception as e:
            spider.logger.error(f"Analytics batch processing failed: {e}")
            self.analytics_batch.clear()
