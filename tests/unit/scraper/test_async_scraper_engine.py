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

        article = scraper_engine.parse_article_html(html_content, "https://example.com/test", sample_news_source)

        assert article.title == "Test Article Title"
        assert article.author == "John Doe"
        assert article.published_date == "2024-01-01"
        assert article.content == "This is the article content."
        assert article.source == "TestSource"
        assert article.url == "https://example.com/test"

    def test_parse_article_missing_fields(self, scraper_engine, sample_news_source):
        """Test article parsing with missing fields.

        Current behavior: parse_article_html returns None when the required
        title/content fields cannot be extracted from the HTML.
        """
        html_content = '<html><body><p>Minimal content</p></body></html>'

        article = scraper_engine.parse_article_html(html_content, "https://example.com/test", sample_news_source)

        assert article is None

    def test_update_stats(self, scraper_engine):
        """Test statistics updates for successful requests via PerformanceMonitor."""
        initial_successful = scraper_engine.monitor.successful_requests

        scraper_engine.monitor.record_success(response_time=0.5)

        assert scraper_engine.monitor.successful_requests == initial_successful + 1
        stats = scraper_engine.get_performance_stats()
        assert stats["avg_response_time"] > 0

    def test_update_stats_failure(self, scraper_engine):
        """Test statistics updates for failures via PerformanceMonitor."""
        initial_failed = scraper_engine.monitor.failed_requests

        scraper_engine.monitor.record_error(source="TestSource")

        assert scraper_engine.monitor.failed_requests == initial_failed + 1

    def test_calculate_reading_time(self, scraper_engine, sample_news_source):
        """Test reading time calculation performed during article parsing.

        Reading time is computed inside parse_article_html as
        max(1, word_count // 200).
        """
        def build_html(num_words):
            words = " ".join(["word"] * num_words)
            return (
                '<html><body>'
                '<h1 class="title">A Sufficiently Long Title Here</h1>'
                '<div class="content">{0}</div>'
                '</body></html>'
            ).format(words)

        # 100 words -> max(1, 0) = 1 minute
        article = scraper_engine.parse_article_html(
            build_html(100), "https://example.com/a", sample_news_source
        )
        assert article.reading_time == 1

        # 400 words -> 400 // 200 = 2 minutes
        article = scraper_engine.parse_article_html(
            build_html(400), "https://example.com/b", sample_news_source
        )
        assert article.reading_time == 2

        # 1000 words -> 1000 // 200 = 5 minutes
        article = scraper_engine.parse_article_html(
            build_html(1000), "https://example.com/c", sample_news_source
        )
        assert article.reading_time == 5

    def test_validate_article_quality_good(self, scraper_engine):
        """Test article quality validation for good content."""
        content = "This is a well-written article with substantial content. " * 20
        article = Article(
            title="Comprehensive Article Title",
            url="https://example.com/good",
            content=content,
            author="John Doe",
            published_date="2024-01-01",
            source="TestSource",
            scraped_date=datetime.now().isoformat(),
            content_length=len(content),
            word_count=len(content.split()),
        )

        score = scraper_engine.validate_article(article)
        quality = scraper_engine.get_quality_label(score)

        assert score >= 80  # Should be high quality
        assert quality == "high"

    def test_validate_article_quality_poor(self, scraper_engine):
        """Test article quality validation for poor content."""
        content = "Short."
        article = Article(
            title="",
            url="https://example.com/poor",
            content=content,
            author="",
            published_date="2024-01-01",
            source="TestSource",
            scraped_date=datetime.now().isoformat(),
            content_length=len(content),
            word_count=len(content.split()),
        )

        score = scraper_engine.validate_article(article)
        quality = scraper_engine.get_quality_label(score)

        assert score < 60  # Should be poor quality
        assert quality == "low"

    @pytest.mark.asyncio
    async def test_save_articles(self, scraper_engine, sample_article, tmp_path):
        """Test article saving to file."""
        output_file = tmp_path / "test_articles.json"

        # Async context manager mock for aiofiles.open(...)
        mock_file = AsyncMock()
        cm = AsyncMock()
        cm.__aenter__.return_value = mock_file
        cm.__aexit__.return_value = None

        with patch('aiofiles.open', return_value=cm) as mock_open:
            await scraper_engine.save_articles([sample_article], str(output_file))

            # Verify file operations
            mock_open.assert_called_once()
            mock_file.write.assert_called_once()

    def test_get_stats(self, scraper_engine):
        """Test performance statistics retrieval."""
        # Record some activity through the monitor
        scraper_engine.monitor.record_success(response_time=0.2)
        scraper_engine.monitor.record_success(response_time=0.4)
        scraper_engine.monitor.record_error(source="TestSource")

        stats = scraper_engine.get_performance_stats()

        assert stats["successful_requests"] == 2
        assert stats["failed_requests"] == 1
        # success_rate is reported as a percentage (2 / 3 * 100)
        assert stats["success_rate"] == pytest.approx(2 / 3 * 100)

    def test_concurrent_limit_validation(self):
        """Test concurrent limit validation during initialization."""
        with patch('scraper.cloudwatch_logger.CloudWatchLogger'), \
             patch('scraper.dynamodb_failure_manager.DynamoDBFailureManager'), \
             patch('scraper.sns_alert_manager.SNSAlertManager'):
            # Test normal limit
            engine = AsyncNewsScraperEngine(max_concurrent=5)
            assert engine.max_concurrent == 5

            # Test different limits
            engine = AsyncNewsScraperEngine(max_concurrent=10)
            assert engine.max_concurrent == 10

    def test_max_threads_validation(self):
        """Test max threads validation during initialization."""
        with patch('scraper.cloudwatch_logger.CloudWatchLogger'), \
             patch('scraper.dynamodb_failure_manager.DynamoDBFailureManager'), \
             patch('scraper.sns_alert_manager.SNSAlertManager'):
            engine = AsyncNewsScraperEngine(max_threads=4)
            assert engine.max_threads == 4

            # Test different thread counts
            engine = AsyncNewsScraperEngine(max_threads=8)
            assert engine.max_threads == 8

    def test_memory_usage_monitoring(self, scraper_engine):
        """Test memory usage monitoring is exposed through performance stats."""
        # Force a deterministic memory sample so avg_memory_mb is populated
        with scraper_engine.monitor.lock:
            scraper_engine.monitor.memory_usage.append(123.0)

        stats = scraper_engine.get_performance_stats()
        assert "avg_memory_mb" in stats
        assert stats["avg_memory_mb"] > 0
