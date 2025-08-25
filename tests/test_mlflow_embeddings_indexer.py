"""
Tests for MLflow-instrumented embeddings and indexer jobs.
Issue #217: Instrument embeddings & indexer jobs with MLflow tracking
"""

import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Import modules to test
from services.embeddings.provider import EmbeddingsProvider
from jobs.rag.indexer import RAGIndexer


class TestEmbeddingsProvider(unittest.TestCase):
    """Test cases for EmbeddingsProvider with MLflow tracking."""

    def setUp(self):
        """Set up test fixtures."""
        self.provider = EmbeddingsProvider(
            model_name="all-MiniLM-L6-v2",
            batch_size=2,  # Small batch for testing
        )
        
        self.sample_texts = [
            "This is a test document about artificial intelligence.",
            "Machine learning is transforming the technology industry.",
            "Deep learning models require large amounts of training data.",
        ]

    def test_provider_initialization(self):
        """Test provider initialization."""
        assert self.provider.model_name == "all-MiniLM-L6-v2"
        assert self.provider.batch_size == 2
        assert self.provider.embedding_dimension > 0
        assert hasattr(self.provider, 'model')

    def test_metrics_reset(self):
        """Test metrics reset functionality."""
        # Modify metrics
        self.provider.metrics["documents_processed"] = 10
        
        # Reset
        self.provider._reset_metrics()
        
        # Check reset values
        assert self.provider.metrics["documents_processed"] == 0
        assert self.provider.metrics["embeddings_generated"] == 0
        assert self.provider.metrics["failures"] == 0

    def test_get_model_info(self):
        """Test model info retrieval."""
        info = self.provider.get_model_info()
        
        assert "model_name" in info
        assert "embedding_dimension" in info
        assert "batch_size" in info
        assert info["model_name"] == "all-MiniLM-L6-v2"

    @patch('services.embeddings.provider.mlrun')
    @patch('mlflow.log_param')
    @patch('mlflow.log_metric')
    @patch('mlflow.log_artifact')
    async def test_generate_embeddings(self, mock_log_artifact, mock_log_metric, mock_log_param, mock_mlrun):
        """Test embeddings generation with MLflow tracking."""
        # Mock MLflow context manager
        mock_mlrun.return_value.__enter__ = MagicMock()
        mock_mlrun.return_value.__exit__ = MagicMock()
        
        # Generate embeddings
        embeddings, metrics = await self.provider.generate_embeddings(
            self.sample_texts,
            experiment_name="test_experiment",
            run_name="test_run"
        )
        
        # Check results
        assert len(embeddings) == len(self.sample_texts)
        assert all(isinstance(emb, np.ndarray) for emb in embeddings)
        assert all(len(emb) == self.provider.embedding_dimension for emb in embeddings)
        
        # Check metrics
        assert metrics["documents_processed"] == len(self.sample_texts)
        assert metrics["embeddings_generated"] == len(self.sample_texts)
        assert metrics["embeddings_per_second"] > 0
        
        # Verify MLflow logging was called
        mock_log_param.assert_called()
        mock_log_metric.assert_called()

    async def test_embeddings_with_failures(self):
        """Test embeddings generation handling failures gracefully."""
        # Create provider with invalid model to force failures
        with patch.object(self.provider.model, 'encode', side_effect=Exception("Model error")):
            embeddings, metrics = await self.provider.generate_embeddings(
                self.sample_texts,
                experiment_name="test_experiment",
                run_name="test_failures"
            )
            
            # Should still return embeddings (zeros) and track failures
            assert len(embeddings) == len(self.sample_texts)
            assert metrics["failures"] > 0


