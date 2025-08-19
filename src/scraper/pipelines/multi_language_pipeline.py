"""
Scrapy pipeline for multi-language article processing.
"""

import logging
import os
from typing import Any, Dict, Optional

from scrapy.exceptions import DropItem

from src.nlp.multi_language_processor import MultiLanguageArticleProcessor
from src.scraper.items import NewsItem

logger = logging.getLogger(__name__)


class MultiLanguagePipeline:
    """
    Scrapy pipeline that processes articles with multi-language support.
    Detects language, translates non-English content, and stores results.
    """

    def __init__(
        self,
        redshift_host: str = None,
        redshift_port: int = 5439,
        redshift_database: str = None,
        redshift_user: str = None,
        redshift_password: str = None,
        aws_region: str = "us-east-1",
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        target_language: str = "en",
        translation_enabled: bool = True,
        quality_threshold: float = 0.7,
        min_content_length: int = 100,
    ):
        """
        Initialize multi-language pipeline.

        Args:
            redshift_host: Redshift cluster host
            redshift_port: Redshift port
            redshift_database: Database name
            redshift_user: Database user
            redshift_password: Database password
            aws_region: AWS region for translate service
            aws_access_key_id: AWS access key ID
            aws_secret_access_key: AWS secret access key
            target_language: Target language for translations
            translation_enabled: Whether to enable translation
            quality_threshold: Minimum quality score for accepting translations
            min_content_length: Minimum content length for processing
        """
        # Use environment variables as fallback
        self.redshift_host = redshift_host or os.getenv("REDSHIFT_HOST")
        self.redshift_port = redshift_port
        self.redshift_database = redshift_database or os.getenv("REDSHIFT_DATABASE")
        self.redshift_user = redshift_user or os.getenv("REDSHIFT_USER")
        self.redshift_password = redshift_password or os.getenv("REDSHIFT_PASSWORD")
        self.aws_region = aws_region
        self.aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = aws_secret_access_key or os.getenv(
            "AWS_SECRET_ACCESS_KEY"
        )
        self.enabled = True
        self.target_language = target_language
        self.translation_enabled = translation_enabled
        self.quality_threshold = quality_threshold
        self.min_content_length = min_content_length
        self.processor = None
        self.stats = {
            "items_processed": 0,
            "items_translated": 0,
            "items_dropped": 0,
            "translation_errors": 0,
            "language_distribution": {},
        }

    def open_spider(self, spider):
        """Initialize pipeline when spider opens."""
        logger.info("Opening multi-language pipeline")

        # Validate required settings
        required_settings = [
            self.redshift_host,
            self.redshift_database,
            self.redshift_user,
            self.redshift_password,
        ]

        if not all(required_settings):
            logger.error("Missing required Redshift configuration")
            raise ValueError("Missing required Redshift configuration")

        # Initialize processor
        try:
            self.processor = MultiLanguageArticleProcessor(
                redshift_host=self.redshift_host,
                redshift_port=self.redshift_port,
                redshift_database=self.redshift_database,
                redshift_user=self.redshift_user,
                redshift_password=self.redshift_password,
                aws_region=self.aws_region,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                target_language=self.target_language,
                translation_enabled=self.translation_enabled,
                quality_threshold=self.quality_threshold,
            )

            logger.info(f"Multi-language processor initialized successfully")
            logger.info(f"Translation enabled: {self.translation_enabled}")
            logger.info(f"Target language: {self.target_language}")

        except Exception as e:
            logger.error(f"Failed to initialize multi-language processor: {e}")
            raise

    def close_spider(self, spider):
        """Cleanup when spider closes."""
        logger.info("Closing multi-language pipeline")

        # Log final statistics
        logger.info(f"Pipeline statistics:")
        logger.info(f"  Items processed: {self.stats['items_processed']}")
        logger.info(f"  Items translated: {self.stats['items_translated']}")
        logger.info(f"  Items dropped: {self.stats['items_dropped']}")
        logger.info(
            f"  Translation errors: {
                self.stats['translation_errors']}"
        )
        logger.info(
            f"  Language distribution: {
                self.stats['language_distribution']}"
        )

        # Get detailed statistics from processor
        if self.processor:
            try:
                detailed_stats = self.processor.get_translation_statistics()
                logger.info(f"Detailed translation statistics: {detailed_stats}")
            except Exception as e:
                logger.error(f"Error getting detailed statistics: {e}")

    def process_item(self, item: NewsItem, spider) -> NewsItem:
        """
        Process a scraped news item with multi-language support.

        Args:
            item: Scraped news item
            spider: Spider instance

        Returns:
            Processed news item

        Raises:
            DropItem: If item should be dropped
        """
        # If pipeline is disabled, return item unchanged
        if not self.enabled:
            return item
        # Validate item
        if not self._validate_item(item):
            self.stats["items_dropped"] += 1
            raise DropItem("Item validation failed")
        try:
            # Convert item to dictionary
            article_data = {
                "id": item.get("url"),  # Use URL as unique identifier
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "published_date": item.get("published_date"),
                "author": item.get("author", ""),
                "category": item.get("category", ""),
            }

            # Process with multi-language support
            result = self.processor.process_article(article_data)

            # Update statistics
            self.stats["items_processed"] += 1

            if result.get("original_language"):
                lang = result["original_language"]
                self.stats["language_distribution"][lang] = (
                    self.stats["language_distribution"].get(lang, 0) + 1
                )

            if result.get("translation_performed"):
                self.stats["items_translated"] += 1

            if result.get("errors"):
                self.stats["translation_errors"] += 1
                logger.warning(
                    f"Translation errors for {
                        article_data['id']}: {
                        result['errors']}"
                )

            # Add processing metadata to item
            item["original_language"] = result.get("original_language")
            item["detection_confidence"] = result.get("detection_confidence")
            item["translation_performed"] = result.get("translation_performed", False)
            item["translation_quality"] = result.get("translation_quality")

            # Add translated content if available
            if result.get("translation_performed"):
                item["translated_title"] = result.get("translated_title")
                item["translated_content"] = result.get("translated_content")
                item["target_language"] = self.target_language

            logger.info(
                f"Successfully processed article: {article_data['id']} "
                f"(language: {result.get('original_language')}, "
                f"translated: {result.get('translation_performed')})"
            )

            return item

        except Exception as e:
            self.stats["items_dropped"] += 1
            logger.error(
                f"Error processing item {
                    item.get(
                        'url',
                        'unknown')}: {e}"
            )
            raise DropItem(f"Processing failed: {str(e)}")

    def _validate_item(self, item: NewsItem) -> bool:
        """
        Validate that the item has required fields and meets quality criteria.

        Args:
            item: News item to validate

        Returns:
            True if item is valid, False otherwise
        """
        # Check required fields
        required_fields = ["title", "content", "url"]
        for field in required_fields:
            if not item.get(field):
                logger.warning(f"Missing required field: {field}")
                return False

        # Check content length
        content = item.get("content", "")
        if len(content.strip()) < self.min_content_length:
            logger.warning(
                f"Content too short: {
                    len(content)} < {
                    self.min_content_length}"
            )
            return False

        # Check for valid URL
        url = item.get("url", "")
        if not url.startswith(("http://", "https://")):
            logger.warning(f"Invalid URL: {url}")
            return False

        return True


