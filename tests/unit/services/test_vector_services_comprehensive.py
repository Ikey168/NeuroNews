#!/usr/bin/env python3
"""
Comprehensive Tests for Vector & Embedding Services
Issue #487: Services & Infrastructure Classes Testing

This module provides comprehensive testing coverage for:
- UnifiedVectorService
- VectorBackend implementations
- EmbeddingProvider
- EmbeddingBackend implementations
"""

import os
import sys
import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))


class TestUnifiedVectorService:
    """Comprehensive tests for UnifiedVectorService"""
    
    def test_initialization_pgvector_backend(self):
        """Test UnifiedVectorService initialization with pgvector backend"""
        with patch('services.vector_service.PgVectorBackend') as mock_backend:
            service = UnifiedVectorService(backend_type='pgvector')
            assert service.backend_type == 'pgvector'
            assert service.backend is not None
            mock_backend.assert_called_once()
    
    def test_initialization_qdrant_backend(self):
        """Test UnifiedVectorService initialization with Qdrant backend"""
        with patch('services.vector_service.QdrantBackend') as mock_backend:
            service = UnifiedVectorService(backend_type='qdrant')
            assert service.backend_type == 'qdrant'
            assert service.backend is not None
            mock_backend.assert_called_once()
    
    def test_initialization_unsupported_backend(self):
        """Test UnifiedVectorService with unsupported backend raises error"""
        with pytest.raises(ValueError, match="Unsupported vector backend"):
            UnifiedVectorService(backend_type='unsupported')
    
    def test_environment_variable_backend_selection(self):
        """Test backend selection from environment variables"""
        with patch.dict(os.environ, {'VECTOR_BACKEND': 'qdrant'}):
            with patch('services.vector_service.QdrantBackend'):
                service = UnifiedVectorService()
                assert service.backend_type == 'qdrant'
    
    def test_create_collection(self):
        """Test collection creation delegation"""
        mock_backend = Mock()
        mock_backend.create_collection.return_value = True
        
        with patch('services.vector_service.PgVectorBackend', return_value=mock_backend):
            service = UnifiedVectorService(backend_type='pgvector')
            result = service.create_collection(name='test_collection')
            
            assert result is True
            mock_backend.create_collection.assert_called_once_with(name='test_collection')
    
    def test_upsert_points(self):
        """Test vector upsert delegation"""
        mock_backend = Mock()
        mock_backend.upsert.return_value = 10
        
        test_points = [
            {'id': '1', 'vector': [0.1, 0.2, 0.3], 'payload': {'text': 'test'}}
        ]
        
        with patch('services.vector_service.PgVectorBackend', return_value=mock_backend):
            service = UnifiedVectorService(backend_type='pgvector')
            result = service.upsert(test_points)
            
            assert result == 10
            mock_backend.upsert.assert_called_once_with(test_points)
    
    def test_search_functionality(self):
        """Test vector search functionality"""
        mock_backend = Mock()
        mock_results = [
            {
                'id': '1',
                'similarity_score': 0.95,
                'content': 'test content',
                'metadata': {'source': 'test'}
            }
        ]
        mock_backend.search.return_value = mock_results
        
        query_vector = [0.1, 0.2, 0.3, 0.4]
        filters = {'source': 'test'}
        
        with patch('services.vector_service.PgVectorBackend', return_value=mock_backend):
            service = UnifiedVectorService(backend_type='pgvector')
            results = service.search(query_vector, k=5, filters=filters)
            
            assert results == mock_results
            mock_backend.search.assert_called_once_with(
                query_vector, 5, filters=filters
            )
    
    def test_delete_by_filter(self):
        """Test deletion by filter criteria"""
        mock_backend = Mock()
        mock_backend.delete_by_filter.return_value = 5
        
        filters = {'source': 'test', 'date_from': '2023-01-01'}
        
        with patch('services.vector_service.PgVectorBackend', return_value=mock_backend):
            service = UnifiedVectorService(backend_type='pgvector')
            result = service.delete_by_filter(filters)
            
            assert result == 5
            mock_backend.delete_by_filter.assert_called_once_with(filters)
    
    def test_health_check(self):
        """Test backend health check"""
        mock_backend = Mock()
        mock_backend.health_check.return_value = True
        
        with patch('services.vector_service.PgVectorBackend', return_value=mock_backend):
            service = UnifiedVectorService(backend_type='pgvector')
            health = service.health_check()
            
            assert health is True
            mock_backend.health_check.assert_called_once()
    
    def test_get_stats(self):
        """Test statistics retrieval"""
        mock_backend = Mock()
        backend_stats = {'total_vectors': 1000, 'collection_size': '10MB'}
        mock_backend.get_stats.return_value = backend_stats
        
        with patch('services.vector_service.PgVectorBackend', return_value=mock_backend):
            service = UnifiedVectorService(backend_type='pgvector')
            stats = service.get_stats()
            
            expected_stats = backend_stats.copy()
            expected_stats['backend_type'] = 'pgvector'
            
            assert stats == expected_stats
            mock_backend.get_stats.assert_called_once()
    
    def test_get_backend_type(self):
        """Test backend type retrieval"""
        with patch('services.vector_service.QdrantBackend'):
            service = UnifiedVectorService(backend_type='qdrant')
            assert service.get_backend_type() == 'qdrant'


