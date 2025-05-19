"""
High-performance asynchronous web scraper.
"""

import asyncio
import aiohttp
from aiohttp_retry import RetryClient, ExponentialRetry
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Any, Optional, Set
import time
from datetime import datetime
import uvloop
from contextlib import asynccontextmanager
import orjson
import cachetools
from urllib.parse import urljoin
import re
from dataclasses import dataclass
from aiohttp import TCPConnector, ClientTimeout
from concurrent.futures import ProcessPoolExecutor

from src.scraper.monitoring.performance import ScraperMetrics, measure_time

logger = logging.getLogger(__name__)

@dataclass
class ScraperConfig:
    """Scraper configuration settings."""
    concurrency: int = 20
    timeout: int = 30
    retries: int = 3
    cache_size: int = 10000
    chunk_size: int = 1024 * 1024  # 1MB
    max_redirects: int = 5
    process_pool_size: int = 4

class AsyncScraper:
    """High-performance asynchronous scraper with optimizations."""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        """
        Initialize scraper.
        
        Args:
            config: Optional scraper configuration
        """
        self.config = config or ScraperConfig()
        self.metrics = ScraperMetrics()
        
        # URL deduplication cache
        self.seen_urls = cachetools.TTLCache(
            maxsize=self.config.cache_size,
            ttl=3600
        )
        
        # Retry configuration
        self.retry_options = ExponentialRetry(
            attempts=self.config.retries,
            start_timeout=1,
            max_timeout=10,
            factor=2
        )
        
        # Connection pooling
        self.connector = TCPConnector(
            limit=self.config.concurrency,
            ttl_dns_cache=300,
            use_dns_cache=True,
            force_close=False
        )
        
        # Request timeout
        self.timeout = ClientTimeout(total=self.config.timeout)
        
        # Concurrency control
        self.semaphore = asyncio.Semaphore(self.config.concurrency)
        
        # Process pool for CPU-bound parsing
        self.process_pool = ProcessPoolExecutor(
            max_workers=self.config.process_pool_size
        )
        
        # Enable uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    @asynccontextmanager
    async def session(self):
        """Create aiohttp session with retry support."""
        async with RetryClient(
            retry_options=self.retry_options,
            connector=self.connector,
            timeout=self.timeout,
            raise_for_status=True
        ) as session:
            yield session

    def _parse_html(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Parse HTML content in separate process.
        
        Args:
            html: HTML content
            url: Source URL
            
        Returns:
            Parsed article data or None
        """
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Extract content (customize for target sites)
            title = soup.find('h1')
            if not title:
                return None
                
            content = soup.find('article') or soup.find(class_='content')
            if not content:
                return None
                
            # Clean text
            title_text = re.sub(r'\s+', ' ', title.get_text()).strip()
            content_text = re.sub(r'\s+', ' ', content.get_text()).strip()
            
            # Extract metadata
            meta = {
                'author': None,
                'date': None,
                'category': None
            }
            
            author_tag = soup.find(class_=['author', 'byline'])
            if author_tag:
                meta['author'] = author_tag.get_text().strip()
                
            date_tag = soup.find(class_=['date', 'time', 'published'])
            if date_tag:
                meta['date'] = date_tag.get_text().strip()
                
            category_tag = soup.find(class_=['category', 'section'])
            if category_tag:
                meta['category'] = category_tag.get_text().strip()
            
            return {
                'url': url,
                'title': title_text,
                'content': content_text,
                'meta': meta,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error parsing {url}: {e}")
            return None

    @measure_time('RequestLatency')
    async def fetch_url(
        self,
        url: str,
        session: RetryClient
    ) -> Optional[str]:
        """
        Fetch URL with retries and timeout.
        
        Args:
            url: URL to fetch
            session: aiohttp session
            
        Returns:
            Page HTML or None if failed
        """
        try:
            async with self.semaphore:
                async with session.get(url) as response:
                    return await response.text()
                    
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    async def process_url(
        self,
        url: str,
        session: RetryClient
    ) -> Optional[Dict[str, Any]]:
        """
        Process single URL - fetch and parse.
        
        Args:
            url: URL to process
            session: aiohttp session
            
        Returns:
            Processed article data or None
        """
        if url in self.seen_urls:
            return None
            
        self.seen_urls[url] = True
        
        html = await self.fetch_url(url, session)
        if not html:
            return None
        
        # Parse in process pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.process_pool,
            self._parse_html,
            html,
            url
        )

    @measure_time('BatchProcessing')
    async def process_urls(
        self,
        urls: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Process multiple URLs concurrently.
        
        Args:
            urls: List of URLs to process
            
        Returns:
            List of processed articles
        """
        async with self.session() as session:
            tasks = [
                self.process_url(url, session)
                for url in urls
            ]
            
            results = await asyncio.gather(*tasks)
            return [r for r in results if r is not None]

    async def crawl(
        self,
        start_urls: List[str],
        max_urls: int = 1000,
        max_depth: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Crawl site recursively from start URLs.
        
        Args:
            start_urls: URLs to start crawling from
            max_urls: Maximum URLs to process
            max_depth: Maximum crawl depth
            
        Returns:
            List of processed articles
        """
        seen_urls: Set[str] = set()
        to_crawl: Set[str] = set(start_urls)
        results = []
        depth = 0
        
        async with self.session() as session:
            while to_crawl and len(seen_urls) < max_urls and depth < max_depth:
                current_urls = list(to_crawl)
                to_crawl.clear()
                
                # Process current batch
                tasks = [
                    self.process_url(url, session)
                    for url in current_urls
                    if url not in seen_urls
                ]
                
                batch_results = await asyncio.gather(*tasks)
                
                for result in batch_results:
                    if result:
                        results.append(result)
                        seen_urls.add(result['url'])
                        
                        # Extract new URLs to crawl
                        if depth + 1 < max_depth:
                            soup = BeautifulSoup(result['content'], 'lxml')
                            for link in soup.find_all('a'):
                                url = link.get('href')
                                if url:
                                    url = urljoin(result['url'], url)
                                    if url not in seen_urls:
                                        to_crawl.add(url)
                                        
                depth += 1
                
                if len(results) >= max_urls:
                    break
                    
        return results[:max_urls]

    def close(self):
        """Clean up resources."""
        self.process_pool.shutdown()
        self.connector.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.close()