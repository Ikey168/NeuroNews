"""
Proxy rotation and management system for NeuroNews scraper.
Provides intelligent proxy rotation, health monitoring, and anti-detection features.
"""

import asyncio
import json
import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp


@dataclass
class ProxyConfig:
    """Configuration for a single proxy."""

    host: str
    port: int
    proxy_type: str = "http"  # http, https, socks4, socks5
    username: Optional[str] = None
    password: Optional[str] = None
    concurrent_limit: int = 5
    location: Optional[str] = None
    provider: Optional[str] = None


@dataclass
class ProxyStats:
    """Statistics tracking for a proxy."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    last_used: float = 0.0
    avg_response_time: float = 0.0
    health_score: float = 100.0
    is_healthy: bool = True
    blocked_until: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100


class ProxyRotationManager:
    """Manages proxy rotation with health monitoring and load balancing."""

    def __init__(
        self, config_path: Optional[str] = None, rotation_strategy: str = "round_robin"
    ):
        self.config_path = config_path
        self.rotation_strategy = rotation_strategy
        self.proxies: List[ProxyConfig] = []
        self.proxy_stats: Dict[str, ProxyStats] = {}
        self.active_connections: Dict[str, int] = defaultdict(int)
        self.current_index = 0
        self.health_check_interval = 300  # 5 minutes
        self._lock = asyncio.Lock()

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # Load configuration if provided
        if config_path:
            self._load_config()

    def _load_config(self):
        """Load proxy configuration from JSON file."""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)

            # Load proxy settings
            proxy_settings = config.get("proxy_settings", {})
            self.rotation_strategy = proxy_settings.get(
                "rotation_strategy", "round_robin"
            )
            self.health_check_interval = proxy_settings.get(
                "health_check_interval", 300
            )

            # Load proxies
            for proxy_data in config.get("proxies", []):
                proxy = ProxyConfig(**proxy_data)
                self.proxies.append(proxy)

                # Initialize stats and connection tracking
                proxy_key = f"{proxy.host}:{proxy.port}"
                self.proxy_stats[proxy_key] = ProxyStats()
                self.active_connections[proxy_key] = 0

            self.logger.info(f"Loaded {len(self.proxies)} proxies from config")

        except Exception as e:
            self.logger.error(f"Error loading proxy config: {e}")

    def add_proxy(self, proxy: ProxyConfig):
        """Add a proxy to the rotation pool."""
        proxy_key = f"{proxy.host}:{proxy.port}"
        if proxy_key not in [f"{p.host}:{p.port}" for p in self.proxies]:
            self.proxies.append(proxy)
            self.proxy_stats[proxy_key] = ProxyStats()
            self.logger.info(f"Added proxy: {proxy_key}")

    async def get_proxy(self) -> Optional[ProxyConfig]:
        """Get next proxy based on rotation strategy."""
        async with self._lock:
            if not self.proxies:
                return None

            if self.rotation_strategy == "round_robin":
                return self._get_round_robin_proxy()
            elif self.rotation_strategy == "random":
                return self._get_random_proxy()
            elif self.rotation_strategy == "health_based":
                return self._get_health_based_proxy()
            else:
                return self._get_round_robin_proxy()

    def _get_round_robin_proxy(self) -> Optional[ProxyConfig]:
        """Get proxy using round-robin strategy."""
        healthy_proxies = [p for p in self.proxies if self._is_proxy_healthy(p)]
        if not healthy_proxies:
            # Fallback to any available proxy
            healthy_proxies = self.proxies

        if healthy_proxies:
            proxy = healthy_proxies[self.current_index % len(healthy_proxies)]
            self.current_index = (self.current_index + 1) % len(healthy_proxies)
            return proxy
        return None

    def _get_random_proxy(self) -> Optional[ProxyConfig]:
        """Get proxy using random strategy."""
        healthy_proxies = [p for p in self.proxies if self._is_proxy_healthy(p)]
        if not healthy_proxies:
            healthy_proxies = self.proxies

        return random.choice(healthy_proxies) if healthy_proxies else None

    def _get_health_based_proxy(self) -> Optional[ProxyConfig]:
        """Get proxy based on health score."""
        healthy_proxies = [p for p in self.proxies if self._is_proxy_healthy(p)]
        if not healthy_proxies:
            return None

        # Sort by health score and select best performing
        proxy_scores = []
        for proxy in healthy_proxies:
            key = f"{proxy.host}:{proxy.port}"
            stats = self.proxy_stats.get(key, ProxyStats())
            proxy_scores.append((proxy, stats.health_score))

        proxy_scores.sort(key=lambda x: x[1], reverse=True)
        return proxy_scores[0][0] if proxy_scores else None

    def _is_proxy_healthy(self, proxy: ProxyConfig) -> bool:
        """Check if proxy is healthy for use."""
        key = f"{proxy.host}:{proxy.port}"
        stats = self.proxy_stats.get(key, ProxyStats())
        return (
            stats.is_healthy and self.active_connections[key] < proxy.concurrent_limit
        )

    async def record_request(
        self, proxy: ProxyConfig, success: bool, response_time: float = 0.0
    ):
        """Record proxy usage statistics."""
        key = f"{proxy.host}:{proxy.port}"
        stats = self.proxy_stats.get(key, ProxyStats())

        stats.total_requests += 1
        if success:
            stats.successful_requests += 1
            stats.consecutive_failures = 0
            # Update health score positively
            stats.health_score = min(100.0, stats.health_score + 1.0)
        else:
            stats.failed_requests += 1
            stats.consecutive_failures += 1
            # Decrease health score
            stats.health_score = max(0.0, stats.health_score - 5.0)

            # Block proxy if too many consecutive failures
            if stats.consecutive_failures >= 5:
                stats.blocked_until = time.time() + 300  # Block for 5 minutes
                self.logger.warning(f"Proxy {key} blocked due to consecutive failures")

        # Update average response time
        if response_time > 0:
            total_time = (
                stats.avg_response_time * (stats.total_requests - 1) + response_time
            )
            stats.avg_response_time = total_time / stats.total_requests

        stats.last_used = time.time()
        self.proxy_stats[key] = stats

    async def check_proxy_health(self, proxy: ProxyConfig) -> bool:
        """Check if a proxy is accessible and working."""
        key = f"{proxy.host}:{proxy.port}"
        try:
            # Test proxy with a simple HTTP request
            proxy_url = f"{proxy.proxy_type}://{proxy.host}:{proxy.port}"

            connector = aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(total=10)

            async with aiohttp.ClientSession(
                connector=connector, timeout=timeout
            ) as session:
                async with session.get(
                    "http://httpbin.org/ip",
                    proxy=proxy_url,
                    proxy_auth=(
                        aiohttp.BasicAuth(proxy.username, proxy.password)
                        if proxy.username
                        else None
                    ),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.debug(
                            f"Proxy {key} health check passed: {data.get('origin')}"
                        )
                        return True
                    else:
                        self.logger.warning(
                            f"Proxy {key} returned status {response.status}"
                        )
                        return False

        except Exception as e:
            self.logger.warning(f"Proxy {key} health check failed: {e}")
            return False

    async def health_check_all(self):
        """Perform health check on all proxies."""
        self.logger.info("Starting proxy health check")
        tasks = []

        for proxy in self.proxies:
            task = self.check_proxy_health(proxy)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for proxy, result in zip(self.proxies, results):
            key = f"{proxy.host}:{proxy.port}"
            stats = self.proxy_stats.get(key, ProxyStats())

            if isinstance(result, bool) and result:
                stats.is_healthy = True
                stats.health_score = min(100.0, stats.health_score + 5.0)
            else:
                stats.is_healthy = False
                stats.health_score = max(0.0, stats.health_score - 10.0)

            self.proxy_stats[key] = stats

        healthy_count = sum(
            1 for stats in self.proxy_stats.values() if stats.is_healthy
        )
        self.logger.info(
            f"Health check complete: {healthy_count}/{len(self.proxies)} proxies healthy"
        )

    async def start_health_monitor(self):
        """Start background health monitoring."""
        if self.health_check_interval > 0:
            self.logger.info(
                f"Starting proxy health monitor (interval: {self.health_check_interval}s)"
            )
            while True:
                try:
                    await self.health_check_all()
                    await asyncio.sleep(self.health_check_interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"Error in health monitor: {e}")
                    await asyncio.sleep(60)  # Wait 1 minute before retry

    async def acquire_connection(self, proxy: ProxyConfig) -> bool:
        """Acquire a connection slot for the proxy."""
        key = f"{proxy.host}:{proxy.port}"
        async with self._lock:
            if self.active_connections[key] < proxy.concurrent_limit:
                self.active_connections[key] += 1
                return True
            return False

    async def release_connection(self, proxy: ProxyConfig):
        """Release a connection slot for the proxy."""
        key = f"{proxy.host}:{proxy.port}"
        async with self._lock:
            if self.active_connections[key] > 0:
                self.active_connections[key] -= 1

    def get_proxy_stats(self) -> Dict[str, Dict]:
        """Get statistics for all proxies."""
        stats = {}
        for proxy in self.proxies:
            key = f"{proxy.host}:{proxy.port}"
            proxy_stats = self.proxy_stats.get(key, ProxyStats())
            stats[key] = {
                "total_requests": proxy_stats.total_requests,
                "successful_requests": proxy_stats.successful_requests,
                "failed_requests": proxy_stats.failed_requests,
                "success_rate": proxy_stats.success_rate,
                "health_score": proxy_stats.health_score,
                "is_healthy": proxy_stats.is_healthy,
                "avg_response_time": proxy_stats.avg_response_time,
                "active_connections": self.active_connections[key],
                "last_used": proxy_stats.last_used,
                "blocked_until": proxy_stats.blocked_until,
            }
        return stats

    async def remove_unhealthy_proxies(self, min_health_score: float = 20.0):
        """Remove proxies below minimum health threshold."""
        removed_count = 0
        proxies_to_remove = []

        for proxy in self.proxies:
            key = f"{proxy.host}:{proxy.port}"
            stats = self.proxy_stats.get(key, ProxyStats())

            if stats.health_score < min_health_score:
                proxies_to_remove.append(proxy)
                removed_count += 1

        for proxy in proxies_to_remove:
            self.proxies.remove(proxy)
            key = f"{proxy.host}:{proxy.port}"
            del self.proxy_stats[key]
            del self.active_connections[key]

        if removed_count > 0:
            self.logger.info(f"Removed {removed_count} unhealthy proxies")

        return removed_count
