"""
FastAPI routes for content search and query processing.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.database.snowflake_analytics_connector import SnowflakeAnalyticsConnector

router = APIRouter(prefix="/search", tags=["search"])


async def get_db():
    """Dependency to get database connection."""
    account = os.getenv("SNOWFLAKE_ACCOUNT")
    if not account:
        raise HTTPException(
            status_code=500, detail="SNOWFLAKE_ACCOUNT environment variable not set"
        )

    db = SnowflakeAnalyticsConnector(
        account=account,
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        database=os.getenv("SNOWFLAKE_DATABASE", "NEURONEWS"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "ANALYTICS_WH"),
    )
    try:
        db.connect()
        yield db
    finally:
        db.disconnect()


@router.get("/articles")
async def search_articles(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results to return"),
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = Query(None, description="Filter by news source"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter until date"),
    sort_by: str = Query("relevance", description="Sort by: relevance, date, popularity"),
    db: SnowflakeAnalyticsConnector = Depends(get_db),
) -> Dict[str, Any]:
    """
    Search articles by keywords with ranking and filtering.
    
    Args:
        q: Search query string (required)
        limit: Maximum number of results (1-100)
        category: Optional category filter
        source: Optional source filter
        start_date: Optional start date filter
        end_date: Optional end date filter
        sort_by: Sort order (relevance, date, popularity)
        db: Database connection (injected)
    
    Returns:
        Dict containing search results and metadata
    """
    try:
        conditions = []
        params = []
        
        # Add search conditions
        search_condition = "(title ILIKE %s OR content ILIKE %s)"
        search_pattern = "%{}%".format(q)
        conditions.append(search_condition)
        params.extend([search_pattern, search_pattern])
        
        # Add filters
        if category:
            conditions.append("category = %s")
            params.append(category)
            
        if source:
            conditions.append("source = %s")
            params.append(source)
            
        if start_date:
            conditions.append("publish_date >= %s")
            params.append(start_date)
            
        if end_date:
            conditions.append("publish_date <= %s")
            params.append(end_date)
        
        where_clause = " AND ".join(conditions)
        
        # Determine sort order
        if sort_by == "date":
            order_clause = "ORDER BY publish_date DESC"
        elif sort_by == "popularity":
            order_clause = "ORDER BY view_count DESC, publish_date DESC"
        else:  # relevance - simple scoring based on title vs content matches
            order_clause = """ORDER BY 
                CASE WHEN title ILIKE %s THEN 2 ELSE 1 END DESC,
                publish_date DESC"""
            params.append(search_pattern)
        
        # Build main search query
        query = """
            SELECT id, title, url, publish_date, source, category,
                   LEFT(content, 200) as snippet,
                   sentiment_score, sentiment_label,
                   CASE WHEN title ILIKE %s THEN 2 ELSE 1 END as relevance_score
            FROM news_articles
            WHERE {where_clause}
            {order_clause}
            LIMIT %s
        """.format(where_clause=where_clause, order_clause=order_clause)
        
        if sort_by == "relevance":
            params.append(search_pattern)  # For relevance scoring in SELECT
        params.append(limit)
        
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
                "snippet": row[6],
                "sentiment": {
                    "score": float(row[7]) if row[7] else None,
                    "label": row[8]
                },
                "relevance_score": int(row[9]) if len(row) > 9 else 1
            })
        
        # Get total count for metadata
        count_query = """
            SELECT COUNT(*) FROM news_articles WHERE {where_clause}
        """.format(where_clause=where_clause)
        
        count_params = params[:-1]  # Remove limit from params
        if sort_by == "relevance":
            count_params = count_params[:-1]  # Remove relevance pattern too
            
        count_results = await db.execute_query(count_query, count_params)
        total_count = count_results[0][0] if count_results else 0
        
        return {
            "query": q,
            "results": articles,
            "total_results": total_count,
            "returned_results": len(articles),
            "filters": {
                "category": category,
                "source": source,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "sort_by": sort_by
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Search error: {}".format(str(e))
        )


@router.get("/facets")
async def get_search_facets(
    q: Optional[str] = Query(None, description="Optional query to scope facets"),
    db: SnowflakeAnalyticsConnector = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get search facets (categories, sources, etc.) for filtering.
    
    Args:
        q: Optional search query to scope facets
        db: Database connection (injected)
        
    Returns:
        Dict containing available facets and counts
    """
    try:
        base_condition = "1=1"
        params = []
        
        if q:
            base_condition = "(title ILIKE %s OR content ILIKE %s)"
            search_pattern = "%{}%".format(q)
            params.extend([search_pattern, search_pattern])
        
        # Get category facets
        category_query = """
            SELECT category, COUNT(*) as count
            FROM news_articles 
            WHERE {condition} AND category IS NOT NULL
            GROUP BY category 
            ORDER BY count DESC
            LIMIT 20
        """.format(condition=base_condition)
        
        category_results = await db.execute_query(category_query, params)
        
        # Get source facets  
        source_query = """
            SELECT source, COUNT(*) as count
            FROM news_articles
            WHERE {condition} AND source IS NOT NULL
            GROUP BY source
            ORDER BY count DESC  
            LIMIT 20
        """.format(condition=base_condition)
        
        source_results = await db.execute_query(source_query, params)
        
        return {
            "categories": [{"name": row[0], "count": int(row[1])} for row in category_results],
            "sources": [{"name": row[0], "count": int(row[1])} for row in source_results],
            "query_scope": q
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving facets: {}".format(str(e))
        )


@router.get("/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=1, description="Partial search query"),
    limit: int = Query(5, ge=1, le=20, description="Maximum suggestions"),
    db: SnowflakeAnalyticsConnector = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Get search suggestions based on partial query.
    
    Args:
        q: Partial search query
        limit: Maximum number of suggestions
        db: Database connection (injected)
        
    Returns:
        List of search suggestions with metadata
    """
    try:
        # Simple suggestion based on article titles and frequent terms
        query = """
            SELECT DISTINCT 
                title,
                source,
                category,
                COUNT(*) as frequency
            FROM news_articles
            WHERE title ILIKE %s
            GROUP BY title, source, category
            ORDER BY frequency DESC, LENGTH(title) ASC
            LIMIT %s
        """
        
        suggestion_pattern = "%{}%".format(q)
        results = await db.execute_query(query, [suggestion_pattern, limit])
        
        suggestions = []
        for row in results:
            suggestions.append({
                "text": row[0],
                "source": row[1],
                "category": row[2], 
                "frequency": int(row[3])
            })
            
        return suggestions
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Error retrieving suggestions: {}".format(str(e))
        )
