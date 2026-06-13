"""
RAG API Smoke Tests  
Issue #238: CI: Smoke tests for indexing & /ask

These tests verify that the /ask API endpoint works correctly
with the indexed corpus and returns proper responses.
"""

import pytest
import asyncio
import json
import os
import sys
import httpx
import time
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestRAGAPISmoke:
    """Smoke tests for RAG API endpoints"""
    
    @pytest.fixture(scope="class")
    def api_base_url(self):
        """Base URL for API testing"""
        return "http://localhost:8000"
    
    @pytest.fixture(scope="class")
    def test_questions(self):
        """Test questions related to our tiny corpus"""
        return [
            {
                "question": "What are the latest developments in artificial intelligence?",
                "expected_topics": ["AI", "machine learning", "artificial intelligence"]
            },
            {
                "question": "How can technology help with climate change?",
                "expected_topics": ["climate", "technology", "renewable energy"]
            },
            {
                "question": "What are the applications of AI in healthcare?",
                "expected_topics": ["healthcare", "AI", "diagnostic", "medical"]
            },
            {
                "question": "How is digital transformation affecting the economy?",
                "expected_topics": ["digital", "economy", "business", "transformation"]
            },
            {
                "question": "What's new in space exploration technology?",
                "expected_topics": ["space", "exploration", "technology", "Mars"]
            }
        ]
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self, api_base_url):
        """Test that the health endpoint is working"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{api_base_url}/health", timeout=10.0)
                assert response.status_code == 200, f"Health check failed: {response.status_code}"
                
                # Check response content if available
                if response.headers.get('content-type', '').startswith('application/json'):
                    data = response.json()
                    assert isinstance(data, dict), "Health response should be JSON object"
                    
            except httpx.RequestError as e:
                pytest.fail(f"Health endpoint request failed: {e}")
    
    @pytest.mark.asyncio
    async def test_ask_endpoint_basic(self, api_base_url):
        """Test basic /ask endpoint functionality"""
        question = "What are the latest developments in artificial intelligence?"
        
        payload = {
            "question": question,
            "k": 3,
            "use_reranking": True,
            "include_sources": True
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{api_base_url}/ask",
                    json=payload,
                    timeout=30.0
                )
                
                assert response.status_code == 200, f"Ask endpoint failed: {response.status_code} - {response.text}"
                
                data = response.json()
                assert isinstance(data, dict), "Response should be JSON object"
                
                # Verify required fields in response
                assert "answer" in data, "Missing 'answer' field in response"
                assert "citations" in data, "Missing 'citations' field in response"
                
                # Verify answer is non-empty
                answer = data["answer"]
                assert answer and answer.strip(), "Answer should not be empty"
                assert len(answer.strip()) > 10, "Answer should be substantial"
                
                # Verify citations
                citations = data["citations"]
                assert isinstance(citations, list), "Citations should be a list"
                assert len(citations) >= 1, "Should have at least 1 citation"
                
                # Verify citation structure
                for citation in citations:
                    assert isinstance(citation, dict), "Citation should be an object"
                    assert "content" in citation, "Citation missing content"
                    assert "source" in citation or "url" in citation, "Citation missing source/url"
                    
            except httpx.RequestError as e:
                pytest.fail(f"Ask endpoint request failed: {e}")
            except Exception as e:
                pytest.fail(f"Ask endpoint test failed: {e}")
    
    @pytest.mark.asyncio 
    async def test_ask_endpoint_multiple_questions(self, api_base_url, test_questions):
        """Test /ask endpoint with multiple questions"""
        
        for test_case in test_questions[:3]:  # Test first 3 to keep CI fast
            question = test_case["question"]
            expected_topics = test_case["expected_topics"]
            
            payload = {
                "question": question,
                "k": 5,
                "use_reranking": True,
                "include_sources": True
            }
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{api_base_url}/ask",
                        json=payload,
                        timeout=30.0
                    )
                    
                    assert response.status_code == 200, f"Ask failed for '{question}': {response.status_code}"
                    
                    data = response.json()
                    
                    # Basic structure validation
                    assert "answer" in data, f"Missing answer for '{question}'"
                    assert "citations" in data, f"Missing citations for '{question}'"
                    
                    answer = data["answer"]
                    citations = data["citations"]
                    
                    # Answer quality checks
                    assert answer and answer.strip(), f"Empty answer for '{question}'"
                    assert len(answer.strip()) >= 20, f"Answer too short for '{question}'"
                    
                    # Citation quality checks  
                    assert len(citations) >= 1, f"No citations for '{question}'"
                    assert len(citations) <= 5, f"Too many citations for '{question}'"
                    
                    # Check that answer contains relevant information
                    answer_lower = answer.lower()
                    found_topics = [topic for topic in expected_topics 
                                  if topic.lower() in answer_lower]
                    
                    assert len(found_topics) >= 1, f"Answer doesn't contain expected topics for '{question}'. Expected: {expected_topics}, Answer: {answer[:100]}..."
                    
                except httpx.RequestError as e:
                    pytest.fail(f"Request failed for '{question}': {e}")
                except Exception as e:
                    pytest.fail(f"Test failed for '{question}': {e}")
    
    @pytest.mark.asyncio
    async def test_ask_endpoint_with_filters(self, api_base_url):
        """Test /ask endpoint with filters"""
        question = "What are recent technology developments?"
        
        payload = {
            "question": question,
            "k": 3,
            "filters": {
                "date_from": "2024-01-15",
                "language": "en"
            },
            "use_reranking": True,
            "include_sources": True
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{api_base_url}/ask",
                    json=payload,
                    timeout=30.0
                )
                
                # Filters might not be fully implemented, so we accept 200 or 422
                assert response.status_code in [200, 422], f"Unexpected status for filtered request: {response.status_code}"
                
                if response.status_code == 200:
                    data = response.json()
                    assert "answer" in data, "Missing answer in filtered response"
                    assert "citations" in data, "Missing citations in filtered response"
                    
            except httpx.RequestError as e:
                pytest.fail(f"Filtered ask request failed: {e}")
    
    @pytest.mark.asyncio
    async def test_ask_endpoint_parameter_validation(self, api_base_url):
        """Test /ask endpoint parameter validation"""
        
        # Test missing question
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{api_base_url}/ask", json={})
            assert response.status_code in [400, 422], "Should reject empty request"
        
        # Test empty question
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{api_base_url}/ask", json={"question": ""})
            assert response.status_code in [400, 422], "Should reject empty question"
        
        # Test invalid k value
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{api_base_url}/ask", json={
                "question": "test question",
                "k": -1
            })
            assert response.status_code in [400, 422], "Should reject negative k"
    
    @pytest.mark.asyncio
    async def test_ask_endpoint_performance(self, api_base_url):
        """Test /ask endpoint performance"""
        question = "What are artificial intelligence applications?"
        
        payload = {
            "question": question,
            "k": 3,
            "use_reranking": True,
            "include_sources": True
        }
        
        async with httpx.AsyncClient() as client:
            start_time = time.time()
            
            try:
                response = await client.post(
                    f"{api_base_url}/ask",
                    json=payload,
                    timeout=45.0  # Generous timeout for CI
                )
                
                end_time = time.time()
                response_time = end_time - start_time
                
                assert response.status_code == 200, f"Performance test failed: {response.status_code}"
                
                # Response should be reasonably fast (under 30 seconds in CI)
                assert response_time < 30.0, f"Response too slow: {response_time:.2f}s"
                
                data = response.json()
                assert "answer" in data and data["answer"], "Performance test should return valid answer"
                
            except httpx.TimeoutException:
                pytest.fail("Ask endpoint timed out during performance test")
            except httpx.RequestError as e:
                pytest.fail(f"Performance test request failed: {e}")
    
    @pytest.mark.asyncio
    async def test_ask_endpoint_citation_quality(self, api_base_url):
        """Test citation quality and relevance"""
        question = "How can AI help with healthcare?"
        
        payload = {
            "question": question,
            "k": 5,
            "use_reranking": True,
            "include_sources": True
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{api_base_url}/ask",
                    json=payload,
                    timeout=30.0
                )
                
                assert response.status_code == 200, f"Citation test failed: {response.status_code}"
                
                data = response.json()
                citations = data.get("citations", [])
                
                assert len(citations) >= 1, "Should have at least 1 citation"
                
                # Check citation quality
                for i, citation in enumerate(citations):
                    assert "content" in citation, f"Citation {i} missing content"
                    assert citation["content"].strip(), f"Citation {i} has empty content"
                    assert len(citation["content"]) >= 10, f"Citation {i} content too short"
                    
                    # Should have either source or URL
                    has_source = "source" in citation and citation["source"]
                    has_url = "url" in citation and citation["url"]
                    assert has_source or has_url, f"Citation {i} missing source and URL"
                    
                    # Check for relevance score if available
                    if "score" in citation:
                        assert isinstance(citation["score"], (int, float)), f"Citation {i} invalid score type"
                        assert citation["score"] >= 0, f"Citation {i} negative score"
                        
            except httpx.RequestError as e:
                pytest.fail(f"Citation quality test failed: {e}")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
