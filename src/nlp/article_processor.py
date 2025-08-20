"""
Article processing pipeline that analyzes sentiment and stores results in Redshift.
"""

import logging
from typing import Dict, List

import psycopg2
from psycopg2.extras import execute_batch

from .sentiment_analysis import create_analyzer

logger = logging.getLogger(__name__)


class ArticleProcessor:
    """Processes articles for sentiment analysis and stores results in Redshift."""

    def __init__(
        self,
        redshift_host: str,
        redshift_port: int,
        redshift_database: str,
        redshift_user: str,
        redshift_password: str,
        sentiment_provider: str = "aws",
        batch_size: int = 25,
        **sentiment_kwargs,
    ):
        """
        Initialize the article processor.

        Args:
            redshift_host: Redshift cluster host
            redshift_port: Redshift port
            redshift_database: Database name
            redshift_user: Database user
            redshift_password: Database password
            sentiment_provider: Which sentiment analyzer to use ("vader", "aws", or "transformers")
            batch_size: Size of batches for processing
            **sentiment_kwargs: Additional arguments for sentiment analyzer
        """
        self.batch_size = batch_size
        self.conn_params = {
            "host": redshift_host,
            "port": redshift_port,
            "database": redshift_database,
            "user": redshift_user,
            "password": redshift_password,
        }

        # Initialize sentiment analyzer
        try:
            self.analyzer = create_analyzer(sentiment_provider, **sentiment_kwargs)
            logger.info(
                "Initialized sentiment analyzer with provider: {0}".format(
                    sentiment_provider
                )
            )
        except Exception as e:
            logger.error("Failed to initialize sentiment analyzer: {0}".format(str(e)))
            raise

        # Create tables if they don't exist
        self._initialize_database()

    def _initialize_database(self):
        """Create necessary database tables if they don't exist."""
        create_tables_sql = """
        CREATE TABLE IF NOT EXISTS article_sentiment (
            article_id VARCHAR(255) PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT,
            content TEXT,
            sentiment VARCHAR(50),
            confidence FLOAT,
            sentiment_scores JSONB,
            provider VARCHAR(50),
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_domain VARCHAR(255),
            publish_date DATE
        );
        """

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    cur.execute(create_tables_sql)
                    conn.commit()
                    logger.info("Successfully initialized database tables")
        except Exception as e:
            logger.error("Failed to initialize database: {0}".format(str(e)))
            raise

    def _store_results(self, results: List[Dict]):
        """Store sentiment analysis results in Redshift."""
        insert_sql = """
        INSERT INTO article_sentiment (
            article_id, url, title, content, sentiment, confidence,
            sentiment_scores, provider, source_domain, publish_date
        ) VALUES (
            %(article_id)s, %(url)s, %(title)s, %(content)s, %(sentiment)s,
            %(confidence)s, %(sentiment_scores)s, %(provider)s,
            %(source_domain)s, %(publish_date)s
        )
        ON CONFLICT (article_id) DO UPDATE SET
            sentiment = EXCLUDED.sentiment,
            confidence = EXCLUDED.confidence,
            sentiment_scores = EXCLUDED.sentiment_scores,
            processed_at = CURRENT_TIMESTAMP;
        """

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    execute_batch(cur, insert_sql, results, page_size=self.batch_size)
                    conn.commit()
                    logger.info(
                        "Successfully stored {0} results in Redshift".format(
                            len(results)
                        )
                    )
        except Exception as e:
            logger.error("Failed to store results in Redshift: {0}".format(str(e)))
            raise

    def process_articles(self, articles: List[Dict]) -> List[Dict]:
        """
        Process a batch of articles through sentiment analysis and store results.

        Args:
            articles: List of article dictionaries with keys:
                     - article_id: Unique identifier
                     - url: Article URL
                     - title: Article title
                     - content: Article content
                     - source_domain: Source website domain
                     - publish_date: Article publication date (optional)

        Returns:
            List of processed results including sentiment analysis
        """
        try:
            # Extract content for analysis
            texts = [
                f"{article.get('title', '')}. {article.get('content', '')}"
                for article in articles
            ]

            # Perform batch sentiment analysis
            sentiment_results = self.analyzer.batch_analyze(
                texts, batch_size=self.batch_size
            )

            # Combine article data with sentiment results
            processed_results = []
            for article, sentiment in zip(articles, sentiment_results):
                result = {
                    "article_id": article["article_id"],
                    "url": article["url"],
                    "title": article.get("title"),
                    "content": article.get("content"),
                    "sentiment": sentiment["sentiment"],
                    "confidence": sentiment["confidence"],
                    "sentiment_scores": sentiment.get("all_scores", {}),
                    "provider": sentiment["provider"],
                    "source_domain": article.get("source_domain"),
                    "publish_date": article.get("publish_date"),
                }
                processed_results.append(result)

            # Store results in Redshift
            self._store_results(processed_results)

            return processed_results

        except Exception as e:
            logger.error("Error processing articles: {0}".format(str(e)))
            raise


# Example usage
if __name__ == "__main__":
    # Example configuration
    config = {
        "redshift_host": "your-cluster.region.redshift.amazonaws.com",
        "redshift_port": 5439,
        "redshift_database": "news_db",
        "redshift_user": "admin",
        "redshift_password": "your-password",
        "sentiment_provider": "aws",
        "region_name": "us-west-2",  # for AWS Comprehend
    }

    # Initialize processor
    processor = ArticleProcessor(**config)

    # Example articles
    articles = [
        {
            "article_id": "123",
            "url": "https://example.com/article1",
            "title": "Company XYZ Reports Strong Growth",
            "content": "Company XYZ announced record profits...",
            "source_domain": "example.com",
            "publish_date": "2025-04-06",
        }
    ]

    # Process articles
    results = processor.process_articles(articles)
    print("Processed {0} articles".format(len(results)))
