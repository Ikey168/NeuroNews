"""
Redshift loader module for NeuroNews.
Handles ETL operations for loading processed articles into Redshift.
"""
import os
import json
import logging
import psycopg2
from typing import Optional, Dict, Any, List
from datetime import datetime
from .s3_storage import S3Storage

# Configure logging
logger = logging.getLogger(__name__)

class RedshiftLoader:
    """Handles ETL operations for loading articles into Redshift."""

    def __init__(
        self,
        host: str,
        port: int = 5439,
        database: str = "neuronews",
        user: str = "admin",
        password: Optional[str] = None,
        s3_storage: Optional[S3Storage] = None
    ):
        """
        Initialize Redshift loader.
        
        Args:
            host: Redshift cluster endpoint
            port: Redshift port (default: 5439)
            database: Database name (default: neuronews)
            user: Database user (default: admin)
            password: Database password. If None, will use environment variable REDSHIFT_PASSWORD
            s3_storage: Optional S3Storage instance. If None, will create new instance using environment variables
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password or os.environ.get('REDSHIFT_PASSWORD')
        
        if not self.password:
            raise ValueError("Database password must be provided either directly or via REDSHIFT_PASSWORD environment variable")
            
        # Initialize S3 storage if not provided
        self.s3_storage = s3_storage or S3Storage(
            bucket_name=os.environ.get('S3_BUCKET', 'neuronews-raw-articles-dev'),
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            aws_region=os.environ.get('AWS_REGION', 'us-west-2')
        )

    def connect(self) -> psycopg2.extensions.connection:
        """
        Create a connection to the Redshift database.
        
        Returns:
            Database connection object
        """
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password
        )

    def load_article(self, article_data: Dict[str, Any]) -> str:
        """
        Load a single article into Redshift.
        
        Args:
            article_data: Dictionary containing article data
            
        Returns:
            ID of the inserted article
            
        Raises:
            ValueError: If required article fields are missing
            psycopg2.Error: If database operation fails
        """
        required_fields = ['id', 'source', 'title', 'content', 'published_date']
        missing_fields = [field for field in required_fields if field not in article_data]
        if missing_fields:
            raise ValueError(f"Missing required article fields: {missing_fields}")

        # Generate ID if not provided
        if 'id' not in article_data:
            article_data['id'] = f"article_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(article_data['title'])}"

        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO news_articles (
                        id, source, title, content, published_date, 
                        sentiment, entities, keywords
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id;
                """, (
                    article_data['id'],
                    article_data['source'],
                    article_data['title'],
                    article_data['content'],
                    article_data['published_date'],
                    article_data.get('sentiment'),
                    json.dumps(article_data.get('entities', {})),
                    json.dumps(article_data.get('keywords', []))
                ))
                article_id = cur.fetchone()[0]
                logger.info(f"Successfully loaded article into Redshift: {article_id}")
                return article_id

    def load_articles_from_s3(
        self,
        s3_prefix: Optional[str] = None,
        batch_size: int = 100,
        max_articles: Optional[int] = None
    ) -> List[str]:
        """
        Load multiple articles from S3 into Redshift.
        
        Args:
            s3_prefix: Optional prefix to filter S3 objects
            batch_size: Number of articles to process in each batch
            max_articles: Maximum number of articles to process
            
        Returns:
            List of loaded article IDs
            
        Raises:
            Exception: If article loading fails
        """
        loaded_ids = []
        processed_count = 0
        
        try:
            articles = self.s3_storage.list_articles(prefix=s3_prefix, max_items=max_articles)
            
            for i in range(0, len(articles), batch_size):
                batch = articles[i:i + batch_size]
                
                for article_obj in batch:
                    try:
                        # Get full article data from S3
                        article = self.s3_storage.get_article(article_obj['key'])
                        article_data = article['data']
                        
                        # Load article into Redshift
                        article_id = self.load_article(article_data)
                        loaded_ids.append(article_id)
                        processed_count += 1
                        
                        if max_articles and processed_count >= max_articles:
                            return loaded_ids
                            
                    except Exception as e:
                        logger.error(f"Failed to load article {article_obj['key']}: {e}")
                        continue
                        
                logger.info(f"Processed batch of {len(batch)} articles")
                
            return loaded_ids
            
        except Exception as e:
            logger.error(f"Failed to load articles from S3: {e}")
            raise

    def delete_article(self, article_id: str) -> None:
        """
        Delete an article from Redshift.
        
        Args:
            article_id: ID of the article to delete
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM news_articles WHERE id = %s", (article_id,))
                logger.info(f"Successfully deleted article from Redshift: {article_id}")