"""
Test suite for async scraper implementation.
Tests AsyncIO functionality, Playwright optimization, ThreadPoolExecutor parallelization,
and performance monitoring.
"""

import asyncio
import pytest
import json
import tempfile
import time
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
import aiohttp

import sys
sys.path.append('/workspaces/NeuroNews/src')

from scraper.async_scraper_engine import AsyncNewsScraperEngine
from scraper.async_scraper_runner import AsyncScraperRunner
from scraper.async_pipelines import AsyncPipelineProcessor
from scraper.performance_monitor import PerformanceDashboard


class TestAsyncScraperEngine:
    """Test the core async scraper engine functionality."""
    
    @pytest.fixture
    async def scraper_engine(self):
        """Create a test scraper engine instance."""
        config = {
            'async_scraper': {
                'max_concurrent': 5,
                'max_threads': 2,
                'headless': True,
                'timeout': 10,
                'retry_attempts': 2,
                'retry_delay': 1,
                'rate_limiting': {
                    'default_rate': 2.0,
                    'burst_size': 3
                }
            },
            'sources': [
                {
                    'name': 'Test Source',
                    'base_url': 'https://example.com',
                    'article_selectors': {
                        'title': 'h1',
                        'content': 'p',
                        'author': '.author',
                        'date': 'time'
                    },
                    'requires_js': False,
                    'enabled': True
                }
            ]
        }
        
        engine = AsyncNewsScraperEngine(config)
        yield engine
        await engine.cleanup()
    
    @pytest.mark.asyncio
    async def test_engine_initialization(self, scraper_engine):
        """Test engine initializes correctly."""
        assert scraper_engine.max_concurrent == 5
        assert scraper_engine.max_threads == 2
        assert scraper_engine.timeout == 10
        assert scraper_engine.retry_attempts == 2
        assert len(scraper_engine.sources) == 1
    
    @pytest.mark.asyncio
    async def test_http_client_session(self, scraper_engine):
        """Test HTTP client session creation and cleanup."""
        # Session should be created
        assert scraper_engine.session is not None
        assert isinstance(scraper_engine.session, aiohttp.ClientSession)
        
        # Test cleanup
        await scraper_engine.cleanup()
        assert scraper_engine.session.closed
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self, scraper_engine):
        """Test rate limiting functionality."""
        start_time = time.time()
        
        # Make multiple rapid requests (should be rate limited)
        tasks = []
        for _ in range(3):
            task = scraper_engine._wait_for_rate_limit('Test Source')
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should take at least some time due to rate limiting
        assert duration > 0.5  # At least 0.5 seconds for rate limiting
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.get')
    async def test_fetch_with_retry(self, mock_get, scraper_engine):
        """Test HTTP fetch with retry logic."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html><h1>Test Title</h1></html>")
        mock_response.headers = {'content-type': 'text/html'}
        mock_get.return_value.__aenter__.return_value = mock_response
        
        result = await scraper_engine._fetch_with_retry('https://example.com')
        
        assert result is not None
        assert 'Test Title' in result
        mock_get.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.get')
    async def test_fetch_with_retry_failure(self, mock_get, scraper_engine):
        """Test HTTP fetch retry on failure."""
        # Mock failed responses
        mock_get.side_effect = aiohttp.ClientError("Connection failed")
        
        result = await scraper_engine._fetch_with_retry('https://example.com')
        
        assert result is None
        # Should retry based on retry_attempts (2)
        assert mock_get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_extract_article_data(self, scraper_engine):
        """Test article data extraction from HTML."""
        html_content = """
        <html>
            <head><title>Test Article</title></head>
            <body>
                <h1>Test Article Title</h1>
                <p>This is test content for the article.</p>
                <div class="author">John Doe</div>
                <time datetime="2024-01-01T12:00:00Z">January 1, 2024</time>
            </body>
        </html>
        """
        
        source_config = scraper_engine.sources[0]
        article = await scraper_engine._extract_article_data(
            html_content, 
            'https://example.com/article', 
            source_config
        )
        
        assert article['title'] == 'Test Article Title'
        assert 'test content' in article['content'].lower()
        assert article['author'] == 'John Doe'
        assert article['url'] == 'https://example.com/article'
        assert article['source'] == 'Test Source'
    
    @pytest.mark.asyncio
    async def test_validate_article(self, scraper_engine):
        """Test article validation logic."""
        # Valid article
        valid_article = {
            'title': 'Valid Article Title',
            'content': 'This is a valid article with sufficient content for testing purposes.',
            'url': 'https://example.com/valid',
            'source': 'Test Source'
        }
        
        assert scraper_engine._validate_article(valid_article) is True
        
        # Invalid article (too short)
        invalid_article = {
            'title': 'Short',
            'content': 'Too short',
            'url': 'https://example.com/invalid',
            'source': 'Test Source'
        }
        
        assert scraper_engine._validate_article(invalid_article) is False


class TestAsyncPipelines:
    """Test async pipeline processor functionality."""
    
    @pytest.fixture
    def pipeline_processor(self):
        """Create a test pipeline processor."""
        config = {
            'pipelines': {
                'validation': {
                    'enabled': True,
                    'min_content_length': 50,
                    'quality_threshold': 60
                },
                'duplicate_detection': {
                    'enabled': True,
                    'title_similarity_threshold': 0.8
                },
                'enhancement': {
                    'enabled': True,
                    'category_extraction': True,
                    'keyword_extraction': True
                }
            }
        }
        
        return AsyncPipelineProcessor(config, max_workers=2)
    
    @pytest.mark.asyncio
    async def test_pipeline_validation(self, pipeline_processor):
        """Test article validation in pipeline."""
        valid_article = {
            'title': 'Valid Article Title',
            'content': 'This is a valid article with sufficient content for testing validation.',
            'url': 'https://example.com/valid',
            'source': 'Test Source'
        }
        
        result = await pipeline_processor._validate_article(valid_article)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_duplicate_detection(self, pipeline_processor):
        """Test duplicate detection functionality."""
        article1 = {
            'title': 'Unique Article Title',
            'content': 'Unique content for the first article.',
            'url': 'https://example.com/article1'
        }
        
        article2 = {
            'title': 'Another Unique Title',
            'content': 'Different content for the second article.',
            'url': 'https://example.com/article2'
        }
        
        # First article should not be duplicate
        assert await pipeline_processor._is_duplicate(article1) is False
        
        # Add to seen articles
        pipeline_processor.seen_urls.add(article1['url'])
        pipeline_processor.seen_articles.append(article1)
        
        # Different article should not be duplicate
        assert await pipeline_processor._is_duplicate(article2) is False
        
        # Same URL should be duplicate
        duplicate_article = dict(article1)
        assert await pipeline_processor._is_duplicate(duplicate_article) is True
    
    @pytest.mark.asyncio
    async def test_article_enhancement(self, pipeline_processor):
        """Test article enhancement functionality."""
        article = {
            'title': 'Technology News Update',
            'content': 'This is an article about the latest technology trends and innovations.',
            'url': 'https://example.com/tech-news',
            'source': 'Test Source'
        }
        
        enhanced = await pipeline_processor._enhance_article(article)
        
        # Should have additional fields
        assert 'category' in enhanced
        assert 'keywords' in enhanced
        assert 'sentiment' in enhanced
        assert 'quality_score' in enhanced
        
        # Check quality score is reasonable
        assert 0 <= enhanced['quality_score'] <= 100
    
    @pytest.mark.asyncio
    async def test_process_batch(self, pipeline_processor):
        """Test batch processing of articles."""
        articles = [
            {
                'title': f'Article {i}',
                'content': f'Content for article {i} with sufficient length for validation.',
                'url': f'https://example.com/article{i}',
                'source': 'Test Source'
            }
            for i in range(5)
        ]
        
        results = await pipeline_processor.process_batch(articles)
        
        # Should return processed articles
        assert len(results) <= len(articles)  # Some might be filtered
        
        for article in results:
            assert 'processed_at' in article
            assert 'quality_score' in article


class TestPerformanceMonitor:
    """Test performance monitoring functionality."""
    
    @pytest.fixture
    def performance_monitor(self):
        """Create a test performance monitor."""
        return PerformanceDashboard(update_interval=1)
    
    def test_monitor_initialization(self, performance_monitor):
        """Test monitor initializes correctly."""
        assert performance_monitor.update_interval == 1
        assert performance_monitor.start_time is not None
        assert len(performance_monitor.metrics) == 0
    
    def test_record_article(self, performance_monitor):
        """Test recording article metrics."""
        performance_monitor.record_article('BBC', success=True, response_time=1.5)
        
        assert len(performance_monitor.metrics) == 1
        metric = performance_monitor.metrics[0]
        
        assert metric['source'] == 'BBC'
        assert metric['success'] is True
        assert metric['response_time'] == 1.5
        assert 'timestamp' in metric
    
    def test_get_stats(self, performance_monitor):
        """Test statistics calculation."""
        # Record some test metrics
        sources = ['BBC', 'CNN', 'BBC', 'CNN', 'BBC']
        success_flags = [True, True, False, True, True]
        response_times = [1.0, 1.5, 0.0, 2.0, 1.2]
        
        for source, success, time in zip(sources, success_flags, response_times):
            performance_monitor.record_article(source, success, time)
        
        stats = performance_monitor.get_stats()
        
        assert stats['total_articles'] == 5
        assert stats['successful_articles'] == 4
        assert stats['failed_articles'] == 1
        assert stats['success_rate'] == 0.8
        assert stats['avg_response_time'] > 0
        
        # Check source stats
        assert 'BBC' in stats['sources']
        assert 'CNN' in stats['sources']
        assert stats['sources']['BBC']['total'] == 3
        assert stats['sources']['CNN']['total'] == 2
    
    def test_get_system_info(self, performance_monitor):
        """Test system information retrieval."""
        system_info = performance_monitor.get_system_info()
        
        assert 'cpu_percent' in system_info
        assert 'memory_percent' in system_info
        assert 'memory_used_mb' in system_info
        assert 'memory_total_mb' in system_info
        
        # Values should be reasonable
        assert 0 <= system_info['cpu_percent'] <= 100
        assert 0 <= system_info['memory_percent'] <= 100
        assert system_info['memory_used_mb'] > 0
        assert system_info['memory_total_mb'] > 0


class TestAsyncScraperRunner:
    """Test the async scraper runner functionality."""
    
    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file for testing."""
        config = {
            'async_scraper': {
                'max_concurrent': 3,
                'max_threads': 2,
                'timeout': 10
            },
            'sources': [
                {
                    'name': 'Test Source',
                    'base_url': 'https://example.com',
                    'article_selectors': {
                        'title': 'h1',
                        'content': 'p'
                    },
                    'enabled': True,
                    'requires_js': False
                }
            ],
            'output': {
                'directory': 'test_output',
                'filename_pattern': 'test_{timestamp}.json'
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            temp_file = f.name
        
        yield temp_file
        
        # Cleanup
        Path(temp_file).unlink(missing_ok=True)
    
    def test_runner_initialization(self, temp_config_file):
        """Test runner initializes with config file."""
        runner = AsyncScraperRunner(temp_config_file)
        
        assert runner.config is not None
        assert runner.config['async_scraper']['max_concurrent'] == 3
        assert len(runner.config['sources']) == 1
    
    @pytest.mark.asyncio
    async def test_runner_execution(self, temp_config_file):
        """Test runner can execute scraping process."""
        runner = AsyncScraperRunner(temp_config_file)
        
        # Mock the scraper engine to avoid actual HTTP requests
        with patch.object(runner, '_create_scraper_engine') as mock_create:
            mock_engine = AsyncMock()
            mock_engine.scrape_articles = AsyncMock(return_value=[
                {
                    'title': 'Test Article',
                    'content': 'Test content',
                    'url': 'https://example.com/test',
                    'source': 'Test Source'
                }
            ])
            mock_engine.cleanup = AsyncMock()
            mock_create.return_value = mock_engine
            
            # Run with test mode
            results = await runner.run(
                test_mode=True,
                max_articles=5,
                enable_monitoring=False
            )
            
            assert len(results) == 1
            assert results[0]['title'] == 'Test Article'


class TestIntegration:
    """Integration tests for the complete async scraper system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_scraping(self):
        """Test complete end-to-end scraping process."""
        # This test would require actual network access or extensive mocking
        # For now, we'll test that all components can be initialized together
        
        config = {
            'async_scraper': {
                'max_concurrent': 2,
                'max_threads': 2,
                'timeout': 5
            },
            'sources': [
                {
                    'name': 'Test Source',
                    'base_url': 'https://httpbin.org',
                    'article_selectors': {
                        'title': 'h1',
                        'content': 'p'
                    },
                    'enabled': True,
                    'requires_js': False
                }
            ],
            'pipelines': {
                'validation': {'enabled': True},
                'duplicate_detection': {'enabled': True},
                'enhancement': {'enabled': True}
            }
        }
        
        # Test that all components can be created
        engine = AsyncNewsScraperEngine(config)
        pipeline = AsyncPipelineProcessor(config)
        monitor = PerformanceDashboard()
        
        # Cleanup
        await engine.cleanup()
        
        assert engine is not None
        assert pipeline is not None
        assert monitor is not None
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self):
        """Test system performance under simulated load."""
        config = {
            'async_scraper': {
                'max_concurrent': 5,
                'max_threads': 3,
                'timeout': 1
            },
            'sources': [],
            'pipelines': {
                'validation': {'enabled': True},
                'duplicate_detection': {'enabled': True},
                'enhancement': {'enabled': True}
            }
        }
        
        engine = AsyncNewsScraperEngine(config)
        pipeline = AsyncPipelineProcessor(config)
        monitor = PerformanceDashboard()
        
        # Simulate processing many articles
        test_articles = [
            {
                'title': f'Article {i}',
                'content': f'Content for article number {i} with sufficient length.',
                'url': f'https://example.com/article{i}',
                'source': 'Test Source',
                'timestamp': time.time()
            }
            for i in range(20)
        ]
        
        start_time = time.time()
        
        # Process articles in batches
        results = []
        for i in range(0, len(test_articles), 5):
            batch = test_articles[i:i+5]
            batch_results = await pipeline.process_batch(batch)
            results.extend(batch_results)
            
            # Record metrics
            for article in batch_results:
                monitor.record_article(
                    article['source'], 
                    success=True, 
                    response_time=0.1
                )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Cleanup
        await engine.cleanup()
        
        # Performance assertions
        assert len(results) > 0
        assert processing_time < 10  # Should process quickly
        
        stats = monitor.get_stats()
        assert stats['total_articles'] > 0
        assert stats['success_rate'] > 0


if __name__ == '__main__':
    # Run the tests
    pytest.main([__file__, '-v'])
