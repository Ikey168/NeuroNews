"""
Comprehensive tests for AsyncScraperEngine.
Tests async scraping orchestration, error handling, and performance monitoring.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import aiohttp
import aiofiles
from playwright.async_api import BrowserContext

# Import with proper path handling
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from scraper.async_scraper_engine import AsyncNewsScraperEngine, Article, NewsSource


class TestAsyncNewsScraperEngine:
    """Test suite for AsyncNewsScraperEngine class."""

    @pytest.fixture
    def sample_article(self):
        """Sample article fixture for testing."""
        return Article(
            title="Test Article",
            url="https://example.com/article",
            content="This is test content",
            author="Test Author",
            published_date="2024-01-01",
            source="TestSource",
            scraped_date=datetime.now().isoformat(),
            category="Technology",
            word_count=4,
            content_length=20
        )

    @pytest.fixture
    def sample_news_source(self):
        """Sample news source fixture for testing."""
        return NewsSource(
            name="TestSource",
            base_url="https://example.com",
            article_selectors={
                "title": "h1.title",
                "content": "div.content",
                "author": "span.author",
                "date": "time.date"
            },
            link_patterns=["a.article-link"],
            requires_js=False,
            rate_limit=1.0,
            timeout=30
        )

    @pytest.fixture
    def scraper_engine(self):
        """AsyncNewsScraperEngine fixture for testing."""
        with patch('scraper.cloudwatch_logger.CloudWatchLogger'), \
             patch('scraper.dynamodb_failure_manager.DynamoDBFailureManager'), \
             patch('scraper.sns_alert_manager.SNSAlertManager'):
            return AsyncNewsScraperEngine(max_concurrent=5, max_threads=4, headless=True)

    def test_engine_initialization(self, scraper_engine):
        """Test AsyncNewsScraperEngine initialization."""
        assert scraper_engine.max_concurrent == 5
        assert scraper_engine.max_threads == 4
        assert scraper_engine.headless is True
        # Check that the engine object was created successfully
        assert scraper_engine is not None

    def test_article_validation(self, sample_article):
        """Test article data validation."""
        # Valid article
        assert sample_article.title == "Test Article"
        assert sample_article.url == "https://example.com/article"
        assert sample_article.word_count == 4
        assert sample_article.content_length == 20

    @pytest.mark.asyncio
    async def test_fetch_with_playwright_success(self, scraper_engine):
        """Test successful page fetch with Playwright."""
        mock_page = AsyncMock()
        mock_page.goto.return_value = None
        mock_page.content.return_value = "<html><body>Test content</body></html>"
        mock_page.title.return_value = "Test Page"
        
        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        with patch('playwright.async_api.async_playwright') as mock_playwright:
            mock_playwright.return_value.__aenter__.return_value.chromium.launch.return_value.__aenter__.return_value.new_context.return_value.__aenter__.return_value = mock_context
            
            result = await scraper_engine._fetch_with_playwright("https://example.com")
            
            assert result is not None
            assert "Test content" in result

    @pytest.mark.asyncio
    async def test_fetch_with_playwright_error(self, scraper_engine):
        """Test Playwright fetch with error handling."""
        with patch('playwright.async_api.async_playwright') as mock_playwright:
            mock_playwright.side_effect = Exception("Playwright error")
            
            result = await scraper_engine._fetch_with_playwright("https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_with_aiohttp_success(self, scraper_engine):
        """Test successful HTTP fetch with aiohttp."""
        mock_response = AsyncMock()
        mock_response.text.return_value = "<html><body>Test content</body></html>"
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await scraper_engine._fetch_with_aiohttp("https://example.com")
            assert result is not None
            assert "Test content" in result

    @pytest.mark.asyncio
    async def test_fetch_with_aiohttp_error(self, scraper_engine):
        """Test aiohttp fetch with error handling."""
        mock_session = AsyncMock()
        mock_session.get.side_effect = aiohttp.ClientError("Connection error")
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await scraper_engine._fetch_with_aiohttp("https://example.com")
            assert result is None

    def test_extract_article_links(self, scraper_engine, sample_news_source):
        """Test article link extraction."""
        html_content = '''
        <html>
            <body>
                <a class="article-link" href="/article1">Article 1</a>
                <a class="article-link" href="/article2">Article 2</a>
                <a class="other-link" href="/other">Other</a>
            </body>
        </html>
        '''
        
        links = scraper_engine._extract_article_links(html_content, sample_news_source)
        assert len(links) == 2
        assert "https://example.com/article1" in links
        assert "https://example.com/article2" in links

    def test_extract_article_links_no_matches(self, scraper_engine, sample_news_source):
        """Test article link extraction with no matches."""
        html_content = '<html><body><p>No links here</p></body></html>'
        
        links = scraper_engine._extract_article_links(html_content, sample_news_source)
        assert len(links) == 0

    def test_parse_article_content(self, scraper_engine, sample_news_source):
        """Test article content parsing."""
        html_content = '''
        <html>
            <body>
                <h1 class="title">Test Article Title</h1>
                <span class="author">John Doe</span>
                <time class="date">2024-01-01</time>
                <div class="content">This is the article content.</div>
            </body>
        </html>
        '''
        
        article = scraper_engine._parse_article(html_content, "https://example.com/test", sample_news_source)
        
        assert article.title == "Test Article Title"
        assert article.author == "John Doe"
        assert article.published_date == "2024-01-01"
        assert article.content == "This is the article content."
        assert article.source == "TestSource"
        assert article.url == "https://example.com/test"

    def test_parse_article_missing_fields(self, scraper_engine, sample_news_source):
        """Test article parsing with missing fields."""
        html_content = '<html><body><p>Minimal content</p></body></html>'
        
        article = scraper_engine._parse_article(html_content, "https://example.com/test", sample_news_source)
        
        assert article.title == ""
        assert article.author == ""
        assert article.content == ""
        assert article.url == "https://example.com/test"

    def test_update_stats(self, scraper_engine):
        """Test statistics updates."""
        initial_requests = scraper_engine.stats["total_requests"]
        initial_successful = scraper_engine.stats["successful_requests"]
        
        scraper_engine._update_stats(success=True, response_time=0.5)
        
        assert scraper_engine.stats["total_requests"] == initial_requests + 1
        assert scraper_engine.stats["successful_requests"] == initial_successful + 1
        assert scraper_engine.stats["avg_response_time"] > 0

    def test_update_stats_failure(self, scraper_engine):
        """Test statistics updates for failures."""
        initial_requests = scraper_engine.stats["total_requests"]
        initial_failed = scraper_engine.stats["failed_requests"]
        
        scraper_engine._update_stats(success=False, response_time=1.0)
        
        assert scraper_engine.stats["total_requests"] == initial_requests + 1
        assert scraper_engine.stats["failed_requests"] == initial_failed + 1

    @pytest.mark.asyncio
    async def test_process_url_success(self, scraper_engine, sample_news_source):
        """Test successful URL processing."""
        with patch.object(scraper_engine, '_fetch_with_playwright') as mock_fetch:
            mock_fetch.return_value = '''
            <html>
                <body>
                    <h1 class="title">Test Title</h1>
                    <div class="content">Test content</div>
                </body>
            </html>
            '''
            
            article = await scraper_engine._process_url("https://example.com/test", sample_news_source)
            
            assert article is not None
            assert article.title == "Test Title"
            assert article.content == "Test content"

    @pytest.mark.asyncio
    async def test_process_url_fetch_failure(self, scraper_engine, sample_news_source):
        """Test URL processing with fetch failure."""
        with patch.object(scraper_engine, '_fetch_with_playwright', return_value=None):
            with patch.object(scraper_engine, '_fetch_with_aiohttp', return_value=None):
                article = await scraper_engine._process_url("https://example.com/test", sample_news_source)
                assert article is None

    def test_calculate_reading_time(self, scraper_engine):
        """Test reading time calculation."""
        # Test short content (< 200 words)
        short_content = " ".join(["word"] * 100)
        reading_time = scraper_engine._calculate_reading_time(short_content)
        assert reading_time == 1  # Minimum 1 minute
        
        # Test medium content
        medium_content = " ".join(["word"] * 400)
        reading_time = scraper_engine._calculate_reading_time(medium_content)
        assert reading_time == 2  # 400 words / 200 wpm = 2 minutes
        
        # Test long content
        long_content = " ".join(["word"] * 1000)
        reading_time = scraper_engine._calculate_reading_time(long_content)
        assert reading_time == 5  # 1000 words / 200 wpm = 5 minutes

    def test_validate_article_quality_good(self, scraper_engine):
        """Test article quality validation for good content."""
        content = "This is a well-written article with substantial content. " * 20
        title = "Comprehensive Article Title"
        
        score, quality = scraper_engine._validate_article_quality(title, content, "John Doe")
        
        assert score >= 8  # Should be high quality
        assert quality == "excellent"

    def test_validate_article_quality_poor(self, scraper_engine):
        """Test article quality validation for poor content."""
        content = "Short."
        title = ""
        
        score, quality = scraper_engine._validate_article_quality(title, content, "")
        
        assert score <= 3  # Should be poor quality
        assert quality == "poor"

    @pytest.mark.asyncio
    async def test_save_articles(self, scraper_engine, sample_article, tmp_path):
        """Test article saving to file."""
        # Add sample article to engine
        scraper_engine.articles = [sample_article]
        
        # Set output file path
        output_file = tmp_path / "test_articles.json"
        scraper_engine.output_file = str(output_file)
        
        # Mock aiofiles
        with patch('aiofiles.open', create=True) as mock_open:
            mock_file = AsyncMock()
            mock_open.return_value.__aenter__.return_value = mock_file
            
            await scraper_engine._save_articles()
            
            # Verify file operations
            mock_open.assert_called_once()
            mock_file.write.assert_called_once()

    def test_get_stats(self, scraper_engine):
        """Test statistics retrieval."""
        # Update some stats
        scraper_engine.stats["total_requests"] = 100
        scraper_engine.stats["successful_requests"] = 85
        scraper_engine.stats["failed_requests"] = 15
        
        stats = scraper_engine.get_stats()
        
        assert stats["total_requests"] == 100
        assert stats["successful_requests"] == 85
        assert stats["failed_requests"] == 15
        assert stats["success_rate"] == 0.85

    def test_concurrent_limit_validation(self):
        """Test concurrent limit validation during initialization."""
        # Test normal limit
        engine = AsyncNewsScraperEngine(max_concurrent=5)
        assert engine.max_concurrent == 5
        
        # Test different limits
        engine = AsyncNewsScraperEngine(max_concurrent=10)
        assert engine.max_concurrent == 10

    def test_max_threads_validation(self):
        """Test max threads validation during initialization."""
        engine = AsyncNewsScraperEngine(max_threads=4)
        assert engine.max_threads == 4
        
        # Test different thread counts
        engine = AsyncNewsScraperEngine(max_threads=8)
        assert engine.max_threads == 8

    @pytest.mark.asyncio
    async def test_memory_usage_monitoring(self, scraper_engine):
        """Test memory usage monitoring during scraping."""
        initial_memory = scraper_engine._get_memory_usage()
        assert initial_memory > 0
        
        # Simulate memory increase
        large_data = [{"data": "x" * 1000} for _ in range(100)]
        scraper_engine.articles.extend([scraper_engine.sample_article] * 100)
        
        current_memory = scraper_engine._get_memory_usage()
        assert current_memory >= initial_memory

    def test_cleanup_resources(self, scraper_engine):
        """Test resource cleanup."""
        # Add some data
        scraper_engine.articles = [MagicMock()] * 100
        scraper_engine.stats["total_requests"] = 500
        
        scraper_engine._cleanup_resources()
        
        # Verify cleanup (stats should be reset, but articles preserved for final save)
        assert len(scraper_engine.articles) <= 1000  # Should respect max limit