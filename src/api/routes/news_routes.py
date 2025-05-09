"""
FastAPI routes for accessing processed news articles.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
from src.database.redshift_loader import RedshiftLoader

router = APIRouter(prefix="/news", tags=["news"])

async def get_db():
    """Dependency to get database connection."""
    host = os.getenv("REDSHIFT_HOST")
    if not host:
        raise HTTPException(
            status_code=500,
            detail="REDSHIFT_HOST environment variable not set"
        )
    
    db = RedshiftLoader(
        host=host,
        database=os.getenv("REDSHIFT_DB", "dev"),
        user=os.getenv("REDSHIFT_USER", "admin"),
        password=os.getenv("REDSHIFT_PASSWORD")
    )
    try:
        await db.connect()
        yield db
    finally:
        await db.close()

@router.get("/articles")
async def get_articles(
    start_date: Optional[datetime] = Query(None, description="Filter articles from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter articles until this date"),
    source: Optional[str] = Query(None, description="Filter by news source"),
    category: Optional[str] = Query(None, description="Filter by article category"),
    db: RedshiftLoader = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Retrieve processed news articles with optional filtering.
    
    Args:
        start_date: Optional start date filter
        end_date: Optional end date filter 
        source: Optional news source filter
        category: Optional category filter
        db: Database connection (injected)
        
    Returns:
        List of article dictionaries with fields:
        - id: Article unique identifier
        - title: Article title
        - url: Original article URL
        - publish_date: Publication date
        - source: News source name
        - category: Article category
        - sentiment: Sentiment analysis result
        
    Raises:
        HTTPException: If database query fails
    """
    try:
        # Build query conditions
        conditions = []
        params = []
        
        if start_date:
            conditions.append("publish_date >= %s")
            params.append(start_date)
            
        if end_date:
            conditions.append("publish_date <= %s") 
            params.append(end_date)
            
        if source:
            conditions.append("source = %s")
            params.append(source)
            
        if category:
            conditions.append("category = %s")
            params.append(category)
            
        # Construct WHERE clause
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT id, title, url, publish_date, source, category, 
                   sentiment_score, sentiment_label
            FROM news_articles 
            WHERE {where_clause}
            ORDER BY publish_date DESC
        """
        
        results = await db.execute_query(query, params)
        
        # Format results
        articles = []
        for row in results:
            articles.append({
                "id": row[0],
                "title": row[1], 
                "url": row[2],
                "publish_date": row[3].isoformat() if row[3] else None,
                "source": row[4],
                "category": row[5],
                "sentiment": {
                    "score": float(row[6]) if row[6] else None,
                    "label": row[7]
                }
            })
            
        return articles
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )

@router.get("/articles/{article_id}")
async def get_article(
    article_id: str,
    db: RedshiftLoader = Depends(get_db)
) -> Dict[str, Any]:
    """
    Retrieve a specific news article by ID.
    
    Args:
        article_id: Unique identifier of the article
        db: Database connection (injected)
        
    Returns:
        Article dictionary with fields:
        - id: Article unique identifier
        - title: Article title
        - url: Original article URL
        - publish_date: Publication date
        - source: News source name
        - category: Article category
        - content: Article content
        - sentiment: Sentiment analysis result
        - entities: Named entities mentioned
        
    Raises:
        HTTPException: If article not found or database error occurs
    """
    try:
        query = """
            SELECT a.id, a.title, a.url, a.publish_date, a.source, 
                   a.category, a.content, a.sentiment_score, a.sentiment_label,
                   array_agg(DISTINCT e.entity) as entities
            FROM news_articles a
            LEFT JOIN article_entities e ON a.id = e.article_id
            WHERE a.id = %s
            GROUP BY a.id, a.title, a.url, a.publish_date, a.source,
                     a.category, a.content, a.sentiment_score, a.sentiment_label
        """
        
        results = await db.execute_query(query, [article_id])
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Article {article_id} not found"
            )
            
        row = results[0]
        article = {
            "id": row[0],
            "title": row[1],
            "url": row[2], 
            "publish_date": row[3].isoformat() if row[3] else None,
            "source": row[4],
            "category": row[5],
            "content": row[6],
            "sentiment": {
                "score": float(row[7]) if row[7] else None,
                "label": row[8]
            },
            "entities": row[9] if row[9] else []
        }
        
        return article
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Database error: {str(e)}"
        )