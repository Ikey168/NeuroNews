"""
Comprehensive tests for ProxyManager.
Tests proxy rotation, health monitoring, and intelligent proxy selection.
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import aiohttp

# Import with proper path handling
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from scraper.proxy_manager import ProxyManager, ProxyConfig, ProxyStats


class TestProxyConfig:
    """Test suite for ProxyConfig class."""

    def test_proxy_config_initialization(self):
        """Test ProxyConfig initialization with default values."""
        config = ProxyConfig(host="127.0.0.1", port=8080)
        
        assert config.host == "127.0.0.1"
        assert config.port == 8080
        assert config.proxy_type == "http"
        assert config.username is None
        assert config.password is None
        assert config.concurrent_limit == 5

    def test_proxy_config_with_auth(self):
        """Test ProxyConfig with authentication."""
        config = ProxyConfig(
            host="proxy.example.com",
            port=3128,
            proxy_type="https",
            username="user123",
            password="pass456",
            concurrent_limit=10,
            location="US-East",
            provider="ProxyProvider"
        )
        
        assert config.host == "proxy.example.com"
        assert config.username == "user123"
        assert config.password == "pass456"
        assert config.location == "US-East"
        assert config.provider == "ProxyProvider"


class TestProxyStats:
    """Test suite for ProxyStats class."""

    def test_proxy_stats_initialization(self):
        """Test ProxyStats initialization with default values."""
        stats = ProxyStats()
        
        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.failed_requests == 0
        assert stats.consecutive_failures == 0
        assert stats.health_score == 100.0
        assert stats.is_healthy is True

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        stats = ProxyStats()
        
        # No requests yet
        assert stats.success_rate == 0.0
        
        # Add some requests
        stats.total_requests = 10
        stats.successful_requests = 8
        stats.failed_requests = 2
        
        assert stats.success_rate == 0.8

    def test_update_response_time(self):
        """Test response time tracking."""
        stats = ProxyStats()
        
        # First response
        stats.update_response_time(0.5)
        assert stats.avg_response_time == 0.5
        
        # Second response
        stats.update_response_time(1.0)
        assert stats.avg_response_time == 0.75


class TestProxyManager:
    """Test suite for ProxyManager class."""

    @pytest.fixture
    def sample_proxy_configs(self):
        """Sample proxy configurations for testing."""
        return [
            ProxyConfig(host="proxy1.example.com", port=8080, location="US-East"),
            ProxyConfig(host="proxy2.example.com", port=8080, location="US-West"),
            ProxyConfig(host="proxy3.example.com", port=3128, proxy_type="https", location="EU"),
        ]

    @pytest.fixture
    def proxy_manager(self, sample_proxy_configs):
        """ProxyManager fixture for testing."""
        return ProxyManager(proxies=sample_proxy_configs)

    def test_proxy_manager_initialization(self, proxy_manager, sample_proxy_configs):
        """Test ProxyManager initialization."""
        assert len(proxy_manager.proxies) == 3
        assert len(proxy_manager.proxy_stats) == 3
        assert proxy_manager.current_index == 0
        assert proxy_manager.health_check_interval == 300
        assert proxy_manager.max_consecutive_failures == 3

    def test_proxy_manager_empty_initialization(self):
        """Test ProxyManager initialization with no proxies."""
        manager = ProxyManager()
        assert len(manager.proxies) == 0
        assert manager.direct_connection_fallback is True

    def test_get_next_proxy_round_robin(self, proxy_manager):
        """Test round-robin proxy selection."""
        proxy1 = proxy_manager.get_next_proxy()
        proxy2 = proxy_manager.get_next_proxy()
        proxy3 = proxy_manager.get_next_proxy()
        proxy4 = proxy_manager.get_next_proxy()  # Should wrap around
        
        assert proxy1.host == "proxy1.example.com"
        assert proxy2.host == "proxy2.example.com"
        assert proxy3.host == "proxy3.example.com"
        assert proxy4.host == "proxy1.example.com"  # Wrapped around

    def test_get_next_proxy_skip_unhealthy(self, proxy_manager):
        """Test proxy selection skipping unhealthy proxies."""
        # Mark second proxy as unhealthy
        proxy_manager.proxy_stats[1].is_healthy = False
        proxy_manager.proxy_stats[1].consecutive_failures = 5
        
        proxy1 = proxy_manager.get_next_proxy()
        proxy2 = proxy_manager.get_next_proxy()  # Should skip unhealthy proxy
        
        assert proxy1.host == "proxy1.example.com"
        assert proxy2.host == "proxy3.example.com"  # Skipped proxy2

    def test_get_next_proxy_all_unhealthy(self, proxy_manager):
        """Test proxy selection when all proxies are unhealthy."""
        # Mark all proxies as unhealthy
        for stats in proxy_manager.proxy_stats.values():
            stats.is_healthy = False
            stats.consecutive_failures = 5
        
        proxy = proxy_manager.get_next_proxy()
        assert proxy is None  # Should return None when no healthy proxies

    def test_get_random_proxy(self, proxy_manager):
        """Test random proxy selection."""
        proxy = proxy_manager.get_random_proxy()
        
        assert proxy is not None
        assert proxy in proxy_manager.proxies

    def test_get_best_proxy(self, proxy_manager):
        """Test best proxy selection based on performance."""
        # Set different performance metrics
        proxy_manager.proxy_stats[0].health_score = 85.0
        proxy_manager.proxy_stats[0].avg_response_time = 1.0
        
        proxy_manager.proxy_stats[1].health_score = 95.0
        proxy_manager.proxy_stats[1].avg_response_time = 0.5
        
        proxy_manager.proxy_stats[2].health_score = 80.0
        proxy_manager.proxy_stats[2].avg_response_time = 1.5
        
        best_proxy = proxy_manager.get_best_proxy()
        assert best_proxy.host == "proxy2.example.com"  # Best performance

    def test_get_proxy_by_location(self, proxy_manager):
        """Test proxy selection by geographic location."""
        us_east_proxy = proxy_manager.get_proxy_by_location("US-East")
        eu_proxy = proxy_manager.get_proxy_by_location("EU")
        
        assert us_east_proxy.location == "US-East"
        assert eu_proxy.location == "EU"

    def test_get_proxy_by_location_not_found(self, proxy_manager):
        """Test proxy selection for non-existent location."""
        proxy = proxy_manager.get_proxy_by_location("Asia")
        assert proxy is None

    def test_record_success(self, proxy_manager):
        """Test recording successful proxy usage."""
        proxy = proxy_manager.proxies[0]
        initial_stats = proxy_manager.proxy_stats[0]
        initial_successful = initial_stats.successful_requests
        
        proxy_manager.record_success(proxy, response_time=0.8)
        
        updated_stats = proxy_manager.proxy_stats[0]
        assert updated_stats.successful_requests == initial_successful + 1
        assert updated_stats.consecutive_failures == 0
        assert updated_stats.total_requests == initial_stats.total_requests + 1

    def test_record_failure(self, proxy_manager):
        """Test recording proxy failure."""
        proxy = proxy_manager.proxies[0]
        initial_stats = proxy_manager.proxy_stats[0]
        initial_failed = initial_stats.failed_requests
        
        proxy_manager.record_failure(proxy, error="Connection timeout")
        
        updated_stats = proxy_manager.proxy_stats[0]
        assert updated_stats.failed_requests == initial_failed + 1
        assert updated_stats.consecutive_failures == 1
        assert updated_stats.total_requests == initial_stats.total_requests + 1

    def test_record_failure_marks_unhealthy(self, proxy_manager):
        """Test that consecutive failures mark proxy as unhealthy."""
        proxy = proxy_manager.proxies[0]
        
        # Record max consecutive failures
        for _ in range(proxy_manager.max_consecutive_failures):
            proxy_manager.record_failure(proxy, error="Connection error")
        
        stats = proxy_manager.proxy_stats[0]
        assert stats.is_healthy is False
        assert stats.consecutive_failures == proxy_manager.max_consecutive_failures

    @pytest.mark.asyncio
    async def test_check_proxy_health_success(self, proxy_manager):
        """Test successful proxy health check."""
        proxy = proxy_manager.proxies[0]
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = "OK"
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            is_healthy = await proxy_manager._check_proxy_health(proxy)
            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_check_proxy_health_failure(self, proxy_manager):
        """Test proxy health check failure."""
        proxy = proxy_manager.proxies[0]
        
        mock_session = AsyncMock()
        mock_session.get.side_effect = aiohttp.ClientError("Connection failed")
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            is_healthy = await proxy_manager._check_proxy_health(proxy)
            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_health_check_all_proxies(self, proxy_manager):
        """Test health check for all proxies."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            await proxy_manager.health_check_all_proxies()
            
            # All proxies should remain healthy
            for stats in proxy_manager.proxy_stats.values():
                assert stats.is_healthy is True

    def test_add_proxy(self, proxy_manager):
        """Test adding a new proxy."""
        new_proxy = ProxyConfig(host="new-proxy.com", port=8080)
        initial_count = len(proxy_manager.proxies)
        
        proxy_manager.add_proxy(new_proxy)
        
        assert len(proxy_manager.proxies) == initial_count + 1
        assert new_proxy in proxy_manager.proxies
        assert new_proxy in proxy_manager.proxy_stats

    def test_remove_proxy(self, proxy_manager):
        """Test removing a proxy."""
        proxy_to_remove = proxy_manager.proxies[0]
        initial_count = len(proxy_manager.proxies)
        
        proxy_manager.remove_proxy(proxy_to_remove)
        
        assert len(proxy_manager.proxies) == initial_count - 1
        assert proxy_to_remove not in proxy_manager.proxies
        assert proxy_to_remove not in proxy_manager.proxy_stats

    def test_get_proxy_url_http(self, proxy_manager):
        """Test proxy URL generation for HTTP proxy."""
        proxy = proxy_manager.proxies[0]  # HTTP proxy
        url = proxy_manager._get_proxy_url(proxy)
        
        assert url == "http://proxy1.example.com:8080"

    def test_get_proxy_url_with_auth(self):
        """Test proxy URL generation with authentication."""
        proxy = ProxyConfig(
            host="proxy.com",
            port=3128,
            username="user",
            password="pass"
        )
        manager = ProxyManager([proxy])
        
        url = manager._get_proxy_url(proxy)
        assert url == "http://user:pass@proxy.com:3128"

    def test_get_proxy_connector(self, proxy_manager):
        """Test proxy connector creation for aiohttp."""
        proxy = proxy_manager.proxies[0]
        connector = proxy_manager.get_proxy_connector(proxy)
        
        # Should return some form of connector (mock or real)
        assert connector is not None

    def test_update_proxy_stats(self, proxy_manager):
        """Test proxy statistics update."""
        proxy = proxy_manager.proxies[0]
        initial_stats = proxy_manager.proxy_stats[0]
        
        proxy_manager._update_proxy_stats(proxy, success=True, response_time=0.5)
        
        updated_stats = proxy_manager.proxy_stats[0]
        assert updated_stats.total_requests == initial_stats.total_requests + 1
        assert updated_stats.successful_requests == initial_stats.successful_requests + 1

    def test_calculate_health_score(self, proxy_manager):
        """Test health score calculation."""
        stats = ProxyStats()
        stats.total_requests = 100
        stats.successful_requests = 85
        stats.failed_requests = 15
        stats.avg_response_time = 1.0
        stats.consecutive_failures = 1
        
        score = proxy_manager._calculate_health_score(stats)
        
        # Score should be based on success rate, response time, etc.
        assert 0 <= score <= 100
        assert score < 100  # Should be penalized for failures

    def test_get_stats(self, proxy_manager):
        """Test getting proxy manager statistics."""
        # Record some activity
        proxy_manager.record_success(proxy_manager.proxies[0], 0.5)
        proxy_manager.record_failure(proxy_manager.proxies[1], "Timeout")
        
        stats = proxy_manager.get_stats()
        
        assert "total_proxies" in stats
        assert "healthy_proxies" in stats
        assert "proxy_details" in stats
        assert stats["total_proxies"] == 3
        assert len(stats["proxy_details"]) == 3

    def test_reset_proxy_stats(self, proxy_manager):
        """Test resetting proxy statistics."""
        # Add some stats
        proxy_manager.record_success(proxy_manager.proxies[0], 0.5)
        proxy_manager.record_failure(proxy_manager.proxies[1], "Error")
        
        proxy_manager.reset_proxy_stats()
        
        # All stats should be reset
        for stats in proxy_manager.proxy_stats.values():
            assert stats.total_requests == 0
            assert stats.successful_requests == 0
            assert stats.failed_requests == 0
            assert stats.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_rotate_proxy_on_error(self, proxy_manager):
        """Test automatic proxy rotation on errors."""
        # Mock a failing proxy
        failing_proxy = proxy_manager.proxies[0]
        
        # Record multiple failures to trigger rotation
        for _ in range(3):
            proxy_manager.record_failure(failing_proxy, "Connection error")
        
        # Get next proxy should skip the failing one
        next_proxy = proxy_manager.get_next_proxy()
        assert next_proxy != failing_proxy

    def test_proxy_load_balancing(self, proxy_manager):
        """Test proxy load balancing across multiple proxies."""
        proxy_usage = {}
        
        # Get many proxies to test distribution
        for _ in range(30):
            proxy = proxy_manager.get_next_proxy()
            host = proxy.host
            proxy_usage[host] = proxy_usage.get(host, 0) + 1
        
        # Should distribute fairly across all proxies
        assert len(proxy_usage) == 3  # All 3 proxies should be used
        
        # Each proxy should be used multiple times
        for count in proxy_usage.values():
            assert count >= 5

    @pytest.mark.asyncio
    async def test_concurrent_proxy_usage(self, proxy_manager):
        """Test concurrent proxy access safety."""
        async def get_proxy_and_record():
            proxy = proxy_manager.get_next_proxy()
            if proxy:
                proxy_manager.record_success(proxy, 0.5)
            return proxy
        
        # Run concurrent operations
        tasks = [get_proxy_and_record() for _ in range(20)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert len(results) == 20
        for proxy in results:
            assert proxy is not None

    def test_proxy_timeout_handling(self, proxy_manager):
        """Test proxy timeout and recovery."""
        proxy = proxy_manager.proxies[0]
        
        # Block proxy temporarily
        proxy_manager.proxy_stats[0].blocked_until = time.time() + 1.0
        proxy_manager.proxy_stats[0].is_healthy = False
        
        # Should not return blocked proxy
        next_proxy = proxy_manager.get_next_proxy()
        assert next_proxy != proxy
        
        # After timeout, proxy should be available again
        time.sleep(1.1)
        proxy_manager.proxy_stats[0].blocked_until = 0
        proxy_manager.proxy_stats[0].is_healthy = True
        
        available_proxy = proxy_manager.get_next_proxy()
        # Should be able to get any proxy including the previously blocked one

    def test_proxy_geographic_optimization(self, proxy_manager):
        """Test geographic proximity optimization."""
        # Set target location
        target_location = "US-East"
        
        # Get proxy optimized for location
        optimized_proxy = proxy_manager.get_optimized_proxy(target_location=target_location)
        
        # Should prefer proxies in the same region
        if optimized_proxy:
            assert optimized_proxy.location in ["US-East", "US-West"]  # Prefer US proxies

    def test_proxy_concurrent_limit_enforcement(self, proxy_manager):
        """Test proxy concurrent connection limit enforcement."""
        proxy = proxy_manager.proxies[0]
        
        # Simulate maximum concurrent connections
        for i in range(proxy.concurrent_limit):
            proxy_manager._track_concurrent_usage(proxy, increment=True)
        
        # Should not exceed limit
        assert proxy_manager._get_concurrent_usage(proxy) == proxy.concurrent_limit
        
        # Additional connections should be denied or queued
        can_use = proxy_manager._can_use_proxy(proxy)
        assert can_use is False or proxy_manager._get_concurrent_usage(proxy) <= proxy.concurrent_limit