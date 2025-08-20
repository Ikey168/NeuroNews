#!/usr/bin/env python3
"""
Kubernetes AI Topic Modeling Processor
Issue #74: Deploy NLP & AI Processing as Kubernetes Jobs

This module implements advanced AI topic modeling processing as a Kubernetes Job,
using GPU acceleration for heavy AI computations and storing results in AWS Redshift.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import numpy as np
import psycopg2
import torch
import umap
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import TfidfVectorizer

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "../../.."))

try:
    from database.redshift_loader import RedshiftETLProcessor
except ImportError as e:
    print("Import error: {0}".format(e))
    print("Please ensure you're running from the project root directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/ai_job.log")],
)
logger = logging.getLogger(__name__)


class KubernetesAIProcessor:
    """
    Kubernetes-native AI topic modeling processor with GPU acceleration,
    advanced machine learning algorithms, and Redshift integration.
    """

    def __init__(
        self,
        job_type: str = "topic-modeling",
        batch_size: int = 25,
        max_workers: int = 1,
        use_gpu: bool = True,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        topic_model_type: str = "LDA",
        num_topics: int = 20,
        output_dir: str = "/app/results",
        model_cache_dir: str = "/app/models",
        gpu_cache_dir: str = "/app/gpu-cache",
    ):
        """
        Initialize the Kubernetes AI processor.

        Args:
            job_type: Type of job (topic-modeling)
            batch_size: Number of articles to process in each batch
            max_workers: Maximum number of worker threads
            use_gpu: Whether to use GPU acceleration
            embedding_model: SentenceTransformer model for embeddings
            topic_model_type: Type of topic model (LDA, UMAP+HDBSCAN)
            num_topics: Number of topics to extract
            output_dir: Directory for output files
            model_cache_dir: Directory for model caching
            gpu_cache_dir: Directory for GPU cache
        """
        self.job_type = job_type
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.use_gpu = use_gpu and torch.cuda.is_available()
        self.embedding_model_name = embedding_model
        self.topic_model_type = topic_model_type
        self.num_topics = num_topics
        self.output_dir = output_dir
        self.model_cache_dir = model_cache_dir
        self.gpu_cache_dir = gpu_cache_dir

        # Create output directories
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.model_cache_dir, exist_ok=True)
        os.makedirs(self.gpu_cache_dir, exist_ok=True)

        # Initialize components
        self.embedding_model = None
        self.topic_model = None
        self.redshift_processor = None
        self.postgres_conn = None

        # GPU optimization settings
        if self.use_gpu:
            torch.cuda.empty_cache()
            # Set GPU memory optimization
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:512"

        # Statistics tracking
        self.stats = {
            "start_time": datetime.now(timezone.utc),
            "articles_processed": 0,
            "articles_failed": 0,
            "topics_extracted": 0,
            "embeddings_generated": 0,
            "batches_processed": 0,
            "total_processing_time": 0,
            "gpu_used": self.use_gpu,
            "embedding_model": self.embedding_model_name,
            "topic_model_type": self.topic_model_type,
            "num_topics": self.num_topics,
        }

        logger.info("Initialized KubernetesAIProcessor:")
        logger.info("  Job Type: {0}".format(self.job_type))
        logger.info("  Batch Size: {0}".format(self.batch_size))
        logger.info("  Max Workers: {0}".format(self.max_workers))
        logger.info("  GPU Enabled: {0}".format(self.use_gpu))
        logger.info("  Embedding Model: {0}".format(self.embedding_model_name))
        logger.info("  Topic Model Type: {0}".format(self.topic_model_type))
        logger.info("  Number of Topics: {0}".format(self.num_topics))
        logger.info("  Output Dir: {0}".format(self.output_dir))

    async def initialize(self):
        """Initialize all components and connections."""
        try:
            logger.info("Initializing AI components...")

            # Set cache directory for models
            os.environ["SENTENCE_TRANSFORMERS_HOME"] = self.model_cache_dir
            os.environ["HF_HOME"] = self.model_cache_dir

            # Initialize embedding model with GPU support
            device = "cuda" if self.use_gpu else "cpu"
            logger.info("Loading embedding model on device: {0}".format(device))

            self.embedding_model = SentenceTransformer(
                self.embedding_model_name,
                device=device,
                cache_folder=self.model_cache_dir,
            )

            logger.info("Embedding model initialized")

            # Initialize topic model based on type
            if self.topic_model_type.upper() == "LDA":
                self.topic_model = LatentDirichletAllocation(
                    n_components=self.num_topics,
                    random_state=42,
                    max_iter=1000,
                    learning_method="batch",
                    n_jobs=-1 if not self.use_gpu else 1,  # Use all CPUs if no GPU
                )
            else:
                # For UMAP+HDBSCAN or other advanced methods
                logger.info("Using UMAP+HDBSCAN for topic modeling")
                self.topic_model = None  # Will be initialized during processing

            logger.info("Topic model ({0}) initialized".format(self.topic_model_type))

            # Initialize Redshift connection
            redshift_config = {
                "host": os.getenv("REDSHIFT_HOST"),
                "database": os.getenv("REDSHIFT_DATABASE", "dev"),
                "user": os.getenv("REDSHIFT_USER", "admin"),
                "password": os.getenv("REDSHIFT_PASSWORD"),
                "port": int(os.getenv("REDSHIFT_PORT", "5439")),
            }

            self.redshift_processor = RedshiftETLProcessor(**redshift_config)
            logger.info("Redshift processor initialized")

            # Initialize PostgreSQL connection for reading articles
            self.postgres_conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST"),
                database=os.getenv("POSTGRES_DATABASE", "neuronews"),
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
            )
            logger.info("PostgreSQL connection established")

            logger.info("All AI components initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize AI components: {0}".format(e))
            raise

    async def fetch_articles_to_process(
        self, limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch articles that need topic modeling processing.

        Args:
            limit: Maximum number of articles to fetch

        Returns:
            List of article dictionaries
        """
        try:
            with self.postgres_conn.cursor() as cur:
                # Get articles that don't have recent topic modeling
                processing_window = datetime.now(timezone.utc) - timedelta(
                    hours=int(os.getenv("PROCESSING_WINDOW_HOURS", "24"))
                )

                query = """
                SELECT
                    article_id,
                    title,
                    content,
                    url,
                    source,
                    published_date,
                    scraped_at,
                    sentiment_label,
                    sentiment_score
                FROM news_articles
                WHERE
                    (topic_processed_at IS NULL
                     OR topic_processed_at < %s)
                    AND LENGTH(content) >= %s
                    AND published_date >= %s
                    AND content IS NOT NULL
                    AND title IS NOT NULL
                ORDER BY published_date DESC
                """

                params = [
                    processing_window,
                    int(
                        os.getenv("MINIMUM_ARTICLE_LENGTH", "200")
                    ),  # Longer minimum for topic modeling
                    datetime.now(timezone.utc)
                    - timedelta(days=14),  # Last 14 days for topic analysis
                ]

                if limit:
                    query += " LIMIT %s"
                    params.append(limit)

                cur.execute(query, params)
                results = cur.fetchall()

                articles = []
                for row in results:
                    article = {
                        "article_id": row[0],
                        "title": row[1],
                        "content": row[2],
                        "url": row[3],
                        "source": row[4],
                        "published_date": row[5],
                        "scraped_at": row[6],
                        "sentiment_label": row[7],
                        "sentiment_score": row[8],
                    }
                    articles.append(article)

                logger.info(
                    "Fetched {0} articles for topic modeling".format(
                        len(articles))
                )
                return articles

        except Exception as e:
            logger.error("Failed to fetch articles: {0}".format(e))
            return []

    def preprocess_texts(self, articles: List[Dict[str, Any]]) -> List[str]:
        """
        Preprocess article texts for topic modeling.

        Args:
            articles: List of article dictionaries

        Returns:
            List of preprocessed texts
        """
        processed_texts = []

        for article in articles:
            try:
                # Combine title and content
                title = article.get("title", "")
                content = article.get("content", "")
                full_text = "{0}. {1}".format(title, content)

                # Basic preprocessing
                # Remove excessive whitespace
                full_text = " ".join(full_text.split())

                # Truncate to reasonable length for topic modeling
                max_length = int(os.getenv("ARTICLE_TEXT_MAX_LENGTH", "5000"))
                if len(full_text) > max_length:
                    # Try to cut at sentence boundary
                    sentences = full_text.split(". ")
                    truncated = ""
                    for sentence in sentences:
                        if len(truncated + sentence) <= max_length:
                            truncated += sentence + ". "
                        else:
                            break
                    full_text = truncated.strip()

                processed_texts.append(full_text)

            except Exception as e:
                logger.error(
                    f"Failed to preprocess article {
                        article.get(
                            'article_id',
                            'unknown')}: {e}"
                )
                # Add empty string to maintain alignment
                processed_texts.append("")

        return processed_texts

    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate sentence embeddings for the texts.

        Args:
            texts: List of preprocessed texts

        Returns:
            NumPy array of embeddings
        """
        try:
            logger.info("Generating embeddings for {0} texts".format(len(texts)))

            # Filter out empty texts
            valid_texts = [text for text in texts if text.strip()]

            if not valid_texts:
                logger.warning("No valid texts found for embedding generation")
                return np.array([])

            # Generate embeddings with GPU acceleration
            embeddings = self.embedding_model.encode(
                valid_texts,
                batch_size=self.batch_size,
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            self.stats["embeddings_generated"] += len(embeddings)
            logger.info("Generated {0} embeddings".format(len(embeddings)))

            return embeddings

        except Exception as e:
            logger.error("Failed to generate embeddings: {0}".format(e))
            return np.array([])

    def perform_topic_modeling(
        self, texts: List[str], embeddings: np.ndarray
    ) -> Tuple[List[int], List[Dict[str, Any]]]:
        """
        Perform topic modeling on the texts and embeddings.

        Args:
            texts: List of preprocessed texts
            embeddings: Sentence embeddings

        Returns:
            Tuple of (topic assignments, topic descriptions)
        """
        try:
            logger.info(
                "Performing topic modeling using {0}".format(
                    self.topic_model_type)
            )

            if self.topic_model_type.upper() == "LDA":
                return self.perform_lda_topic_modeling(texts, embeddings)
            else:
                return self.perform_umap_topic_modeling(texts, embeddings)

        except Exception as e:
            logger.error("Failed to perform topic modeling: {0}".format(e))
            return [], []

    def perform_lda_topic_modeling(
        self, texts: List[str], embeddings: np.ndarray
    ) -> Tuple[List[int], List[Dict[str, Any]]]:
        """
        Perform LDA topic modeling.

        Args:
            texts: List of preprocessed texts
            embeddings: Sentence embeddings (used for similarity but not LDA directly)

        Returns:
            Tuple of (topic assignments, topic descriptions)
        """
        try:
            # Use TF-IDF for LDA input
            vectorizer = TfidfVectorizer(
                max_features=1000,
                stop_words="english",
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.8,
            )

            tfidf_matrix = vectorizer.fit_transform(texts)
            feature_names = vectorizer.get_feature_names_out()

            # Fit LDA model
            logger.info("Fitting LDA model...")
            lda_model = self.topic_model.fit(tfidf_matrix)

            # Get topic assignments
            doc_topic_probs = lda_model.transform(tfidf_matrix)
            topic_assignments = np.argmax(doc_topic_probs, axis=1).tolist()

            # Generate topic descriptions
            topic_descriptions = []
            for topic_idx in range(self.num_topics):
                # Get top words for this topic
                top_word_indices = lda_model.components_[topic_idx].argsort()[-10:][
                    ::-1
                ]
                top_words = [feature_names[i] for i in top_word_indices]
                top_weights = [
                    lda_model.components_[topic_idx][i] for i in top_word_indices
                ]

                topic_desc = {
                    "topic_id": topic_idx,
                    "topic_words": top_words,
                    "topic_weights": top_weights,
                    "topic_label": "Topic_{0}_{1}_{2}".format(topic_idx, 
                        top_words[0], 
                        top_words[1]),
                    "model_type": "LDA",
                }
                topic_descriptions.append(topic_desc)

            self.stats["topics_extracted"] = len(topic_descriptions)
            logger.info(
                "Extracted {0} topics using LDA".format(
                    len(topic_descriptions))
            )

            return topic_assignments, topic_descriptions

        except Exception as e:
            logger.error("Failed to perform LDA topic modeling: {0}".format(e))
            return [], []

    def perform_umap_topic_modeling(
        self, texts: List[str], embeddings: np.ndarray
    ) -> Tuple[List[int], List[Dict[str, Any]]]:
        """
        Perform UMAP + clustering topic modeling.

        Args:
            texts: List of preprocessed texts
            embeddings: Sentence embeddings

        Returns:
            Tuple of (topic assignments, topic descriptions)
        """
        try:
            logger.info("Performing UMAP dimensionality reduction...")

            # UMAP for dimensionality reduction
            umap_model = umap.UMAP(
                n_components=min(50, len(embeddings) // 2),
                random_state=42,
                metric="cosine",
            )

            reduced_embeddings = umap_model.fit_transform(embeddings)

            # K-means clustering on reduced embeddings
            logger.info("Performing K-means clustering...")
            kmeans = KMeans(n_clusters=self.num_topics, random_state=42, n_init=10)

            topic_assignments = kmeans.fit_predict(reduced_embeddings).tolist()

            # Generate topic descriptions using TF-IDF on clustered documents
            topic_descriptions = []

            for topic_idx in range(self.num_topics):
                # Get documents assigned to this topic
                topic_texts = [
                    texts[i] for i, t in enumerate(topic_assignments) if t == topic_idx
                ]

                if topic_texts:
                    # Use TF-IDF to find representative words
                    vectorizer = TfidfVectorizer(
                        max_features=100, stop_words="english", ngram_range=(1, 2)
                    )

                    try:
                        tfidf_matrix = vectorizer.fit_transform(topic_texts)
                        feature_names = vectorizer.get_feature_names_out()

                        # Get average TF-IDF scores
                        avg_scores = np.mean(tfidf_matrix.toarray(), axis=0)
                        top_indices = avg_scores.argsort()[-10:][::-1]

                        top_words = [feature_names[i] for i in top_indices]
                        top_weights = [avg_scores[i] for i in top_indices]

                        topic_desc = {
                            "topic_id": topic_idx,
                            "topic_words": top_words,
                            "topic_weights": top_weights,
                            "topic_label": (
                                "Topic_{0}_{1}_{2}".format(topic_idx, 
                                    top_words[0], 
                                    top_words[1])
                                if top_words
                                else "Topic_{0}".format(topic_idx)
                            ),
                            "model_type": "UMAP+KMeans",
                            "num_documents": len(topic_texts),
                        }
                        topic_descriptions.append(topic_desc)

                    except Exception as e:
                        logger.warning(
                            "Failed to generate description for topic {0}: {1}".format(topic_idx, e)
                        )
                        topic_desc = {
                            "topic_id": topic_idx,
                            "topic_words": [],
                            "topic_weights": [],
                            "topic_label": "Topic_{0}".format(topic_idx),
                            "model_type": "UMAP+KMeans",
                            "num_documents": len(topic_texts),
                        }
                        topic_descriptions.append(topic_desc)

            self.stats["topics_extracted"] = len(topic_descriptions)
            logger.info(
                "Extracted {0} topics using UMAP+KMeans".format(
                    len(topic_descriptions))
            )

            return topic_assignments, topic_descriptions

        except Exception as e:
            logger.error("Failed to perform UMAP topic modeling: {0}".format(e))
            return [], []

    def process_article_batch(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of articles for topic modeling.

        Args:
            articles: List of article dictionaries

        Returns:
            List of topic modeling results
        """
        batch_start_time = time.time()
        results = []

        try:
            logger.info(
                "Processing batch of {0} articles for topic modeling".format(
                    len(articles))
            )

            # Preprocess texts
            texts = self.preprocess_texts(articles)

            # Generate embeddings
            embeddings = self.generate_embeddings(texts)

            if embeddings.size == 0:
                logger.warning("No embeddings generated, skipping topic modeling")
                return []

            # Perform topic modeling
            topic_assignments, topic_descriptions = self.perform_topic_modeling(
                texts, embeddings
            )

            if not topic_assignments:
                logger.warning("No topics assigned, skipping results generation")
                return []

            # Create results for each article
            for i, (article, topic_id) in enumerate(zip(articles, topic_assignments)):
                try:
                    # Find the topic description
                    topic_desc = None
                    for desc in topic_descriptions:
                        if desc["topic_id"] == topic_id:
                            topic_desc = desc
                            break

                    if topic_desc is None:
                        logger.warning(
                            "No topic description found for topic {0}".format(topic_id)
                        )
                        continue

                    result = {
                        "article_id": article["article_id"],
                        "article_title": article["title"],
                        "article_url": article["url"],
                        "article_source": article["source"],
                        "article_published_date": article["published_date"],
                        "article_sentiment_label": article.get("sentiment_label"),
                        "article_sentiment_score": article.get("sentiment_score"),
                        "topic_id": topic_id,
                        "topic_label": topic_desc["topic_label"],
                        "topic_words": json.dumps(topic_desc["topic_words"]),
                        "topic_weights": json.dumps(topic_desc["topic_weights"]),
                        "topic_model_type": topic_desc["model_type"],
                        "processing_timestamp": datetime.now(timezone.utc),
                        "processing_job_type": self.job_type,
                        "embedding_model": self.embedding_model_name,
                        "num_topics": self.num_topics,
                        "gpu_used": self.use_gpu,
                    }
                    results.append(result)
                    self.stats["articles_processed"] += 1

                except Exception as e:
                    logger.error(
                        f"Failed to process article {
                            article['article_id']}: {e}"
                    )
                    self.stats["articles_failed"] += 1

            batch_processing_time = time.time() - batch_start_time
            self.stats["total_processing_time"] += batch_processing_time
            self.stats["batches_processed"] += 1

            logger.info(
                "Processed batch in {0}s, assigned topics to {1} articles".format(
                    batch_processing_time:.2f, 
                    len(results))
            )
            return results

        except Exception as e:
            logger.error("Failed to process batch: {0}".format(e))
            self.stats["articles_failed"] += len(articles)
            return []

    async def store_results_in_redshift(self, results: List[Dict[str, Any]]):
        """
        Store topic modeling results in Redshift.

        Args:
            results: List of topic modeling results
        """
        try:
            if not results:
                return

            logger.info(
                "Storing {0} topic modeling results in Redshift".format(
                    len(results))
            )

            # Store in Redshift
            with self.redshift_processor as processor:
                # Create topic results table if it doesn't exist
                await self.create_topic_results_table(processor)

                # Insert results
                success_count = await processor.batch_insert_topic_results(results)
                logger.info(
                    "Successfully stored {0} topic results in Redshift".format(success_count)
                )

        except Exception as e:
            logger.error("Failed to store results in Redshift: {0}".format(e))
            # Save results to file as backup
            backup_file = os.path.join(
                self.output_dir, "topic_results_backup_{0}.json".format(int(time.time()))
            )
            with open(backup_file, "w") as f:
                json.dump(results, f, indent=2, default=str)
            logger.info("Results saved to backup file: {0}".format(backup_file))

    async def create_topic_results_table(self, processor):
        """Create topic results table in Redshift if it doesn't exist."""
        try:
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS nlp_results.topic_modeling (
                id BIGINT IDENTITY(1,1) PRIMARY KEY,
                article_id VARCHAR(255) NOT NULL,
                article_title VARCHAR(500),
                article_url VARCHAR(1000),
                article_source VARCHAR(100),
                article_published_date TIMESTAMP WITHOUT TIME ZONE,
                article_sentiment_label VARCHAR(50),
                article_sentiment_score DECIMAL(10,8),
                topic_id INTEGER NOT NULL,
                topic_label VARCHAR(200),
                topic_words VARCHAR(2000),
                topic_weights VARCHAR(2000),
                topic_model_type VARCHAR(100),
                processing_timestamp TIMESTAMP WITHOUT TIME ZONE,
                processing_job_type VARCHAR(100),
                embedding_model VARCHAR(200),
                num_topics INTEGER,
                gpu_used BOOLEAN,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT GETDATE()
            )
            DISTKEY(article_id)
            SORTKEY(processing_timestamp, topic_id);
            """

            await processor.execute_sql(create_table_sql)
            logger.info("Topic results table ensured in Redshift")

        except Exception as e:
            logger.error("Failed to create topic results table: {0}".format(e))
            raise

    async def update_postgres_processing_status(self, article_ids: List[str]):
        """
        Update PostgreSQL to mark articles as processed for topic modeling.

        Args:
            article_ids: List of article IDs that were processed
        """
        try:
            with self.postgres_conn.cursor() as cur:
                # Update processing timestamp
                update_sql = """
                UPDATE news_articles
                SET topic_processed_at = %s
                WHERE article_id = ANY(%s)
                """

                cur.execute(update_sql, [datetime.now(timezone.utc), article_ids])

                self.postgres_conn.commit()
                logger.info(
                    "Updated topic processing status for {0} articles".format(
                        len(article_ids))
                )

        except Exception as e:
            logger.error("Failed to update topic processing status: {0}".format(e))
            self.postgres_conn.rollback()

    def save_processing_stats(self):
        """Save job processing statistics."""
        try:
            self.stats["end_time"] = datetime.now(timezone.utc)
            self.stats["total_duration_seconds"] = (
                self.stats["end_time"] - self.stats["start_time"]
            ).total_seconds()

            if self.stats["articles_processed"] > 0:
                self.stats["average_processing_time"] = (
                    self.stats["total_processing_time"]
                    / self.stats["articles_processed"]
                )
                self.stats["throughput_articles_per_second"] = (
                    self.stats["articles_processed"]
                    / self.stats["total_duration_seconds"]
                )

            stats_file = os.path.join(
                self.output_dir, "topic_job_stats_{0}.json".format(int(time.time()))
            )
            with open(stats_file, "w") as f:
                json.dump(self.stats, f, indent=2, default=str)

            logger.info("Processing statistics saved to {0}".format(stats_file))
            logger.info("AI Topic Modeling Job Summary:")
            logger.info(
                f"  Articles Processed: {
                    self.stats['articles_processed']}"
            )
            logger.info(f"  Articles Failed: {self.stats['articles_failed']}")
            logger.info(
                f"  Topics Extracted: {
                    self.stats['topics_extracted']}"
            )
            logger.info(
                f"  Embeddings Generated: {
                    self.stats['embeddings_generated']}"
            )
            logger.info(
                f"  Batches Processed: {
                    self.stats['batches_processed']}"
            )
            logger.info(
                f"  Total Duration: {
                    self.stats['total_duration_seconds']:.2f}s"
            )
            if self.stats["articles_processed"] > 0:
                logger.info(
                    f"  Throughput: {
                        self.stats.get(
                            'throughput_articles_per_second',
                            0):.2f} articles/sec"
                )

        except Exception as e:
            logger.error("Failed to save processing statistics: {0}".format(e))

    async def run_processing_job(self, max_articles: int = None):
        """
        Run the main AI topic modeling processing job.

        Args:
            max_articles: Maximum number of articles to process
        """
        try:
            logger.info("Starting AI topic modeling processing job")

            # Initialize components
            await self.initialize()

            # Fetch articles to process
            articles = await self.fetch_articles_to_process(limit=max_articles)

            if not articles:
                logger.info("No articles found for topic modeling")
                return

            # For topic modeling, process all articles together for better
            # topic coherence
            logger.info(
                "Processing {0} articles for topic modeling".format(
                    len(articles))
            )

            # Process all articles in one large batch (with memory management)
            batch_results = self.process_article_batch(articles)

            # Store results in Redshift
            if batch_results:
                await self.store_results_in_redshift(batch_results)

                # Update PostgreSQL processing status
                article_ids = [r["article_id"] for r in batch_results]
                await self.update_postgres_processing_status(article_ids)

            # Save final statistics
            self.save_processing_stats()

            logger.info("AI topic modeling job completed successfully")
            logger.info(
                f"Processed {
                    self.stats['articles_processed']} articles"
            )
            logger.info(
                f"Extracted {
                    self.stats['topics_extracted']} topics total"
            )

        except Exception as e:
            logger.error("AI topic modeling job failed: {0}".format(e))
            raise

        finally:
            # Cleanup connections and GPU memory
            if self.postgres_conn:
                self.postgres_conn.close()
            if self.redshift_processor:
                await self.redshift_processor.close()
            if self.use_gpu:
                torch.cuda.empty_cache()


async def main():
    """Main entry point for the Kubernetes AI processing job."""
    parser = argparse.ArgumentParser(
        description="Kubernetes AI Topic Modeling Processor"
    )
    parser.add_argument("--job-type", default="topic-modeling", help="Type of job")
    parser.add_argument(
        "--batch-size", type=int, default=25, help="Batch size for processing"
    )
    parser.add_argument(
        "--max-workers", type=int, default=1, help="Maximum worker threads"
    )
    parser.add_argument("--max-articles", type=int, help="Maximum articles to process")
    parser.add_argument(
        "--embedding-model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Embedding model",
    )
    parser.add_argument(
        "--topic-model-type",
        default="LDA",
        choices=["LDA", "UMAP"],
        help="Topic model type",
    )
    parser.add_argument("--num-topics", type=int, default=20, help="Number of topics")
    parser.add_argument("--output-dir", default="/app/results", help="Output directory")
    parser.add_argument(
        "--model-cache-dir", default="/app/models", help="Model cache directory"
    )
    parser.add_argument(
        "--gpu-cache-dir", default="/app/gpu-cache", help="GPU cache directory"
    )
    parser.add_argument(
        "--use-gpu", action="store_true", default=True, help="Use GPU acceleration"
    )

    args = parser.parse_args()

    # Override with environment variables if set
    batch_size = int(os.getenv("BATCH_SIZE", args.batch_size))
    max_workers = int(os.getenv("MAX_WORKERS", args.max_workers))
    use_gpu = os.getenv("USE_GPU", "true").lower() == "true" and args.use_gpu
    num_topics = int(os.getenv("NUM_TOPICS", args.num_topics))
    topic_model_type = os.getenv("TOPIC_MODEL_TYPE", args.topic_model_type)

    # Create processor
    processor = KubernetesAIProcessor(
        job_type=args.job_type,
        batch_size=batch_size,
        max_workers=max_workers,
        use_gpu=use_gpu,
        embedding_model=os.getenv("TOPIC_EMBEDDING_MODEL", args.embedding_model),
        topic_model_type=topic_model_type,
        num_topics=num_topics,
        output_dir=args.output_dir,
        model_cache_dir=args.model_cache_dir,
        gpu_cache_dir=args.gpu_cache_dir,
    )

    # Run the processing job
    try:
        await processor.run_processing_job(max_articles=args.max_articles)
        logger.info("AI topic modeling job completed successfully")
        sys.exit(0)
    except Exception as e:
        logger.error("AI topic modeling job failed: {0}".format(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
