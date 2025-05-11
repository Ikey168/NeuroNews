"""
Performance tests for optimized scraper.
"""

import pytest
import asyncio
import aiohttp
import time
from unittest.mock import patch, MagicMock
import psutil
import resource
from aioresponses import aioresponses
import json

from src.scraper.optimized_scraper import OptimizedScraper
from src.scraper.monitoring.performance import ScraperMetrics

# Test data
TEST_URLS = [f"https://example.com/article{i}" for i in range(100)]
TEST_HTML = """
<html>
    <head><title>Test Article</title></head>
    <body>
        <h1>Article Title</h1>
        <article>Article content goes here.</article>
    </body>
</html>
"""

@pytest.fixture
def scraper():
    """Create test scraper instance."""
    return OptimizedScraper(concurrency=10)

@pytest.fixture
def mock_aioresponse():
    """Mock aiohttp responses."""
    with aioresponses() as m:
        # Setup responses for test URLs
        for url in TEST_URLS:
            m.get(url, status=200, body=TEST_HTML)
        yield m

@pytest.mark.asyncio
async def test_concurrent_requests(scraper, mock_aioresponse):
    """Test concurrent request handling."""
    start_time = time.time()
    
    articles = scraper.run(TEST_URLS[:20])  # Test with 20 URLs
    
    duration = time.time() - start_time
    
    assert len(articles) == 20
    # Should process much faster than sequential (20 * timeout)
    assert duration < 20 * scraper.timeout.total

@pytest.mark.asyncio
async def test_memory_usage(scraper, mock_aioresponse):
    """Test memory usage during scraping."""
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    # Process large number of URLs
    articles = scraper.run(TEST_URLS)
    
    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory
    
    # Memory increase should be reasonable
    assert memory_increase < 100 * 1024 * 1024  # Less than 100MB increase
    
    # Check memory is released
    del articles
    import gc
    gc.collect()
    
    after_gc = process.memory_info().rss
    assert after_gc < final_memory

@pytest.mark.asyncio
async def test_error_handling(scraper):
    """Test error handling and retry logic."""
    with aioresponses() as m:
        # Setup failing URLs
        url = "https://example.com/failing"
        
        # Simulate temporary failures then success
        m.get(url, status=500)
        m.get(url, status=500)
        m.get(url, status=200, body=TEST_HTML)
        
        articles = scraper.run([url])
        assert len(articles) == 1

@pytest.mark.asyncio
async def test_url_deduplication(scraper, mock_aioresponse):
    """Test URL deduplication."""
    # Create list with duplicate URLs
    urls = TEST_URLS[:5] * 2
    
    articles = scraper.run(urls)
    
    # Should only process unique URLs
    assert len(articles) == 5

@pytest.mark.asyncio
async def test_performance_metrics(scraper, mock_aioresponse):
    """Test performance metrics collection."""
    with patch('src.scraper.monitoring.performance.ScraperMetrics') as MockMetrics:
        mock_metrics = MagicMock()
        MockMetrics.return_value = mock_metrics
        
        scraper.metrics = mock_metrics
        articles = scraper.run(TEST_URLS[:5])
        
        # Verify metrics were recorded
        mock_metrics.record_metric.assert_called()
        mock_metrics.publish_metrics.assert_called()

@pytest.mark.asyncio
async def test_concurrency_limit(scraper, mock_aioresponse):
    """Test concurrency limiting."""
    active_requests = 0
    max_active = 0
    
    original_fetch = scraper.fetch_page
    
    async def mock_fetch(*args, **kwargs):
        nonlocal active_requests, max_active
        active_requests += 1
        max_active = max(max_active, active_requests)
        result = await original_fetch(*args, **kwargs)
        active_requests -= 1
        return result
        
    scraper.fetch_page = mock_fetch
    
    articles = scraper.run(TEST_URLS[:20])
    
    assert max_active <= scraper.concurrency

@pytest.mark.asyncio
async def test_timeout_handling(scraper):
    """Test request timeout handling."""
    with aioresponses() as m:
        url = "https://example.com/slow"
        
        # Simulate slow response
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(scraper.timeout.total + 1)
            return TEST_HTML
            
        m.get(url, payload=slow_response)
        
        articles = scraper.run([url])
        assert len(articles) == 0

@pytest.mark.asyncio
async def test_parse_performance(scraper, mock_aioresponse):
    """Test HTML parsing performance."""
    url = TEST_URLS[0]
    
    # Create large HTML document
    large_html = TEST_HTML * 100
    mock_aioresponse.get(url, body=large_html)
    
    start_time = time.time()
    articles = scraper.run([url])
    parse_time = time.time() - start_time
    
    assert len(articles) == 1
    # Parsing should be reasonably fast
    assert parse_time < 1.0  # Less than 1 second

@pytest.mark.asyncio
async def test_connection_reuse(scraper):
    """Test connection pooling and reuse."""
    connections = set()
    
    async def mock_get(*args, **kwargs):
        connections.add(id(args[0]))
        return aiohttp.ClientResponse(
            "GET",
            aiohttp.URL(TEST_URLS[0]),
            writer=None,
            continue100=None,
            timer=None,
            request_info=None,
            traces=None,
            loop=asyncio.get_event_loop(),
            session=None
        )
    
    with patch('aiohttp.ClientSession._request', side_effect=mock_get):
        articles = scraper.run(TEST_URLS[:20])
        
        # Should reuse connections rather than creating new ones
        assert len(connections) <= scraper.concurrency

@pytest.mark.asyncio
async def test_resource_cleanup(scraper, mock_aioresponse):
    """Test proper cleanup of resources."""
    process = psutil.Process()
    initial_fds = process.num_fds()
    
    articles = scraper.run(TEST_URLS[:20])
    
    # Check file descriptors are closed
    assert process.num_fds() <= initial_fds + 5  # Allow small overhead