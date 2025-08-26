"""
Qdrant Vector Store Backend
Issue #239: Qdrant backend parity

This module provides a Qdrant-based vector store that matches the pgvector API,
allowing seamless switching between vector backends via environment variables.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass, asdict

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
    from qdrant_client.http.models import (
        Distance, 
        VectorParams, 
        CollectionInfo,
        PointStruct,
        Filter,
        FieldCondition,
        Range,
        MatchValue,
        SearchRequest
    )
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

import numpy as np

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class QdrantSearchResult:
    """Result from Qdrant vector search, compatible with VectorSearchResult."""
    id: str
    doc_id: str
    chunk_id: str
    title: str
    content: str
    source: str
    url: str
    published_at: Optional[datetime]
    similarity_score: float
    word_count: int
    char_count: int

    @classmethod
    def from_qdrant_point(cls, point, score: float):
        """Convert Qdrant search result to our standard format."""
        payload = point.payload or {}
        
        # Handle datetime conversion
        published_at = None
        if payload.get('published_at'):
            if isinstance(payload['published_at'], str):
                try:
                    published_at = datetime.fromisoformat(payload['published_at'].replace('Z', '+00:00'))
                except ValueError:
                    published_at = None
            elif isinstance(payload['published_at'], datetime):
                published_at = payload['published_at']
        
        return cls(
            id=str(point.id),
            doc_id=payload.get('doc_id', ''),
            chunk_id=payload.get('chunk_id', ''),
            title=payload.get('title', ''),
            content=payload.get('content', ''),
            source=payload.get('source', ''),
            url=payload.get('url', ''),
            published_at=published_at,
            similarity_score=float(score),
            word_count=payload.get('word_count', 0),
            char_count=payload.get('char_count', 0),
        )


@dataclass 
class QdrantSearchFilters:
    """Filters for Qdrant search queries, compatible with VectorSearchFilters."""
    source: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    min_similarity: float = 0.0

    def to_qdrant_filter(self) -> Optional[Filter]:
        """Convert to Qdrant filter format."""
        conditions = []
        
        if self.source:
            conditions.append(
                FieldCondition(
                    key="source",
                    match=MatchValue(value=self.source)
                )
            )
        
        if self.date_from:
            conditions.append(
                FieldCondition(
                    key="published_at_timestamp",
                    range=Range(gte=self.date_from.timestamp())
                )
            )
        
        if self.date_to:
            conditions.append(
                FieldCondition(
                    key="published_at_timestamp", 
                    range=Range(lte=self.date_to.timestamp())
                )
            )
        
        if conditions:
            return Filter(must=conditions)
        return None


class QdrantVectorStore:
    """
    Qdrant-based vector store with pgvector API compatibility.
    
    Features:
    - Cosine similarity search with embeddings
    - Configurable similarity thresholds
    - Source and date filtering
    - Collection management
    - Batch operations
    """
    
    def __init__(
        self, 
        host: Optional[str] = None,
        port: Optional[int] = None,
        collection_name: Optional[str] = None,
        vector_size: int = 384
    ):
        """Initialize the Qdrant vector store."""
        if not QDRANT_AVAILABLE:
            raise ImportError("qdrant-client is required for Qdrant backend. Install with: pip install qdrant-client")
        
        self.host = host or os.getenv('QDRANT_HOST', 'localhost')
        self.port = port or int(os.getenv('QDRANT_PORT', 6333))
        self.collection_name = collection_name or os.getenv('QDRANT_COLLECTION', 'neuronews_vectors')
        self.vector_size = vector_size
        
        # Initialize client
        self.client = QdrantClient(host=self.host, port=self.port)
        
        logger.info(f"Initialized Qdrant client: {self.host}:{self.port}")
    
    def create_collection(self, force_recreate: bool = False) -> bool:
        """
        Create or recreate the vector collection.
        
        Args:
            force_recreate: Whether to recreate if collection exists
            
        Returns:
            True if collection was created/recreated
        """
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_exists = any(c.name == self.collection_name for c in collections)
            
            if collection_exists and not force_recreate:
                logger.info(f"Collection '{self.collection_name}' already exists")
                return False
            
            if collection_exists and force_recreate:
                logger.info(f"Deleting existing collection '{self.collection_name}'")
                self.client.delete_collection(self.collection_name)
            
            # Create collection with cosine distance (matches pgvector behavior)
            logger.info(f"Creating collection '{self.collection_name}' with vector size {self.vector_size}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE
                )
            )
            
            logger.info(f"Collection '{self.collection_name}' created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise
    
    def upsert(
        self, 
        points: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        Upsert points into the collection.
        
        Args:
            points: List of point data with 'id', 'vector', and 'payload'
            batch_size: Number of points to upsert in each batch
            
        Returns:
            Number of points upserted
        """
        try:
            if not points:
                return 0
            
            # Ensure collection exists
            self.create_collection(force_recreate=False)
            
            # Convert to Qdrant PointStruct objects
            qdrant_points = []
            for point_data in points:
                # Generate UUID if no ID provided
                point_id = point_data.get('id', str(uuid.uuid4()))
                
                # Ensure vector is list format
                vector = point_data['vector']
                if isinstance(vector, np.ndarray):
                    vector = vector.tolist()
                
                # Prepare payload with timestamp for date filtering
                payload = point_data.get('payload', {})
                if 'published_at' in payload and payload['published_at']:
                    if isinstance(payload['published_at'], datetime):
                        payload['published_at_timestamp'] = payload['published_at'].timestamp()
                        payload['published_at'] = payload['published_at'].isoformat()
                
                qdrant_point = PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload
                )
                qdrant_points.append(qdrant_point)
            
            # Batch upsert
            total_upserted = 0
            for i in range(0, len(qdrant_points), batch_size):
                batch = qdrant_points[i:i + batch_size]
                
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
                
                total_upserted += len(batch)
                logger.debug(f"Upserted batch {i//batch_size + 1}, points: {len(batch)}")
            
            logger.info(f"Successfully upserted {total_upserted} points to collection '{self.collection_name}'")
            return total_upserted
            
        except Exception as e:
            logger.error(f"Failed to upsert points: {e}")
            raise
    
    def search(
        self,
        query_embedding: Union[np.ndarray, List[float]],
        k: int = 10,
        filters: Optional[QdrantSearchFilters] = None,
        score_threshold: Optional[float] = None
    ) -> List[QdrantSearchResult]:
        """
        Perform vector similarity search.
        
        Args:
            query_embedding: Query embedding vector
            k: Number of results to return (default: 10)
            filters: Optional search filters
            score_threshold: Minimum similarity score threshold
            
        Returns:
            List of ranked search results by similarity
        """
        try:
            # Convert numpy array to list if needed
            if isinstance(query_embedding, np.ndarray):
                query_embedding = query_embedding.tolist()
            
            filters = filters or QdrantSearchFilters()
            
            # Build Qdrant filter
            qdrant_filter = filters.to_qdrant_filter()
            
            # Use minimum similarity from filters if no score_threshold provided
            if score_threshold is None:
                score_threshold = filters.min_similarity
            
            # Perform search
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=k,
                query_filter=qdrant_filter,
                score_threshold=score_threshold if score_threshold > 0 else None
            )
            
            # Convert to our standard format
            results = []
            for result in search_results:
                search_result = QdrantSearchResult.from_qdrant_point(result, result.score)
                results.append(search_result)
            
            logger.info(f"Qdrant search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            raise
    
    def delete_by_filter(self, filters: Dict[str, Any]) -> int:
        """
        Delete points by filter criteria.
        
        Args:
            filters: Dictionary of filter conditions
            
        Returns:
            Number of points deleted
        """
        try:
            # Build Qdrant filter from simple dict
            conditions = []
            
            for key, value in filters.items():
                if key == 'source' and value:
                    conditions.append(
                        FieldCondition(
                            key="source",
                            match=MatchValue(value=value)
                        )
                    )
                elif key == 'doc_id' and value:
                    conditions.append(
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=value)
                        )
                    )
            
            if not conditions:
                logger.warning("No valid filter conditions provided for deletion")
                return 0
            
            qdrant_filter = Filter(must=conditions)
            
            # Perform deletion
            delete_result = self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=qdrant_filter)
            )
            
            logger.info(f"Deleted points with filter: {filters}")
            return 1  # Qdrant doesn't return exact count, so return 1 if successful
            
        except Exception as e:
            logger.error(f"Failed to delete by filter: {e}")
            raise
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection."""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            
            return {
                'name': collection_info.config.name,
                'vector_size': collection_info.config.params.vectors.size,
                'distance': collection_info.config.params.vectors.distance.value,
                'points_count': collection_info.points_count,
                'indexed_vectors_count': collection_info.indexed_vectors_count,
                'status': collection_info.status.value,
                'optimizer_status': collection_info.optimizer_status.ok,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            raise
    
    def health_check(self) -> bool:
        """Check if Qdrant service is healthy."""
        try:
            # Simple health check by listing collections
            collections = self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False
    
    def close(self):
        """Close the Qdrant client connection."""
        if hasattr(self.client, 'close') and callable(self.client.close):
            self.client.close()
        logger.info("Qdrant client connection closed")


def get_qdrant_vector_store(
    host: Optional[str] = None,
    port: Optional[int] = None,
    collection_name: Optional[str] = None,
    vector_size: int = 384
) -> QdrantVectorStore:
    """Factory function to get a Qdrant vector store instance."""
    return QdrantVectorStore(host, port, collection_name, vector_size)


# Convenience functions for direct usage
def qdrant_search(
    query_embedding: Union[np.ndarray, List[float]],
    k: int = 10,
    filters: Optional[QdrantSearchFilters] = None,
    collection_name: Optional[str] = None
) -> List[QdrantSearchResult]:
    """
    Perform vector search with Qdrant.
    
    Args:
        query_embedding: Query embedding vector
        k: Number of results to return
        filters: Optional search filters
        collection_name: Optional collection name override
        
    Returns:
        List of search results
    """
    store = QdrantVectorStore(collection_name=collection_name)
    return store.search(query_embedding, k, filters)
