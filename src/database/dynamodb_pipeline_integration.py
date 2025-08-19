"""
DynamoDB Metadata Pipeline Integration - Issue #23

This module integrates the DynamoDB metadata manager with existing NeuroNews pipelines:
- Scrapy spider integration for automatic metadata indexing
- S3 storage integration for synchronized metadata storage
- Redshift ETL integration for data warehouse synchronization
- Data validation pipeline integration for quality metrics

Integration Points:
1. Scrapy pipelines automatically index article metadata during scraping
2. S3 storage operations trigger metadata indexing
3. Redshift ETL updates metadata with processing status
4. Data validation results are included in metadata
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

# Scrapy integration
try:
    from scrapy import signals
    from scrapy.exceptions import DropItem

    SCRAPY_AVAILABLE = True
except ImportError:
    SCRAPY_AVAILABLE = False

# Local imports
from .dynamodb_metadata_manager import (
    ArticleMetadataIndex,
    DynamoDBMetadataConfig,
    DynamoDBMetadataManager,
    integrate_with_redshift_etl,
    integrate_with_s3_storage,
)


class DynamoDBMetadataPipeline:
    """
    Scrapy pipeline for automatic DynamoDB metadata indexing.

    Integrates with existing scraping infrastructure to automatically
    index article metadata as articles are scraped and processed.
    """

    def __init__(
        self,
        dynamodb_config: Optional[DynamoDBMetadataConfig] = None,
        aws_credentials: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize DynamoDB metadata pipeline.

        Args:
            dynamodb_config: DynamoDB configuration
            aws_credentials: Optional AWS credentials
        """
        self.config = dynamodb_config or DynamoDBMetadataConfig()
        self.aws_credentials = aws_credentials
        self.manager = None
        self.logger = logging.getLogger(__name__)

        # Statistics
        self.stats = {
            "indexed_articles": 0,
            "failed_articles": 0,
            "total_processing_time": 0.0,
            "start_time": None,
        }

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline from crawler settings."""
        # Extract settings from spider configuration
        settings = crawler.settings

        config = DynamoDBMetadataConfig(
            table_name=settings.get(
                "DYNAMODB_METADATA_TABLE", "neuronews-article-metadata"
            ),
            region=settings.get("AWS_REGION", "us-east-1"),
            read_capacity_units=settings.getint("DYNAMODB_READ_CAPACITY", 10),
            write_capacity_units=settings.getint("DYNAMODB_WRITE_CAPACITY", 10),
            enable_full_text_search=settings.getbool("ENABLE_FULL_TEXT_SEARCH", True),
            create_indexes=settings.getbool("CREATE_DYNAMODB_INDEXES", True),
        )

        # AWS credentials from settings
        aws_credentials = None
        if settings.get("AWS_ACCESS_KEY_ID"):
            aws_credentials = {
                "aws_access_key_id": settings.get("AWS_ACCESS_KEY_ID"),
                "aws_secret_access_key": settings.get("AWS_SECRET_ACCESS_KEY"),
            }

        pipeline = cls(config, aws_credentials)

        # Connect to spider signals for lifecycle management
        crawler.signals.connect(pipeline.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(pipeline.spider_closed, signal=signals.spider_closed)

        return pipeline

    async def spider_opened(self, spider):
        """Initialize when spider opens."""
        self.logger.info(f"DynamoDB metadata pipeline opened for spider: {spider.name}")
        self.stats["start_time"] = time.time()

        try:
            self.manager = DynamoDBMetadataManager(self.config, self.aws_credentials)
            self.logger.info("DynamoDB metadata manager initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize DynamoDB manager: {e}")
            raise

    async def spider_closed(self, spider):
        """Cleanup when spider closes."""
        end_time = time.time()
        total_time = end_time - (self.stats["start_time"] or end_time)

        self.logger.info(f"DynamoDB metadata pipeline closed for spider: {spider.name}")
        self.logger.info(f"Indexing statistics:")
        self.logger.info(f"  - Indexed articles: {self.stats['indexed_articles']}")
        self.logger.info(f"  - Failed articles: {self.stats['failed_articles']}")
        self.logger.info(f"  - Total time: {total_time:.2f}s")
        self.logger.info(
            f"  - Average indexing time: {self.stats['total_processing_time']/max(1, self.stats['indexed_articles']):.3f}s"
        )

    async def process_item(self, item, spider):
        """Process scraped item and index metadata."""
        if not self.manager:
            self.logger.warning(
                "DynamoDB manager not initialized, skipping metadata indexing"
            )
            return item

        start_time = time.time()

        try:
            # Convert Scrapy item to article data
            article_data = self._convert_item_to_article_data(item, spider)

            # Index metadata in DynamoDB
            metadata = await self.manager.index_article_metadata(article_data)

            # Add metadata info to item for downstream pipelines
            item["dynamodb_metadata"] = {
                "article_id": metadata.article_id,
                "indexed_date": metadata.indexed_date,
                "content_hash": metadata.content_hash,
            }

            # Update statistics
            processing_time = time.time() - start_time
            self.stats["indexed_articles"] += 1
            self.stats["total_processing_time"] += processing_time

            self.logger.debug(
                f"Indexed metadata for article: {metadata.article_id} ({processing_time:.3f}s)"
            )

            return item

        except Exception as e:
            self.stats["failed_articles"] += 1
            self.logger.error(f"Failed to index article metadata: {e}")

            # Don't drop item, just log error and continue
            return item

    def _convert_item_to_article_data(self, item, spider) -> Dict[str, Any]:
        """Convert Scrapy item to article data format."""
        # Extract standard fields from item
        article_data = {
            "id": item.get("id") or item.get("url", ""),
            "title": item.get("title", ""),
            "source": item.get("source", spider.name),
            "published_date": item.get("published_date", ""),
            "tags": item.get("tags", []),
            "url": item.get("url", ""),
            "author": item.get("author", ""),
            "category": item.get("category", "News"),
            "language": item.get("language", "en"),
            "content": item.get("content", ""),
            "word_count": item.get("word_count", 0),
            "scraped_date": datetime.now(timezone.utc).isoformat(),
            "validation_score": item.get("validation_score", 0),
            "content_quality": item.get("content_quality", "unknown"),
            "sentiment_score": item.get("sentiment_score"),
        }

        # Add spider-specific metadata
        article_data["spider_name"] = spider.name
        article_data["spider_version"] = getattr(spider, "version", "1.0")

        return article_data


class S3MetadataSync:
    """
    Synchronization between S3 storage and DynamoDB metadata.

    Ensures metadata is automatically indexed when articles are stored in S3
    and keeps both systems synchronized.
    """

    def __init__(
        self, dynamodb_manager: DynamoDBMetadataManager, auto_sync: bool = True
    ):
        """
        Initialize S3 metadata sync.

        Args:
            dynamodb_manager: DynamoDB metadata manager
            auto_sync: Enable automatic synchronization
        """
        self.dynamodb_manager = dynamodb_manager
        self.auto_sync = auto_sync
        self.logger = logging.getLogger(__name__)

    async def sync_s3_storage_event(
        self, s3_metadata: Dict[str, Any]
    ) -> Optional[ArticleMetadataIndex]:
        """
        Sync metadata when article is stored in S3.

        Args:
            s3_metadata: S3 storage metadata

        Returns:
            ArticleMetadataIndex or None if sync disabled
        """
        if not self.auto_sync:
            return None

        try:
            metadata = await integrate_with_s3_storage(
                s3_metadata, self.dynamodb_manager
            )
            self.logger.debug(f"Synced S3 metadata for article: {metadata.article_id}")
            return metadata
        except Exception as e:
            self.logger.error(f"Failed to sync S3 metadata: {e}")
            return None

    async def sync_multiple_s3_articles(
        self, s3_metadata_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Sync multiple S3 articles efficiently.

        Args:
            s3_metadata_list: List of S3 metadata dictionaries

        Returns:
            Sync results summary
        """
        if not self.auto_sync:
            return {"status": "disabled", "synced": 0, "failed": 0}

        synced_count = 0
        failed_count = 0
        failed_items = []

        start_time = time.time()

        try:
            # Convert S3 metadata to article data format
            article_data_list = []
            for s3_meta in s3_metadata_list:
                article_data = {
                    "id": s3_meta.get("article_id"),
                    "title": s3_meta.get("title", ""),
                    "source": s3_meta.get("source", ""),
                    "published_date": s3_meta.get("published_date", ""),
                    "url": s3_meta.get("url", ""),
                    "s3_key": s3_meta.get("s3_key", ""),
                    "content_hash": s3_meta.get("content_hash", ""),
                    "scraped_date": s3_meta.get("scraped_date", ""),
                    "processing_status": "stored_s3",
                }
                article_data_list.append(article_data)

            # Batch sync to DynamoDB
            batch_result = await self.dynamodb_manager.batch_index_articles(
                article_data_list
            )
            synced_count = batch_result["indexed_count"]
            failed_count = batch_result["failed_count"]
            failed_items = batch_result["failed_articles"]

        except Exception as e:
            self.logger.error(f"Batch S3 sync failed: {e}")
            failed_count = len(s3_metadata_list)
            failed_items = [{"error": str(e)}]

        sync_time = (time.time() - start_time) * 1000

        result = {
            "status": "completed",
            "total_items": len(s3_metadata_list),
            "synced_count": synced_count,
            "failed_count": failed_count,
            "failed_items": failed_items,
            "sync_time_ms": sync_time,
        }

        self.logger.info(
            f"S3 metadata sync: {synced_count}/{len(s3_metadata_list)} articles ({sync_time:.2f}ms)"
        )
        return result


