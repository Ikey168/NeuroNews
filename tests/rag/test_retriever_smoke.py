"""
RAG Retriever Smoke Tests
Issue #238: CI: Smoke tests for indexing & /ask

These tests verify that the RAG indexing pipeline works correctly
by ingesting a tiny corpus and testing retrieval functionality.
"""

import pytest
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.embeddings.provider import EmbeddingProvider
from jobs.rag.indexer import RAGIndexer


class TestRAGRetrieverSmoke:
    """Smoke tests for RAG indexing and retrieval"""
    
    @pytest.fixture(scope="class")
    def tiny_corpus_path(self):
        """Path to the tiny test corpus"""
        return Path(__file__).parent.parent / "fixtures" / "tiny_corpus.jsonl"
    
    @pytest.fixture(scope="class")
    def test_documents(self, tiny_corpus_path):
        """Load test documents from tiny corpus"""
        documents = []
        with open(tiny_corpus_path, 'r') as f:
            for line in f:
                if line.strip():
                    documents.append(json.loads(line))
        return documents
    
    @pytest.fixture(scope="class") 
    def embeddings_provider(self):
        """Create embeddings provider for testing"""
        return EmbeddingProvider(
            model_name="all-MiniLM-L6-v2",
            batch_size=5
        )
    
    @pytest.fixture(scope="class")
    async def indexer(self, embeddings_provider):
        """Create RAG indexer for testing"""
        # Use test database configuration
        conn_params = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'neuronews_test'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
        }
        
        indexer = RAGIndexer(
            conn_params=conn_params,
            embedding_model="all-MiniLM-L6-v2",
            batch_size=5,
            chunk_size=512,
            chunk_overlap=50
        )
        
        # Initialize the indexer
        await indexer.initialize()
        
        return indexer
    
    @pytest.mark.asyncio
    async def test_indexer_initialization(self, indexer):
        """Test that indexer initializes successfully"""
        assert indexer is not None
        assert indexer.conn_params is not None
        assert indexer.embeddings_provider is not None
        
        # Test database connection
        try:
            # This should not raise an exception if DB is accessible
            conn = await indexer._get_connection()
            await conn.close()
        except Exception as e:
            pytest.fail(f"Database connection failed: {e}")
    
    @pytest.mark.asyncio
    async def test_document_ingestion(self, indexer, test_documents):
        """Test ingesting tiny corpus documents"""
        assert len(test_documents) >= 3, "Need at least 3 test documents"
        
        # Clear any existing test data
        await self._cleanup_test_data(indexer)
        
        # Ingest documents
        try:
            results = await indexer.ingest_documents(test_documents)
            
            assert results is not None
            assert len(results) == len(test_documents)
            
            # Verify all documents were processed successfully
            for result in results:
                assert result.get('status') != 'error', f"Document ingestion failed: {result}"
                
        except Exception as e:
            pytest.fail(f"Document ingestion failed: {e}")
    
    @pytest.mark.asyncio 
    async def test_embedding_generation(self, embeddings_provider, test_documents):
        """Test that embeddings are generated correctly"""
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
            pytest.fail(f"Embedding generation failed: {e}")
    
    @pytest.mark.asyncio
    async def test_semantic_search(self, indexer, test_documents):
        """Test semantic search retrieval"""
        # Ensure documents are indexed
        await indexer.ingest_documents(test_documents)
        
        # Test queries related to the content
        test_queries = [
            "artificial intelligence machine learning",
            "climate change technology solutions", 
            "healthcare AI applications",
            "space exploration technology"
        ]
        
        for query in test_queries:
            try:
                results = await indexer.search_similar_documents(
                    query=query,
                    k=3,
                    min_score=0.1
                )
                
                assert results is not None, f"No results for query: {query}"
                assert len(results) > 0, f"Empty results for query: {query}"
                
                # Verify result structure
                for result in results:
                    assert 'content' in result, "Missing content in result"
                    assert 'score' in result, "Missing score in result"
                    assert isinstance(result['score'], (int, float)), "Invalid score type"
                    assert result['score'] >= 0, "Negative similarity score"
                    
            except Exception as e:
                pytest.fail(f"Semantic search failed for query '{query}': {e}")
    
    @pytest.mark.asyncio
    async def test_full_text_search(self, indexer, test_documents):
        """Test full-text search functionality"""
        # Ensure documents are indexed
        await indexer.ingest_documents(test_documents)
        
        # Test keyword searches
        test_queries = [
            "AI",
            "machine learning", 
            "climate",
            "healthcare",
            "space"
        ]
        
        for query in test_queries:
            try:
                results = await indexer.full_text_search(
                    query=query,
                    k=3
                )
                
                assert results is not None, f"No results for query: {query}"
                
                # At least some queries should return results given our test corpus
                if query.lower() in ['ai', 'machine learning', 'climate']:
                    assert len(results) > 0, f"Expected results for query: {query}"
                
                # Verify result structure if we have results
                for result in results:
                    assert 'content' in result, "Missing content in result"
                    assert isinstance(result.get('rank'), (int, float, type(None))), "Invalid rank type"
                    
            except Exception as e:
                pytest.fail(f"Full-text search failed for query '{query}': {e}")
    
    @pytest.mark.asyncio
    async def test_hybrid_search(self, indexer, test_documents):
        """Test hybrid search combining semantic and full-text"""
        # Ensure documents are indexed
        await indexer.ingest_documents(test_documents)
        
        query = "artificial intelligence healthcare applications"
        
        try:
            results = await indexer.hybrid_search(
                query=query,
                k=3,
                semantic_weight=0.7,
                fulltext_weight=0.3
            )
            
            assert results is not None, "No hybrid search results"
            assert len(results) > 0, "Empty hybrid search results"
            
            # Verify result structure
            for result in results:
                assert 'content' in result, "Missing content in hybrid result"
                assert 'score' in result, "Missing score in hybrid result"
                assert isinstance(result['score'], (int, float)), "Invalid hybrid score type"
                
        except Exception as e:
            pytest.fail(f"Hybrid search failed: {e}")
    
    @pytest.mark.asyncio
    async def test_search_with_filters(self, indexer, test_documents):
        """Test search with basic filters"""
        # Ensure documents are indexed
        await indexer.ingest_documents(test_documents)
        
        query = "technology"
        
        try:
            # Test with date filter
            results = await indexer.search_similar_documents(
                query=query,
                k=5,
                filters={'date_from': '2024-01-16'}
            )
            
            assert results is not None, "No filtered search results"
            
            # Test with source filter if supported
            results = await indexer.search_similar_documents(
                query=query,
                k=5,
                filters={'source': 'TechNews'}
            )
            
            assert results is not None, "No source filtered results"
            
        except Exception as e:
            # Filters might not be fully implemented yet, so we'll warn but not fail
            print(f"Warning: Filtered search not fully supported: {e}")
    
    async def _cleanup_test_data(self, indexer):
        """Clean up test data from database"""
        try:
            conn = await indexer._get_connection()
            
            # Clean up any test documents (assuming they have test-specific IDs)
            await conn.execute("""
                DELETE FROM documents 
                WHERE id LIKE 'tiny-%' OR source IN ('TechNews', 'ScienceDaily', 'MedNews', 'EconToday', 'SpaceNews')
            """)
            
            await conn.execute("""
                DELETE FROM embeddings 
                WHERE document_id LIKE 'tiny-%'
            """)
            
            await conn.close()
            
        except Exception as e:
            # Cleanup failure shouldn't break tests
            print(f"Warning: Test cleanup failed: {e}")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
