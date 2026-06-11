"""
Tests for embedding provider and backends.
Issue #228: Embedding provider (local + cloud pluggable)

Tests the unified API, backend consistency, and deterministic behavior.
"""

import os
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from services.embeddings import EmbeddingProvider, get_embedding_provider
from services.embeddings.backends.local_sentence_transformers import LocalSentenceTransformersBackend


class TestEmbeddingProvider:
    """Test cases for the main EmbeddingProvider class."""
    
    def test_local_provider_initialization(self):
        """Test local provider initialization with default settings."""
        provider = EmbeddingProvider(provider="local")
        
        assert provider.provider_name == "local"
        assert provider.batch_size == 32
        assert provider.max_retries == 3
        assert provider.backend is not None
        assert provider.dim() > 0
        assert "local" in provider.name()
    
    def test_local_provider_with_custom_model(self):
        """Test local provider with custom model name."""
        provider = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2"
        )
        
        assert "all-MiniLM-L6-v2" in provider.name()
        assert provider.dim() == 384  # Known dimension for all-MiniLM-L6-v2
    
    def test_embed_texts_shape_consistency(self):
        """Test that embed_texts returns consistent shape [N, dim]."""
        provider = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            deterministic_seed=42
        )
        
        # Test different input sizes
        test_cases = [
            [],  # Empty list
            ["single text"],  # Single text
            ["first text", "second text"],  # Multiple texts
            ["text " + str(i) for i in range(10)]  # Batch
        ]
        
        for texts in test_cases:
            embeddings = provider.embed_texts(texts)
            
            # Check shape
            expected_shape = (len(texts), provider.dim())
            assert embeddings.shape == expected_shape, f"Shape mismatch for {len(texts)} texts"
            
            # Check dtype
            assert embeddings.dtype == np.float32 or embeddings.dtype == np.float64
    
    def test_deterministic_behavior(self):
        """Test that deterministic seed produces consistent results."""
        texts = ["test text", "another test"]
        
        # Generate embeddings with same seed twice
        provider1 = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            deterministic_seed=42
        )
        embeddings1 = provider1.embed_texts(texts)
        
        provider2 = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            deterministic_seed=42
        )
        embeddings2 = provider2.embed_texts(texts)
        
        # Should be identical
        np.testing.assert_array_almost_equal(embeddings1, embeddings2, decimal=5)
    
    def test_batch_processing(self):
        """Test batch processing with different batch sizes."""
        provider = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            batch_size=2,
            deterministic_seed=42
        )
        
        texts = ["text " + str(i) for i in range(5)]
        embeddings = provider.embed_texts(texts)
        
        assert embeddings.shape == (5, provider.dim())
        
        # Test single processing (batch_size=1)
        provider_single = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            batch_size=1,
            deterministic_seed=42
        )
        embeddings_single = provider_single.embed_texts(texts)
        
        # Results should be the same regardless of batch size
        np.testing.assert_array_almost_equal(embeddings, embeddings_single, decimal=4)
    
    def test_api_methods(self):
        """Test the required API methods."""
        provider = EmbeddingProvider(provider="local")
        
        # Test dim() returns integer
        dim = provider.dim()
        assert isinstance(dim, int)
        assert dim > 0
        
        # Test name() returns string
        name = provider.name()
        assert isinstance(name, str)
        assert len(name) > 0
        
        # Test embed_texts() with simple input
        texts = ["hello world"]
        embeddings = provider.embed_texts(texts)
        assert embeddings.shape == (1, dim)
    
    def test_invalid_provider(self):
        """Test that invalid provider raises appropriate error."""
        with pytest.raises(ValueError, match="Unknown provider"):
            EmbeddingProvider(provider="invalid_provider")


class TestLocalSentenceTransformersBackend:
    """Test cases for the local sentence transformers backend."""
    
    def test_backend_initialization(self):
        """Test backend initialization."""
        backend = LocalSentenceTransformersBackend(model_name="all-MiniLM-L6-v2")
        
        assert backend.model_name == "all-MiniLM-L6-v2"
        assert backend.dim() == 384
        assert "sentence-transformers" in backend.name()
    
    def test_embed_texts_empty_input(self):
        """Test handling of empty input."""
        backend = LocalSentenceTransformersBackend(model_name="all-MiniLM-L6-v2")
        
        embeddings = backend.embed_texts([])
        assert embeddings.shape == (0, backend.dim())
    
    def test_embed_texts_single_text(self):
        """Test embedding single text."""
        backend = LocalSentenceTransformersBackend(
            model_name="all-MiniLM-L6-v2",
            deterministic_seed=42
        )
        
        embeddings = backend.embed_texts(["hello world"])
        assert embeddings.shape == (1, backend.dim())
        
        # Check that embedding is normalized (for cosine similarity)
        norm = np.linalg.norm(embeddings[0])
        assert abs(norm - 1.0) < 0.01  # Should be approximately 1 due to normalization
    
    def test_get_model_info(self):
        """Test model info method."""
        backend = LocalSentenceTransformersBackend(
            model_name="all-MiniLM-L6-v2",
            deterministic_seed=42
        )
        
        info = backend.get_model_info()
        assert "model_name" in info
        assert "embedding_dimension" in info
        assert "device" in info
        assert info["model_name"] == "all-MiniLM-L6-v2"
        assert info["embedding_dimension"] == 384
        assert info["deterministic_seed"] == 42


