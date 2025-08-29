"""
Enhanced Article Processor with Named Entity Recognition (NER) capabilities.
Extends the base ArticleProcessor to include entity extraction and storage.
"""

import json
import logging
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import execute_batch

from .article_processor import ArticleProcessor
from .ner_processor import create_ner_processor

logger = logging.getLogger(__name__)


class NERArticleProcessor(ArticleProcessor):
    """
    Enhanced article processor that includes Named Entity Recognition.

    Processes articles for both sentiment analysis and entity extraction,
    storing results in AWS Redshift.
    """

    def __init__(
        self,
        snowflake_account: str,
        snowflake_user: str,
        snowflake_password: str,
        snowflake_warehouse: str = "ANALYTICS_WH",
        snowflake_database: str = "NEURONEWS", 
        snowflake_schema: str = "PUBLIC",
        sentiment_provider: str = "aws",
        ner_model: str = "dbmdz/bert-large-cased-finetuned-conll03-english",
        ner_enabled: bool = True,
        ner_confidence_threshold: float = 0.7,
        batch_size: int = 25,
        **kwargs,
    ):
        """
        Initialize the NER-enabled article processor.

        Args:
            snowflake_account: Snowflake account identifier
            snowflake_user: Database user
            snowflake_password: Database password
            snowflake_warehouse: Snowflake warehouse name
            snowflake_database: Database name
            snowflake_schema: Schema name
            sentiment_provider: Which sentiment analyzer to use
            ner_model: Pre-trained NER model name
            ner_enabled: Whether to enable NER processing
            ner_confidence_threshold: Minimum confidence for entity extraction
            batch_size: Batch size for processing
            **kwargs: Additional arguments
        """
        # Initialize parent class
        super().__init__(
            snowflake_account=snowflake_account,
            snowflake_user=snowflake_user,
            snowflake_password=snowflake_password,
            snowflake_warehouse=snowflake_warehouse,
            snowflake_database=snowflake_database,
            snowflake_schema=snowflake_schema,
            sentiment_provider=sentiment_provider,
            batch_size=batch_size,
            **kwargs,
        )

        self.ner_enabled = ner_enabled

        # Initialize NER processor if enabled
        if self.ner_enabled:
            try:
                self.ner_processor = create_ner_processor(
                    model_name=ner_model, confidence_threshold=ner_confidence_threshold
                )
                logger.info(
                    "Initialized NER processor with model: {0}".format(ner_model)
                )
            except Exception as e:
                logger.error("Failed to initialize NER processor: {0}".format(e))
                logger.warning("Continuing without NER capabilities")
                self.ner_enabled = False
                self.ner_processor = None
        else:
            self.ner_processor = None
            logger.info("NER processing disabled")

        # Initialize enhanced database schema
        self._initialize_ner_database()

    def _initialize_ner_database(self):
        """Initialize database tables with NER support."""
        # Call parent initialization first
        super()._initialize_database()

        # Add NER-specific tables
        create_ner_tables_sql = """
        -- Table for storing extracted entities
        CREATE TABLE IF NOT EXISTS article_entities (
            id BIGINT IDENTITY(1,1) PRIMARY KEY,
            article_id VARCHAR(255) NOT NULL,
            entity_text VARCHAR(500) NOT NULL,
            entity_type VARCHAR(50) NOT NULL,
            confidence FLOAT NOT NULL,
            start_position INTEGER,
            end_position INTEGER,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (article_id) REFERENCES article_sentiment(article_id)
        );

        -- Index for efficient querying
        CREATE INDEX IF NOT EXISTS idx_article_entities_article_id ON article_entities(article_id);
        CREATE INDEX IF NOT EXISTS idx_article_entities_type ON article_entities(entity_type);
        CREATE INDEX IF NOT EXISTS idx_article_entities_text ON article_entities(entity_text);

        -- View for entity statistics
        CREATE OR REPLACE VIEW entity_statistics AS
        SELECT
            entity_type,
            COUNT(*) as entity_count,
            COUNT(DISTINCT article_id) as article_count,
            AVG(confidence) as avg_confidence,
            MIN(confidence) as min_confidence,
            MAX(confidence) as max_confidence
        FROM article_entities
        GROUP BY entity_type
        ORDER BY entity_count DESC;

        -- View for most common entities
        CREATE OR REPLACE VIEW common_entities AS
        SELECT
            entity_text,
            entity_type,
            COUNT(*) as frequency,
            AVG(confidence) as avg_confidence,
            COUNT(DISTINCT article_id) as article_count
        FROM article_entities
        GROUP BY entity_text, entity_type
        HAVING COUNT(*) >= 2
        ORDER BY frequency DESC, avg_confidence DESC;
        """

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    cur.execute(create_ner_tables_sql)
                    conn.commit()
                    logger.info("Successfully initialized NER database tables")
        except Exception as e:
            logger.error("Failed to initialize NER database: {0}".format(e))
            # Don't raise - continue without NER tables

    def process_articles(self, articles: List[Dict]) -> List[Dict]:
        """
        Process articles with both sentiment analysis and NER.

        Args:
            articles: List of article dictionaries

        Returns:
            List of processed results including sentiment and entities
        """
        try:
            logger.info(
                "Processing {0} articles with NER enabled: {1}".format(
                    len(articles), self.ner_enabled
                )
            )

            # First, process with sentiment analysis (parent class)
            sentiment_results = super().process_articles(articles)

            # If NER is disabled, return sentiment results only
            if not self.ner_enabled:
                return sentiment_results

            # Extract entities for each article
            enhanced_results = []
            entity_batch = []

            for article, sentiment_result in zip(articles, sentiment_results):
                # Combine title and content for entity extraction
                full_text = f"{article.get('title', '')}. {article.get('content', '')}"

                # Extract entities
                entities = self.ner_processor.extract_entities(
                    text=full_text, article_id=article["article_id"]
                )

                # Prepare entities for batch storage
                for entity in entities:
                    entity_record = {
                        "article_id": article["article_id"],
                        "entity_text": entity["text"],
                        "entity_type": entity["type"],
                        "confidence": entity["confidence"],
                        "start_position": entity.get("start_position"),
                        "end_position": entity.get("end_position"),
                    }
                    entity_batch.append(entity_record)

                # Enhance sentiment result with entity information
                enhanced_result = sentiment_result.copy()
                enhanced_result["entities"] = entities
                enhanced_result["entity_count"] = len(entities)
                enhanced_result["entity_types"] = list(set(e["type"] for e in entities))

                enhanced_results.append(enhanced_result)

            # Store entities in database
            if entity_batch:
                self._store_entities(entity_batch)

            # Update news_articles table with entities JSON
            self._update_articles_with_entities(enhanced_results)

            logger.info(
                "Successfully processed {0} articles with {1} entities".format(
                    len(articles), len(entity_batch)
                )
            )
            return enhanced_results

        except Exception as e:
            logger.error("Error in NER article processing: {0}".format(e))
            # Fall back to sentiment-only processing
            if hasattr(super(), "process_articles"):
                return super().process_articles(articles)
            raise

    def _store_entities(self, entities: List[Dict]):
        """Store extracted entities in the database."""
        if not entities:
            return

        insert_sql = """
        INSERT INTO article_entities (
            article_id, entity_text, entity_type, confidence,
            start_position, end_position
        ) VALUES (
            %(article_id)s, %(entity_text)s, %(entity_type)s, %(confidence)s,
            %(start_position)s, %(end_position)s
        );
        """

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    execute_batch(cur, insert_sql, entities, page_size=self.batch_size)
                    conn.commit()
                    logger.info(
                        "Successfully stored {0} entities".format(len(entities))
                    )
        except Exception as e:
            logger.error("Failed to store entities: {0}".format(e))
            # Don't raise - continue processing

    def _update_articles_with_entities(self, results: List[Dict]):
        """Update the main news_articles table with entity JSON."""
        if not results:
            return

        # Prepare updates for news_articles table
        updates = []
        for result in results:
            if "entities" in result:
                # Convert entities to JSON format for storage
                entities_json = json.dumps(
                    [
                        {
                            "text": entity["text"],
                            "type": entity["type"],
                            "confidence": entity["confidence"],
                        }
                        for entity in result["entities"]
                    ]
                )

                updates.append(
                    {"article_id": result["article_id"], "entities": entities_json}
                )

        if not updates:
            return

        update_sql = """
        UPDATE news_articles
        SET entities = %(entities)s
        WHERE id = %(article_id)s;
        """

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    execute_batch(cur, update_sql, updates, page_size=self.batch_size)
                    conn.commit()
                    logger.info(
                        "Successfully updated {0} articles with entity data".format(
                            len(updates)
                        )
                    )
        except Exception as e:
            logger.error("Failed to update articles with entities: {0}".format(e))
            # Don't raise - entity data is still stored in separate table

    def get_entity_statistics(self) -> Dict[str, Any]:
        """Get entity extraction statistics."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    # Get overall statistics
                    cur.execute(
                        "SELECT * FROM entity_statistics ORDER BY entity_count DESC;"
                    )
                    entity_stats = cur.fetchall()

                    # Get most common entities
                    cur.execute("SELECT * FROM common_entities LIMIT 50;")
                    common_entities = cur.fetchall()

                    # Get processing statistics from NER processor
                    ner_stats = (
                        self.ner_processor.get_statistics()
                        if self.ner_processor
                        else {}
                    )

                    return {
                        "ner_processor_stats": ner_stats,
                        "entity_type_statistics": [
                            {
                                "type": row[0],
                                "count": row[1],
                                "article_count": row[2],
                                "avg_confidence": float(row[3]),
                                "min_confidence": float(row[4]),
                                "max_confidence": float(row[5]),
                            }
                            for row in entity_stats
                        ],
                        "most_common_entities": [
                            {
                                "text": row[0],
                                "type": row[1],
                                "frequency": row[2],
                                "avg_confidence": float(row[3]),
                                "article_count": row[4],
                            }
                            for row in common_entities
                        ],
                    }

        except Exception as e:
            logger.error("Failed to get entity statistics: {0}".format(e))
            return {}

    def search_entities(
        self,
        entity_text: str = None,
        entity_type: str = None,
        min_confidence: float = 0.5,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search for entities with optional filters.

        Args:
            entity_text: Filter by entity text (partial match)
            entity_type: Filter by entity type
            min_confidence: Minimum confidence threshold
            limit: Maximum number of results

        Returns:
            List of matching entities with article information
        """
        try:
            conditions = ["ae.confidence >= %(min_confidence)s"]
            params = {"min_confidence": min_confidence, "limit": limit}

            if entity_text:
                conditions.append("ae.entity_text ILIKE %(entity_text)s")
                params["entity_text"] = "%{0}%".format(entity_text)

            if entity_type:
                conditions.append("ae.entity_type = %(entity_type)s")
                params["entity_type"] = entity_type

            search_sql = """
            SELECT
                ae.entity_text,
                ae.entity_type,
                ae.confidence,
                ae.article_id,
                as_table.title,
                as_table.url,
                ae.extracted_at
            FROM article_entities ae
            JOIN article_sentiment as_table ON ae.article_id = as_table.article_id
            WHERE {where_clause}
            ORDER BY ae.confidence DESC, ae.extracted_at DESC
            LIMIT %(limit)s;
            """

            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    cur.execute(search_sql, params)
                    results = cur.fetchall()

                    return [
                        {
                            "entity_text": row[0],
                            "entity_type": row[1],
                            "confidence": float(row[2]),
                            "article_id": row[3],
                            "article_title": row[4],
                            "article_url": row[5],
                            "extracted_at": row[6].isoformat() if row[6] else None,
                        }
                        for row in results
                    ]

        except Exception as e:
            logger.error("Failed to search entities: {0}".format(e))
            return []


# Factory function for easy instantiation
def create_ner_article_processor(**config) -> NERArticleProcessor:
    """
    Create a NER-enabled article processor with configuration.

    Args:
        **config: Configuration parameters

    Returns:
        Configured NERArticleProcessor instance
    """
    return NERArticleProcessor(**config)