class LanguageFilterPipeline:
    def _get_original_language(self, item: Dict[str, Any]) -> str:
        # Return detected language from item['language_info'] if present
        info = item.get("language_info", {})
        return info.get("detected_language", "unknown")

    """
    Pipeline that filters articles based on detected language.
    """

    def __init__(
        self,
        allowed_languages: Optional[list] = None,
        blocked_languages: Optional[list] = None,
        require_translation: bool = False,
    ):
        """
        Initialize language filter pipeline.

        Args:
            allowed_languages: List of allowed language codes (None = allow all)
            blocked_languages: List of blocked language codes
            require_translation: Whether to require translated content
        """
        self.allowed_languages = set(allowed_languages) if allowed_languages else None
        self.blocked_languages = set(blocked_languages) if blocked_languages else set()
        self.require_translation = require_translation

        self.stats = {"items_passed": 0, "items_filtered": 0, "filter_reasons": {}}

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline instance from crawler settings."""
        settings = crawler.settings

        # Add settings to the MultiLanguagePipeline instance
        return MultiLanguagePipeline(
            redshift_host=settings.get("REDSHIFT_HOST"),
            redshift_port=settings.getint("REDSHIFT_PORT", 5439),
            redshift_database=settings.get("REDSHIFT_DATABASE"),
            redshift_user=settings.get("REDSHIFT_USER"),
            redshift_password=settings.get("REDSHIFT_PASSWORD"),
            aws_region=settings.get("AWS_REGION", "us-east-1"),
            aws_access_key_id=settings.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=settings.get("AWS_SECRET_ACCESS_KEY"),
            target_language=settings.get("TARGET_LANGUAGE", "en"),
            translation_enabled=settings.getbool("TRANSLATION_ENABLED", True),
            quality_threshold=settings.getfloat("TRANSLATION_QUALITY_THRESHOLD", 0.7),
            min_content_length=settings.getint("MIN_CONTENT_LENGTH", 100),
        )

        return cls(
            allowed_languages=settings.getlist("ALLOWED_LANGUAGES"),
            blocked_languages=settings.getlist("BLOCKED_LANGUAGES"),
            require_translation=settings.getbool("REQUIRE_TRANSLATION", False),
        )

    def close_spider(self, spider):
        """Log statistics when spider closes."""
        logger.info("Language filter pipeline statistics:")
        logger.info(f"  Items passed: {self.stats['items_passed']}")
        logger.info(f"  Items filtered: {self.stats['items_filtered']}")
        logger.info(f"  Filter reasons: {self.stats['filter_reasons']}")

    def process_item(self, item: NewsItem, spider) -> NewsItem:
        """
        Filter item based on language criteria.

        Args:
            item: News item to filter
            spider: Spider instance

        Returns:
            News item if it passes filters

        Raises:
            DropItem: If item should be filtered out
        """
        original_language = item.get("original_language")
        translation_performed = item.get("translation_performed", False)

        # Check if language is blocked
        if original_language in self.blocked_languages:
            self._record_filter_reason("blocked_language")
            raise DropItem(f"Language {original_language} is blocked")

        # Check if language is allowed
        if self.allowed_languages and original_language not in self.allowed_languages:
            self._record_filter_reason("language_not_allowed")
            raise DropItem(f"Language {original_language} not in allowed list")

        # Check translation requirement
        if self.require_translation and not translation_performed:
            self._record_filter_reason("translation_required")
            raise DropItem("Translation required but not performed")

        self.stats["items_passed"] += 1
        return item

    def _record_filter_reason(self, reason: str):
        """Record why an item was filtered."""
        self.stats["items_filtered"] += 1
        self.stats["filter_reasons"][reason] = (
            self.stats["filter_reasons"].get(reason, 0) + 1
        )
