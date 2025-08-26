"""
Parity Tests for Vector Backends
Issue #239: Qdrant backend parity

These tests verify that pgvector and Qdrant backends produce
equivalent results for the same queries.
"""

import json
import os
import time
import unittest
from datetime import datetime, timedelta
from typing import List, Dict, Any

import numpy as np
import pytest

# Test configuration
TEST_VECTOR_SIZE = 384
TEST_COLLECTION_NAME = "test_neuronews_vectors"


class VectorBackendParityTests(unittest.TestCase):
    """Test parity between pgvector and Qdrant backends."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.test_documents = [
            {
                'id': 'doc1',
                'vector': np.random.rand(TEST_VECTOR_SIZE).tolist(),
                'payload': {
                    'doc_id': 'doc1',
                    'chunk_id': 'chunk1',
                    'title': 'AI Revolution in Healthcare',
                    'content': 'Artificial intelligence is transforming healthcare delivery through advanced machine learning algorithms.',
                    'source': 'TechNews',
                    'url': 'https://example.com/ai-healthcare',
                    'published_at': datetime.now() - timedelta(days=1),
                    'word_count': 15,
                    'char_count': 95
                }
            },
            {
                'id': 'doc2', 
                'vector': np.random.rand(TEST_VECTOR_SIZE).tolist(),
                'payload': {
                    'doc_id': 'doc2',
                    'chunk_id': 'chunk2',
                    'title': 'Climate Change Impact on Agriculture',
                    'content': 'Global warming is affecting crop yields and agricultural practices worldwide.',
                    'source': 'ScienceDaily',
                    'url': 'https://example.com/climate-agriculture',
                    'published_at': datetime.now() - timedelta(days=2),
                    'word_count': 12,
                    'char_count': 78
                }
            },
            {
                'id': 'doc3',
                'vector': np.random.rand(TEST_VECTOR_SIZE).tolist(), 
                'payload': {
                    'doc_id': 'doc3',
                    'chunk_id': 'chunk3',
                    'title': 'Space Exploration Milestones',
                    'content': 'Recent achievements in space technology are opening new frontiers for human exploration.',
                    'source': 'SpaceNews',
                    'url': 'https://example.com/space-exploration',
                    'published_at': datetime.now() - timedelta(days=3),
                    'word_count': 14,
                    'char_count': 88
                }
            }
        ]
        
        cls.query_vector = np.random.rand(TEST_VECTOR_SIZE).tolist()
    
    def setUp(self):
        """Set up individual test."""
        # Skip tests if backends not available
        self.pgvector_available = self._check_pgvector_available()
        self.qdrant_available = self._check_qdrant_available()
        
        if not (self.pgvector_available or self.qdrant_available):
            self.skipTest("Neither pgvector nor Qdrant backend available")
    
    def _check_pgvector_available(self) -> bool:
        """Check if pgvector backend is available."""
        try:
            from services.vector_service import PgVectorBackend
            backend = PgVectorBackend()
            return backend.health_check()
        except Exception:
            return False
    
    def _check_qdrant_available(self) -> bool:
        """Check if Qdrant backend is available."""
        try:
            from services.vector_service import QdrantBackend
            backend = QdrantBackend(collection_name=TEST_COLLECTION_NAME)
            return backend.health_check()
        except Exception:
            return False
    
    def _setup_backend(self, backend_type: str):
        """Set up a specific backend for testing."""
        if backend_type == 'qdrant' and self.qdrant_available:
            from services.vector_service import QdrantBackend
            backend = QdrantBackend(collection_name=TEST_COLLECTION_NAME)
            backend.create_collection(force_recreate=True)
            backend.upsert(self.test_documents)
            return backend
        elif backend_type == 'pgvector' and self.pgvector_available:
            from services.vector_service import PgVectorBackend
            backend = PgVectorBackend()
            backend.create_collection()
            backend.upsert(self.test_documents)
            return backend
        else:
            return None
    
    @pytest.mark.skipif(not os.getenv('INTEGRATION_TESTS'), reason="Integration test")
    def test_search_parity_basic(self):
        """Test basic search parity between backends."""
        results = {}
        
        # Test both backends if available
        for backend_type in ['pgvector', 'qdrant']:
            backend = self._setup_backend(backend_type)
            if backend:
                search_results = backend.search(self.query_vector, k=3)
                results[backend_type] = search_results
        
        # Compare results if both backends available
        if len(results) == 2:
            pg_results = results['pgvector']
            qdrant_results = results['qdrant']
            
            # Should return same number of results
            self.assertEqual(len(pg_results), len(qdrant_results))
            
            # Results should contain same document IDs (order may differ)
            pg_doc_ids = {r['doc_id'] for r in pg_results}
            qdrant_doc_ids = {r['doc_id'] for r in qdrant_results}
            self.assertEqual(pg_doc_ids, qdrant_doc_ids)
            
            print(f"✅ Basic search parity verified: {len(pg_results)} results")
    
    @pytest.mark.skipif(not os.getenv('INTEGRATION_TESTS'), reason="Integration test")
    def test_search_parity_with_filters(self):
        """Test search parity with filters."""
        filters = {
            'source': 'TechNews',
            'min_similarity': 0.0
        }
        
        results = {}
        
        for backend_type in ['pgvector', 'qdrant']:
            backend = self._setup_backend(backend_type)
            if backend:
                search_results = backend.search(self.query_vector, k=3, filters=filters)
                results[backend_type] = search_results
        
        if len(results) == 2:
            pg_results = results['pgvector']
            qdrant_results = results['qdrant']
            
            # Both should filter to same source
            for result in pg_results:
                self.assertEqual(result['source'], 'TechNews')
            
            for result in qdrant_results:
                self.assertEqual(result['source'], 'TechNews')
            
            print(f"✅ Filtered search parity verified")
    
    @pytest.mark.skipif(not os.getenv('INTEGRATION_TESTS'), reason="Integration test")
    def test_upsert_parity(self):
        """Test upsert operations parity."""
        new_doc = {
            'id': 'doc4',
            'vector': np.random.rand(TEST_VECTOR_SIZE).tolist(),
            'payload': {
                'doc_id': 'doc4',
                'chunk_id': 'chunk4',
                'title': 'New Document',
                'content': 'This is a new test document.',
                'source': 'TestSource',
                'url': 'https://example.com/new-doc',
                'published_at': datetime.now(),
                'word_count': 6,
                'char_count': 25
            }
        }
        
        for backend_type in ['pgvector', 'qdrant']:
            backend = self._setup_backend(backend_type)
            if backend:
                # Upsert new document
                count = backend.upsert([new_doc])
                self.assertGreater(count, 0)
                
                # Verify it can be found
                results = backend.search(new_doc['vector'], k=1)
                self.assertGreater(len(results), 0)
                self.assertEqual(results[0]['doc_id'], 'doc4')
                
                print(f"✅ Upsert parity verified for {backend_type}")
    
    def test_unified_service_switching(self):
        """Test that unified service switches backends correctly."""
        from services.vector_service import UnifiedVectorService
        
        # Test backend selection
        if self.qdrant_available:
            service = UnifiedVectorService(backend_type='qdrant', collection_name=TEST_COLLECTION_NAME)
            self.assertEqual(service.get_backend_type(), 'qdrant')
            self.assertTrue(service.health_check())
        
        if self.pgvector_available:
            service = UnifiedVectorService(backend_type='pgvector')
            self.assertEqual(service.get_backend_type(), 'pgvector')
            self.assertTrue(service.health_check())
        
        print("✅ Unified service backend switching verified")
    
    def test_environment_variable_switching(self):
        """Test switching backends via environment variables."""
        from services.vector_service import get_vector_service
        
        original_backend = os.getenv('VECTOR_BACKEND')
        
        try:
            if self.qdrant_available:
                os.environ['VECTOR_BACKEND'] = 'qdrant'
                service = get_vector_service(collection_name=TEST_COLLECTION_NAME)
                self.assertEqual(service.get_backend_type(), 'qdrant')
            
            if self.pgvector_available:
                os.environ['VECTOR_BACKEND'] = 'pgvector'
                service = get_vector_service()
                self.assertEqual(service.get_backend_type(), 'pgvector')
            
            print("✅ Environment variable switching verified")
            
        finally:
            # Restore original environment
            if original_backend is not None:
                os.environ['VECTOR_BACKEND'] = original_backend
            elif 'VECTOR_BACKEND' in os.environ:
                del os.environ['VECTOR_BACKEND']
    
    def test_performance_comparison(self):
        """Compare performance between backends."""
        if not (self.pgvector_available and self.qdrant_available):
            self.skipTest("Both backends required for performance comparison")
        
        performance_results = {}
        
        # Test search performance for both backends
        for backend_type in ['pgvector', 'qdrant']:
            backend = self._setup_backend(backend_type)
            
            # Measure search time
            start_time = time.time()
            for _ in range(10):  # Run 10 searches
                results = backend.search(self.query_vector, k=5)
            end_time = time.time()
            
            avg_time = (end_time - start_time) / 10
            performance_results[backend_type] = {
                'avg_search_time': avg_time,
                'results_count': len(results)
            }
        
        # Log performance comparison
        print("\n📊 Performance Comparison:")
        for backend, metrics in performance_results.items():
            print(f"  {backend}: {metrics['avg_search_time']:.4f}s avg search time")
        
        # Both should return same number of results
        pg_count = performance_results['pgvector']['results_count']
        qdrant_count = performance_results['qdrant']['results_count']
        self.assertEqual(pg_count, qdrant_count)
        
        print("✅ Performance comparison completed")


def run_parity_tests():
    """Run the parity tests."""
    print("🧪 Running Vector Backend Parity Tests")
    print("=" * 50)
    
    # Set integration test flag
    os.environ['INTEGRATION_TESTS'] = '1'
    
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        # Clean up
        if 'INTEGRATION_TESTS' in os.environ:
            del os.environ['INTEGRATION_TESTS']


if __name__ == "__main__":
    run_parity_tests()
