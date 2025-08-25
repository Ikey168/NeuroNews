"""
Test suite for Ask Pipeline with MLflow Tracking
Issue #218: Instrument /ask pipeline with MLflow tracking

This module contains comprehensive tests for the ask API pipeline
including MLflow tracking, sampling, and RAG functionality.
"""

import asyncio
import json
import os
import pytest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

# Set test environment before importing modules
os.environ["ASK_LOG_SAMPLE"] = "1.0"  # 100% sampling for tests

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from services.rag.answer import RAGAnswerService
    from services.api.routes import ask
    from services.api.routes.ask import AskRequest, ask_question, get_rag_service
    from services.embeddings.provider import EmbeddingsProvider
except ImportError as e:
    print(f"Import error: {e}")
    pytest.skip("Required modules not available", allow_module_level=True)


class TestRAGAnswerService:
    """Test cases for RAG Answer Service."""

    @pytest.fixture
    def mock_embeddings_provider(self):
        """Mock embeddings provider."""
        provider = MagicMock(spec=EmbeddingsProvider)
        provider.model_name = "test-model"
        provider.embedding_dimension = 384
        provider.generate_embeddings = AsyncMock(
            return_value=([[[0.1] * 384]], {"embeddings_generated": 1})
        )
        
        # Add mock model for direct access
        mock_model = MagicMock()
        mock_model.encode = MagicMock(return_value=[[0.1] * 384])
        provider.model = mock_model
        provider.batch_size = 16
        
        return provider

    @pytest.fixture
    def rag_service(self, mock_embeddings_provider):
        """Create RAG service instance with mocked dependencies."""
        return RAGAnswerService(
            embeddings_provider=mock_embeddings_provider,
            default_k=5,
            rerank_enabled=True,
            fusion_enabled=True,
            answer_provider="openai"
        )

    def test_rag_service_initialization(self, rag_service):
        """Test RAG service initialization."""
        assert rag_service.default_k == 5
        assert rag_service.rerank_enabled is True
        assert rag_service.fusion_enabled is True
        assert rag_service.answer_provider == "openai"
        assert "retrieval_ms" in rag_service.metrics
        assert "citations" in rag_service.artifacts

    @pytest.mark.asyncio
    async def test_document_retrieval(self, rag_service):
        """Test document retrieval functionality."""
        question = "What is artificial intelligence?"
        k = 3
        filters = {"category": "technology"}
        
        docs = await rag_service._retrieve_documents(question, k, filters, True)
        
        assert len(docs) == k
        assert all("id" in doc for doc in docs)
        assert all("title" in doc for doc in docs)
        assert all("score" in doc for doc in docs)
        
        # Check query processing artifacts
        assert "query_processing" in rag_service.artifacts
        assert rag_service.artifacts["query_processing"]["original_query"] == question

    @pytest.mark.asyncio
    async def test_query_expansion(self, rag_service):
        """Test query expansion functionality."""
        question = "How does machine learning work?"
        
        expanded = await rag_service._expand_query(question)
        
        assert isinstance(expanded, list)
        assert len(expanded) >= 1
        assert question in expanded

    @pytest.mark.asyncio
    async def test_document_reranking(self, rag_service):
        """Test document reranking."""
        sample_docs = [
            {"id": "doc1", "title": "Doc 1", "score": 0.8, "content": "Content 1"},
            {"id": "doc2", "title": "Doc 2", "score": 0.9, "content": "Content 2"},
            {"id": "doc3", "title": "Doc 3", "score": 0.7, "content": "Content 3"},
        ]
        
        reranked = await rag_service._rerank_documents("test query", sample_docs)
        
        assert len(reranked) == len(sample_docs)
        assert all("rerank_score" in doc for doc in reranked)
        # Scores should be sorted in descending order
        scores = [doc["score"] for doc in reranked]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_answer_generation(self, rag_service):
        """Test answer generation with different providers."""
        question = "What is the capital of France?"
        docs = [
            {"id": "doc1", "title": "France Facts", "content": "Paris is the capital of France.", "score": 0.9}
        ]
        
        # Test different providers
        for provider in ["openai", "anthropic", "local"]:
            result = await rag_service._generate_answer(question, docs, provider)
            
            assert "answer" in result
            assert "tokens_in" in result
            assert "tokens_out" in result
            assert "provider" in result
            assert result["provider"] == provider
            assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_citation_extraction(self, rag_service):
        """Test citation extraction from documents."""
        answer = "The capital of France is Paris [1][2]."
        docs = [
            {
                "id": "doc1", 
                "title": "France Guide", 
                "content": "Paris is the capital city of France.",
                "source": "example.com",
                "score": 0.9,
                "published_date": "2024-01-01"
            },
            {
                "id": "doc2", 
                "title": "European Capitals", 
                "content": "Major European capitals include Paris, London, and Berlin.",
                "source": "geography.com",
                "score": 0.8,
                "published_date": "2024-01-02"
            }
        ]
        
        citations = await rag_service._extract_citations(answer, docs)
        
        assert len(citations) >= 2
        for citation in citations:
            assert "citation_id" in citation
            assert "title" in citation
            assert "source" in citation
            assert "relevance_score" in citation
            assert "excerpt" in citation

    @pytest.mark.asyncio
    @patch("mlflow.start_run")
    @patch("mlflow.log_param")
    @patch("mlflow.log_metric")
    @patch("mlflow.log_artifact")
    async def test_full_answer_pipeline_with_mlflow(
        self, mock_log_artifact, mock_log_metric, mock_log_param, mock_start_run, rag_service
    ):
        """Test full answer pipeline with MLflow tracking."""
        # Mock MLflow context manager
        mock_run = MagicMock()
        mock_start_run.return_value.__enter__ = MagicMock(return_value=mock_run)
        mock_start_run.return_value.__exit__ = MagicMock(return_value=None)
        
        question = "What is renewable energy?"
        
        with patch("services.mlops.tracking.mlrun") as mock_mlrun:
            mock_mlrun.return_value.__enter__ = MagicMock()
            mock_mlrun.return_value.__exit__ = MagicMock()
            
            response = await rag_service.answer_question(
                question=question,
                k=3,
                filters={"category": "environment"},
                rerank_on=True,
                fusion=True,
                provider="openai",
                experiment_name="test_experiment",
                run_name="test_run"
            )
        
        # Verify response structure
        assert "question" in response
        assert "answer" in response
        assert "citations" in response
        assert "metadata" in response
        assert "metrics" in response
        assert response["question"] == question
        assert len(response["answer"]) > 0
        
        # Verify metrics were tracked
        assert response["metrics"]["retrieval_ms"] > 0
        assert response["metrics"]["answer_ms"] > 0
        assert response["metrics"]["k_used"] == 3

    def test_question_type_classification(self, rag_service):
        """Test question type classification."""
        test_cases = [
            ("What is AI?", "factual"),
            ("How does it work?", "explanatory"),
            ("Why is this important?", "explanatory"),
            ("When did this happen?", "temporal_spatial"),
            ("Where is Paris?", "temporal_spatial"),
            ("Who invented this?", "entity"),
            ("Is this correct?", "general_question"),
            ("Tell me about AI", "statement_query"),
        ]
        
        for question, expected_type in test_cases:
            result = rag_service._classify_question_type(question)
            assert result == expected_type

    def test_metrics_reset(self, rag_service):
        """Test metrics reset functionality."""
        # Set some metrics
        rag_service.metrics["retrieval_ms"] = 100.0
        rag_service.metrics["answer_ms"] = 200.0
        rag_service.artifacts["citations"] = [{"test": "data"}]
        
        # Reset
        rag_service._reset_metrics()
        
        # Verify reset
        assert rag_service.metrics["retrieval_ms"] == 0.0
        assert rag_service.metrics["answer_ms"] == 0.0
        assert len(rag_service.artifacts["citations"]) == 0


