"""
Article Embedder for Event Detection System (Issue #31)

This module generates BERT embeddings for news articles to enable clustering
and event detection. Uses sentence-transformers for high-quality embeddings.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import nltk
import numpy as np
import psycopg2
from nltk.corpus import stopwords
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer

# Download required NLTK data
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

try:
    nltk.data.find("corpora/stopwords")
except LookupError:
    nltk.download("stopwords", quiet=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ArticleEmbedder:
    """
    Generates BERT embeddings for news articles.

    Features:
    - Multiple pre-trained BERT models support
    - Text preprocessing and cleaning
    - Batch processing for efficiency
    - Database integration for embedding storage
    - Quality assessment and metrics
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        conn_params: Optional[Dict] = None,
        max_length: int = 512,
        batch_size: int = 32,
    ):
        """
        Initialize the article embedder.

        Args:
            model_name: Sentence transformer model name
            conn_params: Database connection parameters
            max_length: Maximum token length for embeddings
            batch_size: Batch size for processing
        """
        self.model_name = model_name
        self.conn_params = conn_params or {}
        self.max_length = max_length
        self.batch_size = batch_size

        # Initialize model
        logger.info("Loading embedding model: {0}".format(model_name))
        start_time = time.time()
        self.model = SentenceTransformer(model_name)
        load_time = time.time() - start_time
        logger.info("Model loaded in {0}s".format(load_time))

        # Get model info
        self.embedding_dimension = self.model.get_sentence_embedding_dimension()
        logger.info("Embedding dimension: {0}".format(
            self.embedding_dimension))

        # Initialize stopwords
        self.stop_words = set(stopwords.words("english"))

        # Processing statistics
        self.stats = {
            "articles_processed": 0,
            "embeddings_generated": 0,
            "total_processing_time": 0.0,
            "cache_hits": 0,
            "errors": 0,
        }

    def preprocess_text(self, text: str, title: str = "") -> str:
        """
        Preprocess article text for embedding generation.

        Args:
            text: Article content
            title: Article title

        Returns:
            Preprocessed text ready for embedding
        """
        try:
            # Combine title and content
            full_text = "{0}. {1}".format(title, text) if title else text

            # Basic cleaning
            # Remove excessive whitespace
            full_text = re.sub(r"\s+", " ", full_text)

            # Remove URLs (simplified regex)
            full_text = re.sub(r"https?://\S+", "", full_text)

            # Remove email addresses
            full_text = re.sub(r"\S+@\S+", "", full_text)

            # Remove special characters but keep basic punctuation
            full_text = re.sub(r'[^\w\s.,!?;:()\-\'"]+', " ", full_text)

            # Remove excessive punctuation
            full_text = re.sub(r"[.]{2,}", ".", full_text)
            full_text = re.sub(r"[!]{2,}", "!", full_text)
            full_text = re.sub(r"[?]{2,}", "?", full_text)

            # Normalize quotes - using escape sequences for special quotes
            full_text = re.sub(
                r"[\u201c\u201d]", '"', full_text
            )  # Unicode smart quotes
            full_text = re.sub(
                r"[\u2018\u2019]", "'", full_text
            )  # Unicode smart apostrophes

            # Remove leading/trailing whitespace
            full_text = full_text.strip()

            # Truncate if too long (keep first part which usually contains main
            # info)
            words = full_text.split()
            if len(words) > 400:  # Approximate token limit
                full_text = " ".join(words[:400])

            return full_text

        except Exception as e:
            logger.error("Error preprocessing text: {0}".format(e))
            return text[:1000]  # Fallback to first 1000 chars

    def create_text_hash(self, text: str) -> str:
        """Create hash of preprocessed text for deduplication."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def generate_embedding(
        self, text: str, title: str = "", article_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate embedding for a single article.

        Args:
            text: Article content
            title: Article title
            article_id: Article ID for tracking

        Returns:
            Dictionary containing embedding and metadata
        """
        start_time = time.time()

        try:
            # Preprocess text
            preprocessed_text = self.preprocess_text(text, title)
            text_hash = self.create_text_hash(preprocessed_text)

            # Check for existing embedding in database
            if self.conn_params and article_id:
                existing_embedding = await self._get_existing_embedding(
                    article_id, text_hash
                )
                if existing_embedding:
                    self.stats["cache_hits"] += 1
                    logger.debug(
                        "Using cached embedding for article {0}".format(
                            article_id)
                    )
                    return existing_embedding

            # Generate embedding
            embedding_vector = self.model.encode(
                preprocessed_text, convert_to_numpy=True, show_progress_bar=False
            )

            # Calculate quality metrics
            quality_score = self._calculate_embedding_quality(
                embedding_vector, preprocessed_text
            )

            processing_time = time.time() - start_time

            # Prepare result
            result = {
                "article_id": article_id,
                "embedding_vector": embedding_vector.tolist(),
                "embedding_dimension": len(embedding_vector),
                "text_preprocessed": preprocessed_text,
                "text_hash": text_hash,
                "tokens_count": len(preprocessed_text.split()),
                "embedding_quality_score": quality_score,
                "processing_time": processing_time,
                "embedding_model": self.model_name,
                "created_at": datetime.now().isoformat(),
            }

            # Update statistics
            self.stats["embeddings_generated"] += 1
            self.stats["total_processing_time"] += processing_time

            logger.debug(
                "Generated embedding for article {0} in {1:.2f}s".format(
                    article_id, processing_time
                )
            )

            return result

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(
                "Error generating embedding for article {0}: {1}".format(
                    article_id, e)
            )
            raise

    async def generate_embeddings_batch(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate embeddings for multiple articles in batch.

        Args:
            articles: List of article dictionaries with 'id', 'title', 'content'

        Returns:
            List of embedding results
        """
        logger.info("Processing batch of {0} articles".format(len(articles)))
        start_time = time.time()

        try:
            # Preprocess all texts
            preprocessed_data = []
            for article in articles:
                preprocessed_text = self.preprocess_text(
                    article.get("content", ""), article.get("title", "")
                )
                preprocessed_data.append(
                    {
                        "article_id": article.get("id"),
                        "title": article.get("title", ""),
                        "preprocessed_text": preprocessed_text,
                        "text_hash": self.create_text_hash(preprocessed_text),
                    }
                )

            # Check for existing embeddings
            if self.conn_params:
                preprocessed_data = await self._filter_existing_embeddings(
                    preprocessed_data
                )

            if not preprocessed_data:
                logger.info("All embeddings already exist in cache")
                return []

            # Generate embeddings in batch
            texts_to_embed = [item["preprocessed_text"]
                for item in preprocessed_data]

            logger.info(
                "Generating embeddings for {0} new articles".format(
                    len(texts_to_embed))
            )
            embedding_vectors = self.model.encode(
                texts_to_embed,
                batch_size=self.batch_size,
                convert_to_numpy=True,
                show_progress_bar=True,
            )

            # Prepare results
            results = []
            for i, data in enumerate(preprocessed_data):
                embedding_vector = embedding_vectors[i]
                quality_score = self._calculate_embedding_quality(
                    embedding_vector, data["preprocessed_text"]
                )

                result = {
                    "article_id": data["article_id"],
                    "embedding_vector": embedding_vector.tolist(),
                    "embedding_dimension": len(embedding_vector),
                    "text_preprocessed": data["preprocessed_text"],
                    "text_hash": data["text_hash"],
                    "tokens_count": len(data["preprocessed_text"].split()),
                    "embedding_quality_score": quality_score,
                    "processing_time": 0.0,  # Will be updated below
                    "embedding_model": self.model_name,
                    "created_at": datetime.now().isoformat(),
                }
                results.append(result)

            # Calculate processing time
            total_time = time.time() - start_time
            avg_time_per_article = total_time / len(results) if results else 0

            for result in results:
                result["processing_time"] = avg_time_per_article

            # Update statistics
            self.stats["articles_processed"] += len(articles)
            self.stats["embeddings_generated"] += len(results)
            self.stats["total_processing_time"] += total_time

            logger.info(
                "Generated {0} embeddings in {1:.2f}s ({2:.2f}s per article)".format(
                    len(results), total_time, avg_time_per_article
                )
            )

            return results

        except Exception as e:
            self.stats["errors"] += 1
            logger.error("Error in batch embedding generation: {0}".format(e))
            raise

    def _calculate_embedding_quality(
        self, embedding_vector: np.ndarray, text: str
    ) -> float:
        """
        Calculate quality score for an embedding.

        Args:
            embedding_vector: The embedding vector
            text: Original text

        Returns:
            Quality score between 0 and 1
        """
        try:
            # Calculate various quality metrics

            # 1. Vector magnitude (should not be too small)
            magnitude = np.linalg.norm(embedding_vector)
            magnitude_score = min(1.0, magnitude / 10.0)  # Normalize

            # 2. Vector variance (should have good distribution)
            variance = np.var(embedding_vector)
            variance_score = min(1.0, variance * 10)  # Normalize

            # 3. Text length adequacy
            text_length = len(text.split())
            if text_length < 5:
                text_score = 0.2
            elif text_length < 20:
                text_score = 0.6
            elif text_length < 100:
                text_score = 1.0
            else:
                text_score = 0.9  # Very long texts might be noisy

            # 4. Non-zero elements ratio
            non_zero_ratio = np.count_nonzero(
                embedding_vector) / len(embedding_vector)
            sparsity_score = min(1.0, non_zero_ratio * 2)

            # Combine scores with weights
            quality_score = (
                0.3 * magnitude_score
                + 0.2 * variance_score
                + 0.3 * text_score
                + 0.2 * sparsity_score
            )

            return min(1.0, max(0.0, quality_score))

        except Exception as e:
            logger.warning(
                "Error calculating embedding quality: {0}".format(e))
            return 0.5  # Default medium quality

    async def _get_existing_embedding(
        self, article_id: str, text_hash: str
    ) -> Optional[Dict]:
        """Check if embedding already exists in database."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT
                            article_id,
                            embedding_vector::text as embedding_vector_json,
                            embedding_dimension,
                            text_preprocessed,
                            text_hash,
                            tokens_count,
                            embedding_quality_score,
                            processing_time,
                            embedding_model,
                            created_at
                        FROM article_embeddings
                        WHERE article_id = %s
                        AND text_hash = %s
                        AND embedding_model = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                    """,
                        (article_id, text_hash, self.model_name),
                    )

                    row = cur.fetchone()
                    if row:
                        # Parse the JSON embedding vector
                        embedding_vector = json.loads(
                            row["embedding_vector_json"])

                        return {
                            "article_id": row["article_id"],
                            "embedding_vector": embedding_vector,
                            "embedding_dimension": row["embedding_dimension"],
                            "text_preprocessed": row["text_preprocessed"],
                            "text_hash": row["text_hash"],
                            "tokens_count": row["tokens_count"],
                            "embedding_quality_score": (
                                float(row["embedding_quality_score"])
                                if row["embedding_quality_score"]
                                else 0.5
                            ),
                            "processing_time": (
                                float(row["processing_time"])
                                if row["processing_time"]
                                else 0.0
                            ),
                            "embedding_model": row["embedding_model"],
                            "created_at": (
                                row["created_at"].isoformat()
                                if row["created_at"]
                                else None
                            ),
                            f"rom_cache": True,
                        }

            return None

        except Exception as e:
            logger.warning("Error checking existing embedding: {0}".format(e))
            return None

    async def _filter_existing_embeddings(
        self, articles_data: List[Dict]
    ) -> List[Dict]:
        """Filter out articles that already have embeddings."""
        try:
            if not articles_data:
                return []

            # Get article IDs and hashes
            article_ids = [item["article_id"] for item in articles_data]
            text_hashes = [item["text_hash"] for item in articles_data]

            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    # Check which embeddings already exist
                    cur.execute(
                        """
                        SELECT DISTINCT article_id, text_hash
                        FROM article_embeddings
                        WHERE article_id = ANY(%s)
                        AND text_hash = ANY(%s)
                        AND embedding_model = %s
                    """,
                        (article_ids, text_hashes, self.model_name),
                    )

                    existing_combinations = set()
                    for row in cur.fetchall():
                        existing_combinations.add((row[0], row[1]))

            # Filter out existing ones
            filtered_data = []
            for item in articles_data:
                if (item["article_id"], item["text_hash"]) not in existing_combinations:
                    filtered_data.append(item)
                else:
                    self.stats["cache_hits"] += 1

            logger.info(
                "Filtered out {0} existing embeddings".format(
                    len(articles_data) - len(filtered_data)
                )
            )
            return filtered_data

        except Exception as e:
            logger.warning(
                "Error filtering existing embeddings: {0}".format(e))
            return articles_data  # Return all if error

    async def store_embeddings(self, embeddings: List[Dict[str, Any]]) -> int:
        """
        Store embeddings in the database.

        Args:
            embeddings: List of embedding dictionaries

        Returns:
            Number of embeddings stored
        """
        if not self.conn_params or not embeddings:
            return 0

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    # Prepare data for insertion
                    values = []
                    for emb in embeddings:
                        values.append(
                            (
                                emb["article_id"],
                                self.model_name,
                                emb["embedding_dimension"],
                                json.dumps(emb["embedding_vector"]),
                                emb["text_preprocessed"],
                                emb["text_hash"],
                                emb["tokens_count"],
                                emb["embedding_quality_score"],
                                emb["processing_time"],
                            )
                        )

                    # Insert embeddings
                    cur.executemany(
                        """
                        INSERT INTO article_embeddings (
                            article_id, embedding_model, embedding_dimension,
                            embedding_vector, text_preprocessed, text_hash,
                            tokens_count, embedding_quality_score, processing_time
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (article_id, text_hash, embedding_model) DO NOTHING
                    """,
                        values,
                    )

                    stored_count = cur.rowcount
                    conn.commit()

                    logger.info(
                        "Stored {0} embeddings in database".format(
                            stored_count)
                    )
                    return stored_count

        except Exception as e:
            logger.error("Error storing embeddings: {0}".format(e))
            return 0

    async def get_embeddings_for_clustering(
        self,
        limit: Optional[int] = None,
        category_filter: Optional[str] = None,
        days_back: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve embeddings for clustering analysis.

        Args:
            limit: Maximum number of embeddings to retrieve
            category_filter: Filter by article category
            days_back: Only get articles from last N days

        Returns:
            List of embeddings with article metadata
        """
        if not self.conn_params:
            return []

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Build query
                    query = """
                        SELECT
                            ae.article_id,
                            ae.embedding_vector::text as embedding_vector_json,
                            ae.embedding_dimension,
                            ae.embedding_quality_score,
                            a.title,
                            a.content,
                            a.source,
                            a.published_date,
                            a.category,
                            a.sentiment_score,
                            a.source_credibility
                        FROM article_embeddings ae
                        JOIN news_articles a ON ae.article_id = a.id
                        WHERE ae.embedding_model = %s
                        AND a.published_date >= CURRENT_DATE - INTERVAL '%s days'
                        AND a.source_credibility IN ('trusted', 'reliable')
                        AND ae.embedding_quality_score >= 0.3
                    """

                    params = [self.model_name, days_back]

                    if category_filter:
                        query += " AND a.category = %s"
                        params.append(category_filter)

                    query += " ORDER BY a.published_date DESC"

                    if limit:
                        query += " LIMIT %s"
                        params.append(limit)

                    cur.execute(query, params)
                    rows = cur.fetchall()

                    # Process results
                    embeddings = []
                    for row in rows:
                        embedding_vector = json.loads(
                            row["embedding_vector_json"])

                        embeddings.append(
                            {
                                "article_id": row["article_id"],
                                "embedding_vector": np.array(embedding_vector),
                                "embedding_dimension": row["embedding_dimension"],
                                "embedding_quality_score": (
                                    float(row["embedding_quality_score"])
                                    if row["embedding_quality_score"]
                                    else 0.5
                                ),
                                "title": row["title"],
                                "content": row["content"],
                                "source": row["source"],
                                "published_date": row["published_date"],
                                "category": row["category"],
                                "sentiment_score": (
                                    float(row["sentiment_score"])
                                    if row["sentiment_score"]
                                    else 0.0
                                ),
                                "source_credibility": row["source_credibility"],
                            }
                        )

                    logger.info(
                        "Retrieved {0} embeddings for clustering".format(
                            len(embeddings)
                        )
                    )
                    return embeddings

        except Exception as e:
            logger.error("Error retrieving embeddings: {0}".format(e))
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics."""
        stats = self.stats.copy()
        stats["model_name"] = self.model_name
        stats["embedding_dimension"] = self.embedding_dimension
        stats["avg_processing_time"] = (
            stats["total_processing_time"] / stats["embeddings_generated"]
            if stats["embeddings_generated"] > 0
            else 0
        )
        return stats

    async def create_embeddings_table(self):
        """Create the article_embeddings table if it doesn't exist."""
        if not self.conn_params:
            return

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    # This should already be created by schema.sql, but ensure
                    # it exists
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS article_embeddings (
                            id BIGINT IDENTITY(1,1) PRIMARY KEY,
                            article_id VARCHAR(255) NOT NULL,
                            embedding_model VARCHAR(255) NOT NULL,
                            embedding_dimension INTEGER NOT NULL,
                            embedding_vector SUPER NOT NULL,
                            text_preprocessed TEXT,
                            text_hash VARCHAR(64),
                            tokens_count INTEGER,
                            embedding_quality_score DECIMAL(5,4),
                            processing_time DECIMAL(8,4),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(article_id, text_hash, embedding_model)
                        )
                    """
                    )
                    conn.commit()
                    logger.info("Article embeddings table ready")

        except Exception as e:
            logger.error("Error creating embeddings table: {0}".format(e))


# Helper functions for configuration
def get_redshift_connection_params() -> Dict[str, str]:
    """Get Redshift connection parameters from environment variables."""
    import os

    return {
        "host": os.getenv("REDSHIFT_HOST", "localhost"),
        "port": int(os.getenv("REDSHIFT_PORT", 5432)),
        "database": os.getenv("REDSHIFT_DATABASE", "neuronews"),
        "user": os.getenv("REDSHIFT_USER", "admin"),
        "password": os.getenv("REDSHIFT_PASSWORD", "password"),
    }


# Available embedding models
EMBEDDING_MODELS = {
    "all-MiniLM-L6-v2": {
        "dimension": 384,
        "description": "Fast and efficient, good for most use cases",
        "speed": f"ast",
        "quality": "good",
    },
    "all-mpnet-base-v2": {
        "dimension": 768,
        "description": "High quality embeddings, slower processing",
        "speed": "medium",
        "quality": "excellent",
    },
    "all-distilroberta-v1": {
        "dimension": 768,
        "description": "Balanced speed and quality",
        "speed": "medium",
        "quality": "very good",
    },
    "paraphrase-multilingual-MiniLM-L12-v2": {
        "dimension": 384,
        "description": "Multilingual support",
        "speed": "medium",
        "quality": "good",
    },
}


if __name__ == "__main__":
    # Test the embedder

    async def test_embedder():
        embedder = ArticleEmbedder(
            model_name="all-MiniLM-L6-v2", conn_params=get_redshift_connection_params()
        )

        # Test single embedding
        sample_article = {
            "id": "test_001",
            "title": "Test Article",
            "content": "This is a test article for embedding generation.",
        }

        result = await embedder.generate_embedding(
            sample_article["content"], sample_article["title"], sample_article["id"]
        )

        print(
            f"Generated embedding with dimension: {result['embedding_dimension']}"
        )
        print(f"Quality score: {result['embedding_quality_score']:.3f}")
        print(f"Processing time: {result['processing_time']:.3f}s")

        # Print statistics
        stats = embedder.get_statistics()
        print("\nStatistics: {0}".format(stats))

    asyncio.run(test_embedder())
