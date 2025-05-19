"""
High concurrency tests for scraper performance.
"""

import pytest
import asyncio
from aioresponses import aioresponses
import time
import aiohttp
from typing import List, Dict, Any
import logging
import random
from concurrent.futures import ProcessPoolExecutor
import psutil
import resource

from src.scraper.async_scraper import AsyncScraper, ScraperConfig
from src.scraper.proxy_manager import RequestManager, ProxyRotator, UserAgentRotator
from src.scraper.retry_handler import RequestRetryHandler, RetryConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test data
TEST_SOURCES = {
    'reuters': [
        'https://www.reuters.com/world',
        'https://www.reuters.com/business',
        'https://www.reuters.com/markets',
        'https://www.reuters.com/technology'
    ],
    'bloomberg': [
        'https://www.bloomberg.com/markets',
        'https://www.bloomberg.com/technology',
        'https://www.bloomberg.com/politics',
        'https://www.bloomberg.com/economics'
    ],
    'wsj': [
        'https://www.wsj.com/news/markets',
        'https://www.wsj.com/news/business',
        'https://www.wsj.com/news/world',
        'https://www.wsj.com/news/technology'
    ],
    'ft': [
        'https://www.ft.com/markets',
        'https://www.ft.com/companies',
        'https://www.ft.com/technology',
        'https://www.ft.com/world'
    ],
    'nyt': [
        'https://www.nytimes.com/section/business',
        'https://www.nytimes.com/section/technology',
        'https://www.nytimes.com/section/world',
        'https://www.nytimes.com/section/markets'
    ]
}

# HTML templates for different response sizes
HTML_TEMPLATES = {
    'small': """
        <html><body>
            <h1>Small Article {id}</h1>
            <article>Short content for testing.</article>
        </body></html>
    """,
    'medium': """
        <html><body>
            <h1>Medium Article {id}</h1>
            <article>{content}</article>
        </body></html>
    """,
    'large': """
        <html><body>
            <h1>Large Article {id}</h1>
            <article>{content}</article>
            <div class="comments">{comments}</div>
        </body></html>
    """
}

@pytest.fixture
def scraper():
    """Create test scraper with high concurrency config."""
    config = ScraperConfig(
        concurrency=20,
        timeout=30,
        cache_size=10000,
        process_pool_size=4
    )
    return AsyncScraper(config)

@pytest.fixture
def request_manager():
    """Create test request manager."""
    proxy_rotator = ProxyRotator()
    user_agent_rotator = UserAgentRotator()
    return RequestManager(proxy_rotator, user_agent_rotator)

@pytest.fixture
def retry_handler():
    """Create test retry handler."""
    config = RetryConfig(max_retries=3, base_delay=0.1)
    return RequestRetryHandler(config)

def generate_test_content(size: str, article_id: int) -> str:
    """Generate test HTML content of different sizes."""
    if size == 'small':
        return HTML_TEMPLATES['small'].format(id=article_id)
    elif size == 'medium':
        content = ' '.join(['Test content'] * 100)
        return HTML_TEMPLATES['medium'].format(id=article_id, content=content)
    else:
        content = ' '.join(['Test content'] * 500)
        comments = ' '.join(['Test comment'] * 200)
        return HTML_TEMPLATES['large'].format(
            id=article_id,
            content=content,
            comments=comments
        )

async def simulate_network_conditions(url: str) -> Dict[str, Any]:
    """Simulate various network conditions."""
    conditions = {
        'delay': random.uniform(0.1, 2.0),
        'error_chance': random.uniform(0, 0.2),
        'size': random.choice(['small', 'medium', 'large'])
    }
    
    if random.random() < conditions['error_chance']:
        if random.random() < 0.5:
            raise aiohttp.ClientError("Simulated network error")
        else:
            return {'status': random.choice([429, 500, 503])}
            
    return {
        'status': 200,
        'body': generate_test_content(conditions['size'], hash(url) % 1000),
        'delay': conditions['delay']
    }

@pytest.mark.asyncio
async def test_high_concurrency_scraping(scraper, mock_aioresponse):
    """Test scraping multiple sources concurrently."""
    # Setup mock responses
    for source_urls in TEST_SOURCES.values():
        for url in source_urls:
            conditions = await simulate_network_conditions(url)
            mock_aioresponse.get(url, **conditions)
    
    # Test concurrent scraping
    start_time = time.time()
    
    all_urls = [
        url for urls in TEST_SOURCES.values()
        for url in urls
    ]
    
    results = await scraper.process_urls(all_urls)
    
    duration = time.time() - start_time
    
    # Verify results
    assert len(results) > 0
    assert duration < len(all_urls)  # Should be faster than sequential
    
    # Check resource usage
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    assert memory_mb < 1024  # Less than 1GB

@pytest.mark.asyncio
async def test_proxy_rotation_under_load(request_manager, mock_aioresponse):
    """Test proxy rotation with high concurrency."""
    test_urls = [
        url for urls in TEST_SOURCES.values()
        for url in urls
    ]
    
    # Setup responses
    for url in test_urls:
        conditions = await simulate_network_conditions(url)
        mock_aioresponse.get(url, **conditions)
    
    # Make concurrent requests
    async def fetch_url(url: str) -> Any:
        return await request_manager.make_request(url)
        
    tasks = [fetch_url(url) for url in test_urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Analyze results
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) > 0

@pytest.mark.asyncio
async def test_retry_behavior_under_load(retry_handler, mock_aioresponse):
    """Test retry behavior with concurrent requests."""
    test_urls = [
        url for urls in TEST_SOURCES.values()
        for url in urls
    ][:10]  # Test with 10 URLs
    
    retry_counts: Dict[str, int] = {url: 0 for url in test_urls}
    
    async def test_request(url: str) -> None:
        conditions = await simulate_network_conditions(url)
        if conditions.get('status') != 200:
            retry_counts[url] += 1
            raise aiohttp.ClientError("Simulated error")
            
    tasks = [
        retry_handler.retry_async(test_request, url)
        for url in test_urls
    ]
    
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Verify retry behavior
    assert any(count > 0 for count in retry_counts.values())

@pytest.mark.asyncio
async def test_memory_usage_under_load(scraper):
    """Test memory usage with large responses."""
    # Generate large test URLs
    test_urls = [
        url for urls in TEST_SOURCES.values()
        for url in urls
    ]
    
    # Monitor memory usage
    initial_memory = psutil.Process().memory_info().rss
    
    with aioresponses() as m:
        for url in test_urls:
            m.get(
                url,
                status=200,
                body=generate_test_content('large', hash(url) % 1000)
            )
            
        await scraper.process_urls(test_urls)
    
    final_memory = psutil.Process().memory_info().rss
    memory_increase = (final_memory - initial_memory) / 1024 / 1024
    
    # Check memory increase is reasonable
    assert memory_increase < 500  # Less than 500MB increase

@pytest.mark.asyncio
async def test_cpu_usage_under_load(scraper):
    """Test CPU usage with concurrent processing."""
    test_urls = [
        url for urls in TEST_SOURCES.values()
        for url in urls
    ]
    
    cpu_percent = psutil.cpu_percent(interval=None)
    
    with aioresponses() as m:
        for url in test_urls:
            m.get(
                url,
                status=200,
                body=generate_test_content('medium', hash(url) % 1000)
            )
            
        await scraper.process_urls(test_urls)
    
    final_cpu = psutil.cpu_percent(interval=None)
    
    # Verify CPU usage is reasonable
    assert final_cpu - cpu_percent < 80  # Less than 80% increase

if __name__ == '__main__':
    pytest.main(['-v', __file__])