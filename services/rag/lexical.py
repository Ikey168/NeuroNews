"""
Lexical Search Service using PostgreSQL Full-Text Search
Issue #231: Lexical search (Postgres FTS) for hybrid retrieval

This module provides BM25-like lexical search capabilities using PostgreSQL's
tsvector and tsrank functionality for fast text-based retrieval.
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Union, Any, Tuple
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class LexicalSearchResult:
    """Result from lexical search with ranking and highlighting."""
    id: str
    doc_id: str
    chunk_id: str
    title: str
    content: str
    source: str
    language: str
    published_at: Optional[datetime]
    url: str
    rank: float
    headline: str
    word_count: int
    char_count: int


@dataclass
class SearchFilters:
    """Filters for lexical search queries."""
    source: Optional[str] = None
    language: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    min_rank: float = 0.0


class LexicalSearchService:
    """
    PostgreSQL Full-Text Search service for lexical retrieval.
    
    Features:
    - BM25-like ranking using ts_rank_cd
    - Query highlighting with ts_headline
    - Configurable filters (source, language, date range)
    - Automatic tsvector updates via triggers
    - Performance monitoring and statistics
    """
    
    def __init__(self, connection_params: Optional[Dict[str, Any]] = None):
        """Initialize the lexical search service."""
        self.connection_params = connection_params or self._default_connection_params()
        self.connection = None
        
    def _default_connection_params(self) -> Dict[str, Any]:
        """Get default database connection parameters."""
        return {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5433)),
            'database': os.getenv('POSTGRES_DB', 'neuronews_vector'),
            'user': os.getenv('POSTGRES_USER', 'neuronews'),
            'password': os.getenv('POSTGRES_PASSWORD', 'neuronews_vector_pass'),
        }
    
    def connect(self):
        """Connect to PostgreSQL database."""
        try:
            self.connection = psycopg2.connect(**self.connection_params)
            logger.info(f"Connected to database for lexical search: {self.connection_params['database']}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from database."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Disconnected from database")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    def search(
        self,
        query: str,
        k: int = 10,
        filters: Optional[SearchFilters] = None
    ) -> List[LexicalSearchResult]:
        """
        Perform lexical search using PostgreSQL FTS.
        
        Args:
            query: Search query text
            k: Number of results to return (default: 10)
            filters: Optional search filters
            
        Returns:
            List of ranked search results with highlights
        """
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first or use context manager.")
        
        filters = filters or SearchFilters()
        
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # Convert filters to JSONB
                filter_json = {
                    'source': filters.source,
                    'language': filters.language,
                    'date_from': filters.date_from.isoformat() if filters.date_from else None,
                    'date_to': filters.date_to.isoformat() if filters.date_to else None,
                    'min_rank': filters.min_rank,
                }
                
                # Execute lexical search function
                cursor.execute(
                    "SELECT * FROM lexical_topk(%s, %s, %s)",
                    (query, k, json.dumps(filter_json))
                )
                
                results = cursor.fetchall()
                
                # Convert to LexicalSearchResult objects
                search_results = []
                for row in results:
                    result = LexicalSearchResult(
                        id=str(row['id']),
                        doc_id=row['doc_id'],
                        chunk_id=row['chunk_id'],
                        title=row['title'] or '',
                        content=row['content'] or '',
                        source=row['source'] or '',
                        language=row['language'] or 'unknown',
                        published_at=row['published_at'],
                        url=row['url'] or '',
                        rank=float(row['rank']),
                        headline=row['headline'] or '',
                        word_count=row['word_count'] or 0,
                        char_count=row['char_count'] or 0,
                    )
                    search_results.append(result)
                
                logger.info(f"Lexical search for '{query}' returned {len(search_results)} results")
                return search_results
                
        except Exception as e:
            logger.error(f"Lexical search failed for query '{query}': {e}")
            raise
    
    def simple_search(
        self,
        query: str,
        k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Perform simple lexical search without filters.
        
        Args:
            query: Search query text
            k: Number of results to return
            
        Returns:
            List of simple search results
        """
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first or use context manager.")
        
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT * FROM simple_lexical_search(%s, %s)",
                    (query, k)
                )
                
                results = cursor.fetchall()
                
                # Convert to dict list
                search_results = []
                for row in results:
                    result = {
                        'doc_id': row['doc_id'],
                        'chunk_id': row['chunk_id'],
                        'title': row['title'] or '',
                        'rank': float(row['rank']),
                        'headline': row['headline'] or '',
                    }
                    search_results.append(result)
                
                logger.info(f"Simple search for '{query}' returned {len(search_results)} results")
                return search_results
                
        except Exception as e:
            logger.error(f"Simple search failed for query '{query}': {e}")
            raise
    
    def get_search_stats(self) -> Dict[str, Any]:
        """Get statistics about the full-text search index."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first or use context manager.")
        
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM fts_stats")
                stats = cursor.fetchone()
                
                if stats:
                    return dict(stats)
                else:
                    return {}
                    
        except Exception as e:
            logger.error(f"Failed to get search stats: {e}")
            raise
    
    def reindex_chunk(self, chunk_id: str):
        """Manually reindex a specific chunk's search vector."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first or use context manager.")
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE chunks 
                    SET search_vector = 
                        setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                        setweight(to_tsvector('english', COALESCE(content, '')), 'B')
                    WHERE chunk_id = %s
                """, (chunk_id,))
                
                self.connection.commit()
                logger.info(f"Reindexed search vector for chunk: {chunk_id}")
                
        except Exception as e:
            logger.error(f"Failed to reindex chunk {chunk_id}: {e}")
            self.connection.rollback()
            raise
    
    def reindex_all(self):
        """Manually reindex all chunks' search vectors."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first or use context manager.")
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE chunks 
                    SET search_vector = 
                        setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                        setweight(to_tsvector('english', COALESCE(content, '')), 'B')
                    WHERE doc_id IS NOT NULL
                """)
                
                rows_updated = cursor.rowcount
                self.connection.commit()
                logger.info(f"Reindexed search vectors for {rows_updated} chunks")
                return rows_updated
                
        except Exception as e:
            logger.error(f"Failed to reindex all chunks: {e}")
            self.connection.rollback()
            raise
    
    def test_query_parsing(self, query: str) -> Dict[str, Any]:
        """Test how a query gets parsed into tsquery."""
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first or use context manager.")
        
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        %s as original_query,
                        plainto_tsquery('english', %s) as parsed_tsquery,
                        to_tsquery('english', %s || ':*') as prefix_tsquery
                """, (query, query, query))
                
                result = cursor.fetchone()
                return dict(result) if result else {}
                
        except Exception as e:
            logger.error(f"Query parsing test failed for '{query}': {e}")
            return {'error': str(e)}


def get_lexical_search_service(connection_params: Optional[Dict[str, Any]] = None) -> LexicalSearchService:
    """Factory function to get a lexical search service instance."""
    return LexicalSearchService(connection_params)


# Convenience functions for direct usage
def lexical_search(
    query: str,
    k: int = 10,
    filters: Optional[SearchFilters] = None,
    connection_params: Optional[Dict[str, Any]] = None
) -> List[LexicalSearchResult]:
    """
    Convenience function for one-off lexical searches.
    
    Args:
        query: Search query text
        k: Number of results to return
        filters: Optional search filters
        connection_params: Optional database connection parameters
        
    Returns:
        List of search results
    """
    with get_lexical_search_service(connection_params) as service:
        return service.search(query, k, filters)


def simple_lexical_search(
    query: str,
    k: int = 10,
    connection_params: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function for simple lexical searches.
    
    Args:
        query: Search query text
        k: Number of results to return
        connection_params: Optional database connection parameters
        
    Returns:
        List of simple search results
    """
    with get_lexical_search_service(connection_params) as service:
        return service.simple_search(query, k)
