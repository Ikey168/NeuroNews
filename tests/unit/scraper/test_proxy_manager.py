"""
Tests for the proxy rotation subsystem in ``scraper.proxy_manager``.

The module exposes ``ProxyConfig`` (a proxy definition), ``ProxyStats`` (per
proxy statistics) and ``ProxyRotationManager`` (rotation, health tracking and
load balancing across proxies). These tests exercise that real public API.
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import aiohttp

# Import with proper path handling.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

try:
    from scraper.proxy_manager import (
        ProxyConfig,
        ProxyStats,
        ProxyRotationManager,
    )
except ImportError as _e:  # stale or optional dependency
    pytest.skip("module import failed: {0}".format(_e), allow_module_level=True)


def _key(proxy: ProxyConfig) -> str:
    return "{0}:{1}".format(proxy.host, proxy.port)


class TestProxyConfig:
    """Test suite for ProxyConfig dataclass."""

    def test_proxy_config_initialization(self):
        config = ProxyConfig(host="127.0.0.1", port=8080)

        assert config.host == "127.0.0.1"
        assert config.port == 8080
        assert config.proxy_type == "http"
        assert config.username is None
        assert config.password is None
        assert config.concurrent_limit == 5

    def test_proxy_config_with_auth(self):
        config = ProxyConfig(
            host="proxy.example.com",
            port=3128,
            proxy_type="https",
            username="user123",
            password="pass456",
            concurrent_limit=10,
            location="US-East",
            provider="ProxyProvider",
        )

        assert config.host == "proxy.example.com"
        assert config.proxy_type == "https"
        assert config.username == "user123"
        assert config.password == "pass456"
        assert config.concurrent_limit == 10
        assert config.location == "US-East"
        assert config.provider == "ProxyProvider"


class TestProxyStats:
    """Test suite for ProxyStats dataclass."""

    def test_proxy_stats_initialization(self):
        stats = ProxyStats()

        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.failed_requests == 0
        assert stats.consecutive_failures == 0
        assert stats.health_score == 100.0
        assert stats.is_healthy is True
        assert stats.blocked_until == 0.0

    def test_success_rate_zero_when_no_requests(self):
        stats = ProxyStats()
        assert stats.success_rate == 0.0

    def test_success_rate_is_percentage(self):
        stats = ProxyStats()
        stats.total_requests = 10
        stats.successful_requests = 8
        stats.failed_requests = 2

        # success_rate is expressed as a percentage.
        assert stats.success_rate == 80.0


class TestProxyRotationManager:
    """Test suite for ProxyRotationManager."""

    @pytest.fixture
    def sample_proxy_configs(self):
        return [
            ProxyConfig(host="proxy1.example.com", port=8080, location="US-East"),
            ProxyConfig(host="proxy2.example.com", port=8080, location="US-West"),
            ProxyConfig(
                host="proxy3.example.com",
                port=3128,
                proxy_type="https",
                location="EU",
            ),
        ]

    @pytest.fixture
    def proxy_manager(self, sample_proxy_configs):
        manager = ProxyRotationManager(rotation_strategy="round_robin")
        for proxy in sample_proxy_configs:
            manager.add_proxy(proxy)
        return manager

    def test_initialization_empty(self):
        manager = ProxyRotationManager()
        assert manager.proxies == []
        assert manager.proxy_stats == {}
        assert manager.current_index == 0
        assert manager.health_check_interval == 300
        assert manager.rotation_strategy == "round_robin"

    def test_add_proxy_registers_stats(self, proxy_manager, sample_proxy_configs):
        assert len(proxy_manager.proxies) == 3
        assert len(proxy_manager.proxy_stats) == 3
        for proxy in sample_proxy_configs:
            assert _key(proxy) in proxy_manager.proxy_stats

    def test_add_proxy_deduplicates(self, proxy_manager):
        dup = ProxyConfig(host="proxy1.example.com", port=8080)
        proxy_manager.add_proxy(dup)
        assert len(proxy_manager.proxies) == 3  # unchanged

    @pytest.mark.asyncio
    async def test_get_proxy_round_robin(self, proxy_manager):
        p1 = await proxy_manager.get_proxy()
        p2 = await proxy_manager.get_proxy()
        p3 = await proxy_manager.get_proxy()
        p4 = await proxy_manager.get_proxy()  # wraps around

        assert p1.host == "proxy1.example.com"
        assert p2.host == "proxy2.example.com"
        assert p3.host == "proxy3.example.com"
        assert p4.host == "proxy1.example.com"

    @pytest.mark.asyncio
    async def test_get_proxy_none_when_empty(self):
        manager = ProxyRotationManager()
        assert await manager.get_proxy() is None

    @pytest.mark.asyncio
    async def test_get_proxy_skips_unhealthy(self, proxy_manager, sample_proxy_configs):
        # Mark the second proxy unhealthy.
        proxy_manager.proxy_stats[_key(sample_proxy_configs[1])].is_healthy = False

        hosts = set()
        for _ in range(6):
            proxy = await proxy_manager.get_proxy()
            hosts.add(proxy.host)

        assert "proxy2.example.com" not in hosts
        assert "proxy1.example.com" in hosts
        assert "proxy3.example.com" in hosts

    @pytest.mark.asyncio
    async def test_random_strategy_returns_known_proxy(self, sample_proxy_configs):
        manager = ProxyRotationManager(rotation_strategy="random")
        for proxy in sample_proxy_configs:
            manager.add_proxy(proxy)

        proxy = await manager.get_proxy()
        assert proxy in manager.proxies

    @pytest.mark.asyncio
    async def test_health_based_strategy_picks_highest_score(
        self, sample_proxy_configs
    ):
        manager = ProxyRotationManager(rotation_strategy="health_based")
        for proxy in sample_proxy_configs:
            manager.add_proxy(proxy)

        manager.proxy_stats[_key(sample_proxy_configs[0])].health_score = 85.0
        manager.proxy_stats[_key(sample_proxy_configs[1])].health_score = 95.0
        manager.proxy_stats[_key(sample_proxy_configs[2])].health_score = 80.0

        best = await manager.get_proxy()
        assert best.host == "proxy2.example.com"

    @pytest.mark.asyncio
    async def test_record_request_success(self, proxy_manager, sample_proxy_configs):
        proxy = sample_proxy_configs[0]
        stats = proxy_manager.proxy_stats[_key(proxy)]

        await proxy_manager.record_request(proxy, success=True, response_time=0.8)

        assert stats.total_requests == 1
        assert stats.successful_requests == 1
        assert stats.consecutive_failures == 0
        assert stats.avg_response_time == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_record_request_failure(self, proxy_manager, sample_proxy_configs):
        proxy = sample_proxy_configs[0]
        stats = proxy_manager.proxy_stats[_key(proxy)]

        await proxy_manager.record_request(proxy, success=False)

        assert stats.failed_requests == 1
        assert stats.consecutive_failures == 1
        assert stats.total_requests == 1
        assert stats.health_score < 100.0

    @pytest.mark.asyncio
    async def test_consecutive_failures_block_proxy(
        self, proxy_manager, sample_proxy_configs
    ):
        proxy = sample_proxy_configs[0]
        stats = proxy_manager.proxy_stats[_key(proxy)]

        for _ in range(5):
            await proxy_manager.record_request(proxy, success=False)

        assert stats.consecutive_failures == 5
        assert stats.blocked_until > time.time()

    @pytest.mark.asyncio
    async def test_check_proxy_health_success(self, proxy_manager, sample_proxy_configs):
        proxy = sample_proxy_configs[0]

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"origin": "1.2.3.4"}

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            healthy = await proxy_manager.check_proxy_health(proxy)
            assert healthy is True

    @pytest.mark.asyncio
    async def test_check_proxy_health_failure(self, proxy_manager, sample_proxy_configs):
        proxy = sample_proxy_configs[0]

        with patch(
            "aiohttp.ClientSession",
            side_effect=aiohttp.ClientError("Connection failed"),
        ):
            healthy = await proxy_manager.check_proxy_health(proxy)
            assert healthy is False

    @pytest.mark.asyncio
    async def test_health_check_all_marks_healthy(
        self, proxy_manager, sample_proxy_configs
    ):
        with patch.object(
            proxy_manager, "check_proxy_health", new=AsyncMock(return_value=True)
        ):
            await proxy_manager.health_check_all()

        for stats in proxy_manager.proxy_stats.values():
            assert stats.is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_all_marks_unhealthy(
        self, proxy_manager, sample_proxy_configs
    ):
        with patch.object(
            proxy_manager, "check_proxy_health", new=AsyncMock(return_value=False)
        ):
            await proxy_manager.health_check_all()

        for stats in proxy_manager.proxy_stats.values():
            assert stats.is_healthy is False

    @pytest.mark.asyncio
    async def test_acquire_and_release_connection(
        self, proxy_manager, sample_proxy_configs
    ):
        proxy = sample_proxy_configs[0]
        key = _key(proxy)

        # Fill up to the concurrent limit.
        for _ in range(proxy.concurrent_limit):
            assert await proxy_manager.acquire_connection(proxy) is True

        assert proxy_manager.active_connections[key] == proxy.concurrent_limit
        # Over the limit is denied.
        assert await proxy_manager.acquire_connection(proxy) is False

        await proxy_manager.release_connection(proxy)
        assert proxy_manager.active_connections[key] == proxy.concurrent_limit - 1

    @pytest.mark.asyncio
    async def test_is_proxy_healthy_respects_concurrent_limit(
        self, proxy_manager, sample_proxy_configs
    ):
        proxy = sample_proxy_configs[0]
        key = _key(proxy)

        assert proxy_manager._is_proxy_healthy(proxy) is True
        proxy_manager.active_connections[key] = proxy.concurrent_limit
        assert proxy_manager._is_proxy_healthy(proxy) is False

    def test_get_proxy_stats_reports_all(self, proxy_manager):
        stats = proxy_manager.get_proxy_stats()
        assert len(stats) == 3
        for entry in stats.values():
            assert "total_requests" in entry
            assert "success_rate" in entry
            assert "is_healthy" in entry
            assert "health_score" in entry

    @pytest.mark.asyncio
    async def test_remove_unhealthy_proxies(self, proxy_manager, sample_proxy_configs):
        # Drive one proxy's health score below the removal threshold.
        proxy = sample_proxy_configs[0]
        proxy_manager.proxy_stats[_key(proxy)].health_score = 5.0

        removed = await proxy_manager.remove_unhealthy_proxies(min_health_score=20.0)

        assert removed == 1
        assert proxy not in proxy_manager.proxies
        assert _key(proxy) not in proxy_manager.proxy_stats

    @pytest.mark.asyncio
    async def test_load_balancing_distribution(self, proxy_manager):
        usage = {}
        for _ in range(30):
            proxy = await proxy_manager.get_proxy()
            usage[proxy.host] = usage.get(proxy.host, 0) + 1

        assert len(usage) == 3
        for count in usage.values():
            assert count >= 5

    @pytest.mark.asyncio
    async def test_concurrent_get_proxy_is_safe(self, proxy_manager):
        async def one():
            proxy = await proxy_manager.get_proxy()
            if proxy is not None:
                await proxy_manager.record_request(proxy, success=True, response_time=0.5)
            return proxy

        results = await asyncio.gather(*[one() for _ in range(20)])
        assert len(results) == 20
        assert all(r is not None for r in results)
