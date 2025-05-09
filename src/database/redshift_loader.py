"""RedshiftLoader class for database interactions."""

import os
import psycopg2
from datetime import datetime
from typing import List, Dict, Any, Optional

class RedshiftLoader:
    """Handles loading and retrieving data from AWS Redshift."""
    
    def __init__(self, host: str, database: str = "dev", 
                 user: str = "admin", password: Optional[str] = None):
        """Initialize RedshiftLoader.
        
        Args:
            host: Redshift cluster endpoint
            database: Database name
            user: Username for authentication
            password: Password for authentication (can be None if using env var)
        """
        self._host = host
        self._database = database
        self._user = user
        self._password = password or os.environ.get("REDSHIFT_PASSWORD")
        if not self._password:
            raise ValueError("Password must be provided or set in REDSHIFT_PASSWORD env var")
        
        self._conn = None
        self._cursor = None

    async def connect(self) -> None:
        """Establish connection to Redshift."""
        if self._conn is None:
            self._conn = psycopg2.connect(
                host=self._host,
                database=self._database,
                user=self._user,
                password=self._password
            )
            self._cursor = self._conn.cursor()

    async def close(self) -> None:
        """Close database connection."""
        if self._cursor:
            self._cursor.close()
        if self._conn:
            self._conn.close()
            self._conn = None
            self._cursor = None

    async def execute_query(self, query: str, params: Optional[List] = None) -> List:
        """Execute a query and return results.
        
        Args:
            query: SQL query string
            params: Optional list of parameters for query
            
        Returns:
            List of query result rows
        """
        self._cursor.execute(query, params or [])
        return self._cursor.fetchall()

    async def get_latest_articles(self, 
                                limit: int = 10,
                                min_score: float = None,
                                sentiment: str = None,
                                category: str = None) -> List[Dict[str, Any]]:
        """Fetch latest news articles with optional filtering.
        
        Args:
            limit: Maximum number of articles to return
            min_score: Optional minimum sentiment score filter
            sentiment: Optional sentiment label filter (POSITIVE/NEGATIVE/NEUTRAL)
            category: Optional category filter
            
        Returns:
            List of article dictionaries containing:
            - id: Unique identifier
            - title: Article title
            - url: Source URL
            - publish_date: Publication date
            - category: Article category
            - source: News source
            - sentiment_score: Numerical sentiment score
            - sentiment_label: Sentiment classification
        """
        conditions = []
        params = []
        
        if min_score is not None:
            conditions.append("sentiment_score >= %s")
            params.append(min_score)
            
        if sentiment:
            conditions.append("sentiment_label = %s")
            params.append(sentiment.upper())
            
        if category:
            conditions.append("category = %s")
            params.append(category)
            
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT id, title, url, publish_date, category, source,
                   sentiment_score, sentiment_label
            FROM news_articles
            WHERE {where_clause}
            ORDER BY publish_date DESC
            LIMIT %s
        """
        params.append(limit)
        
        results = await self.execute_query(query, params)
        
        articles = []
        for row in results:
            articles.append({
                "id": row[0],
                "title": row[1],
                "url": row[2],
                "publish_date": row[3].isoformat() if row[3] else None,
                "category": row[4],
                "source": row[5],
                "sentiment": {
                    "score": float(row[6]) if row[6] else None,
                    "label": row[7]
                }
            })
            
        return articles

    async def load_article(self, article_data: Dict[str, Any]) -> None:
        """Load a single article into Redshift.
        
        Args:
            article_data: Dictionary containing article fields
        """
        required_fields = ["id", "title", "url", "content"]
        missing = [f for f in required_fields if f not in article_data]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
            
        query = """
            INSERT INTO news_articles (
                id, title, url, content, publish_date, 
                source, category, sentiment_score, sentiment_label
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params = [
            article_data["id"],
            article_data["title"],
            article_data["url"],
            article_data["content"],
            article_data.get("publish_date"),
            article_data.get("source"),
            article_data.get("category"),
            article_data.get("sentiment_score"),
            article_data.get("sentiment_label")
        ]
        
        await self.execute_query(query, params)
        self._conn.commit()

    async def delete_article(self, article_id: str) -> bool:
        """Delete an article from Redshift.
        
        Args:
            article_id: Unique identifier of article to delete
            
        Returns:
            True if article was deleted, False if not found
        """
        query = "DELETE FROM news_articles WHERE id = %s"
        self._cursor.execute(query, [article_id])
        deleted = self._cursor.rowcount > 0
        self._conn.commit()
        return deleted