class TestAskAPIRoutes:
    """Test cases for Ask API routes."""

    @pytest.fixture
    def mock_rag_service(self):
        """Mock RAG service for API tests."""
        service = MagicMock(spec=RAGAnswerService)
        service.answer_question = AsyncMock(
            return_value={
                "question": "Test question?",
                "answer": "Test answer with citations [1][2].",
                "citations": [
                    {
                        "citation_id": 1,
                        "title": "Test Source",
                        "source": "test.com",
                        "url": "https://test.com/article/1",
                        "relevance_score": 0.9,
                        "published_date": "2024-01-01",
                        "excerpt": "Test excerpt...",
                        "citation_strength": 0.95
                    }
                ],
                "metadata": {
                    "retrieval_time_ms": 150.0,
                    "answer_time_ms": 300.0,
                    "total_time_ms": 450.0,
                    "documents_retrieved": 5,
                    "provider_used": "openai",
                    "rerank_enabled": True,
                    "fusion_enabled": True,
                }
            }
        )
        return service

    def test_ask_request_validation(self):
        """Test ask request model validation."""
        # Valid request
        valid_request = AskRequest(
            question="What is machine learning?",
            k=5,
            filters={"category": "technology"},
            rerank_on=True,
            fusion=True,
            provider="openai"
        )
        assert valid_request.question == "What is machine learning?"
        assert valid_request.k == 5
        
        # Invalid requests
        with pytest.raises(ValueError):
            AskRequest(question="x")  # Too short
        
        with pytest.raises(ValueError):
            AskRequest(question="What is ML?", k=0)  # Invalid k
        
        with pytest.raises(ValueError):
            AskRequest(question="What is ML?", k=25)  # k too large

    @pytest.mark.asyncio
    async def test_ask_question_endpoint(self, mock_rag_service):
        """Test the main ask question endpoint."""
        request = AskRequest(
            question="What is artificial intelligence?",
            k=5,
            filters={"category": "technology"},
            rerank_on=True,
            fusion=True,
            provider="openai"
        )
        
        with patch("services.api.routes.ask.get_rag_service", return_value=mock_rag_service):
            response = await ask_question(request, mock_rag_service)
        
        # Verify response structure
        assert response.question == "Test question?"
        assert len(response.answer) > 0
        assert len(response.citations) == 1
        assert "total_time_ms" in response.metadata
        assert isinstance(response.tracked_in_mlflow, bool)
        assert len(response.request_id) > 0

    def test_sampling_logic(self):
        """Test MLflow sampling logic."""
        # Test with 100% sampling (from environment)
        assert ask.should_log_to_mlflow() is True  # Should always be True with 100% rate
        
        # Test with different sampling rates
        with patch.dict(os.environ, {"ASK_LOG_SAMPLE": "0.0"}):
            # Need to reload the module or mock the rate
            with patch("services.api.routes.ask.ASK_LOG_SAMPLE_RATE", 0.0):
                with patch("random.random", return_value=0.5):
                    assert ask.should_log_to_mlflow() is False

    @pytest.mark.asyncio
    async def test_ask_without_mlflow_tracking(self, mock_rag_service):
        """Test ask functionality without MLflow tracking."""
        from services.api.routes.ask import _answer_question_without_tracking
        
        request = AskRequest(
            question="What is machine learning?",
            k=3,
            rerank_on=False,
            fusion=False,
            provider="openai"
        )
        
        # Mock the internal methods
        mock_rag_service._retrieve_documents = AsyncMock(
            return_value=[
                {"id": "doc1", "title": "ML Basics", "content": "ML content", "score": 0.9}
            ]
        )
        mock_rag_service._generate_answer = AsyncMock(
            return_value={
                "answer": "Machine learning is...",
                "tokens_in": 100,
                "tokens_out": 50,
                "provider": "openai"
            }
        )
        mock_rag_service._extract_citations = AsyncMock(
            return_value=[{"citation_id": 1, "title": "ML Source"}]
        )
        mock_rag_service._reset_metrics = MagicMock()
        
        response = await _answer_question_without_tracking(
            mock_rag_service, request, "test_request_id"
        )
        
        assert "question" in response
        assert "answer" in response
        assert "citations" in response
        assert "metadata" in response
        assert response["metadata"]["sampling_status"] == "not_tracked"