class TestRAGIndexer(unittest.TestCase):
    """Test cases for RAGIndexer with MLflow tracking."""

    def setUp(self):
        """Set up test fixtures."""
        self.indexer = RAGIndexer(
            chunk_size=50,  # Small chunks for testing
            chunk_overlap=10,
            batch_size=2,
            embedding_model="all-MiniLM-L6-v2",
        )
        
        self.sample_docs = [
            {
                "id": "test_doc_1",
                "title": "Test Document 1",
                "content": "This is a test document with enough content to create multiple chunks. " * 10
            },
            {
                "id": "test_doc_2", 
                "title": "Test Document 2",
                "content": "This is another test document with sufficient content for chunking. " * 8
            }
        ]

    def test_indexer_initialization(self):
        """Test indexer initialization."""
        assert self.indexer.chunk_size == 50
        assert self.indexer.chunk_overlap == 10
        assert self.indexer.batch_size == 2
        assert self.indexer.embedding_model == "all-MiniLM-L6-v2"
        assert hasattr(self.indexer, 'embeddings_provider')

    def test_text_splitting(self):
        """Test text chunking functionality."""
        text = "This is a test document. " * 20  # 100 words
        chunks = self.indexer._split_text(text, "test_doc", 0)
        
        assert len(chunks) > 1  # Should create multiple chunks
        assert all(chunk["word_count"] <= self.indexer.chunk_size for chunk in chunks)
        assert all("chunk_id" in chunk for chunk in chunks)
        assert all("text" in chunk for chunk in chunks)

    def test_chunk_overlap(self):
        """Test that chunks have proper overlap."""
        text = "word " * 100  # 100 words
        chunks = self.indexer._split_text(text, "test_doc", 0)
        
        if len(chunks) > 1:
            # Check that consecutive chunks have overlap
            first_chunk_words = chunks[0]["text"].split()
            second_chunk_words = chunks[1]["text"].split()
            
            # Should have some overlap
            overlap_found = any(word in second_chunk_words[:self.indexer.chunk_overlap] 
                               for word in first_chunk_words[-self.indexer.chunk_overlap:])
            assert overlap_found

    async def test_create_chunks(self):
        """Test chunk creation from documents."""
        chunks = await self.indexer._create_chunks(self.sample_docs)
        
        assert len(chunks) > len(self.sample_docs)  # Should create multiple chunks
        assert all("doc_id" in chunk for chunk in chunks)
        assert all("chunk_id" in chunk for chunk in chunks)
        assert all("text" in chunk for chunk in chunks)
        
        # Check metrics updated
        assert self.indexer.metrics["docs_processed"] == len(self.sample_docs)
        assert self.indexer.metrics["chunks_created"] == len(chunks)

    def test_metrics_reset(self):
        """Test metrics reset functionality."""
        # Modify metrics
        self.indexer.metrics["docs_processed"] = 5
        
        # Reset
        self.indexer._reset_metrics()
        
        # Check reset values
        assert self.indexer.metrics["docs_processed"] == 0
        assert self.indexer.metrics["chunks_created"] == 0
        assert self.indexer.metrics["failures"] == 0

    @patch('jobs.rag.indexer.mlrun')
    @patch('mlflow.log_param')
    @patch('mlflow.log_metric') 
    @patch('mlflow.log_artifact')
    async def test_index_documents(self, mock_log_artifact, mock_log_metric, mock_log_param, mock_mlrun):
        """Test full document indexing with MLflow tracking."""
        # Mock MLflow context manager
        mock_mlrun.return_value.__enter__ = MagicMock()
        mock_mlrun.return_value.__exit__ = MagicMock()
        
        # Index documents
        results = await self.indexer.index_documents(
            self.sample_docs,
            experiment_name="test_indexing",
            run_name="test_index_run"
        )
        
        # Check results
        assert "chunks_created" in results
        assert "embeddings_generated" in results
        assert "metrics" in results
        assert results["chunks_created"] > 0
        assert results["embeddings_generated"] > 0
        
        # Check that MLflow logging was called
        mock_log_param.assert_called()
        mock_log_metric.assert_called()

    async def test_build_index(self):
        """Test vector index building."""
        # Create sample chunks and embeddings
        chunks = [
            {"chunk_id": "test_1", "text": "test text 1"},
            {"chunk_id": "test_2", "text": "test text 2"},
        ]
        embeddings = [
            np.random.random(384),  # Simulate embeddings
            np.random.random(384),
        ]
        
        # Build index
        index_results = await self.indexer._build_index(chunks, embeddings)
        
        assert "index_type" in index_results
        assert "vectors_indexed" in index_results
        assert "build_time" in index_results
        assert index_results["vectors_indexed"] == len(embeddings)

    async def test_store_indexed_data(self):
        """Test storage of indexed data."""
        # Create sample data
        chunks = [
            {"chunk_id": "test_1", "text": "test text 1"},
            {"chunk_id": "test_2", "text": "test text 2"},
        ]
        embeddings = [
            np.random.random(384),
            np.random.random(384),
        ]
        
        # Store data
        storage_results = await self.indexer._store_indexed_data(chunks, embeddings)
        
        assert "chunks_stored" in storage_results
        assert "embeddings_stored" in storage_results
        assert storage_results["chunks_stored"] == len(chunks)
        assert storage_results["embeddings_stored"] == len(embeddings)


