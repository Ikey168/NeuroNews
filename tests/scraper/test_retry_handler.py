"""
Tests for retry handling functionality.
"""

import pytest
import asyncio
import aiohttp
from aioresponses import aioresponses
import time
from unittest.mock import Mock, AsyncMock

from src.scraper.retry_handler import (
    RetryHandler,
    RequestRetryHandler,
    RetryConfig,
    RetryState
)

# Test configurations
TEST_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=0.1,
    max_delay=1.0,
    exponential_backoff=2.0,
    jitter=0.1
)

@pytest.fixture
def retry_handler():
    """Create test retry handler."""
    return RetryHandler(TEST_CONFIG)

@pytest.fixture
def request_retry_handler():
    """Create test request retry handler."""
    return RequestRetryHandler(TEST_CONFIG)

@pytest.mark.asyncio
async def test_retry_async_success():
    """Test successful async retry."""
    handler = RetryHandler(TEST_CONFIG)
    
    # Function succeeds on first try
    async def test_func():
        return "success"
        
    result = await handler.retry_async(test_func)
    assert result == "success"

@pytest.mark.asyncio
async def test_retry_async_eventual_success():
    """Test retry with eventual success."""
    handler = RetryHandler(TEST_CONFIG)
    attempts = 0
    
    async def test_func():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionError("Test error")
        return "success"
        
    result = await handler.retry_async(test_func)
    assert result == "success"
    assert attempts == 2

@pytest.mark.asyncio
async def test_retry_async_max_retries():
    """Test maximum retry attempts."""
    handler = RetryHandler(TEST_CONFIG)
    attempts = 0
    
    async def test_func():
        nonlocal attempts
        attempts += 1
        raise ConnectionError("Test error")
        
    with pytest.raises(ConnectionError):
        await handler.retry_async(test_func)
        
    assert attempts == TEST_CONFIG.max_retries + 1

@pytest.mark.asyncio
async def test_retry_hooks():
    """Test retry hooks execution."""
    handler = RetryHandler(TEST_CONFIG)
    before_called = False
    after_called = False
    
    def before_hook(state: RetryState):
        nonlocal before_called
        before_called = True
        assert state.attempt > 0
        
    def after_hook(state: RetryState):
        nonlocal after_called
        after_called = True
        assert state.attempt > 0
        
    handler.add_before_retry_hook(before_hook)
    handler.add_after_retry_hook(after_hook)
    
    async def test_func():
        if not before_called:  # First attempt
            raise ConnectionError("Test error")
        return "success"
        
    result = await handler.retry_async(test_func)
    
    assert result == "success"
    assert before_called
    assert after_called

def test_retry_state():
    """Test retry state tracking."""
    state = RetryState(TEST_CONFIG)
    
    assert state.attempt == 0
    assert state.should_retry
    
    # Test delay calculation
    delays = [state.calculate_delay() for _ in range(3)]
    assert all(isinstance(d, float) for d in delays)
    assert delays[1] > delays[0]  # Exponential backoff
    
    # Test max retries
    state.attempt = TEST_CONFIG.max_retries
    assert not state.should_retry

@pytest.mark.asyncio
async def test_request_retry_handler():
    """Test HTTP request retry handling."""
    handler = RequestRetryHandler(TEST_CONFIG)
    url = "https://example.com/test"
    
    with aioresponses() as m:
        # Fail twice, succeed on third try
        m.get(url, status=500)
        m.get(url, status=503)
        m.get(url, status=200, payload={"status": "ok"})
        
        async with aiohttp.ClientSession() as session:
            response = await handler.retry_request(session, url)
            assert response.status == 200

@pytest.mark.asyncio
async def test_request_retry_different_errors():
    """Test retrying different types of failures."""
    handler = RequestRetryHandler(TEST_CONFIG)
    url = "https://example.com/test"
    
    with aioresponses() as m:
        # Test different error scenarios
        m.get(url, exception=aiohttp.ClientError())  # Network error
        m.get(url, status=429)  # Rate limit
        m.get(url, status=500)  # Server error
        m.get(url, status=200)  # Success
        
        async with aiohttp.ClientSession() as session:
            response = await handler.retry_request(session, url)
            assert response.status == 200

@pytest.mark.asyncio
async def test_retry_context():
    """Test retry context manager."""
    handler = RetryHandler(TEST_CONFIG)
    attempts = 0
    
    async def test_func():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionError("Test error")
        return "success"
        
    async with handler.retry_context(test_func) as result:
        assert result == "success"
        
    assert attempts == 2

@pytest.mark.asyncio
async def test_retry_delay_bounds():
    """Test retry delay boundaries."""
    config = RetryConfig(
        max_retries=5,
        base_delay=0.1,
        max_delay=1.0,
        exponential_backoff=10.0  # Large factor to test max_delay
    )
    handler = RetryHandler(config)
    state = RetryState(config)
    
    delays = []
    for _ in range(5):
        delay = state.calculate_delay()
        delays.append(delay)
        state.attempt += 1
        
    # Check delay bounds
    assert all(0 < d <= config.max_delay for d in delays)
    assert delays[-1] == config.max_delay  # Should hit max delay

@pytest.mark.asyncio
async def test_async_hooks():
    """Test async retry hooks."""
    handler = RetryHandler(TEST_CONFIG)
    hook_called = False
    
    async def async_hook(state: RetryState):
        nonlocal hook_called
        await asyncio.sleep(0.1)
        hook_called = True
        
    handler.add_before_retry_hook(async_hook)
    
    async def test_func():
        if not hook_called:
            raise ConnectionError("Test error")
        return "success"
        
    result = await handler.retry_async(test_func)
    assert result == "success"
    assert hook_called

@pytest.mark.asyncio
async def test_hook_error_handling():
    """Test error handling in hooks."""
    handler = RetryHandler(TEST_CONFIG)
    main_executed = False
    
    def failing_hook(state: RetryState):
        raise ValueError("Hook error")
        
    handler.add_before_retry_hook(failing_hook)
    
    async def test_func():
        nonlocal main_executed
        main_executed = True
        return "success"
        
    result = await handler.retry_async(test_func)
    
    # Main function should execute despite hook error
    assert result == "success"
    assert main_executed