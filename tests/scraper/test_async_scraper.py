"""
Tests for enhanced asynchronous scraper.
"""

import pytest
import asyncio
from aioresponses import aioresponses
import aiohttp
from bs4 import BeautifulSoup
import tempfile
from pathlib import Path
import re
from datetime import datetime, timedelta
import time

from src.scraper.async_scraper import AsyncScraper, ScraperConfig

# Test data
TEST_HTML = """
<html>
    <head><title>Test Article</title></head>
    <body>
        <h1>Test Article Title</h1>
        <div class="byline">By Test Author</div>
        <div class="date">2025-05-19</div>
        <div class="category">Technology</div>
        <article>
            Test article content.
            <a href="/article1">Link 1</a>
            <a href="https://example.com/article2">Link 2</a>
        </article>
    </body>
</html>
"""

TEST_URLS = [f"https://example.com/article{i}" for i in range(50)]

@pytest.fixture
def scraper():
    """Create test scraper instance."""
    config = ScraperConfig(
        concurrency=5,
        timeout=5,
        retries=2,
        cache_size=100
    )
    return AsyncScraper(config)

@pytest.fixture
async def mock_session():
    """Mock aiohttp session with responses."""
    with aioresponses() as m:
        # Setup test responses
        for url in TEST_URLS:
            m.get(url, status=200, body=TEST_HTML)
        yield m

@pytest.mark.asyncio
async def test_fetch_single_url(scraper, mock_session):
    """Test fetching a single URL."""
    url = TEST_URLS[0]
    
    async with scraper.session() as session:
        html = await scraper.fetch_url(url, session)
        
    assert html is not None
    assert "Test Article Title" in html
    assert len(html) > 0

@pytest.mark.asyncio
async def test_parse_html(scraper):
    """Test HTML parsing."""
    url = TEST_URLS[0]
    result = scraper._parse_html(TEST_HTML, url)
    
    assert result is not None
    assert result['url'] == url
    assert result['title'] == "Test Article Title"
    assert "Test article content" in result['content']
    assert result['meta']['author'] == "Test Author"
    assert result['meta']['date'] == "2025-05-19"
    assert result['meta']['category'] == "Technology"

@pytest.mark.asyncio
async def test_concurrent_processing(scraper, mock_session):
    """Test concurrent URL processing."""
    start_time = time.time()
    
    results = await scraper.process_urls(TEST_URLS[:10])
    
    duration = time.time() - start_time
    
    assert len(results) == 10
    # Should be faster than sequential (10 * timeout)
    assert duration < 10 * scraper.config.timeout

@pytest.mark.asyncio
async def test_url_deduplication(scraper, mock_session):
    """Test URL deduplication."""
    # Create list with duplicate URLs
    urls = TEST_URLS[:5] * 2
    
    results = await scraper.process_urls(urls)
    
    assert len(results) == 5  # Should only process unique URLs
    assert len(scraper.seen_urls) == 5

@pytest.mark.asyncio
async def test_error_handling(scraper):
    """Test handling of failed requests."""
    with aioresponses() as m:
        # Setup mix of responses
        m.get(TEST_URLS[0], status=200, body=TEST_HTML)
        m.get(TEST_URLS[1], status=500)
        m.get(TEST_URLS[2], exception=asyncio.TimeoutError)
        m.get(TEST_URLS[3], status=404)
        
        results = await scraper.process_urls(TEST_URLS[:4])
        
        assert len(results) == 1  # Only successful request
        assert results[0]['url'] == TEST_URLS[0]

@pytest.mark.asyncio
async def test_retry_mechanism(scraper):
    """Test request retry mechanism."""
    with aioresponses() as m:
        url = TEST_URLS[0]
        
        # Fail twice then succeed
        m.get(url, status=500)
        m.get(url, status=500)
        m.get(url, status=200, body=TEST_HTML)
        
        async with scraper.session() as session:
            html = await scraper.fetch_url(url, session)
            
        assert html is not None
        assert "Test Article Title" in html

@pytest.mark.asyncio
async def test_crawl_functionality(scraper):
    """Test recursive crawling."""
    with aioresponses() as m:
        # Setup initial URL
        m.get(TEST_URLS[0], status=200, body=TEST_HTML)
        
        # Setup linked URLs
        m.get("https://example.com/article1", status=200, body=TEST_HTML)
        m.get("https://example.com/article2", status=200, body=TEST_HTML)
        
        results = await scraper.crawl(
            [TEST_URLS[0]],
            max_urls=3,
            max_depth=2
        )
        
        assert len(results) == 3
        assert any(r['url'] == TEST_URLS[0] for r in results)
        assert any(r['url'] == "https://example.com/article1" for r in results)
        assert any(r['url'] == "https://example.com/article2" for r in results)

@pytest.mark.asyncio
async def test_resource_cleanup(scraper):
    """Test proper resource cleanup."""
    # Track open connections
    open_connections = len(psutil.Process().connections())
    
    async with AsyncScraper() as s:
        await s.process_urls(TEST_URLS[:5])
    
    # Check connections are closed
    assert len(psutil.Process().connections()) <= open_connections

@pytest.mark.asyncio
async def test_concurrency_limit(scraper, mock_session):
    """Test concurrency limiting."""
    active_requests = 0
    max_concurrent = 0
    
    original_fetch = scraper.fetch_url
    
    async def mock_fetch(*args, **kwargs):
        nonlocal active_requests, max_concurrent
        active_requests += 1
        max_concurrent = max(max_concurrent, active_requests)
        result = await original_fetch(*args, **kwargs)
        active_requests -= 1
        return result
    
    scraper.fetch_url = mock_fetch
    
    await scraper.process_urls(TEST_URLS[:20])
    
    assert max_concurrent <= scraper.config.concurrency

@pytest.mark.asyncio
async def test_html_parsing_errors(scraper):
    """Test handling of invalid HTML."""
    invalid_html = [
        "",  # Empty
        "Not HTML",  # Plain text
        "<html><body>No article</body></html>",  # Missing required elements
        None  # None input
    ]
    
    for html in invalid_html:
        result = scraper._parse_html(html, TEST_URLS[0])
        assert result is None

@pytest.mark.asyncio
async def test_process_pool(scraper):
    """Test process pool for HTML parsing."""
    # Create large HTML to test CPU-bound parsing
    large_html = TEST_HTML * 1000
    
    start_time = time.time()
    results = []
    
    # Parse multiple times to test pool
    for _ in range(5):
        result = scraper._parse_html(large_html, TEST_URLS[0])
        results.append(result)
    
    duration = time.time() - start_time
    
    assert len(results) == 5
    assert all(r is not None for r in results)
    # Should be faster than sequential processing
    assert duration < 5 * 0.5  # Assuming each parse takes ~0.5s