class TestPgVectorBackend:
    """Tests for PostgreSQL pgvector backend"""
    
    def test_initialization_success(self):
        """Test successful PgVectorBackend initialization"""
        with patch('services.rag.vector.VectorSearchService') as mock_service:
            backend = PgVectorBackend()
            assert backend.service is not None
            mock_service.assert_called_once()
    
    def test_initialization_import_error(self):
        """Test PgVectorBackend initialization with import error"""
        with patch('services.rag.vector.VectorSearchService', side_effect=ImportError('Module not found')):
            with pytest.raises(ImportError, match="pgvector backend requires"):
                PgVectorBackend()
    
    def test_create_collection(self):
        """Test collection creation (always returns True for pgvector)"""
        with patch('services.vector_service.VectorSearchService'):
            backend = PgVectorBackend()
            result = backend.create_collection()
            assert result is True
    
    def test_upsert_not_implemented_warning(self):
        """Test upsert method returns count with warning"""
        with patch('services.vector_service.VectorSearchService'):
            backend = PgVectorBackend()
            points = [{'id': '1'}, {'id': '2'}]
            result = backend.upsert(points)
            assert result == 2
    
    def test_search_with_filters(self):
        """Test search with filter conversion"""
        mock_service_instance = Mock()
        mock_results = [Mock(id='1', similarity_score=0.9, content='test')]
        mock_service_instance.search.return_value = mock_results
        
        with patch('services.vector_service.VectorSearchService') as mock_service:
            with patch('services.vector_service.VectorSearchFilters') as mock_filters:
                backend = PgVectorBackend()
                backend.service = mock_service_instance
                
                query_vector = [0.1, 0.2, 0.3]
                filters = {'source': 'test', 'min_similarity': 0.8}
                
                results = backend.search(query_vector, k=10, filters=filters)
                
                assert len(results) == 1
                mock_service_instance.search.assert_called_once()
    
    def test_health_check_success(self):
        """Test successful health check"""
        mock_service_instance = Mock()
        
        with patch('services.vector_service.VectorSearchService'):
            backend = PgVectorBackend()
            backend.service = mock_service_instance
            
            result = backend.health_check()
            assert result is True
    
    def test_health_check_failure(self):
        """Test health check failure"""
        mock_service_instance = Mock()
        mock_service_instance.__enter__.side_effect = Exception('Connection failed')
        
        with patch('services.vector_service.VectorSearchService'):
            backend = PgVectorBackend()
            backend.service = mock_service_instance
            
            result = backend.health_check()
            assert result is False


class TestQdrantBackend:
    """Tests for Qdrant vector backend"""
    
    def test_initialization_success(self):
        """Test successful QdrantBackend initialization"""
        with patch('services.vector_service.QdrantVectorStore') as mock_store:
            backend = QdrantBackend()
            assert backend.store is not None
            mock_store.assert_called_once()
    
    def test_initialization_import_error(self):
        """Test QdrantBackend initialization with import error"""
        with patch('services.vector_service.QdrantVectorStore', side_effect=ImportError('Qdrant not found')):
            with pytest.raises(ImportError, match="Qdrant backend requires"):
                QdrantBackend()
    
    def test_create_collection_delegation(self):
        """Test collection creation delegation to Qdrant store"""
        mock_store = Mock()
        mock_store.create_collection.return_value = True
        
        with patch('services.vector_service.QdrantVectorStore', return_value=mock_store):
            backend = QdrantBackend()
            result = backend.create_collection(name='test', size=384)
            
            assert result is True
            mock_store.create_collection.assert_called_once_with(name='test', size=384)
    
    def test_upsert_delegation(self):
        """Test upsert delegation to Qdrant store"""
        mock_store = Mock()
        mock_store.upsert.return_value = 10
        
        points = [{'id': '1', 'vector': [0.1, 0.2]}]
        
        with patch('services.vector_service.QdrantVectorStore', return_value=mock_store):
            backend = QdrantBackend()
            result = backend.upsert(points)
            
            assert result == 10
            mock_store.upsert.assert_called_once_with(points)
    
    def test_search_with_filter_conversion(self):
        """Test search with filter conversion"""
        mock_store = Mock()
        mock_results = [Mock(id='1', similarity_score=0.95)]
        mock_store.search.return_value = mock_results
        
        with patch('services.vector_service.QdrantVectorStore', return_value=mock_store):
            with patch('services.vector_service.QdrantSearchFilters'):
                backend = QdrantBackend()
                
                query_vector = [0.1, 0.2, 0.3]
                filters = {'source': 'test'}
                
                results = backend.search(query_vector, k=5, filters=filters)
                
                assert len(results) == 1
                mock_store.search.assert_called_once()
    
    def test_delete_by_filter_delegation(self):
        """Test delete by filter delegation"""
        mock_store = Mock()
        mock_store.delete_by_filter.return_value = 3
        
        filters = {'source': 'old_data'}
        
        with patch('services.vector_service.QdrantVectorStore', return_value=mock_store):
            backend = QdrantBackend()
            result = backend.delete_by_filter(filters)
            
            assert result == 3
            mock_store.delete_by_filter.assert_called_once_with(filters)
    
    def test_health_check_delegation(self):
        """Test health check delegation"""
        mock_store = Mock()
        mock_store.health_check.return_value = True
        
        with patch('services.vector_service.QdrantVectorStore', return_value=mock_store):
            backend = QdrantBackend()
            result = backend.health_check()
            
            assert result is True
            mock_store.health_check.assert_called_once()