class TestGetEmbeddingProvider:
    """Test cases for the factory function."""
    
    def test_factory_function_default(self):
        """Test factory function with defaults."""
        provider = get_embedding_provider()
        
        assert provider.provider_name == "local"  # Default provider
        assert provider.dim() > 0
    
    def test_factory_function_with_params(self):
        """Test factory function with parameters."""
        provider = get_embedding_provider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            batch_size=16
        )
        
        assert provider.provider_name == "local"
        assert provider.batch_size == 16
        assert "all-MiniLM-L6-v2" in provider.name()
    
    @patch.dict(os.environ, {"EMBEDDING_PROVIDER": "local", "EMBEDDING_MODEL_NAME": "all-MiniLM-L6-v2"})
    def test_factory_function_with_env_vars(self):
        """Test factory function with environment variables."""
        provider = get_embedding_provider()
        
        assert provider.provider_name == "local"
        assert "all-MiniLM-L6-v2" in provider.name()


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
class TestOpenAIBackend:
    """Test cases for OpenAI backend (requires API key)."""
    
    def test_openai_backend_initialization(self):
        """Test OpenAI backend initialization."""
        from services.embeddings.backends.openai import OpenAIBackend
        
        backend = OpenAIBackend(model_name="text-embedding-ada-002")
        
        assert backend.model_name == "text-embedding-ada-002"
        assert backend.dim() == 1536
        assert "openai" in backend.name()
    
    def test_openai_embed_texts(self):
        """Test OpenAI embedding generation."""
        from services.embeddings.backends.openai import OpenAIBackend
        
        backend = OpenAIBackend(model_name="text-embedding-ada-002")
        
        texts = ["hello world"]
        embeddings = backend.embed_texts(texts)
        
        assert embeddings.shape == (1, backend.dim())
        assert embeddings.dtype in [np.float32, np.float64]


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
class TestOpenAIBackendMocked:
    """Test OpenAI backend with mocked API calls."""
    
    @patch('openai.Embedding.create')
    def test_openai_backend_mocked(self, mock_create):
        """Test OpenAI backend with mocked API."""
        # Mock the API response
        mock_create.return_value = {
            "data": [
                {"embedding": [0.1] * 1536}
            ]
        }
        
        from services.embeddings.backends.openai import OpenAIBackend
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            backend = OpenAIBackend(model_name="text-embedding-ada-002")
            
            embeddings = backend.embed_texts(["test text"])
            
            assert embeddings.shape == (1, 1536)
            mock_create.assert_called_once()


class TestIntegration:
    """Integration tests for the complete embedding system."""
    
    def test_provider_switching(self):
        """Test switching between different providers."""
        # Local provider
        local_provider = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            deterministic_seed=42
        )
        
        texts = ["test text for embedding"]
        local_embeddings = local_provider.embed_texts(texts)
        
        assert local_embeddings.shape == (1, local_provider.dim())
        assert "local" in local_provider.name()
    
    def test_consistency_across_calls(self):
        """Test that multiple calls with same input produce consistent results."""
        provider = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            deterministic_seed=42
        )
        
        texts = ["consistent test text"]
        
        embeddings1 = provider.embed_texts(texts)
        embeddings2 = provider.embed_texts(texts)
        
        np.testing.assert_array_almost_equal(embeddings1, embeddings2, decimal=5)
    
    def test_large_batch_processing(self):
        """Test processing of larger batches."""
        provider = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            batch_size=5,
            deterministic_seed=42
        )
        
        # Create a larger batch
        texts = [f"Document number {i} with some content" for i in range(20)]
        
        embeddings = provider.embed_texts(texts)
        
        assert embeddings.shape == (20, provider.dim())
        
        # Check that all embeddings are different (not zeros or identical)
        for i in range(len(embeddings)):
            assert not np.allclose(embeddings[i], 0)
            if i > 0:
                assert not np.allclose(embeddings[i], embeddings[0])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
