"""
Tests for Query Cache and Rate Limiting (Issue #240)
"""
import os
import time
import pytest
from fastapi.testclient import TestClient
from services.api.main import app, query_cache

client = TestClient(app)

@pytest.mark.asyncio
async def test_query_cache_basic():
    """Test that repeated identical queries return cached result faster."""
    payload = {
        "question": "What is the capital of France?",
        "k": 3,
        "filters": {},
        "rerank_on": True,
        "fusion": True,
        "provider": "openai"
    }
    # First request (should not be cached)
    t0 = time.time()
    r1 = client.post("/api/ask/", json=payload)
    t1 = time.time()
    assert r1.status_code == 200
    # Second request (should be cached)
    t2 = time.time()
    r2 = client.post("/api/ask/", json=payload)
    t3 = time.time()
    assert r2.status_code == 200
    # Cached response should be faster
    uncached_time = t1 - t0
    cached_time = t3 - t2
    print(f"Uncached: {uncached_time:.3f}s, Cached: {cached_time:.3f}s")
    assert cached_time < uncached_time
    # Response should indicate cache hit (tracked_in_mlflow False)
    assert r2.json()["tracked_in_mlflow"] is False

@pytest.mark.asyncio
async def test_rate_limit():
    """Test that rate limit returns 429 after exceeding limit."""
    # Set low rate limit for test
    os.environ["RATE_LIMIT"] = "3"
    os.environ["RATE_LIMIT_WINDOW"] = "5"
    # Send 4 requests quickly
    payload = {
        "question": "Test rate limit?",
        "k": 2,
        "filters": {},
        "rerank_on": True,
        "fusion": True,
        "provider": "openai"
    }
    responses = []
    for _ in range(4):
        resp = client.post("/api/ask/", json=payload)
        responses.append(resp)
        time.sleep(0.5)
    codes = [r.status_code for r in responses]
    print(f"Rate limit test status codes: {codes}")
    assert 429 in codes
    # Reset env
    del os.environ["RATE_LIMIT"]
    del os.environ["RATE_LIMIT_WINDOW"]
