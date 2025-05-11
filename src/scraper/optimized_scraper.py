"""
Optimized web scraper with performance monitoring.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urljoin
import cachetools
import uvloop
import orjson
from aiohttp import ClientTimeout
from aiohttp_retry import RetryClient, ExponentialRetry

from src.scraper.monitoring.performance import (
    ScraperMetrics,
    measure_time,
    PerformanceOptimizer
)

logger = logging.getLogger(__name__)

class OptimizedScraper:
    """Performance-optimized web scraper."""
    
    def __init__(
        self,
        concurrency: int = 10,
        cache_size: int = 1000,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize scraper with performance settings.
        
        Args:
            concurrency: Maximum concurrent requests
            cache_size: Size of URL cache
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.concurrency = concurrency
        self.timeout = ClientTimeout(total=timeout)
        self.metrics = ScraperMetrics()
        
        # URL deduplication cache
        self.seen_urls = cachetools.TTLCache(
            maxsize=cache_size,
            ttl=3600  # 1 hour TTL
        )
        
        # Retry strategy
        self.retry_options = ExponentialRetry(
            attempts=max_retries,
            start_timeout=1,
            max_timeout=10,
            factor=2
        )
        
        # Semaphore for concurrency control
        self.semaphore = asyncio.Semaphore(concurrency)
        
        # Enable uvloop for better performance
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    @measure_time('RequestLatency')
    async def fetch_page(
        self,
        url: str,
        session: RetryClient
    ) -> Optional[str]:
        """
        Fetch a page with timeout and retry handling.
        
        Args:
            url: URL to fetch
            session: Aiohttp session
            
        Returns:
            Page HTML content or None if failed
        """
        try:
            async with self.semaphore:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(
                            f"Failed to fetch {url} - Status: {response.status}"
                        )
                        return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None

    @measure_time('ParsingTime')
    def parse_article(
        self,
        html: str,
        url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Parse article content with optimized BeautifulSoup.
        
        Args:
            html: Page HTML content
            url: Article URL
            
        Returns:
            Parsed article data or None if parsing failed
        """
        try:
            # Use lxml parser for better performance
            soup = BeautifulSoup(html, 'lxml')
            
            # Basic article extraction - customize for target sites
            title = soup.find('h1')
            content = soup.find('article') or soup.find(class_='content')
            
            if not title or not content:
                return None
                
            return {
                'url': url,
                'title': title.get_text(strip=True),
                'content': content.get_text(strip=True),
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error parsing {url}: {str(e)}")
            return None

    async def process_url(
        self,
        url: str,
        session: RetryClient
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single URL - fetch and parse.
        
        Args:
            url: URL to process
            session: Aiohttp session
            
        Returns:
            Processed article data or None
        """
        # Skip if URL was recently processed
        if url in self.seen_urls:
            return None
            
        self.seen_urls[url] = True
        
        html = await self.fetch_page(url, session)
        if not html:
            return None
            
        return self.parse_article(html, url)

    @measure_time('ProcessingTime')
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
        async with PerformanceOptimizer() as metrics:
            self.metrics = metrics
            
            # Configure connection pooling
            conn = aiohttp.TCPConnector(
                limit=self.concurrency,
                ttl_dns_cache=300
            )
            
            async with RetryClient(
                retry_options=self.retry_options,
                connector=conn,
                timeout=self.timeout
            ) as session:
                # Process URLs concurrently
                tasks = [
                    self.process_url(url, session)
                    for url in urls
                ]
                
                results = await asyncio.gather(*tasks)
                
                # Filter out failures
                return [r for r in results if r is not None]

    def run(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Run the scraper synchronously.
        
        Args:
            urls: List of URLs to process
            
        Returns:
            List of processed articles
        """
        return asyncio.run(self.process_urls(urls))

if __name__ == '__main__':
    # Example usage
    urls = [
        'https://example.com/article1',
        'https://example.com/article2'
    ]
    
    scraper = OptimizedScraper()
    articles = scraper.run(urls)
    
    # Use orjson for faster JSON serialization
    print(orjson.dumps(articles).decode())