class TestEmbeddingProvider:
    """Comprehensive tests for EmbeddingProvider"""
    
    def test_initialization_local_provider(self):
        """Test EmbeddingProvider initialization with local backend"""
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend') as mock_backend:
            provider = EmbeddingProvider(provider='local')
            assert provider.provider_name == 'local'
            assert provider.backend is not None
            mock_backend.assert_called_once()
    
    def test_initialization_openai_provider(self):
        """Test EmbeddingProvider initialization with OpenAI backend"""
        with patch('services.embeddings.provider.OpenAIBackend') as mock_backend:
            provider = EmbeddingProvider(provider='openai')
            assert provider.provider_name == 'openai'
            assert provider.backend is not None
            mock_backend.assert_called_once()
    
    def test_initialization_unknown_provider(self):
        """Test EmbeddingProvider with unknown provider raises error"""
        with pytest.raises(ValueError, match="Unknown provider"):
            EmbeddingProvider(provider='unknown')
    
    def test_deterministic_seed_setting(self):
        """Test deterministic seed is set correctly"""
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend'):
            with patch('numpy.random.seed') as mock_seed:
                EmbeddingProvider(provider='local', deterministic_seed=42)
                mock_seed.assert_called_once_with(42)
    
    def test_embed_texts_empty_input(self):
        """Test embed_texts with empty input"""
        mock_backend = Mock()
        mock_backend.dim.return_value = 384
        
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend', return_value=mock_backend):
            provider = EmbeddingProvider(provider='local')
            result = provider.embed_texts([])
            
            assert result.shape == (0, 384)
    
    def test_embed_texts_single_batch(self):
        """Test embed_texts with single batch"""
        mock_backend = Mock()
        mock_embeddings = np.array([[0.1, 0.2], [0.3, 0.4]])
        mock_backend.embed_texts.return_value = mock_embeddings
        mock_backend.dim.return_value = 2
        
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend', return_value=mock_backend):
            provider = EmbeddingProvider(provider='local', batch_size=32)
            texts = ['text1', 'text2']
            result = provider.embed_texts(texts)
            
            np.testing.assert_array_equal(result, mock_embeddings)
            mock_backend.embed_texts.assert_called_once_with(texts)
    
    def test_embed_texts_multiple_batches(self):
        """Test embed_texts with multiple batches"""
        mock_backend = Mock()
        batch1 = np.array([[0.1, 0.2]])
        batch2 = np.array([[0.3, 0.4]])
        mock_backend.embed_texts.side_effect = [batch1, batch2]
        mock_backend.dim.return_value = 2
        
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend', return_value=mock_backend):
            provider = EmbeddingProvider(provider='local', batch_size=1)
            texts = ['text1', 'text2']
            result = provider.embed_texts(texts)
            
            expected = np.vstack([batch1, batch2])
            np.testing.assert_array_equal(result, expected)
            assert mock_backend.embed_texts.call_count == 2
    
    def test_embed_texts_retry_mechanism(self):
        """Test embed_texts retry mechanism on failure"""
        mock_backend = Mock()
        mock_backend.embed_texts.side_effect = [
            Exception('Temporary failure'),
            np.array([[0.1, 0.2]])
        ]
        mock_backend.dim.return_value = 2
        
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend', return_value=mock_backend):
            provider = EmbeddingProvider(provider='local', max_retries=3)
            texts = ['text1']
            result = provider.embed_texts(texts)
            
            expected = np.array([[0.1, 0.2]])
            np.testing.assert_array_equal(result, expected)
            assert mock_backend.embed_texts.call_count == 2
    
    def test_embed_texts_max_retries_exceeded(self):
        """Test embed_texts when max retries exceeded"""
        mock_backend = Mock()
        mock_backend.embed_texts.side_effect = Exception('Persistent failure')
        
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend', return_value=mock_backend):
            provider = EmbeddingProvider(provider='local', max_retries=2)
            texts = ['text1']
            
            with pytest.raises(Exception, match='Persistent failure'):
                provider.embed_texts(texts)
            
            assert mock_backend.embed_texts.call_count == 2
    
    def test_dim_delegation(self):
        """Test dimension delegation to backend"""
        mock_backend = Mock()
        mock_backend.dim.return_value = 768
        
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend', return_value=mock_backend):
            provider = EmbeddingProvider(provider='local')
            dim = provider.dim()
            
            assert dim == 768
            mock_backend.dim.assert_called_once()
    
    def test_name_composition(self):
        """Test provider name composition"""
        mock_backend = Mock()
        mock_backend.name.return_value = 'all-MiniLM-L6-v2'
        
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend', return_value=mock_backend):
            provider = EmbeddingProvider(provider='local')
            name = provider.name()
            
            assert name == 'local:all-MiniLM-L6-v2'
            mock_backend.name.assert_called_once()


