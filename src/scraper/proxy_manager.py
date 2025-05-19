"""
Proxy rotation and user-agent management for scraping.
"""

import aiohttp
import random
import asyncio
from typing import List, Dict, Optional, Set, Tuple
import logging
from datetime import datetime, timedelta
import json
from pathlib import Path
import aiofiles
from dataclasses import dataclass
import time
import collections
import boto3
from aiohttp import TCPConnector

logger = logging.getLogger(__name__)

@dataclass
class ProxyStats:
    """Statistics for proxy performance."""
    success_count: int = 0
    failure_count: int = 0
    last_used: float = 0
    last_success: float = 0
    avg_response_time: float = 0
    banned_until: Optional[float] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0

class ProxyRotator:
    """Manage proxy rotation and health monitoring."""
    
    def __init__(
        self,
        proxy_file: Optional[str] = None,
        min_success_rate: float = 0.7,
        ban_threshold: int = 3,
        ban_duration: int = 300  # 5 minutes
    ):
        """
        Initialize proxy rotator.
        
        Args:
            proxy_file: Path to proxy list file
            min_success_rate: Minimum acceptable success rate
            ban_threshold: Consecutive failures before banning
            ban_duration: Ban duration in seconds
        """
        self.proxies: Dict[str, ProxyStats] = {}
        self.proxy_file = proxy_file
        self.min_success_rate = min_success_rate
        self.ban_threshold = ban_threshold
        self.ban_duration = ban_duration
        self.consecutive_failures: Dict[str, int] = collections.defaultdict(int)
        self._lock = asyncio.Lock()

    async def load_proxies(self) -> None:
        """Load proxies from file or AWS Secrets Manager."""
        if self.proxy_file and Path(self.proxy_file).exists():
            async with aiofiles.open(self.proxy_file) as f:
                content = await f.read()
                proxy_list = json.loads(content)
        else:
            # Load from AWS Secrets Manager
            client = boto3.client('secretsmanager')
            response = client.get_secret_value(SecretId='proxy-list')
            proxy_list = json.loads(response['SecretString'])
        
        for proxy in proxy_list:
            self.proxies[proxy] = ProxyStats()

    async def get_proxy(self) -> Optional[str]:
        """
        Get next available proxy.
        
        Returns:
            Proxy URL or None if none available
        """
        async with self._lock:
            current_time = time.time()
            available_proxies = [
                proxy for proxy, stats in self.proxies.items()
                if (stats.success_rate >= self.min_success_rate or stats.success_count < 10) and
                (stats.banned_until is None or current_time > stats.banned_until)
            ]
            
            if not available_proxies:
                return None
                
            # Prioritize proxies with higher success rates
            weighted_proxies = [
                (proxy, self.proxies[proxy].success_rate)
                for proxy in available_proxies
            ]
            total_weight = sum(weight for _, weight in weighted_proxies)
            
            if total_weight == 0:
                return random.choice(available_proxies)
                
            # Weighted random selection
            r = random.uniform(0, total_weight)
            current = 0
            for proxy, weight in weighted_proxies:
                current += weight
                if r <= current:
                    return proxy
                    
            return available_proxies[0]

    def report_success(self, proxy: str, response_time: float) -> None:
        """
        Report successful proxy use.
        
        Args:
            proxy: Proxy URL
            response_time: Request response time
        """
        if proxy not in self.proxies:
            self.proxies[proxy] = ProxyStats()
            
        stats = self.proxies[proxy]
        stats.success_count += 1
        stats.last_success = time.time()
        stats.last_used = time.time()
        
        # Update average response time
        if stats.avg_response_time == 0:
            stats.avg_response_time = response_time
        else:
            stats.avg_response_time = (stats.avg_response_time * 0.9 + response_time * 0.1)
            
        self.consecutive_failures[proxy] = 0

    def report_failure(self, proxy: str, ban: bool = False) -> None:
        """
        Report proxy failure.
        
        Args:
            proxy: Proxy URL
            ban: Whether to ban the proxy
        """
        if proxy not in self.proxies:
            self.proxies[proxy] = ProxyStats()
            
        stats = self.proxies[proxy]
        stats.failure_count += 1
        stats.last_used = time.time()
        
        self.consecutive_failures[proxy] += 1
        
        # Ban proxy if too many failures
        if ban or self.consecutive_failures[proxy] >= self.ban_threshold:
            stats.banned_until = time.time() + self.ban_duration
            logger.warning(f"Banning proxy {proxy} for {self.ban_duration} seconds")