class RedshiftMetadataSync:
    """
    Synchronization between Redshift ETL and DynamoDB metadata.

    Updates metadata when articles are processed and loaded into Redshift.
    """

    def __init__(
        self, dynamodb_manager: DynamoDBMetadataManager, auto_update: bool = True
    ):
        """
        Initialize Redshift metadata sync.

        Args:
            dynamodb_manager: DynamoDB metadata manager
            auto_update: Enable automatic updates
        """
        self.dynamodb_manager = dynamodb_manager
        self.auto_update = auto_update
        self.logger = logging.getLogger(__name__)

    async def sync_redshift_load_event(self, redshift_record: Dict[str, Any]) -> bool:
        """
        Update metadata when article is loaded to Redshift.

        Args:
            redshift_record: Redshift ETL record

        Returns:
            Success status
        """
        if not self.auto_update:
            return False

        try:
            success = await integrate_with_redshift_etl(
                redshift_record, self.dynamodb_manager
            )
            if success:
                self.logger.debug(
                    f"Updated metadata for Redshift load: {redshift_record.get('article_id')}"
                )
            return success
        except Exception as e:
            self.logger.error(f"Failed to sync Redshift metadata: {e}")
            return False

    async def sync_batch_redshift_loads(
        self, redshift_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Sync multiple Redshift loads efficiently.

        Args:
            redshift_records: List of Redshift records

        Returns:
            Sync results summary
        """
        if not self.auto_update:
            return {"status": "disabled", "updated": 0, "failed": 0}

        updated_count = 0
        failed_count = 0
        failed_items = []

        start_time = time.time()

        for record in redshift_records:
            try:
                success = await self.sync_redshift_load_event(record)
                if success:
                    updated_count += 1
                else:
                    failed_count += 1
                    failed_items.append(
                        {
                            "article_id": record.get("article_id"),
                            "error": "Update failed",
                        }
                    )
            except Exception as e:
                failed_count += 1
                failed_items.append(
                    {"article_id": record.get("article_id"), "error": str(e)}
                )

        sync_time = (time.time() - start_time) * 1000

        result = {
            "status": "completed",
            "total_records": len(redshift_records),
            "updated_count": updated_count,
            "failed_count": failed_count,
            "failed_items": failed_items,
            "sync_time_ms": sync_time,
        }

        self.logger.info(
            f"Redshift metadata sync: {updated_count}/{len(redshift_records)} updates ({sync_time:.2f}ms)"
        )
        return result


class DataValidationMetadataSync:
    """
    Integration with data validation pipeline to include quality metrics in metadata.
    """

    def __init__(
        self,
        dynamodb_manager: DynamoDBMetadataManager,
        include_validation_metrics: bool = True,
    ):
        """
        Initialize data validation metadata sync.

        Args:
            dynamodb_manager: DynamoDB metadata manager
            include_validation_metrics: Include validation results in metadata
        """
        self.dynamodb_manager = dynamodb_manager
        self.include_validation_metrics = include_validation_metrics
        self.logger = logging.getLogger(__name__)

    async def sync_validation_results(
        self, article_id: str, validation_result: Dict[str, Any]
    ) -> bool:
        """
        Update metadata with validation results.

        Args:
            article_id: Article identifier
            validation_result: Validation pipeline result

        Returns:
            Success status
        """
        if not self.include_validation_metrics:
            return False

        try:
            # Extract validation metrics
            updates = {
                "validation_score": validation_result.get("quality_score", 0),
                "content_quality": validation_result.get("content_quality", "unknown"),
                "validation_flags": validation_result.get("validation_flags", []),
                "warnings": validation_result.get("warnings", []),
                "is_duplicate": validation_result.get("is_duplicate", False),
                "source_reputation": validation_result.get(
                    "source_reputation", "unknown"
                ),
                "last_validated": datetime.now(timezone.utc).isoformat(),
            }

            success = await self.dynamodb_manager.update_article_metadata(
                article_id, updates
            )
            if success:
                self.logger.debug(
                    f"Updated validation metadata for article: {article_id}"
                )
            return success

        except Exception as e:
            self.logger.error(f"Failed to sync validation metadata: {e}")
            return False


class MetadataIntegrationOrchestrator:
    """
    Orchestrates all metadata integrations and provides unified interface.
    """

    def __init__(
        self,
        dynamodb_config: DynamoDBMetadataConfig,
        aws_credentials: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize metadata integration orchestrator.

        Args:
            dynamodb_config: DynamoDB configuration
            aws_credentials: Optional AWS credentials
        """
        self.config = dynamodb_config
        self.aws_credentials = aws_credentials
        self.logger = logging.getLogger(__name__)

        # Initialize managers
        self.dynamodb_manager = DynamoDBMetadataManager(
            dynamodb_config, aws_credentials
        )
        self.s3_sync = S3MetadataSync(self.dynamodb_manager)
        self.redshift_sync = RedshiftMetadataSync(self.dynamodb_manager)
        self.validation_sync = DataValidationMetadataSync(self.dynamodb_manager)

    async def initialize(self):
        """Initialize all integration components."""
        self.logger.info("Initializing metadata integration orchestrator...")

        # Perform health check
        health = await self.dynamodb_manager.health_check()
        if health["status"] != "healthy":
            raise RuntimeError(f"DynamoDB manager unhealthy: {health}")

        self.logger.info("Metadata integration orchestrator initialized successfully")

    async def process_scraped_article(
        self, article_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Complete processing for a scraped article through all integrations.

        Args:
            article_data: Scraped article data

        Returns:
            Processing results
        """
        start_time = time.time()
        results = {
            "article_id": article_data.get("id"),
            "dynamodb_indexed": False,
            "s3_synced": False,
            "validation_synced": False,
            "errors": [],
        }

        try:
            # 1. Index in DynamoDB
            metadata = await self.dynamodb_manager.index_article_metadata(article_data)
            results["article_id"] = metadata.article_id
            results["dynamodb_indexed"] = True

            # 2. Sync S3 if metadata available
            if "s3_key" in article_data:
                s3_metadata = {
                    "article_id": metadata.article_id,
                    "title": metadata.title,
                    "source": metadata.source,
                    "published_date": metadata.published_date,
                    "s3_key": article_data["s3_key"],
                    "content_hash": metadata.content_hash,
                    "scraped_date": metadata.scraped_date,
                }
                await self.s3_sync.sync_s3_storage_event(s3_metadata)
                results["s3_synced"] = True

            # 3. Sync validation results if available
            if "validation_result" in article_data:
                await self.validation_sync.sync_validation_results(
                    metadata.article_id, article_data["validation_result"]
                )
                results["validation_synced"] = True

        except Exception as e:
            error_msg = f"Processing failed: {e}"
            results["errors"].append(error_msg)
            self.logger.error(error_msg)

        processing_time = (time.time() - start_time) * 1000
        results["processing_time_ms"] = processing_time

        return results

    async def get_integration_statistics(self) -> Dict[str, Any]:
        """Get comprehensive integration statistics."""
        try:
            # Get DynamoDB statistics
            db_stats = await self.dynamodb_manager.get_metadata_statistics()

            # Get health status
            health = await self.dynamodb_manager.health_check()

            return {
                "dynamodb_stats": db_stats,
                "health_status": health,
                "integration_status": {
                    "s3_sync": self.s3_sync.auto_sync,
                    "redshift_sync": self.redshift_sync.auto_update,
                    "validation_sync": self.validation_sync.include_validation_metrics,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Failed to get integration statistics: {e}")
            return {"error": str(e)}


# ============================================
# Pipeline Utility Functions
# ============================================


def create_scrapy_pipeline_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create Scrapy pipeline configuration for DynamoDB metadata indexing.

    Args:
        settings: Scrapy settings dictionary

    Returns:
        Pipeline configuration
    """
    return {
        "ITEM_PIPELINES": {
            "src.database.dynamodb_pipeline_integration.DynamoDBMetadataPipeline": 300,
        },
        "DYNAMODB_METADATA_TABLE": settings.get(
            "table_name", "neuronews-article-metadata"
        ),
        "AWS_REGION": settings.get("region", "us-east-1"),
        "ENABLE_FULL_TEXT_SEARCH": settings.get("enable_search", True),
        "CREATE_DYNAMODB_INDEXES": settings.get("create_indexes", True),
    }


async def sync_existing_s3_articles(
    s3_storage, dynamodb_manager: DynamoDBMetadataManager
) -> Dict[str, Any]:
    """
    Sync existing S3 articles with DynamoDB metadata.

    Args:
        s3_storage: S3 storage instance
        dynamodb_manager: DynamoDB manager

    Returns:
        Sync results
    """
    try:
        # Get all S3 articles (this would need to be implemented in S3 storage)
        # For now, return a placeholder
        return {
            "status": "completed",
            "message": "S3 sync functionality requires S3 storage integration",
            "synced_count": 0,
        }
    except Exception as e:
        return {"status": "failed", "error": str(e), "synced_count": 0}
