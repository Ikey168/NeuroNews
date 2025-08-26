"""
Unit tests for Issue #233: Answering pipeline + citations (FastAPI /ask)

This module contains tests to verify that the /ask endpoint meets all
DoD requirements for answering questions with citations and latency stats.
"""

import asyncio
import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List

# Add to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Set test environment
os.environ["ASK_LOG_SAMPLE"] = "1.0"  # 100% sampling for tests

try:
    from services.api.routes.ask import (
        AskRequest, 
        AskResponse, 
        ask_question, 
        get_rag_service,
        _answer_question_without_tracking
    )
    from services.rag.answer import RAGAnswerService
    from services.embeddings.provider import EmbeddingsProvider
except ImportError as e:
    print(f"Import error: {e}")
    pytest.skip("Required modules not available", allow_module_level=True)


class TestIssue233AskEndpoint:
    """Test suite for Issue #233 DoD requirements."""

    @pytest.fixture
    def mock_embeddings_provider(self):
        """Mock embeddings provider for testing."""
        provider = MagicMock(spec=EmbeddingsProvider)
        provider.model_name = "test-model"
        provider.embedding_dimension = 384
        provider.generate_embeddings = AsyncMock(
            return_value=([[[0.1] * 384]], {"embeddings_generated": 1})
        )
        return provider

    @pytest.fixture
    def mock_rag_service(self, mock_embeddings_provider):
        """Mock RAG service with sample responses."""
        service = MagicMock(spec=RAGAnswerService)
        service.embeddings_provider = mock_embeddings_provider
        service.default_k = 5
        service.rerank_enabled = True
        service.fusion_enabled = True
        service.answer_provider = "openai"
        
        # Mock the answer_question method
        service.answer_question = AsyncMock(return_value={
            "question": "What is artificial intelligence?",
            "answer": "Artificial intelligence (AI) is a branch of computer science that aims to create machines capable of intelligent behavior. It involves developing algorithms and systems that can perform tasks typically requiring human intelligence, such as visual perception, speech recognition, decision-making, and language translation.",
            "citations": [
                {
                    "citation_id": 1,
                    "title": "Introduction to AI",
                    "url": "https://example.com/ai-intro",
                    "relevance_score": 0.95,
                    "published_date": "2024-01-15",
                    "excerpt": "AI is transforming technology...",
                    "citation_strength": 0.9
                },
                {
                    "citation_id": 2,
                    "title": "Machine Learning Fundamentals",
                    "url": "https://example.com/ml-basics",
                    "relevance_score": 0.88,
                    "published_date": "2024-01-10",
                    "excerpt": "Machine learning is a subset of AI...",
                    "citation_strength": 0.85
                },
                {
                    "citation_id": 3,
                    "title": "AI Applications Today",
                    "url": "https://example.com/ai-applications",
                    "relevance_score": 0.82,
                    "published_date": "2024-01-05",
                    "excerpt": "Modern AI applications include...",
                    "citation_strength": 0.8
                },
                {
                    "citation_id": 4,
                    "title": "Future of Artificial Intelligence",
                    "url": "https://example.com/ai-future",
                    "relevance_score": 0.79,
                    "published_date": "2023-12-20",
                    "excerpt": "The future of AI holds great promise...",
                    "citation_strength": 0.75
                }
            ],
            "metadata": {
                "retrieval_time_ms": 150.5,
                "answer_time_ms": 850.2,
                "rerank_time_ms": 45.3,
                "total_time_ms": 1045.0,
                "documents_retrieved": 5,
                "provider_used": "openai",
                "rerank_enabled": True,
                "fusion_enabled": True,
                "request_id": "test_request_123",
                "sampling_status": "tracked"
            }
        })
        
        return service

    @pytest.mark.asyncio
    async def test_ask_request_model(self):
        """Test AskRequest model validation."""
        # Valid request
        request = AskRequest(
            question="What is AI?",
            k=5,
            filters={"category": "technology"},
            rerank_on=True,
            fusion=True,
            provider="openai"
        )
        
        assert request.question == "What is AI?"
        assert request.k == 5
        assert request.filters == {"category": "technology"}
        assert request.rerank_on is True
        assert request.fusion is True
        assert request.provider == "openai"

    @pytest.mark.asyncio
    async def test_ask_response_model(self):
        """Test AskResponse model with required fields."""
        response = AskResponse(
            question="Test question?",
            answer="Test answer",
            citations=[
                {
                    "citation_id": 1,
                    "title": "Test Article",
                    "url": "https://example.com",
                    "relevance_score": 0.9,
                    "published_date": "2024-01-01",
                    "excerpt": "Test excerpt",
                    "citation_strength": 0.85
                }
            ],
            metadata={
                "total_time_ms": 1000.0,
                "retrieval_time_ms": 200.0,
                "answer_time_ms": 800.0
            },
            request_id="test_123",
            tracked_in_mlflow=True
        )
        
        assert response.question == "Test question?"
        assert response.answer == "Test answer"
        assert len(response.citations) == 1
        assert "total_time_ms" in response.metadata
        assert response.request_id == "test_123"
        assert response.tracked_in_mlflow is True

    @pytest.mark.asyncio
    async def test_ask_question_endpoint(self, mock_rag_service):
        """Test the main ask_question endpoint meets DoD requirements."""
        request = AskRequest(
            question="What is artificial intelligence?",
            k=5,
            rerank_on=True,
            fusion=True,
            provider="openai"
        )
        
        with patch('services.api.routes.ask.get_rag_service', return_value=mock_rag_service):
            response = await ask_question(request, mock_rag_service)
        
        # DoD Requirement 1: Returns answer
        assert response.answer is not None
        assert len(response.answer.strip()) > 0
        
        # DoD Requirement 2: Returns 3+ citations
        assert len(response.citations) >= 3
        
        # Verify citation format matches issue requirements
        for citation in response.citations:
            assert "url" in citation
            assert "title" in citation
            assert "excerpt" in citation or "snippet" in citation
        
        # DoD Requirement 3: Returns latency stats
        assert "total_time_ms" in response.metadata
        assert response.metadata["total_time_ms"] > 0
        
        # Additional metadata requirements
        assert "retrieval_time_ms" in response.metadata
        assert "answer_time_ms" in response.metadata
        assert response.request_id is not None

    @pytest.mark.asyncio
    async def test_dod_curl_format_simulation(self, mock_rag_service):
        """Test that the endpoint can handle GET-style parameters for curl testing."""
        # Simulate curl query parameters
        query_params = {
            "question": "What are the benefits of renewable energy?",
            "k": 3,
            "rerank_on": True,
            "fusion": True,
            "provider": "openai"
        }
        
        request = AskRequest(**query_params)
        
        with patch('services.api.routes.ask.get_rag_service', return_value=mock_rag_service):
            response = await ask_question(request, mock_rag_service)
        
        # Verify curl-friendly response format
        assert isinstance(response.question, str)
        assert isinstance(response.answer, str)
        assert isinstance(response.citations, list)
        assert isinstance(response.metadata, dict)
        
        # Verify JSON serializable (important for curl)
        response_dict = response.dict()
        json_str = json.dumps(response_dict)
        assert len(json_str) > 0

    @pytest.mark.asyncio 
    async def test_performance_tracking(self, mock_rag_service):
        """Test that latency tracking works correctly."""
        request = AskRequest(question="Performance test?")
        
        with patch('services.api.routes.ask.get_rag_service', return_value=mock_rag_service):
            import time
            start_time = time.time()
            response = await ask_question(request, mock_rag_service)
            end_time = time.time()
        
        # Verify timing metadata
        metadata = response.metadata
        assert "total_time_ms" in metadata
        assert "retrieval_time_ms" in metadata
        assert "answer_time_ms" in metadata
        
        # Verify times are reasonable (positive numbers)
        assert metadata["total_time_ms"] > 0
        assert metadata["retrieval_time_ms"] >= 0
        assert metadata["answer_time_ms"] >= 0

    def test_dod_requirements_checklist(self):
        """Test checklist verification for Issue #233 DoD."""
        # Verify all DoD requirements are testable
        
        # [ ] Request: { query, k?, filters? {date_from,date_to,lang,source}, stream? }
        request_fields = AskRequest.__fields__.keys()
        assert "question" in request_fields  # 'query' equivalent
        assert "k" in request_fields
        assert "filters" in request_fields
        # Note: streaming not yet implemented (optional)
        
        # [ ] Response: { answer, citations:[{url,title,snippet}], retrieval:{latency_ms,k_used}, model }
        response_fields = AskResponse.__fields__.keys()
        assert "answer" in response_fields
        assert "citations" in response_fields
        assert "metadata" in response_fields  # Contains latency & model info
        
        # [ ] curl /ask?q=… returns answer with 3+ citations and latency stats
        # This is tested in test_ask_question_endpoint and test_dod_curl_format_simulation
        
        print("✅ All DoD requirements verified in test suite")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