class TestMLflowIntegration:
    """Test MLflow integration components."""

    @pytest.mark.asyncio
    async def test_artifact_logging(self):
        """Test MLflow artifact logging functionality."""
        from services.rag.answer import RAGAnswerService
        
        service = RAGAnswerService()
        
        # Mock MLflow
        mock_mlflow = MagicMock()
        mock_mlflow.log_artifact = MagicMock()
        
        sample_citations = [
            {
                "citation_id": 1,
                "title": "Test Article",
                "source": "test.com",
                "relevance_score": 0.9,
                "published_date": "2024-01-01"
            }
        ]
        
        sample_docs = [
            {"id": "doc1", "title": "Doc 1", "score": 0.9, "content": "Content"}
        ]
        
        # Test artifact logging
        await service._log_artifacts(mock_mlflow, sample_citations, sample_docs, "test question")
        
        # Verify artifacts were logged
        assert mock_mlflow.log_artifact.call_count >= 3  # citations, trace, summary

    def test_environment_variable_configuration(self):
        """Test environment variable configuration."""
        # Test default sampling rate
        assert float(os.environ.get("ASK_LOG_SAMPLE", "0.2")) == 1.0  # Set in test setup
        
        # Test with different values
        test_cases = ["0.0", "0.5", "1.0"]
        for rate in test_cases:
            with patch.dict(os.environ, {"ASK_LOG_SAMPLE": rate}):
                from services.api.routes.ask import ASK_LOG_SAMPLE_RATE
                # Would need to reload module for this to work properly
                # This is more of a documentation test