class TestFactoryFunctions:
    """Tests for factory and convenience functions"""
    
    def test_get_vector_service_factory(self):
        """Test get_vector_service factory function"""
        with patch('services.vector_service.UnifiedVectorService') as mock_service:
            result = get_vector_service(backend_type='qdrant', param1='value1')
            
            mock_service.assert_called_once_with('qdrant', param1='value1')
            assert result is not None
    
    def test_vector_search_convenience_function(self):
        """Test vector_search convenience function"""
        mock_service = Mock()
        mock_results = [{'id': '1', 'score': 0.95}]
        mock_service.search.return_value = mock_results
        
        with patch('services.vector_service.get_vector_service', return_value=mock_service):
            query_vector = [0.1, 0.2, 0.3]
            filters = {'source': 'test'}
            
            results = vector_search(query_vector, k=5, filters=filters, backend_type='qdrant')
            
            assert results == mock_results
            mock_service.search.assert_called_once_with(query_vector, 5, filters)
    
    def test_get_embedding_provider_factory(self):
        """Test get_embedding_provider factory function"""
        with patch('services.embeddings.provider.EmbeddingProvider') as mock_provider:
            result = get_embedding_provider(provider='openai', model_name='text-embedding-ada-002')
            
            mock_provider.assert_called_once_with(
                provider='openai',
                model_name='text-embedding-ada-002'
            )
            assert result is not None
    
    def test_get_embedding_provider_environment_variables(self):
        """Test get_embedding_provider with environment variables"""
        env_vars = {
            'EMBEDDING_PROVIDER': 'openai',
            'EMBEDDING_MODEL_NAME': 'text-embedding-3-small'
        }
        
        with patch.dict(os.environ, env_vars):
            with patch('services.embeddings.provider.EmbeddingProvider') as mock_provider:
                result = get_embedding_provider()
                
                mock_provider.assert_called_once_with(
                    provider='openai',
                    model_name='text-embedding-3-small'
                )


class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases and error handling scenarios"""
    
    def test_vector_service_with_none_backend_type(self):
        """Test vector service with None backend type uses environment default"""
        with patch.dict(os.environ, {'VECTOR_BACKEND': 'pgvector'}):
            with patch('services.vector_service.PgVectorBackend'):
                service = UnifiedVectorService(backend_type=None)
                assert service.backend_type == 'pgvector'
    
    def test_embedding_provider_batch_size_edge_cases(self):
        """Test embedding provider with edge case batch sizes"""
        mock_backend = Mock()
        mock_backend.embed_texts.return_value = np.array([[0.1, 0.2]])
        mock_backend.dim.return_value = 2
        
        with patch('services.embeddings.provider.LocalSentenceTransformersBackend', return_value=mock_backend):
            # Test with batch size larger than text count
            provider = EmbeddingProvider(provider='local', batch_size=100)
            result = provider.embed_texts(['single_text'])
            
            assert result.shape == (1, 2)
            mock_backend.embed_texts.assert_called_once_with(['single_text'])
    
    def test_vector_search_with_numpy_array(self):
        """Test vector search with numpy array input"""
        mock_service = Mock()
        mock_results = [{'id': '1'}]
        mock_service.search.return_value = mock_results
        
        with patch('services.vector_service.get_vector_service', return_value=mock_service):
            query_vector = np.array([0.1, 0.2, 0.3])
            results = vector_search(query_vector, k=10)
            
            assert results == mock_results
            # Verify numpy array was passed correctly
            call_args = mock_service.search.call_args[0]
            np.testing.assert_array_equal(call_args[0], query_vector)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])