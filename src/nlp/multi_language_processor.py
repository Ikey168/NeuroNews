"""
Multi-language article processor that handles language detection, translation, and storage.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

from .article_processor import ArticleProcessor
from .language_processor import (
    AWSTranslateService,
    LanguageDetector,
    TranslationQualityChecker,
)

logger = logging.getLogger(__name__)


class MultiLanguageArticleProcessor(ArticleProcessor):
    def detect_and_store_language(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        # Simulate detection and storage
        detection = self.language_detector.detect_language(
            article_data.get("content", "")
        )
        result = {
            "detected_language": detection.get("language"),
            "confidence": detection.get("confidence"),
        }
        # Optionally store detection
        self.store_language_detection(
            {
                "article_id": article_data.get("id"),
                "detected_language": detection.get("language"),
                "confidence": detection.get("confidence"),
            }
        )
        return result

    def translate_article(
        self, article_data: Dict[str, Any], source_language: str, target_language: str
    ) -> Dict[str, Any]:
        # Use the translation service
        translation = self.translate_service.translate_text(
            article_data.get("content", ""), source_language, target_language
        )
        result = {
            "translated_text": translation.get("translated_text"),
            "error": translation.get("error"),
        }
        if translation.get("translated_text"):
            result["translated_content"] = translation.get("translated_text")
        return result

    def update_language_stats(self, lang: str):
        # Simulate updating language distribution
        if not hasattr(self, "language_distribution"):
            self.language_distribution = {}
        self.language_distribution[lang] = self.language_distribution.get(lang, 0) + 1

    def get_processing_statistics(self) -> Dict[str, Any]:
        # Return language distribution stats
        return {"language_distribution": getattr(self, "language_distribution", {})}

    """
    Extended article processor that handles multi-language content.
    Detects language, translates non-English content, and stores both versions.
    """

    def __init__(
        self,
        redshift_host: str,
        redshift_port: int,
        redshift_database: str,
        redshift_user: str,
        redshift_password: str,
        aws_region: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        target_language: str = "en",
        translation_enabled: bool = True,
        quality_threshold: float = 0.7,
        **kwargs,
    ):
        """
        Initialize multi-language article processor.

        Args:
            redshift_host: Redshift cluster host
            redshift_port: Redshift port
            redshift_database: Database name
            redshift_user: Database user
            redshift_password: Database password
            aws_region: AWS region for translate service
            aws_access_key_id: AWS access key ID
            aws_secret_access_key: AWS secret access key
            target_language: Target language for translations (default: 'en')
            translation_enabled: Whether to enable translation
            quality_threshold: Minimum quality score for accepting translations
            **kwargs: Additional arguments for parent class
        """
        # Initialize parent class
        super().__init__(
            redshift_host,
            redshift_port,
            redshift_database,
            redshift_user,
            redshift_password,
            **kwargs,
        )

        # Initialize language processing components
        self.target_language = target_language
        self.translation_enabled = translation_enabled
        self.quality_threshold = quality_threshold

        self.language_detector = LanguageDetector(fallback_language=target_language)

        if translation_enabled:
            self.translate_service = AWSTranslateService(
                region_name=aws_region,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
            )
        else:
            self.translate_service = None

        self.quality_checker = TranslationQualityChecker()

        # Create translation tables if they don't exist
        self._create_translation_tables()

    def _create_translation_tables(self):
        """Create database tables for storing translations if they don't exist."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    # Article translations table
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS article_translations (
                            id SERIAL PRIMARY KEY,
                            article_id VARCHAR(255) NOT NULL,
                            original_language VARCHAR(10) NOT NULL,
                            target_language VARCHAR(10) NOT NULL,
                            original_title TEXT,
                            translated_title TEXT,
                            original_content TEXT,
                            translated_content TEXT,
                            translation_quality_score FLOAT,
                            translation_confidence FLOAT,
                            translation_issues TEXT,
                            translation_recommendations TEXT,
                            translated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            translation_provider VARCHAR(50) DEFAULT 'aws_translate',
                            UNIQUE(article_id, target_language)
                        )
                    """
                    )

                    # Language detection results table
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS language_detections (
                            id SERIAL PRIMARY KEY,
                            article_id VARCHAR(255) NOT NULL,
                            detected_language VARCHAR(10) NOT NULL,
                            detection_confidence FLOAT,
                            detection_method VARCHAR(50),
                            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            text_length INTEGER,
                            UNIQUE(article_id)
                        )
                    """
                    )

                    conn.commit()
                    logger.info("Translation tables created successfully")

        except Exception as e:
            logger.error(f"Error creating translation tables: {e}")
            raise

    def process_article(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process article with multi-language support.

        Args:
            article_data: Article data dictionary

        Returns:
            Processing result with translation information
        """
        article_id = article_data.get("id") or self._generate_article_id(article_data)
        title = article_data.get("title", "")
        content = article_data.get("content", "")

        logger.info(f"Processing article {article_id} with multi-language support")

        result = {
            "article_id": article_id,
            "original_language": None,
            "translation_performed": False,
            "translation_quality": None,
            "errors": [],
        }

        try:
            # Step 1: Detect language
            text_to_analyze = f"{title} {content}".strip()
            detected_language, confidence = self.language_detector.detect_language(
                text_to_analyze
            )

            # Store language detection result
            self._store_language_detection(
                article_id,
                detected_language,
                confidence,
                "local_heuristic",
                len(text_to_analyze),
            )

            result["original_language"] = detected_language
            result["detection_confidence"] = confidence

            logger.info(
                f"Detected language: {detected_language} (confidence: {confidence:.2f})"
            )

            # Step 2: Translate if needed
            if (
                self.translation_enabled
                and detected_language != self.target_language
                and self.translate_service
            ):

                translation_result = self._translate_article(
                    article_id, title, content, detected_language
                )
                result.update(translation_result)

            # Step 3: Process with sentiment analysis (use translated text if available)
            processing_text = result.get("translated_content", content)
            processing_title = result.get("translated_title", title)

            # Create modified article data for processing
            processed_article = article_data.copy()
            processed_article.update(
                {
                    "title": processing_title,
                    "content": processing_text,
                    "original_language": detected_language,
                    "processed_language": (
                        self.target_language
                        if result["translation_performed"]
                        else detected_language
                    ),
                }
            )

            # Call parent class processing
            sentiment_result = super().process_article([processed_article])
            result["sentiment_analysis"] = sentiment_result

            logger.info(f"Successfully processed article {article_id}")

        except Exception as e:
            error_msg = f"Error processing article {article_id}: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        return result

    def _translate_article(
        self, article_id: str, title: str, content: str, source_language: str
    ) -> Dict[str, Any]:
        """
        Translate article title and content.

        Args:
            article_id: Article identifier
            title: Article title
            content: Article content
            source_language: Source language code

        Returns:
            Translation result dictionary
        """
        result = {
            "translation_performed": False,
            "translated_title": title,
            "translated_content": content,
            "translation_quality": None,
        }

        try:
            # Translate title
            title_translation = self.translate_service.translate_text(
                title, source_language, self.target_language
            )

            # Translate content
            content_translation = self.translate_service.translate_text(
                content, source_language, self.target_language
            )

            if title_translation["error"] or content_translation["error"]:
                logger.warning(
                    f"Translation errors: title={title_translation['error']}, content={content_translation['error']}"
                )
                return result

            # Check translation quality
            title_quality = self.quality_checker.check_translation_quality(
                title,
                title_translation["translated_text"],
                source_language,
                self.target_language,
            )

            content_quality = self.quality_checker.check_translation_quality(
                content,
                content_translation["translated_text"],
                source_language,
                self.target_language,
            )

            # Calculate overall quality score
            overall_quality = (
                title_quality["quality_score"] + content_quality["quality_score"]
            ) / 2

            # Only accept translation if quality is above threshold
            if overall_quality >= self.quality_threshold:
                result.update(
                    {
                        "translation_performed": True,
                        "translated_title": title_translation["translated_text"],
                        "translated_content": content_translation["translated_text"],
                        "translation_quality": overall_quality,
                    }
                )

                # Store translation in database
                self._store_translation(
                    article_id,
                    source_language,
                    self.target_language,
                    title,
                    title_translation["translated_text"],
                    content,
                    content_translation["translated_text"],
                    overall_quality,
                    title_translation["confidence"],
                    title_quality["issues"] + content_quality["issues"],
                    title_quality["recommendations"]
                    + content_quality["recommendations"],
                )

                logger.info(
                    f"Translation completed with quality score: {overall_quality:.2f}"
                )

            else:
                logger.warning(
                    f"Translation quality too low: {overall_quality:.2f} < {self.quality_threshold}"
                )

        except Exception as e:
            logger.error(f"Error translating article {article_id}: {e}")
            result["translation_error"] = str(e)

        return result

    def _store_language_detection(
        self,
        article_id: str,
        detected_language: str,
        confidence: float,
        method: str,
        text_length: int,
    ):
        """Store language detection result in database."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO language_detections 
                        (article_id, detected_language, detection_confidence, detection_method, text_length)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (article_id) DO UPDATE SET
                            detected_language = EXCLUDED.detected_language,
                            detection_confidence = EXCLUDED.detection_confidence,
                            detection_method = EXCLUDED.detection_method,
                            text_length = EXCLUDED.text_length,
                            detected_at = CURRENT_TIMESTAMP
                    """,
                        (
                            article_id,
                            detected_language,
                            confidence,
                            method,
                            text_length,
                        ),
                    )

                    conn.commit()

        except Exception as e:
            logger.error(f"Error storing language detection: {e}")

    def _store_translation(
        self,
        article_id: str,
        original_language: str,
        target_language: str,
        original_title: str,
        translated_title: str,
        original_content: str,
        translated_content: str,
        quality_score: float,
        confidence: float,
        issues: List[str],
        recommendations: List[str],
    ):
        """Store translation result in database."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO article_translations 
                        (article_id, original_language, target_language, original_title, translated_title,
                         original_content, translated_content, translation_quality_score, translation_confidence,
                         translation_issues, translation_recommendations)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (article_id, target_language) DO UPDATE SET
                            original_language = EXCLUDED.original_language,
                            original_title = EXCLUDED.original_title,
                            translated_title = EXCLUDED.translated_title,
                            original_content = EXCLUDED.original_content,
                            translated_content = EXCLUDED.translated_content,
                            translation_quality_score = EXCLUDED.translation_quality_score,
                            translation_confidence = EXCLUDED.translation_confidence,
                            translation_issues = EXCLUDED.translation_issues,
                            translation_recommendations = EXCLUDED.translation_recommendations,
                            translated_at = CURRENT_TIMESTAMP
                    """,
                        (
                            article_id,
                            original_language,
                            target_language,
                            original_title,
                            translated_title,
                            original_content,
                            translated_content,
                            quality_score,
                            confidence,
                            json.dumps(issues),
                            json.dumps(recommendations),
                        ),
                    )

                    conn.commit()

        except Exception as e:
            logger.error(f"Error storing translation: {e}")

    def _generate_article_id(self, article_data: Dict[str, Any]) -> str:
        """Generate a unique article ID based on article content."""
        content_hash = hashlib.md5(
            f"{article_data.get('url', '')}{article_data.get('title', '')}".encode()
        ).hexdigest()
        return f"article_{content_hash[:12]}"

    def get_translation_statistics(self) -> Dict[str, Any]:
        """Get translation statistics from the database."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Language distribution
                    cursor.execute(
                        """
                        SELECT detected_language, COUNT(*) as count
                        FROM language_detections
                        GROUP BY detected_language
                        ORDER BY count DESC
                    """
                    )
                    language_distribution = dict(cursor.fetchall())

                    # Translation success rates
                    cursor.execute(
                        """
                        SELECT 
                            original_language,
                            target_language,
                            COUNT(*) as translation_count,
                            AVG(translation_quality_score) as avg_quality,
                            AVG(translation_confidence) as avg_confidence
                        FROM article_translations
                        GROUP BY original_language, target_language
                        ORDER BY translation_count DESC
                    """
                    )
                    translation_stats = cursor.fetchall()

                    # Quality distribution
                    cursor.execute(
                        """
                        SELECT 
                            CASE 
                                WHEN translation_quality_score >= 0.8 THEN 'high'
                                WHEN translation_quality_score >= 0.6 THEN 'medium'
                                ELSE 'low'
                            END as quality_category,
                            COUNT(*) as count
                        FROM article_translations
                        GROUP BY quality_category
                    """
                    )
                    quality_distribution = dict(cursor.fetchall())

                    return {
                        "language_distribution": language_distribution,
                        "translation_stats": [dict(row) for row in translation_stats],
                        "quality_distribution": quality_distribution,
                        "total_articles_processed": sum(language_distribution.values()),
                        "total_translations": sum(
                            row["translation_count"] for row in translation_stats
                        ),
                    }

        except Exception as e:
            logger.error(f"Error getting translation statistics: {e}")
            return {}

    def process_batch(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a batch of articles with multi-language support.

        Args:
            articles: List of article dictionaries

        Returns:
            List of processing results
        """
        results = []

        logger.info(f"Processing batch of {len(articles)} articles")

        for i, article in enumerate(articles):
            try:
                result = self.process_article(article)
                results.append(result)

                if (i + 1) % 10 == 0:
                    logger.info(f"Processed {i + 1}/{len(articles)} articles")

            except Exception as e:
                logger.error(f"Error processing article {i}: {e}")
                results.append(
                    {"article_id": article.get("id", f"unknown_{i}"), "error": str(e)}
                )

        logger.info(f"Completed batch processing: {len(results)} results")
        return results

    def create_language_detection_table(self) -> bool:
        """
        Create the language detection table in the database.

        Returns:
            True if successful, False otherwise
        """
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS language_detections (
            id BIGINT IDENTITY(1,1) PRIMARY KEY,
            article_id VARCHAR(255) NOT NULL,
            detected_language VARCHAR(10),
            detection_confidence DECIMAL(5,3),
            detection_method VARCHAR(50),
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_article_id (article_id),
            INDEX idx_detected_language (detected_language),
            INDEX idx_detection_confidence (detection_confidence)
        );
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(create_table_sql)
                self.connection.commit()
                logger.info("Language detection table created successfully")
                return True
        except Exception as e:
            logger.error(f"Error creating language detection table: {e}")
            return False

    def create_translation_table(self) -> bool:
        """
        Create the translation table in the database.

        Returns:
            True if successful, False otherwise
        """
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS article_translations (
            id BIGINT IDENTITY(1,1) PRIMARY KEY,
            article_id VARCHAR(255) NOT NULL,
            original_language VARCHAR(10),
            target_language VARCHAR(10),
            original_title TEXT,
            translated_title TEXT,
            original_content TEXT,
            translated_content TEXT,
            translation_quality_score DECIMAL(5,3),
            translation_issues TEXT,
            translated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_article_id (article_id),
            INDEX idx_original_language (original_language),
            INDEX idx_target_language (target_language),
            INDEX idx_quality_score (translation_quality_score)
        );
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(create_table_sql)
                self.connection.commit()
                logger.info("Translation table created successfully")
                return True
        except Exception as e:
            logger.error(f"Error creating translation table: {e}")
            return False

    def store_language_detection(self, detection_data: Dict[str, Any]) -> bool:
        """
        Store language detection results in the database.

        Args:
            detection_data: Dictionary with detection results

        Returns:
            True if successful, False otherwise
        """
        insert_sql = """
        INSERT INTO language_detections 
        (article_id, detected_language, detection_confidence, detection_method)
        VALUES (%s, %s, %s, %s);
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    insert_sql,
                    (
                        detection_data.get("article_id"),
                        detection_data.get("detected_language"),
                        detection_data.get("confidence"),
                        detection_data.get("method", "pattern_based"),
                    ),
                )
                self.connection.commit()
                logger.debug(
                    f"Language detection stored for article {detection_data.get('article_id')}"
                )
                return True
        except Exception as e:
            logger.error(f"Error storing language detection: {e}")
            return False

    def store_translation(self, translation_data: Dict[str, Any]) -> bool:
        """
        Store translation results in the database.

        Args:
            translation_data: Dictionary with translation results

        Returns:
            True if successful, False otherwise
        """
        insert_sql = """
        INSERT INTO article_translations 
        (article_id, original_language, target_language, original_title, 
         translated_title, original_content, translated_content, 
         translation_quality_score, translation_issues)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    insert_sql,
                    (
                        translation_data.get("article_id"),
                        translation_data.get("original_language"),
                        translation_data.get("target_language"),
                        translation_data.get("original_title"),
                        translation_data.get("translated_title"),
                        translation_data.get("original_content"),
                        translation_data.get("translated_content"),
                        translation_data.get("quality_score"),
                        json.dumps(translation_data.get("issues", [])),
                    ),
                )
                self.connection.commit()
                logger.debug(
                    f"Translation stored for article {translation_data.get('article_id')}"
                )
                return True
        except Exception as e:
            logger.error(f"Error storing translation: {e}")
            return False