class TestIntegration(unittest.TestCase):
    """Integration tests for embeddings and indexer working together."""

    @patch('services.embeddings.provider.mlrun')
    @patch('jobs.rag.indexer.mlrun')
    @patch('mlflow.log_param')
    @patch('mlflow.log_metric')
    @patch('mlflow.log_artifact')
    async def test_end_to_end_workflow(self, mock_log_artifact, mock_log_metric, mock_log_param, 
                                      mock_indexer_mlrun, mock_provider_mlrun):
        """Test complete end-to-end workflow."""
        # Mock MLflow context managers
        mock_provider_mlrun.return_value.__enter__ = MagicMock()
        mock_provider_mlrun.return_value.__exit__ = MagicMock()
        mock_indexer_mlrun.return_value.__enter__ = MagicMock()
        mock_indexer_mlrun.return_value.__exit__ = MagicMock()
        
        # Create indexer
        indexer = RAGIndexer(
            chunk_size=30,
            chunk_overlap=5,
            batch_size=2,
            embedding_model="all-MiniLM-L6-v2",
        )
        
        # Sample documents
        docs = [
            {
                "id": "integration_test_1",
                "title": "Integration Test Document",
                "content": "This is a comprehensive test document for integration testing. " * 15
            }
        ]
        
        # Run full indexing pipeline
        results = await indexer.index_documents(
            docs,
            experiment_name="integration_test",
            run_name="full_pipeline_test"
        )
        
        # Verify complete pipeline execution
        assert results["chunks_created"] > 0
        assert results["embeddings_generated"] > 0
        assert results["total_time"] > 0
        
        # Verify MLflow tracking
        assert mock_log_param.called
        assert mock_log_metric.called


# Pytest fixtures for async tests
@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Async test runners
@pytest.mark.asyncio
async def test_embeddings_provider_async():
    """Async test for embeddings provider."""
    provider = EmbeddingsProvider(model_name="all-MiniLM-L6-v2", batch_size=2)
    texts = ["Test text 1", "Test text 2"]
    
    with patch('services.embeddings.provider.mlrun') as mock_mlrun:
        mock_mlrun.return_value.__enter__ = MagicMock()
        mock_mlrun.return_value.__exit__ = MagicMock()
        
        embeddings, metrics = await provider.generate_embeddings(texts)
        
        assert len(embeddings) == len(texts)
        assert metrics["embeddings_generated"] == len(texts)


@pytest.mark.asyncio 
async def test_rag_indexer_async():
    """Async test for RAG indexer."""
    indexer = RAGIndexer(chunk_size=20, chunk_overlap=5, batch_size=2)
    docs = [{"id": "test", "title": "Test", "content": "Test content " * 20}]
    
    with patch('jobs.rag.indexer.mlrun') as mock_mlrun:
        mock_mlrun.return_value.__enter__ = MagicMock()
        mock_mlrun.return_value.__exit__ = MagicMock()
        
        results = await indexer.index_documents(docs)
        
        assert results["chunks_created"] > 0
        assert results["embeddings_generated"] > 0


if __name__ == "__main__":
    # Run tests
    unittest.main()
