import asyncio
import hashlib
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import aiohttp
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logger = logging.getLogger(__name__)


class ArticleType(Enum):
    """Enum for article types to organize S3 storage."""

    RAW = "raw_articles"
    PROCESSED = "processed_articles"


@dataclass
class ArticleMetadata:
    """Metadata for article storage tracking."""

    article_id: str
    source: str
    url: str
    title: str
    published_date: str
    scraped_date: str
    content_hash: str
    file_size: int
    s3_key: str
    article_type: ArticleType
    processing_status: str = "pending"
    error_message: Optional[str] = None


@dataclass
class S3StorageConfig:
    """Configuration for S3 storage operations."""

    bucket_name: str
    region: str = "us-east-1"
    raw_prefix: str = "raw_articles"
    processed_prefix: str = "processed_articles"
    enable_versioning: bool = True
    enable_encryption: bool = True
    storage_class: str = "STANDARD"
    lifecycle_days: int = 365
    max_file_size_mb: int = 100


class S3ArticleStorage:
    def __init__(
        self,
        config: S3StorageConfig,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ):
        """
        Initialize S3 article storage handler.

        Args:
            config: S3 storage configuration
            aws_access_key_id: AWS access key ID (optional, uses environment/IAM if None)
            aws_secret_access_key: AWS secret access key (optional, uses environment/IAM if None)
        """
        self.config = config
        self.bucket_name = config.bucket_name

        # Initialize S3 client with error handling
        try:
            session_config = {"region_name": config.region}

            if aws_access_key_id and aws_secret_access_key:
                session_config.update(
                    {
                        "aws_access_key_id": aws_access_key_id,
                        "aws_secret_access_key": aws_secret_access_key,
                    }
                )

            self.s3_client = boto3.client("s3", **session_config)

            # Verify bucket access and create if needed
            self._ensure_bucket_exists()

        except NoCredentialsError:
            logger.warning("AWS credentials not found. S3 operations will fail.")
            self.s3_client = None
        except ValueError as e:
            # Re-raise ValueError from bucket validation
            raise e
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            self.s3_client = None

    def _ensure_bucket_exists(self) -> None:
        """Ensure S3 bucket exists and is accessible."""
        if not self.s3_client:
            return

        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"S3 bucket {self.bucket_name} is accessible")

            # Configure bucket if needed
            self._configure_bucket()

        except ClientError as e:
            error_code = int(e.response["Error"]["Code"])
            if error_code == 404:
                logger.warning(f"Bucket {self.bucket_name} does not exist")
                # In production, bucket should be pre-created
                raise ValueError(f"Bucket {self.bucket_name} does not exist")
            elif error_code == 403:
                raise ValueError(f"Access denied to bucket {self.bucket_name}")
            else:
                raise

    def _configure_bucket(self) -> None:
        """Configure bucket settings like versioning and encryption."""
        if not self.s3_client:
            return

        try:
            # Enable versioning if configured
            if self.config.enable_versioning:
                self.s3_client.put_bucket_versioning(
                    Bucket=self.bucket_name,
                    VersioningConfiguration={"Status": "Enabled"},
                )

            # Configure lifecycle rules
            lifecycle_config = {
                "Rules": [
                    {
                        "ID": "neuronews-lifecycle",
                        "Status": "Enabled",
                        "Filter": {"Prefix": ""},
                        "Transitions": [
                            {"Days": 30, "StorageClass": "STANDARD_IA"},
                            {"Days": 90, "StorageClass": "GLACIER"},
                        ],
                        "Expiration": {"Days": self.config.lifecycle_days},
                    }
                ]
            }

            self.s3_client.put_bucket_lifecycle_configuration(
                Bucket=self.bucket_name, LifecycleConfiguration=lifecycle_config
            )

        except ClientError as e:
            logger.warning(f"Could not configure bucket settings: {e}")

    def _generate_article_id(self, article: Dict[str, Any]) -> str:
        """Generate unique article ID based on content."""
        # Create ID from URL and title for consistency
        content_string = f"{article.get('url', '')}{article.get('title', '')}"
        return hashlib.md5(content_string.encode()).hexdigest()

    def _calculate_content_hash(self, content: str) -> str:
        """Calculate SHA-256 hash of article content."""
        return hashlib.sha256(content.encode()).hexdigest()

    def _generate_s3_key(
        self,
        article: Dict[str, Any],
        article_type: ArticleType,
        date_override: Optional[str] = None,
    ) -> str:
        """
        Generate S3 key for an article following the required structure:
        raw_articles/YYYY/MM/DD/ or processed_articles/YYYY/MM/DD/

        Args:
            article: Article data dictionary
            article_type: Type of article (raw or processed)
            date_override: Override date (format: YYYY-MM-DD)

        Returns:
            S3 key string
        """
        try:
            # Use date override or article published date or current date
            if date_override:
                date_str = date_override
            elif "published_date" in article:
                date_str = article["published_date"]
            else:
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Parse date and create directory structure
            date_parts = date_str.split("-")
            if len(date_parts) != 3:
                raise ValueError(f"Invalid date format: {date_str}")

            year, month, day = date_parts

            # Generate article ID
            article_id = article.get("id") or self._generate_article_id(article)

            # Create S3 key with proper structure
            prefix = article_type.value
            key = f"{prefix}/{year}/{month}/{day}/{article_id}.json"

            return key

        except (KeyError, ValueError, IndexError) as e:
            logger.error(f"Error generating S3 key: {e}")
            # Fallback to simple structure
            article_id = str(uuid.uuid4())
            prefix = article_type.value
            current_date = datetime.now(timezone.utc)
            return f"{prefix}/{current_date.strftime('%Y/%m/%d')}/{article_id}.json"

    async def store_raw_article(
        self, article: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None
    ) -> ArticleMetadata:
        """
        Store a raw scraped article in S3.

        Args:
            article: Raw article data from scraper
            metadata: Optional additional metadata

        Returns:
            ArticleMetadata object with storage information

        Raises:
            ValueError: If required fields are missing or S3 client unavailable
        """
        if not self.s3_client:
            raise ValueError("S3 client not available")

        # Validate required fields
        required_fields = ["title", "content", "url"]
        missing_fields = [field for field in required_fields if not article.get(field)]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        try:
            # Generate article metadata
            article_id = self._generate_article_id(article)
            content_hash = self._calculate_content_hash(article["content"])

            # Add metadata to article
            enhanced_article = {
                **article,
                "id": article_id,
                "scraped_date": datetime.now(timezone.utc).isoformat(),
                "content_hash": content_hash,
                "storage_type": "raw",
                "metadata": metadata or {},
            }

            # Generate S3 key
            s3_key = self._generate_s3_key(enhanced_article, ArticleType.RAW)

            # Serialize article data
            article_json = json.dumps(enhanced_article, ensure_ascii=False, indent=2)
            file_size = len(article_json.encode("utf-8"))

            # Check file size
            if file_size > self.config.max_file_size_mb * 1024 * 1024:
                raise ValueError(f"Article too large: {file_size} bytes")

            # Upload to S3
            extra_args = {}
            if self.config.enable_encryption:
                extra_args["ServerSideEncryption"] = "AES256"
            if self.config.storage_class != "STANDARD":
                extra_args["StorageClass"] = self.config.storage_class

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=article_json,
                ContentType="application/json",
                **extra_args,
            )

            # Create metadata object
            article_metadata = ArticleMetadata(
                article_id=article_id,
                source=article.get("source", "unknown"),
                url=article["url"],
                title=article["title"],
                published_date=article.get(
                    "published_date", enhanced_article["scraped_date"][:10]
                ),
                scraped_date=enhanced_article["scraped_date"],
                content_hash=content_hash,
                file_size=file_size,
                s3_key=s3_key,
                article_type=ArticleType.RAW,
                processing_status="stored",
            )

            logger.info(f"Stored raw article {article_id} to S3: {s3_key}")
            return article_metadata

        except Exception as e:
            logger.error(f"Failed to store raw article: {e}")
            raise

    async def store_processed_article(
        self,
        article: Dict[str, Any],
        processing_metadata: Optional[Dict[str, Any]] = None,
    ) -> ArticleMetadata:
        """
        Store a processed article in S3.

        Args:
            article: Processed article data
            processing_metadata: Metadata about processing pipeline

        Returns:
            ArticleMetadata object with storage information
        """
        if not self.s3_client:
            raise ValueError("S3 client not available")

        try:
            # Generate metadata
            article_id = article.get("id") or self._generate_article_id(article)
            content_hash = self._calculate_content_hash(str(article))

            # Add processing metadata
            enhanced_article = {
                **article,
                "id": article_id,
                "processed_date": datetime.now(timezone.utc).isoformat(),
                "content_hash": content_hash,
                "storage_type": "processed",
                "processing_metadata": processing_metadata or {},
            }

            # Generate S3 key for processed articles
            s3_key = self._generate_s3_key(enhanced_article, ArticleType.PROCESSED)

            # Upload to S3
            article_json = json.dumps(enhanced_article, ensure_ascii=False, indent=2)
            file_size = len(article_json.encode("utf-8"))

            extra_args = {}
            if self.config.enable_encryption:
                extra_args["ServerSideEncryption"] = "AES256"

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=article_json,
                ContentType="application/json",
                **extra_args,
            )

            # Create metadata
            article_metadata = ArticleMetadata(
                article_id=article_id,
                source=article.get("source", "unknown"),
                url=article.get("url", ""),
                title=article.get("title", ""),
                published_date=article.get(
                    "published_date", enhanced_article["processed_date"][:10]
                ),
                scraped_date=enhanced_article["processed_date"],
                content_hash=content_hash,
                file_size=file_size,
                s3_key=s3_key,
                article_type=ArticleType.PROCESSED,
                processing_status="processed",
            )

            logger.info(f"Stored processed article {article_id} to S3: {s3_key}")
            return article_metadata

        except Exception as e:
            logger.error(f"Failed to store processed article: {e}")
            raise

    async def retrieve_article(self, s3_key: str) -> Dict[str, Any]:
        """
        Retrieve an article from S3 by its key.

        Args:
            s3_key: S3 key for the article

        Returns:
            Article data dictionary

        Raises:
            ValueError: If S3 client unavailable or key not found
        """
        if not self.s3_client:
            raise ValueError("S3 client not available")

        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            article_json = response["Body"].read().decode("utf-8")
            article = json.loads(article_json)

            logger.info(f"Retrieved article from S3: {s3_key}")
            return article

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NoSuchKey":
                raise ValueError(f"Article not found: {s3_key}")
            else:
                logger.error(f"Failed to retrieve article {s3_key}: {e}")
                raise
        except Exception as e:
            logger.error(f"Error retrieving article {s3_key}: {e}")
            raise

    async def verify_article_integrity(self, s3_key: str) -> bool:
        """
        Verify the integrity of an article by checking its content hash.

        Args:
            s3_key: S3 key for the article

        Returns:
            True if article integrity is verified, False otherwise
        """
        try:
            article = await self.retrieve_article(s3_key)

            # Get stored hash
            stored_hash = article.get("content_hash")
            if not stored_hash:
                logger.warning(f"No content hash found for article: {s3_key}")
                return False

            # Calculate current hash
            content = article.get("content", "")
            current_hash = self._calculate_content_hash(content)

            # Compare hashes
            is_valid = stored_hash == current_hash
            if not is_valid:
                logger.error(f"Content hash mismatch for article: {s3_key}")

            return is_valid

        except Exception as e:
            logger.error(f"Error verifying article integrity {s3_key}: {e}")
            return False

    async def list_articles_by_date(
        self, date: str, article_type: ArticleType, limit: Optional[int] = None
    ) -> List[str]:
        """
        List articles by date and type.

        Args:
            date: Date in YYYY-MM-DD format
            article_type: Type of articles to list
            limit: Maximum number of articles to return

        Returns:
            List of S3 keys
        """
        if not self.s3_client:
            return []

        try:
            # Convert date to S3 prefix
            date_parts = date.split("-")
            if len(date_parts) != 3:
                raise ValueError(f"Invalid date format: {date}")

            year, month, day = date_parts
            prefix = f"{article_type.value}/{year}/{month}/{day}/"

            return await self.list_articles_by_prefix(prefix, limit)

        except Exception as e:
            logger.error(f"Error listing articles by date {date}: {e}")
            return []

    async def list_articles_by_prefix(
        self, prefix: str, limit: Optional[int] = None
    ) -> List[str]:
        """
        List articles by S3 prefix.

        Args:
            prefix: S3 prefix to filter
            limit: Maximum number of articles to return

        Returns:
            List of S3 keys
        """
        if not self.s3_client:
            return []

        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            keys = []

            page_iterator = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)

            for page in page_iterator:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        keys.append(obj["Key"])
                        if limit and len(keys) >= limit:
                            return keys

            return keys

        except Exception as e:
            logger.error(f"Error listing articles by prefix {prefix}: {e}")
            return []

    async def batch_store_raw_articles(
        self, articles: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None
    ) -> List[ArticleMetadata]:
        """
        Store multiple raw articles in batch.

        Args:
            articles: List of article dictionaries
            metadata: Optional metadata to apply to all articles

        Returns:
            List of ArticleMetadata objects
        """
        if not self.s3_client:
            raise ValueError("S3 client not available")

        results = []
        errors = []

        for i, article in enumerate(articles):
            try:
                metadata_result = await self.store_raw_article(article, metadata)
                results.append(metadata_result)
            except Exception as e:
                error_msg = f"Failed to store article {i}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

                # Create error metadata
                article_id = self._generate_article_id(article)
                error_metadata = ArticleMetadata(
                    article_id=article_id,
                    source=article.get("source", "unknown"),
                    url=article.get("url", ""),
                    title=article.get("title", ""),
                    published_date=article.get(
                        "published_date",
                        datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    ),
                    scraped_date=datetime.now(timezone.utc).isoformat(),
                    content_hash="",
                    file_size=0,
                    s3_key="",
                    article_type=ArticleType.RAW,
                    processing_status="error",
                    error_message=str(e),
                )
                results.append(error_metadata)

        if errors:
            logger.warning(f"Batch operation completed with {len(errors)} errors")

        return results

    async def get_storage_statistics(self) -> Dict[str, Any]:
        """
        Get storage statistics for the S3 bucket.

        Returns:
            Dictionary with storage statistics
        """
        if not self.s3_client:
            return {"error": "S3 client not available"}

        try:
            stats = {
                "raw_articles": {"count": 0, "total_size": 0},
                "processed_articles": {"count": 0, "total_size": 0},
                "total_count": 0,
                "total_size": 0,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            # Count raw articles
            raw_keys = await self.list_articles_by_prefix(ArticleType.RAW.value)
            stats["raw_articles"]["count"] = len(raw_keys)

            # Count processed articles
            processed_keys = await self.list_articles_by_prefix(
                ArticleType.PROCESSED.value
            )
            stats["processed_articles"]["count"] = len(processed_keys)

            # Calculate total
            stats["total_count"] = (
                stats["raw_articles"]["count"] + stats["processed_articles"]["count"]
            )

            # Get size information (sample of files for performance)
            sample_keys = raw_keys[:10] + processed_keys[:10]
            total_sample_size = 0

            for key in sample_keys:
                try:
                    response = self.s3_client.head_object(
                        Bucket=self.bucket_name, Key=key
                    )
                    total_sample_size += response.get("ContentLength", 0)
                except Exception:
                    pass

            # Estimate total size
            if sample_keys:
                avg_size = total_sample_size / len(sample_keys)
                stats["total_size"] = int(avg_size * stats["total_count"])
                stats["raw_articles"]["total_size"] = int(
                    avg_size * stats["raw_articles"]["count"]
                )
                stats["processed_articles"]["total_size"] = int(
                    avg_size * stats["processed_articles"]["count"]
                )

            return stats

        except Exception as e:
            logger.error(f"Error getting storage statistics: {e}")
            return {"error": str(e)}

    async def cleanup_old_articles(self, days: int = 365) -> int:
        """
        Clean up articles older than specified days.

        Args:
            days: Number of days to keep articles

        Returns:
            Number of articles deleted
        """
        if not self.s3_client:
            return 0

        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            deleted_count = 0

            # List all articles
            for article_type in [ArticleType.RAW, ArticleType.PROCESSED]:
                keys = await self.list_articles_by_prefix(article_type.value)

                for key in keys:
                    try:
                        response = self.s3_client.head_object(
                            Bucket=self.bucket_name, Key=key
                        )
                        last_modified = response.get("LastModified")

                        if last_modified and last_modified < cutoff_date:
                            self.s3_client.delete_object(
                                Bucket=self.bucket_name, Key=key
                            )
                            deleted_count += 1
                            logger.info(f"Deleted old article: {key}")

                    except Exception as e:
                        logger.error(f"Error processing article {key}: {e}")

            logger.info(f"Cleanup completed: {deleted_count} articles deleted")
            return deleted_count

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0

    def delete_article(self, key: str) -> None:
        """
        Delete an article from S3.

        Args:
            key: S3 key for the article
        """
        if not self.s3_client:
            raise ValueError("S3 client not available")

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"Deleted article: {key}")
        except Exception as e:
            logger.error(f"Error deleting article {key}: {e}")
            raise

    async def export_articles_to_local(
        self,
        local_directory: str,
        date_filter: Optional[str] = None,
        article_type: Optional[ArticleType] = None,
    ) -> int:
        """
        Export articles from S3 to local directory.

        Args:
            local_directory: Local directory to export to
            date_filter: Optional date filter (YYYY-MM-DD)
            article_type: Optional article type filter

        Returns:
            Number of articles exported
        """
        if not self.s3_client:
            return 0

        try:
            os.makedirs(local_directory, exist_ok=True)
            exported_count = 0

            # Determine which articles to export
            if date_filter and article_type:
                keys = await self.list_articles_by_date(date_filter, article_type)
            elif article_type:
                keys = await self.list_articles_by_prefix(article_type.value)
            else:
                keys = []
                for atype in [ArticleType.RAW, ArticleType.PROCESSED]:
                    keys.extend(await self.list_articles_by_prefix(atype.value))

            for key in keys:
                try:
                    # Create local file path
                    local_path = os.path.join(local_directory, key.replace("/", "_"))

                    # Download file
                    self.s3_client.download_file(self.bucket_name, key, local_path)
                    exported_count += 1

                except Exception as e:
                    logger.error(f"Error exporting article {key}: {e}")

            logger.info(f"Exported {exported_count} articles to {local_directory}")
            return exported_count

        except Exception as e:
            logger.error(f"Error during export: {e}")
            return 0


