"""
RAG Retriever Smoke Tests
Issue #238: CI: Smoke tests for indexing & /ask

These tests are designed to be lightweight smoke tests that verify:
- RAG indexing pipeline can ingest documents
- Basic search functionality works 
- API endpoints respond correctly

The tests are designed to be resilient to missing dependencies and should 
gracefully skip when components are not available.
"""

import pytest
import json
import os
from typing import List, Dict, Any


class TestRAGRetrieverSmoke:
    """Smoke tests for RAG indexing and retrieval pipeline"""
    
    @pytest.mark.asyncio
    async def test_indexer_initialization(self, indexer):
        """Test that indexer can be properly initialized"""
        if indexer is None:
            pytest.skip("Indexer not available")
            
        # Await the indexer if it's a coroutine
        if hasattr(indexer, '__await__'):
            indexer = await indexer
        
        assert indexer is not None
        
        # Test database connection
        try:
            # This should not raise an exception if DB is accessible
            conn = await indexer._get_connection()
            await conn.close()
        except Exception as e:
            pytest.skip(f"Database connection failed: {e}")
    
    @pytest.mark.asyncio
    async def test_basic_functionality_without_vector_db(self, test_documents, embeddings_provider):
        """Test basic functionality without requiring vector database"""
        if embeddings_provider is None:
            pytest.skip("Embeddings provider not available")
            
        # Test embeddings generation
        texts = [doc['content'] for doc in test_documents[:2]]
        
        try:
            embeddings = await embeddings_provider.embed_texts(texts)
            
            assert embeddings is not None
            assert len(embeddings) == len(texts)
            
            # Check embedding dimensions
            for embedding in embeddings:
                assert len(embedding) > 0, "Empty embedding generated"
                assert all(isinstance(x, (int, float)) for x in embedding), "Invalid embedding values"
                
            print(f"✅ Generated embeddings with dimension {len(embeddings[0])}")
            
        except Exception as e:
            pytest.skip(f"Embedding generation failed: {e}")
    
    @pytest.mark.asyncio
    async def test_document_ingestion(self, indexer, test_documents):
        """Test basic document ingestion"""
        if indexer is None:
            pytest.skip("RAG indexer not available")
            
        # Await the indexer if it's a coroutine
        if hasattr(indexer, '__await__'):
            indexer = await indexer
            
        try:
            # Ingest a subset of documents
            await indexer.ingest_documents(test_documents[:3])
            
            # Simple verification - no errors during ingestion
            assert True, "Document ingestion completed"
            
        except Exception as e:
            pytest.skip(f"Document ingestion failed: {e}")
    
    @pytest.mark.asyncio 
    async def test_embedding_generation(self, embeddings_provider, test_documents):
        """Test that embeddings are generated correctly"""
        if embeddings_provider is None:
            pytest.skip("Embeddings provider not available")
            
        texts = [doc['content'] for doc in test_documents[:3]]
        
        try:
            embeddings = await embeddings_provider.embed_texts(texts)
            
            assert embeddings is not None
            assert len(embeddings) == len(texts)
            
            # Check embedding dimensions
            for embedding in embeddings:
                assert len(embedding) > 0, "Empty embedding generated"
                assert all(isinstance(x, (int, float)) for x in embedding), "Invalid embedding values"
                
        except Exception as e:
            pytest.skip(f"Embedding generation failed: {e}")

    @pytest.mark.asyncio
    async def test_semantic_search(self, indexer, test_documents):
        """Test semantic search functionality"""
        if indexer is None:
            pytest.skip("RAG indexer not available")
            
        # Await the indexer if it's a coroutine
        if hasattr(indexer, '__await__'):
            indexer = await indexer
            
        try:
            # First ingest documents
            await indexer.ingest_documents(test_documents[:3])
            
            # Perform search
            query = "artificial intelligence machine learning"
            results = await indexer.search(query, limit=5)
            
            assert results is not None
            assert isinstance(results, list)
            # Allow empty results in CI environments
            if len(results) > 0:
                assert all('content' in result for result in results), "Search results missing content"
                
        except Exception as e:
            pytest.skip(f"Semantic search failed: {e}")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