class UserAgentRotator:
    """Manage user-agent rotation."""
    
    def __init__(self, custom_agents: Optional[List[str]] = None):
        """
        Initialize user-agent rotator.
        
        Args:
            custom_agents: Optional list of custom user agents
        """
        self.user_agents = custom_agents or [
            # Chrome
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            
            # Firefox
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0',
            
            # Safari
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            
            # Edge
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59'
        ]
        
        # Track usage patterns
        self.usage_counts = collections.defaultdict(int)
        self._last_used: Dict[str, float] = {}

    def get_random_agent(self) -> str:
        """
        Get random user agent.
        
        Returns:
            Random user agent string
        """
        current_time = time.time()
        
        # Filter out recently used agents
        available_agents = [
            agent for agent in self.user_agents
            if current_time - self._last_used.get(agent, 0) > 1  # 1 second cooldown
        ]
        
        if not available_agents:
            available_agents = self.user_agents
            
        # Weight by inverse of usage count
        weights = [
            1 / (self.usage_counts[agent] + 1)
            for agent in available_agents
        ]
        
        agent = random.choices(available_agents, weights=weights)[0]
        
        self.usage_counts[agent] += 1
        self._last_used[agent] = current_time
        
        return agent

class RequestManager:
    """Manage proxy and user-agent rotation for requests."""
    
    def __init__(
        self,
        proxy_rotator: ProxyRotator,
        user_agent_rotator: UserAgentRotator
    ):
        """
        Initialize request manager.
        
        Args:
            proxy_rotator: Proxy rotation manager
            user_agent_rotator: User agent rotation manager
        """
        self.proxy_rotator = proxy_rotator
        self.user_agent_rotator = user_agent_rotator
        
    async def get_session(self) -> Tuple[aiohttp.ClientSession, str]:
        """
        Create session with proxy and user agent.
        
        Returns:
            Tuple of (session, proxy_url)
        """
        proxy = await self.proxy_rotator.get_proxy()
        user_agent = self.user_agent_rotator.get_random_agent()
        
        if not proxy:
            raise RuntimeError("No proxies available")
            
        connector = TCPConnector(force_close=True)
        session = aiohttp.ClientSession(
            connector=connector,
            headers={'User-Agent': user_agent},
            proxy=proxy
        )
        
        return session, proxy

    async def make_request(
        self,
        url: str,
        method: str = 'GET',
        **kwargs
    ) -> Optional[aiohttp.ClientResponse]:
        """
        Make request with automatic proxy/agent rotation.
        
        Args:
            url: Request URL
            method: HTTP method
            **kwargs: Additional request arguments
            
        Returns:
            Response object or None if all proxies failed
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            session, proxy = await self.get_session()
            start_time = time.time()
            
            try:
                async with session:
                    async with session.request(method, url, **kwargs) as response:
                        duration = time.time() - start_time
                        
                        if response.status == 200:
                            self.proxy_rotator.report_success(proxy, duration)
                            return response
                        elif response.status in (403, 429):  # Banned/Rate limited
                            self.proxy_rotator.report_failure(proxy, ban=True)
                        else:
                            self.proxy_rotator.report_failure(proxy)
                            
            except Exception as e:
                logger.error(f"Request error with proxy {proxy}: {e}")
                self.proxy_rotator.report_failure(proxy)
                
            retry_count += 1
            
        return None