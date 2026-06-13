"""Comprehensive tests for src/scraper/proxy_manager.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiohttp")

from scraper.proxy_manager import (  # noqa: E402
    ProxyConfig,
    ProxyRotationManager,
    ProxyStats,
)


def cfg(host="1.1.1.1", port=8080, **over):
    return ProxyConfig(host=host, port=port, **over)


class TestProxyStats:
    def test_success_rate_zero_requests(self):
        assert ProxyStats().success_rate == 0.0

    def test_success_rate(self):
        s = ProxyStats(total_requests=10, successful_requests=8)
        assert s.success_rate == 80.0

    def test_defaults(self):
        s = ProxyStats()
        assert s.is_healthy is True
        assert s.health_score == 100.0


class TestAddProxy:
    def test_add(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg())
        assert len(m.proxies) == 1
        assert "1.1.1.1:8080" in m.proxy_stats

    def test_no_duplicates(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg())
        m.add_proxy(cfg())
        assert len(m.proxies) == 1


class TestRotationStrategies:
    @pytest.mark.asyncio
    async def test_empty_returns_none(self):
        assert await ProxyRotationManager().get_proxy() is None

    @pytest.mark.asyncio
    async def test_round_robin_cycles(self):
        m = ProxyRotationManager(rotation_strategy="round_robin")
        m.add_proxy(cfg(host="a", port=1))
        m.add_proxy(cfg(host="b", port=2))
        first = await m.get_proxy()
        second = await m.get_proxy()
        third = await m.get_proxy()
        assert {first.host, second.host} == {"a", "b"}
        assert third.host == first.host  # cycled back

    @pytest.mark.asyncio
    async def test_random_strategy(self):
        m = ProxyRotationManager(rotation_strategy="random")
        m.add_proxy(cfg(host="a", port=1))
        proxy = await m.get_proxy()
        assert proxy.host == "a"

    @pytest.mark.asyncio
    async def test_health_based_picks_highest(self):
        m = ProxyRotationManager(rotation_strategy="health_based")
        m.add_proxy(cfg(host="low", port=1))
        m.add_proxy(cfg(host="high", port=2))
        m.proxy_stats["low:1"].health_score = 30.0
        m.proxy_stats["high:2"].health_score = 95.0
        proxy = await m.get_proxy()
        assert proxy.host == "high"

    @pytest.mark.asyncio
    async def test_unknown_strategy_falls_back(self):
        m = ProxyRotationManager(rotation_strategy="bogus")
        m.add_proxy(cfg(host="a", port=1))
        assert (await m.get_proxy()).host == "a"


class TestHealthCheck:
    def test_healthy_by_default(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg())
        assert m._is_proxy_healthy(cfg()) is True

    def test_unhealthy_when_marked(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg())
        m.proxy_stats["1.1.1.1:8080"].is_healthy = False
        assert m._is_proxy_healthy(cfg()) is False

    def test_unhealthy_at_connection_limit(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg(concurrent_limit=2))
        m.active_connections["1.1.1.1:8080"] = 2
        assert m._is_proxy_healthy(cfg(concurrent_limit=2)) is False


class TestRecordRequest:
    @pytest.mark.asyncio
    async def test_success_increases_health(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg())
        m.proxy_stats["1.1.1.1:8080"].health_score = 50.0
        await m.record_request(cfg(), success=True, response_time=0.5)
        stats = m.proxy_stats["1.1.1.1:8080"]
        assert stats.successful_requests == 1
        assert stats.health_score == 51.0
        assert stats.avg_response_time == 0.5

    @pytest.mark.asyncio
    async def test_failure_decreases_health(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg())
        await m.record_request(cfg(), success=False)
        stats = m.proxy_stats["1.1.1.1:8080"]
        assert stats.failed_requests == 1
        assert stats.consecutive_failures == 1
        assert stats.health_score == 95.0

    @pytest.mark.asyncio
    async def test_blocks_after_consecutive_failures(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg())
        for _ in range(5):
            await m.record_request(cfg(), success=False)
        assert m.proxy_stats["1.1.1.1:8080"].blocked_until > 0


class TestConnections:
    @pytest.mark.asyncio
    async def test_acquire_release(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg(concurrent_limit=2))
        assert await m.acquire_connection(cfg()) is True
        assert m.active_connections["1.1.1.1:8080"] == 1
        await m.release_connection(cfg())
        assert m.active_connections["1.1.1.1:8080"] == 0


class TestStatsAndCleanup:
    def test_get_proxy_stats(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg())
        stats = m.get_proxy_stats()
        assert "1.1.1.1:8080" in stats

    @pytest.mark.asyncio
    async def test_remove_unhealthy(self):
        m = ProxyRotationManager()
        m.add_proxy(cfg(host="good", port=1))
        m.add_proxy(cfg(host="bad", port=2))
        m.proxy_stats["bad:2"].health_score = 5.0
        await m.remove_unhealthy_proxies(min_health_score=20.0)
        hosts = {p.host for p in m.proxies}
        assert "good" in hosts
        assert "bad" not in hosts