# Backwards compatibility class
class S3Storage(S3ArticleStorage):
    """Backwards compatible S3Storage class."""

    def __init__(
        self,
        bucket_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: str = "us-east-1",
        prefix: str = "news_articles",
    ):
        """Initialize with backwards compatible parameters."""
        config = S3StorageConfig(
            bucket_name=bucket_name,
            region=aws_region,
            raw_prefix=prefix,
            processed_prefix=f"{prefix}_processed",
        )
        super().__init__(config, aws_access_key_id, aws_secret_access_key)
        self.prefix = prefix

    def _generate_s3_key(self, article: Dict[str, Any]) -> str:
        """Legacy _generate_s3_key method for backwards compatibility."""
        # Get date from article or use current date
        if "published_date" in article:
            date_str = article["published_date"]
        else:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Parse date and create directory structure
        date_parts = date_str.split("-")
        if len(date_parts) != 3:
            date_parts = datetime.now(timezone.utc).strftime("%Y-%m-%d").split("-")

        year, month, day = date_parts

        # Generate content hash
        content = f"{article.get('title', '')}{article.get('content', '')}{article.get('url', '')}"
        content_hash = self._calculate_content_hash(content)[:8]

        # Create legacy key structure
        source = article.get("source", "unknown").replace(" ", "-").lower()

        return f"{self.prefix}/{year}/{month}/{day}/{source}/{content_hash}.json"

    def upload_article(self, article: Dict[str, Any]) -> str:
        """Upload article using legacy interface."""
        # Validate required fields for legacy interface
        required_fields = ["title", "content", "source"]
        missing_fields = [field for field in required_fields if not article.get(field)]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        if not self.s3_client:
            raise ValueError("S3 client not available")

        # Add URL if not present (for legacy compatibility)
        enhanced_article = dict(article)
        if "url" not in enhanced_article:
            enhanced_article["url"] = (
                f"legacy://{article.get('source', 'unknown')}/{article.get('title', 'unknown')}"
            )

        # Generate legacy S3 key using our legacy method
        s3_key = self._generate_s3_key(enhanced_article)

        # Add metadata
        enhanced_article.update(
            {
                "scraped_date": datetime.now(timezone.utc).isoformat(),
                "content_hash": self._calculate_content_hash(
                    enhanced_article["content"]
                ),
                "storage_type": "raw",
            }
        )

        # Upload to S3
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(enhanced_article, ensure_ascii=False),
                ContentType="application/json",
            )
            logger.info(f"Successfully uploaded article to S3: {s3_key}")
            return s3_key

        except Exception as e:
            logger.error(f"Failed to upload article to S3: {e}")
            raise

    def get_article(self, key: str) -> Dict[str, Any]:
        """Get article using legacy interface."""
        import asyncio

        return asyncio.run(self.retrieve_article(key))

    def list_articles(self, prefix: Optional[str] = None) -> List[str]:
        """List articles using legacy interface."""
        import asyncio

        prefix = prefix or self.prefix
        return asyncio.run(self.list_articles_by_prefix(prefix))

    def delete_article(self, key: str) -> None:
        """Delete article using legacy interface."""
        if not self.s3_client:
            raise ValueError("S3 client not available")
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)

    def upload_file(self, local_path: str, s3_key: str) -> str:
        """Upload file to S3."""
        if not self.s3_client:
            raise ValueError("S3 client not available")
        self.s3_client.upload_file(local_path, self.bucket_name, s3_key)
        return s3_key

    def download_file(self, s3_key: str, local_path: str) -> None:
        """Download file from S3."""
        if not self.s3_client:
            raise ValueError("S3 client not available")
        self.s3_client.download_file(self.bucket_name, s3_key, local_path)