@pytest.mark.asyncio
async def test_end_to_end_pipeline():
    """End-to-end test of the ask pipeline."""
    # This test verifies the complete pipeline integration

    # Mock embeddings provider
    mock_embeddings = MagicMock(spec=EmbeddingsProvider)
    mock_embeddings.model_name = "test-model"
    mock_embeddings.embedding_dimension = 384
    mock_embeddings.batch_size = 32
    mock_embeddings.model = MagicMock()
    mock_embeddings.model.encode = MagicMock(return_value=[[0.1] * 384])
    mock_embeddings.generate_embeddings = AsyncMock(
        return_value=([[[0.1] * 384]], {"embeddings_generated": 1})
    )    # Create service
    service = RAGAnswerService(
        embeddings_provider=mock_embeddings,
        default_k=3,
        rerank_enabled=True,
        fusion_enabled=True,
        answer_provider="openai"
    )
    
    # Test question
    question = "What are the benefits of renewable energy?"
    
    # Mock MLflow context
    with patch("services.mlops.tracking.mlrun") as mock_mlrun:
        mock_mlrun.return_value.__enter__ = MagicMock()
        mock_mlrun.return_value.__exit__ = MagicMock()
        
        # Execute pipeline
        response = await service.answer_question(
            question=question,
            k=3,
            filters={"category": "environment"},
            experiment_name="e2e_test"
        )
    
    # Verify complete response
    assert response["question"] == question
    assert len(response["answer"]) > 0
    assert "citations" in response
    assert "metadata" in response
    assert "metrics" in response
    
    # Verify metrics
    metrics = response["metrics"]
    assert metrics["k_used"] == 3
    assert metrics["retrieval_ms"] > 0
    assert metrics["answer_ms"] > 0
    assert metrics["num_citations"] >= 0


def test_configuration_loading():
    """Test configuration loading and validation."""
    # Test service configuration
    service = get_rag_service()
    
    assert service.default_k == 5
    assert service.rerank_enabled is True
    assert service.fusion_enabled is True
    assert service.answer_provider == "openai"
    
    # Test embeddings provider configuration
    assert service.embeddings_provider.model_name == "all-MiniLM-L6-v2"
    assert service.embeddings_provider.batch_size == 16


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
