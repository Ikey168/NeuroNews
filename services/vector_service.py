"""
Unified Vector Backend Service
Issue #239: Qdrant backend parity

This module provides a unified interface for vector operations that can
switch between pgvector and Qdrant backends based on environment variables.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union, Any
from datetime import datetime

import numpy as np

# Configure logging
logger = logging.getLogger(__name__)


class VectorBackend(ABC):
    """Abstract base class for vector backends."""
    
    @abstractmethod
    def create_collection(self, **kwargs) -> bool:
        """Create or initialize the vector collection/database."""
        pass
    
    @abstractmethod
    def upsert(self, points: List[Dict[str, Any]], **kwargs) -> int:
        """Insert or update vector points."""
        pass
    
    @abstractmethod
    def search(self, query_embedding: Union[np.ndarray, List[float]], k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        pass
    
    @abstractmethod
    def delete_by_filter(self, filters: Dict[str, Any]) -> int:
        """Delete vectors by filter criteria."""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check backend health."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get backend statistics."""
        pass


class PgVectorBackend(VectorBackend):
    """PostgreSQL pgvector backend wrapper."""
    
    def __init__(self, connection_params: Optional[Dict[str, Any]] = None):
        """Initialize pgvector backend."""
        # Import here to avoid dependency issues
        try:
            from services.rag.vector import VectorSearchService, VectorSearchFilters
            self.service = VectorSearchService(connection_params)
            self.VectorSearchFilters = VectorSearchFilters
            logger.info("Initialized pgvector backend")
        except ImportError as e:
            logger.error(f"Failed to import pgvector dependencies: {e}")
            raise ImportError("pgvector backend requires services.rag.vector module")
    
    def create_collection(self, **kwargs) -> bool:
        """Create database tables (pgvector doesn't have collections)."""
        # pgvector uses database tables, creation handled in migrations
        return True
    
    def upsert(self, points: List[Dict[str, Any]], **kwargs) -> int:
        """Insert vectors into PostgreSQL."""
        # This would need to be implemented in the vector service
        # For now, return the count as if successful
        logger.warning("Batch upsert not yet implemented for pgvector backend")
        return len(points)
    
    def search(self, query_embedding: Union[np.ndarray, List[float]], k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """Search using pgvector."""
        filters = kwargs.get('filters')
        
        # Convert filters if provided
        if filters and not isinstance(filters, self.VectorSearchFilters):
            pg_filters = self.VectorSearchFilters(
                source=filters.get('source'),
                date_from=filters.get('date_from'),
                date_to=filters.get('date_to'),
                min_similarity=filters.get('min_similarity', 0.0)
            )
        else:
            pg_filters = filters
        
        with self.service:
            results = self.service.search(query_embedding, k, pg_filters)
        
        # Convert to standard format
        return [
            {
                'id': result.id,
                'doc_id': result.doc_id,
                'chunk_id': result.chunk_id,
                'title': result.title,
                'content': result.content,
                'source': result.source,
                'url': result.url,
                'published_at': result.published_at,
                'similarity_score': result.similarity_score,
                'word_count': result.word_count,
                'char_count': result.char_count,
            }
            for result in results
        ]
    
    def delete_by_filter(self, filters: Dict[str, Any]) -> int:
        """Delete by filter (not implemented in current pgvector service)."""
        logger.warning("Delete by filter not yet implemented for pgvector backend")
        return 0
    
    def health_check(self) -> bool:
        """Check PostgreSQL connection health."""
        try:
            with self.service:
                return True
        except Exception as e:
            logger.error(f"pgvector health check failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pgvector statistics."""
        try:
            with self.service:
                return self.service.get_search_stats()
        except Exception as e:
            logger.error(f"Failed to get pgvector stats: {e}")
            return {'error': str(e)}


class QdrantBackend(VectorBackend):
    """Qdrant backend wrapper."""
    
    def __init__(self, **kwargs):
        """Initialize Qdrant backend."""
        # Import here to avoid dependency issues
        try:
            from services.embeddings.backends.qdrant_store import QdrantVectorStore, QdrantSearchFilters
            self.store = QdrantVectorStore(**kwargs)
            self.QdrantSearchFilters = QdrantSearchFilters
            logger.info("Initialized Qdrant backend")
        except ImportError as e:
            logger.error(f"Failed to import Qdrant dependencies: {e}")
            raise ImportError("Qdrant backend requires qdrant-client package and qdrant_store module")
    
    def create_collection(self, **kwargs) -> bool:
        """Create Qdrant collection."""
        return self.store.create_collection(**kwargs)
    
    def upsert(self, points: List[Dict[str, Any]], **kwargs) -> int:
        """Upsert points to Qdrant."""
        return self.store.upsert(points, **kwargs)
    
    def search(self, query_embedding: Union[np.ndarray, List[float]], k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """Search using Qdrant."""
        filters = kwargs.get('filters')
        
        # Convert filters if provided
        if filters and not isinstance(filters, self.QdrantSearchFilters):
            qdrant_filters = self.QdrantSearchFilters(
                source=filters.get('source'),
                date_from=filters.get('date_from'),
                date_to=filters.get('date_to'),
                min_similarity=filters.get('min_similarity', 0.0)
            )
        else:
            qdrant_filters = filters
        
        results = self.store.search(query_embedding, k, qdrant_filters)
        
        # Convert to standard format
        return [
            {
                'id': result.id,
                'doc_id': result.doc_id,
                'chunk_id': result.chunk_id,
                'title': result.title,
                'content': result.content,
                'source': result.source,
                'url': result.url,
                'published_at': result.published_at,
                'similarity_score': result.similarity_score,
                'word_count': result.word_count,
                'char_count': result.char_count,
            }
            for result in results
        ]
    
    def delete_by_filter(self, filters: Dict[str, Any]) -> int:
        """Delete by filter using Qdrant."""
        return self.store.delete_by_filter(filters)
    
    def health_check(self) -> bool:
        """Check Qdrant health."""
        return self.store.health_check()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Qdrant statistics."""
        try:
            return self.store.get_collection_info()
        except Exception as e:
            logger.error(f"Failed to get Qdrant stats: {e}")
            return {'error': str(e)}


class UnifiedVectorService:
    """
    Unified vector service that switches backends based on environment variables.
    
    Environment Variables:
        VECTOR_BACKEND: 'qdrant' or 'pgvector' (default: 'pgvector')
        QDRANT_HOST: Qdrant host (default: 'localhost')
        QDRANT_PORT: Qdrant port (default: 6333)
        QDRANT_COLLECTION: Collection name (default: 'neuronews_vectors')
    """
    
    def __init__(self, backend_type: Optional[str] = None, **kwargs):
        """
        Initialize the unified vector service.
        
        Args:
            backend_type: Override backend type ('qdrant' or 'pgvector')
            **kwargs: Backend-specific configuration
        """
        self.backend_type = backend_type or os.getenv('VECTOR_BACKEND', 'pgvector').lower()
        
        if self.backend_type == 'qdrant':
            self.backend = QdrantBackend(**kwargs)
        elif self.backend_type == 'pgvector':
            connection_params = kwargs.get('connection_params')
            self.backend = PgVectorBackend(connection_params)
        else:
            raise ValueError(f"Unsupported vector backend: {self.backend_type}")
        
        logger.info(f"Initialized unified vector service with {self.backend_type} backend")
    
    def create_collection(self, **kwargs) -> bool:
        """Create collection/database."""
        return self.backend.create_collection(**kwargs)
    
    def upsert(self, points: List[Dict[str, Any]], **kwargs) -> int:
        """Upsert vectors."""
        return self.backend.upsert(points, **kwargs)
    
    def search(
        self, 
        query_embedding: Union[np.ndarray, List[float]], 
        k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        return self.backend.search(query_embedding, k, filters=filters, **kwargs)
    
    def delete_by_filter(self, filters: Dict[str, Any]) -> int:
        """Delete vectors by filter."""
        return self.backend.delete_by_filter(filters)
    
    def health_check(self) -> bool:
        """Check backend health."""
        return self.backend.health_check()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get backend statistics."""
        stats = self.backend.get_stats()
        stats['backend_type'] = self.backend_type
        return stats
    
    def get_backend_type(self) -> str:
        """Get the current backend type."""
        return self.backend_type


def get_vector_service(backend_type: Optional[str] = None, **kwargs) -> UnifiedVectorService:
    """
    Factory function to get a unified vector service.
    
    Args:
        backend_type: Override backend type ('qdrant' or 'pgvector')
        **kwargs: Backend-specific configuration
        
    Returns:
        UnifiedVectorService instance
    """
    return UnifiedVectorService(backend_type, **kwargs)


# Convenience functions
def vector_search(
    query_embedding: Union[np.ndarray, List[float]],
    k: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    backend_type: Optional[str] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Perform vector search using the configured backend.
    
    Args:
        query_embedding: Query embedding vector
        k: Number of results to return
        filters: Optional search filters
        backend_type: Override backend type
        **kwargs: Backend-specific parameters
        
    Returns:
        List of search results
    """
    service = get_vector_service(backend_type, **kwargs)
    return service.search(query_embedding, k, filters)