# S3 Ingestion Functions
async def ingest_scraped_articles_to_s3(
    articles: List[Dict[str, Any]],
    s3_config: S3StorageConfig,
    aws_credentials: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Main S3 ingestion function for scraped articles.

    Args:
        articles: List of scraped articles
        s3_config: S3 storage configuration
        aws_credentials: Optional AWS credentials

    Returns:
        Ingestion results with statistics and any errors
    """
    if not articles:
        return {
            "status": "success",
            "total_articles": 0,
            "stored_articles": 0,
            "errors": [],
        }

    # Initialize S3 storage
    aws_key = aws_credentials.get("aws_access_key_id") if aws_credentials else None
    aws_secret = (
        aws_credentials.get("aws_secret_access_key") if aws_credentials else None
    )

    storage = S3ArticleStorage(s3_config, aws_key, aws_secret)

    # Store articles
    try:
        results = await storage.batch_store_raw_articles(articles)

        # Analyze results
        successful_stores = [r for r in results if r.processing_status == "stored"]
        errors = [r for r in results if r.processing_status == "error"]

        # Get storage statistics
        stats = await storage.get_storage_statistics()

        return {
            "status": "success" if not errors else "partial_success",
            "total_articles": len(articles),
            "stored_articles": len(successful_stores),
            "failed_articles": len(errors),
            "errors": [r.error_message for r in errors if r.error_message],
            "storage_statistics": stats,
            "stored_keys": [r.s3_key for r in successful_stores],
        }

    except Exception as e:
        logger.error(f"Critical error during S3 ingestion: {e}")
        return {
            "status": "error",
            "total_articles": len(articles),
            "stored_articles": 0,
            "failed_articles": len(articles),
            "errors": [str(e)],
            "storage_statistics": {},
        }


async def verify_s3_data_consistency(
    s3_config: S3StorageConfig,
    sample_size: int = 100,
    aws_credentials: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Verify data consistency and integrity of articles stored in S3.

    Args:
        s3_config: S3 storage configuration
        sample_size: Number of articles to sample for verification
        aws_credentials: Optional AWS credentials

    Returns:
        Verification results with statistics
    """
    # Initialize S3 storage
    aws_key = aws_credentials.get("aws_access_key_id") if aws_credentials else None
    aws_secret = (
        aws_credentials.get("aws_secret_access_key") if aws_credentials else None
    )

    storage = S3ArticleStorage(s3_config, aws_key, aws_secret)

    try:
        # Get sample of articles
        raw_keys = await storage.list_articles_by_prefix(
            ArticleType.RAW.value, limit=sample_size // 2
        )
        processed_keys = await storage.list_articles_by_prefix(
            ArticleType.PROCESSED.value, limit=sample_size // 2
        )

        all_keys = raw_keys + processed_keys

        if not all_keys:
            return {
                "status": "success",
                "message": "No articles found to verify",
                "total_checked": 0,
                "valid_articles": 0,
                "invalid_articles": 0,
                "errors": [],
            }

        # Verify each article
        valid_count = 0
        invalid_count = 0
        errors = []

        for key in all_keys:
            try:
                is_valid = await storage.verify_article_integrity(key)
                if is_valid:
                    valid_count += 1
                else:
                    invalid_count += 1
                    errors.append(f"Integrity check failed for: {key}")

            except Exception as e:
                invalid_count += 1
                errors.append(f"Error verifying {key}: {str(e)}")

        # Get overall statistics
        stats = await storage.get_storage_statistics()

        return {
            "status": "success" if invalid_count == 0 else "warning",
            "message": f"Verified {len(all_keys)} articles",
            "total_checked": len(all_keys),
            "valid_articles": valid_count,
            "invalid_articles": invalid_count,
            "integrity_rate": (valid_count / len(all_keys)) * 100 if all_keys else 0,
            "errors": errors,
            "storage_statistics": stats,
        }

    except Exception as e:
        logger.error(f"Error during data consistency verification: {e}")
        return {
            "status": "error",
            "message": f"Verification failed: {str(e)}",
            "total_checked": 0,
            "valid_articles": 0,
            "invalid_articles": 0,
            "errors": [str(e)],
        }
