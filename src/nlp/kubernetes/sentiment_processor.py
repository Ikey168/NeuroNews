#!/usr/bin/env python3
"""
Kubernetes Sentiment Analysis Processor
Issue #74: Deploy NLP & AI Processing as Kubernetes Jobs

This module implements sentiment analysis processing as a Kubernetes Job,
integrating with existing sentiment analysis infrastructure and storing
results in AWS Redshift.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import torch
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          pipeline)

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "../../.."))

try:
    from database.redshift_loader import RedshiftETLProcessor
    from nlp.ner_article_processor import NERArticleProcessor
    from nlp.sentiment_analysis import SentimentAnalyzer
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure you're running from the project root directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/sentiment_job.log")],
)
logger = logging.getLogger(__name__)


class KubernetesSentimentProcessor:
    """
    Kubernetes-native sentiment analysis processor with GPU acceleration,
    batch processing, and Redshift integration.
    """

    def __init__(
        self,
        job_type: str = "sentiment-analysis",
        batch_size: int = 100,
        max_workers: int = 4,
        use_gpu: bool = True,
        model_name: str = "cardiffnlp/twitter-roberta-base-sentiment-latest",
        output_dir: str = "/app/results",
        model_cache_dir: str = "/app/models",
    ):
        """
        Initialize the Kubernetes sentiment processor.

        Args:
            job_type: Type of job (sentiment-analysis)
            batch_size: Number of articles to process in each batch
            max_workers: Maximum number of worker threads
            use_gpu: Whether to use GPU acceleration
            model_name: HuggingFace model name for sentiment analysis
            output_dir: Directory for output files
            model_cache_dir: Directory for model caching
        """
        self.job_type = job_type
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.use_gpu = use_gpu and torch.cuda.is_available()
        self.model_name = model_name
        self.output_dir = output_dir
        self.model_cache_dir = model_cache_dir

        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.model_cache_dir, exist_ok=True)

        # Initialize components
        self.sentiment_analyzer = None
        self.redshift_processor = None
        self.postgres_conn = None

        # Statistics tracking
        self.stats = {
            "start_time": datetime.now(timezone.utc),
            "articles_processed": 0,
            "articles_failed": 0,
            "batches_processed": 0,
            "total_processing_time": 0,
            "gpu_used": self.use_gpu,
            "model_name": self.model_name,
        }

        logger.info(f"Initialized KubernetesSentimentProcessor:")
        logger.info(f"  Job Type: {self.job_type}")
        logger.info(f"  Batch Size: {self.batch_size}")
        logger.info(f"  Max Workers: {self.max_workers}")
        logger.info(f"  GPU Enabled: {self.use_gpu}")
        logger.info(f"  Model: {self.model_name}")
        logger.info(f"  Output Dir: {self.output_dir}")

    async def initialize(self):
        """Initialize all components and connections."""
        try:
            logger.info("Initializing components...")

            # Initialize sentiment analyzer with GPU support
            device = "cuda" if self.use_gpu else "cpu"
            logger.info(f"Using device: {device}")

            # Set cache directory for models
            os.environ["TRANSFORMERS_CACHE"] = self.model_cache_dir
            os.environ["HF_HOME"] = self.model_cache_dir

            # Initialize sentiment analyzer
            self.sentiment_analyzer = SentimentAnalyzer(
                model_name=self.model_name, device=device
            )

            logger.info("Sentiment analyzer initialized")

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

            logger.info("All components initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise

    async def fetch_articles_to_process(
        self, limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch articles that need sentiment analysis processing.

        Args:
            limit: Maximum number of articles to fetch

        Returns:
            List of article dictionaries
        """
        try:
            with self.postgres_conn.cursor() as cur:
                # Get articles that don't have recent sentiment analysis
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
                    scraped_at
                FROM news_articles 
                WHERE 
                    (sentiment_processed_at IS NULL 
                     OR sentiment_processed_at < %s)
                    AND LENGTH(content) >= %s
                    AND published_date >= %s
                ORDER BY published_date DESC
                """

                params = [
                    processing_window,
                    int(os.getenv("MINIMUM_ARTICLE_LENGTH", "100")),
                    datetime.now(timezone.utc) - timedelta(days=7),  # Last 7 days
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
                    }
                    articles.append(article)

                logger.info(f"Fetched {len(articles)} articles for processing")
                return articles

        except Exception as e:
            logger.error(f"Failed to fetch articles: {e}")
            return []

    def process_article_batch(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of articles for sentiment analysis.

        Args:
            articles: List of article dictionaries

        Returns:
            List of processing results
        """
        batch_start_time = time.time()
        results = []

        try:
            logger.info(f"Processing batch of {len(articles)} articles")

            # Prepare texts for batch processing
            texts = []
            for article in articles:
                # Combine title and content for analysis
                full_text = f"{article.get('title', '')}. {article.get('content', '')}"
                # Truncate to maximum length
                max_length = int(os.getenv("ARTICLE_TEXT_MAX_LENGTH", "10000"))
                if len(full_text) > max_length:
                    full_text = full_text[:max_length] + "..."
                texts.append(full_text)

            # Perform batch sentiment analysis
            if hasattr(self.sentiment_analyzer, "analyze_batch"):
                # Use batch processing if available
                sentiment_results = self.sentiment_analyzer.analyze_batch(texts)
            else:
                # Fall back to individual processing
                sentiment_results = []
                for text in texts:
                    result = self.sentiment_analyzer.analyze(text)
                    sentiment_results.append(result)

            # Combine results with article metadata
            for i, (article, sentiment_result) in enumerate(
                zip(articles, sentiment_results)
            ):
                try:
                    result = {
                        "article_id": article["article_id"],
                        "title": article["title"],
                        "url": article["url"],
                        "source": article["source"],
                        "published_date": article["published_date"],
                        "scraped_at": article["scraped_at"],
                        "sentiment_label": sentiment_result["label"],
                        "sentiment_score": float(sentiment_result["score"]),
                        "sentiment_confidence": float(
                            sentiment_result.get(
                                "confidence", sentiment_result["score"]
                            )
                        ),
                        "sentiment_all_scores": sentiment_result.get("all_scores", {}),
                        "processing_timestamp": datetime.now(timezone.utc),
                        "processing_job_type": self.job_type,
                        "model_name": self.model_name,
                        "gpu_used": self.use_gpu,
                    }
                    results.append(result)
                    self.stats["articles_processed"] += 1

                except Exception as e:
                    logger.error(
                        f"Failed to process article {article['article_id']}: {e}"
                    )
                    self.stats["articles_failed"] += 1

            batch_processing_time = time.time() - batch_start_time
            self.stats["total_processing_time"] += batch_processing_time
            self.stats["batches_processed"] += 1

            logger.info(f"Processed batch in {batch_processing_time:.2f}s")
            return results

        except Exception as e:
            logger.error(f"Failed to process batch: {e}")
            self.stats["articles_failed"] += len(articles)
            return []

    async def store_results_in_redshift(self, results: List[Dict[str, Any]]):
        """
        Store sentiment analysis results in Redshift.

        Args:
            results: List of processing results
        """
        try:
            if not results:
                return

            logger.info(f"Storing {len(results)} results in Redshift")

            # Prepare data for Redshift
            redshift_records = []
            for result in results:
                record = {
                    "article_id": result["article_id"],
                    "sentiment_label": result["sentiment_label"],
                    "sentiment_score": result["sentiment_score"],
                    "sentiment_confidence": result["sentiment_confidence"],
                    "sentiment_all_scores": json.dumps(result["sentiment_all_scores"]),
                    "processing_timestamp": result["processing_timestamp"],
                    "processing_job_type": result["processing_job_type"],
                    "model_name": result["model_name"],
                    "gpu_used": result["gpu_used"],
                }
                redshift_records.append(record)

            # Store in Redshift
            with self.redshift_processor as processor:
                # Create sentiment results table if it doesn't exist
                await self.create_sentiment_results_table(processor)

                # Insert results
                success_count = await processor.batch_insert_sentiment_results(
                    redshift_records
                )
                logger.info(
                    f"Successfully stored {success_count} sentiment results in Redshift"
                )

        except Exception as e:
            logger.error(f"Failed to store results in Redshift: {e}")
            # Save results to file as backup
            backup_file = os.path.join(
                self.output_dir, f"sentiment_results_backup_{int(time.time())}.json"
            )
            with open(backup_file, "w") as f:
                json.dump(results, f, indent=2, default=str)
            logger.info(f"Results saved to backup file: {backup_file}")

    async def create_sentiment_results_table(self, processor):
        """Create sentiment results table in Redshift if it doesn't exist."""
        try:
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS nlp_results.sentiment_analysis (
                id BIGINT IDENTITY(1,1) PRIMARY KEY,
                article_id VARCHAR(255) NOT NULL,
                sentiment_label VARCHAR(50) NOT NULL,
                sentiment_score DECIMAL(10,8) NOT NULL,
                sentiment_confidence DECIMAL(10,8),
                sentiment_all_scores VARCHAR(1000),
                processing_timestamp TIMESTAMP WITHOUT TIME ZONE,
                processing_job_type VARCHAR(100),
                model_name VARCHAR(200),
                gpu_used BOOLEAN,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT GETDATE()
            )
            DISTKEY(article_id)
            SORTKEY(processing_timestamp, sentiment_score);
            """

            await processor.execute_sql(create_table_sql)
            logger.info("Sentiment results table ensured in Redshift")

        except Exception as e:
            logger.error(f"Failed to create sentiment results table: {e}")
            raise

    async def update_postgres_processing_status(self, article_ids: List[str]):
        """
        Update PostgreSQL to mark articles as processed.

        Args:
            article_ids: List of article IDs that were processed
        """
        try:
            with self.postgres_conn.cursor() as cur:
                # Update processing timestamp
                update_sql = """
                UPDATE news_articles 
                SET sentiment_processed_at = %s
                WHERE article_id = ANY(%s)
                """

                cur.execute(update_sql, [datetime.now(timezone.utc), article_ids])

                self.postgres_conn.commit()
                logger.info(
                    f"Updated processing status for {len(article_ids)} articles"
                )

        except Exception as e:
            logger.error(f"Failed to update processing status: {e}")
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
                self.output_dir, f"sentiment_job_stats_{int(time.time())}.json"
            )
            with open(stats_file, "w") as f:
                json.dump(self.stats, f, indent=2, default=str)

            logger.info(f"Processing statistics saved to {stats_file}")
            logger.info(f"Job Summary:")
            logger.info(f"  Articles Processed: {self.stats['articles_processed']}")
            logger.info(f"  Articles Failed: {self.stats['articles_failed']}")
            logger.info(f"  Batches Processed: {self.stats['batches_processed']}")
            logger.info(
                f"  Total Duration: {self.stats['total_duration_seconds']:.2f}s"
            )
            if self.stats["articles_processed"] > 0:
                logger.info(
                    f"  Throughput: {self.stats.get('throughput_articles_per_second', 0):.2f} articles/sec"
                )

        except Exception as e:
            logger.error(f"Failed to save processing statistics: {e}")

    async def run_processing_job(self, max_articles: int = None):
        """
        Run the main sentiment analysis processing job.

        Args:
            max_articles: Maximum number of articles to process
        """
        try:
            logger.info("Starting sentiment analysis processing job")

            # Initialize components
            await self.initialize()

            # Fetch articles to process
            articles = await self.fetch_articles_to_process(limit=max_articles)

            if not articles:
                logger.info("No articles found for processing")
                return

            # Process articles in batches
            all_results = []

            # Use ThreadPoolExecutor for concurrent batch processing
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Split articles into batches
                article_batches = [
                    articles[i : i + self.batch_size]
                    for i in range(0, len(articles), self.batch_size)
                ]

                # Submit batch processing tasks
                future_to_batch = {
                    executor.submit(self.process_article_batch, batch): batch
                    for batch in article_batches
                }

                # Collect results as they complete
                for future in as_completed(future_to_batch):
                    batch = future_to_batch[future]
                    try:
                        batch_results = future.result()
                        all_results.extend(batch_results)

                        # Store batch results in Redshift immediately
                        if batch_results:
                            await self.store_results_in_redshift(batch_results)

                            # Update PostgreSQL processing status
                            article_ids = [r["article_id"] for r in batch_results]
                            await self.update_postgres_processing_status(article_ids)

                    except Exception as e:
                        logger.error(f"Batch processing failed: {e}")

            # Save final statistics
            self.save_processing_stats()

            logger.info(f"Sentiment analysis job completed successfully")
            logger.info(f"Processed {len(all_results)} articles total")

        except Exception as e:
            logger.error(f"Sentiment analysis job failed: {e}")
            raise

        finally:
            # Cleanup connections
            if self.postgres_conn:
                self.postgres_conn.close()
            if self.redshift_processor:
                await self.redshift_processor.close()


async def main():
    """Main entry point for the Kubernetes sentiment processing job."""
    parser = argparse.ArgumentParser(
        description="Kubernetes Sentiment Analysis Processor"
    )
    parser.add_argument("--job-type", default="sentiment-analysis", help="Type of job")
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Batch size for processing"
    )
    parser.add_argument(
        "--max-workers", type=int, default=4, help="Maximum worker threads"
    )
    parser.add_argument("--max-articles", type=int, help="Maximum articles to process")
    parser.add_argument(
        "--model-name",
        default="cardiffnlp/twitter-roberta-base-sentiment-latest",
        help="Model name",
    )
    parser.add_argument("--output-dir", default="/app/results", help="Output directory")
    parser.add_argument(
        "--model-cache-dir", default="/app/models", help="Model cache directory"
    )
    parser.add_argument(
        "--use-gpu", action="store_true", default=True, help="Use GPU acceleration"
    )

    args = parser.parse_args()

    # Override with environment variables if set
    batch_size = int(os.getenv("BATCH_SIZE", args.batch_size))
    max_workers = int(os.getenv("MAX_WORKERS", args.max_workers))
    use_gpu = os.getenv("USE_GPU", "true").lower() == "true" and args.use_gpu

    # Create processor
    processor = KubernetesSentimentProcessor(
        job_type=args.job_type,
        batch_size=batch_size,
        max_workers=max_workers,
        use_gpu=use_gpu,
        model_name=os.getenv("MODEL_NAME", args.model_name),
        output_dir=args.output_dir,
        model_cache_dir=args.model_cache_dir,
    )

    # Run the processing job
    try:
        await processor.run_processing_job(max_articles=args.max_articles)
        logger.info("Sentiment analysis job completed successfully")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Sentiment analysis job failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
