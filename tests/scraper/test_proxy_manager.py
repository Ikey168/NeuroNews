"""
Tests for proxy rotation and user-agent management.
"""

import pytest
import asyncio
import aiohttp
from aioresponses import aioresponses
import json
import time
from pathlib import Path
import tempfile
import os
from unittest.mock import patch, MagicMock

from src.scraper.proxy_manager import (
    ProxyRotator,
    UserAgentRotator,
    RequestManager,
    ProxyStats
)

# Test data
TEST_PROXIES = [
    'http://proxy1.example.com:8080',
    'http://proxy2.example.com:8080',
    'http://proxy3.example.com:8080'
]

TEST_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Firefox/89.0'
]

@pytest.fixture
def proxy_file():
    """Create temporary proxy list file."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        json.dump(TEST_PROXIES, f)
        return f.name

@pytest.fixture
def proxy_rotator(proxy_file):
    """Create test proxy rotator."""
    return ProxyRotator(
        proxy_file=proxy_file,
        min_success_rate=0.5,
        ban_threshold=2,
        ban_duration=60
    )

@pytest.fixture
def user_agent_rotator():
    """Create test user agent rotator."""
    return UserAgentRotator(custom_agents=TEST_USER_AGENTS)

@pytest.fixture
def request_manager(proxy_rotator, user_agent_rotator):
    """Create test request manager."""
    return RequestManager(proxy_rotator, user_agent_rotator)

@pytest.mark.asyncio
async def test_load_proxies(proxy_rotator):
    """Test loading proxies from file."""
    await proxy_rotator.load_proxies()
    assert len(proxy_rotator.proxies) == len(TEST_PROXIES)
    for proxy in TEST_PROXIES:
        assert proxy in proxy_rotator.proxies

@pytest.mark.asyncio
async def test_load_proxies_from_aws():
    """Test loading proxies from AWS Secrets Manager."""
    mock_secret = {'SecretString': json.dumps(TEST_PROXIES)}
    
    with patch('boto3.client') as mock_client:
        mock_client.return_value.get_secret_value.return_value = mock_secret
        
        rotator = ProxyRotator()
        await rotator.load_proxies()
        
        assert len(rotator.proxies) == len(TEST_PROXIES)
        mock_client.return_value.get_secret_value.assert_called_with(
            SecretId='proxy-list'
        )

@pytest.mark.asyncio
async def test_proxy_selection(proxy_rotator):
    """Test proxy selection algorithm."""
    await proxy_rotator.load_proxies()
    
    # Report some successes and failures
    proxy_rotator.report_success(TEST_PROXIES[0], 0.5)
    proxy_rotator.report_success(TEST_PROXIES[0], 0.6)
    proxy_rotator.report_failure(TEST_PROXIES[1])
    
    # Get proxy multiple times
    selected_proxies = set()
    for _ in range(10):
        proxy = await proxy_rotator.get_proxy()
        selected_proxies.add(proxy)
    
    # Should prefer successful proxy but still use others
    assert TEST_PROXIES[0] in selected_proxies
    assert len(selected_proxies) > 1

def test_proxy_stats():
    """Test proxy statistics tracking."""
    stats = ProxyStats()
    
    # Test success rate calculation
    stats.success_count = 8
    stats.failure_count = 2
    assert stats.success_rate == 0.8
    
    # Test new proxy
    new_stats = ProxyStats()
    assert new_stats.success_rate == 0

@pytest.mark.asyncio
async def test_proxy_banning(proxy_rotator):
    """Test proxy banning mechanism."""
    await proxy_rotator.load_proxies()
    proxy = TEST_PROXIES[0]
    
    # Report failures up to threshold
    for _ in range(proxy_rotator.ban_threshold):
        proxy_rotator.report_failure(proxy)
    
    # Proxy should be banned
    stats = proxy_rotator.proxies[proxy]
    assert stats.banned_until is not None
    assert stats.banned_until > time.time()
    
    # Banned proxy should not be selected
    selected_proxy = await proxy_rotator.get_proxy()
    assert selected_proxy != proxy

def test_user_agent_rotation(user_agent_rotator):
    """Test user agent rotation."""
    # Get multiple user agents
    agents = set()
    for _ in range(10):
        agent = user_agent_rotator.get_random_agent()
        agents.add(agent)
        
    # Should use all available agents
    assert agents == set(TEST_USER_AGENTS)
    
    # Check usage tracking
    for agent in TEST_USER_AGENTS:
        assert user_agent_rotator.usage_counts[agent] > 0

@pytest.mark.asyncio
async def test_request_manager(request_manager):
    """Test request manager integration."""
    url = 'https://example.com'
    
    with aioresponses() as m:
        # Mock successful request
        m.get(url, status=200, body='Success')
        
        async with (await request_manager.get_session())[0] as session:
            async with session.get(url) as response:
                assert response.status == 200
                
                # Check headers
                headers = dict(response.request_info.headers)
                assert 'User-Agent' in headers
                assert headers['User-Agent'] in TEST_USER_AGENTS

@pytest.mark.asyncio
async def test_request_retries(request_manager):
    """Test request retry behavior."""
    url = 'https://example.com'
    
    with aioresponses() as m:
        # Mock failed requests then success
        m.get(url, status=403)  # Banned
        m.get(url, status=429)  # Rate limited
        m.get(url, status=200, body='Success')
        
        response = await request_manager.make_request(url)
        assert response is not None
        assert response.status == 200

@pytest.mark.asyncio
async def test_concurrent_requests(request_manager):
    """Test concurrent request handling."""
    urls = [f'https://example.com/{i}' for i in range(5)]
    
    with aioresponses() as m:
        for url in urls:
            m.get(url, status=200, body='Success')
            
        tasks = [request_manager.make_request(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        
        assert all(r is not None and r.status == 200 for r in responses)

@pytest.mark.asyncio
async def test_proxy_cleanup(request_manager):
    """Test proxy/session cleanup."""
    url = 'https://example.com'
    
    with aioresponses() as m:
        m.get(url, status=200, body='Success')
        
        # Create and use session
        session, proxy = await request_manager.get_session()
        async with session:
            async with session.get(url) as response:
                assert response.status == 200
        
        # Session should be closed
        assert session.closed

@pytest.mark.asyncio
async def test_error_handling(request_manager):
    """Test error handling in requests."""
    url = 'https://example.com'
    
    with aioresponses() as m:
        # Mock network error
        m.get(url, exception=aiohttp.ClientError())
        
        response = await request_manager.make_request(url)
        assert response is None  # Should handle error gracefully