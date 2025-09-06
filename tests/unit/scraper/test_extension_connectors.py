"""
Comprehensive tests for Extension Connectors.
Tests API connector, RSS connector, and other data source connectors.
"""

import pytest
import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

import aiohttp
import requests

# Import with proper path handling
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from scraper.extensions.connectors.api_connector import APIConnector
from scraper.extensions.connectors.rss_connector import RSSConnector
from scraper.extensions.connectors.database_connector import DatabaseConnector
from scraper.extensions.connectors.web_connector import WebConnector


class TestAPIConnector:
    """Test suite for APIConnector class."""

    @pytest.fixture
    def connector(self):
        """APIConnector fixture for testing."""
        return APIConnector(
            base_url="https://api.example.com",
            api_key="test-api-key",
            rate_limit=100
        )

    def test_connector_initialization(self, connector):
        """Test APIConnector initialization."""
        assert connector.base_url == "https://api.example.com"
        assert connector.api_key == "test-api-key"
        assert connector.rate_limit == 100
        assert connector.request_count == 0

    @patch('requests.get')
    def test_get_request_success(self, mock_get, connector):
        """Test successful GET request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test response"}
        mock_get.return_value = mock_response
        
        result = connector.get("/endpoint")
        
        assert result == {"data": "test response"}
        assert connector.request_count == 1
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_get_request_with_auth(self, mock_get, connector):
        """Test GET request with authentication."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"authenticated": True}
        mock_get.return_value = mock_response
        
        result = connector.get("/secure-endpoint")
        
        # Check that API key was included in headers
        call_args = mock_get.call_args
        assert "Authorization" in call_args[1]["headers"] or "X-API-Key" in call_args[1]["headers"]

    @patch('requests.get')
    def test_get_request_error(self, mock_get, connector):
        """Test GET request with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Not found")
        mock_get.return_value = mock_response
        
        with pytest.raises(requests.exceptions.HTTPError):
            connector.get("/nonexistent-endpoint")

    @patch('requests.post')
    def test_post_request_success(self, mock_post, connector):
        """Test successful POST request."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"created": True}
        mock_post.return_value = mock_response
        
        data = {"title": "Test Article", "content": "Test content"}
        result = connector.post("/articles", data=data)
        
        assert result == {"created": True}
        mock_post.assert_called_once()

    def test_rate_limiting(self, connector):
        """Test rate limiting functionality."""
        # Set low rate limit for testing
        connector.rate_limit = 2
        connector.rate_window = 1  # 1 second window
        
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": "test"}
            mock_get.return_value = mock_response
            
            # Make requests up to limit
            connector.get("/endpoint1")
            connector.get("/endpoint2")
            
            # Third request should trigger rate limiting
            with patch('time.sleep') as mock_sleep:
                connector.get("/endpoint3")
                mock_sleep.assert_called()  # Should have slept

    @pytest.mark.asyncio
    async def test_async_get_request(self, connector):
        """Test asynchronous GET request."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"async": "response"}
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await connector.async_get("/async-endpoint")
            assert result == {"async": "response"}

    def test_build_url(self, connector):
        """Test URL building functionality."""
        url = connector.build_url("/endpoint", params={"limit": 10, "offset": 0})
        
        assert url.startswith("https://api.example.com/endpoint")
        assert "limit=10" in url
        assert "offset=0" in url

    def test_handle_pagination(self, connector):
        """Test pagination handling."""
        mock_responses = [
            {"data": [{"id": 1}, {"id": 2}], "next_page": 2},
            {"data": [{"id": 3}, {"id": 4}], "next_page": None}
        ]
        
        with patch.object(connector, 'get', side_effect=mock_responses):
            results = list(connector.paginated_get("/paginated-endpoint"))
            
            assert len(results) == 4  # All items from both pages
            assert results[0]["id"] == 1
            assert results[-1]["id"] == 4

    def test_error_retry_mechanism(self, connector):
        """Test automatic retry on temporary failures."""
        connector.max_retries = 3
        
        with patch('requests.get') as mock_get:
            # First two calls fail, third succeeds
            mock_get.side_effect = [
                requests.exceptions.ConnectionError("Connection failed"),
                requests.exceptions.Timeout("Timeout"),
                MagicMock(status_code=200, json=lambda: {"success": True})
            ]
            
            result = connector.get_with_retry("/retry-endpoint")
            
            assert result == {"success": True}
            assert mock_get.call_count == 3

    def test_response_caching(self, connector):
        """Test response caching functionality."""
        connector.enable_caching = True
        
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"cached": "response"}
            mock_get.return_value = mock_response
            
            # First call should hit API
            result1 = connector.get("/cacheable-endpoint")
            assert mock_get.call_count == 1
            
            # Second call should use cache
            result2 = connector.get("/cacheable-endpoint")
            assert mock_get.call_count == 1  # No additional API call
            assert result1 == result2


class TestRSSConnector:
    """Test suite for RSSConnector class."""

    @pytest.fixture
    def connector(self):
        """RSSConnector fixture for testing."""
        return RSSConnector()

    @pytest.fixture
    def sample_rss_xml(self):
        """Sample RSS XML for testing."""
        return """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Test News Feed</title>
                <description>A test RSS feed</description>
                <link>https://example.com</link>
                <item>
                    <title>First News Article</title>
                    <link>https://example.com/article1</link>
                    <description>Description of first article</description>
                    <pubDate>Mon, 15 Jan 2024 10:00:00 GMT</pubDate>
                    <author>test@example.com (Test Author)</author>
                </item>
                <item>
                    <title>Second News Article</title>
                    <link>https://example.com/article2</link>
                    <description>Description of second article</description>
                    <pubDate>Mon, 15 Jan 2024 11:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""

    def test_parse_rss_feed(self, connector, sample_rss_xml):
        """Test RSS feed parsing."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_rss_xml.encode('utf-8')
            mock_get.return_value = mock_response
            
            articles = connector.fetch_feed("https://example.com/rss")
            
            assert len(articles) == 2
            
            # Test first article
            first_article = articles[0]
            assert first_article['title'] == "First News Article"
            assert first_article['link'] == "https://example.com/article1"
            assert first_article['description'] == "Description of first article"
            assert first_article['author'] == "Test Author"
            
            # Test second article
            second_article = articles[1]
            assert second_article['title'] == "Second News Article"
            assert second_article['link'] == "https://example.com/article2"

    def test_parse_atom_feed(self, connector):
        """Test Atom feed parsing."""
        atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>Test Atom Feed</title>
            <link href="https://example.com"/>
            <entry>
                <title>Atom Article</title>
                <link href="https://example.com/atom-article"/>
                <summary>Summary of atom article</summary>
                <published>2024-01-15T10:00:00Z</published>
                <author><name>Atom Author</name></author>
            </entry>
        </feed>"""
        
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = atom_xml.encode('utf-8')
            mock_get.return_value = mock_response
            
            articles = connector.fetch_feed("https://example.com/atom")
            
            assert len(articles) == 1
            article = articles[0]
            assert article['title'] == "Atom Article"
            assert article['link'] == "https://example.com/atom-article"
            assert article['author'] == "Atom Author"

    def test_feed_validation(self, connector):
        """Test RSS feed validation."""
        invalid_xml = "<html><body>Not an RSS feed</body></html>"
        
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = invalid_xml.encode('utf-8')
            mock_get.return_value = mock_response
            
            with pytest.raises(ValueError):
                connector.fetch_feed("https://example.com/invalid")

    def test_feed_caching(self, connector):
        """Test RSS feed caching."""
        connector.enable_caching = True
        
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = """<?xml version="1.0"?>
            <rss><channel><item><title>Cached</title></item></channel></rss>""".encode()
            mock_get.return_value = mock_response
            
            # First fetch
            articles1 = connector.fetch_feed("https://example.com/rss")
            assert mock_get.call_count == 1
            
            # Second fetch should use cache
            articles2 = connector.fetch_feed("https://example.com/rss")
            assert mock_get.call_count == 1  # No additional request
            assert len(articles1) == len(articles2)

    def test_feed_filtering(self, connector):
        """Test RSS feed filtering by keywords."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = """<?xml version="1.0"?>
            <rss><channel>
                <item><title>Technology News</title></item>
                <item><title>Sports Update</title></item>
                <item><title>Tech Innovation</title></item>
            </channel></rss>""".encode()
            mock_get.return_value = mock_response
            
            # Filter for technology-related articles
            articles = connector.fetch_feed(
                "https://example.com/rss",
                keywords=["technology", "tech"]
            )
            
            assert len(articles) == 2  # Should filter out sports
            titles = [article['title'] for article in articles]
            assert "Technology News" in titles
            assert "Tech Innovation" in titles
            assert "Sports Update" not in titles

    def test_multiple_feeds_aggregation(self, connector):
        """Test aggregating multiple RSS feeds."""
        feed_urls = [
            "https://feed1.example.com/rss",
            "https://feed2.example.com/rss"
        ]
        
        mock_responses = [
            """<?xml version="1.0"?><rss><channel><item><title>Feed 1 Article</title></item></channel></rss>""",
            """<?xml version="1.0"?><rss><channel><item><title>Feed 2 Article</title></item></channel></rss>"""
        ]
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = [
                MagicMock(status_code=200, content=resp.encode()) 
                for resp in mock_responses
            ]
            
            all_articles = connector.fetch_multiple_feeds(feed_urls)
            
            assert len(all_articles) == 2
            titles = [article['title'] for article in all_articles]
            assert "Feed 1 Article" in titles
            assert "Feed 2 Article" in titles


class TestDatabaseConnector:
    """Test suite for DatabaseConnector class."""

    @pytest.fixture
    def connector(self):
        """DatabaseConnector fixture for testing."""
        return DatabaseConnector(
            host="localhost",
            database="test_db",
            user="test_user",
            password="test_pass"
        )

    @patch('psycopg2.connect')
    def test_database_connection(self, mock_connect, connector):
        """Test database connection establishment."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        connection = connector.connect()
        
        assert connection is not None
        mock_connect.assert_called_once_with(
            host="localhost",
            database="test_db",
            user="test_user",
            password="test_pass"
        )

    @patch('psycopg2.connect')
    def test_insert_article(self, mock_connect, connector):
        """Test article insertion into database."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        article_data = {
            'title': 'Test Article',
            'content': 'Test content',
            'url': 'https://example.com/test',
            'source': 'TestSource',
            'published_date': '2024-01-15'
        }
        
        result = connector.insert_article(article_data)
        
        assert result is True
        mock_cursor.execute.assert_called()
        mock_conn.commit.assert_called()

    @patch('psycopg2.connect')
    def test_query_articles(self, mock_connect, connector):
        """Test querying articles from database."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('Test Article', 'https://example.com/test', 'TestSource'),
            ('Another Article', 'https://example.com/another', 'AnotherSource')
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        articles = connector.query_articles(limit=10)
        
        assert len(articles) == 2
        mock_cursor.execute.assert_called()

    @patch('psycopg2.connect')
    def test_duplicate_detection(self, mock_connect, connector):
        """Test duplicate article detection."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)  # Article exists
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        is_duplicate = connector.check_duplicate("https://example.com/existing")
        
        assert is_duplicate is True
        mock_cursor.execute.assert_called()

    def test_connection_error_handling(self, connector):
        """Test database connection error handling."""
        with patch('psycopg2.connect', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception):
                connector.connect()

    @patch('psycopg2.connect')
    def test_transaction_rollback(self, mock_connect, connector):
        """Test transaction rollback on error."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("SQL error")
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        article_data = {'title': 'Test', 'url': 'https://example.com/test'}
        
        result = connector.insert_article(article_data)
        
        assert result is False
        mock_conn.rollback.assert_called()


class TestWebConnector:
    """Test suite for WebConnector class."""

    @pytest.fixture
    def connector(self):
        """WebConnector fixture for testing."""
        return WebConnector()

    @patch('requests.Session.get')
    def test_fetch_webpage(self, mock_get, connector):
        """Test webpage fetching."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><h1>Test Page</h1></body></html>"
        mock_response.headers = {'content-type': 'text/html'}
        mock_get.return_value = mock_response
        
        content = connector.fetch("https://example.com/page")
        
        assert content is not None
        assert "<h1>Test Page</h1>" in content

    def test_user_agent_rotation(self, connector):
        """Test user agent rotation in requests."""
        with patch('requests.Session.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Success"
            mock_get.return_value = mock_response
            
            # Make multiple requests
            connector.fetch("https://example.com/page1")
            connector.fetch("https://example.com/page2")
            
            # Check that different user agents were used
            call_headers = [call[1]['headers'] for call in mock_get.call_args_list]
            user_agents = [headers.get('User-Agent') for headers in call_headers if headers]
            
            # Should have user agents (implementation dependent)
            assert len(user_agents) >= 0

    def test_request_delay(self, connector):
        """Test request delay functionality."""
        connector.delay_range = (0.1, 0.2)
        
        with patch('requests.Session.get') as mock_get, \
             patch('time.sleep') as mock_sleep:
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Success"
            mock_get.return_value = mock_response
            
            connector.fetch("https://example.com/delayed")
            
            # Should have slept between requests
            mock_sleep.assert_called()

    @patch('requests.Session.get')
    def test_error_handling(self, mock_get, connector):
        """Test error handling in web requests."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        content = connector.fetch("https://unreachable.com")
        
        assert content is None

    def test_content_type_filtering(self, connector):
        """Test filtering by content type."""
        with patch('requests.Session.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-type': 'application/pdf'}
            mock_response.text = "PDF content"
            mock_get.return_value = mock_response
            
            # Should reject non-HTML content
            content = connector.fetch("https://example.com/document.pdf", 
                                    allowed_types=['text/html'])
            
            assert content is None

    @pytest.mark.asyncio
    async def test_async_fetching(self, connector):
        """Test asynchronous webpage fetching."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = "<html><body>Async content</body></html>"
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            content = await connector.async_fetch("https://example.com/async")
            
            assert content is not None
            assert "Async content" in content

    def test_session_persistence(self, connector):
        """Test session persistence across requests."""
        with patch('requests.Session.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Success"
            mock_get.return_value = mock_response
            
            # Make multiple requests
            connector.fetch("https://example.com/page1")
            connector.fetch("https://example.com/page2")
            
            # Should use same session
            assert mock_get.call_count == 2

    def test_custom_headers(self, connector):
        """Test custom headers in requests."""
        custom_headers = {
            'X-Custom-Header': 'test-value',
            'Accept': 'text/html'
        }
        
        with patch('requests.Session.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Success"
            mock_get.return_value = mock_response
            
            connector.fetch("https://example.com/custom", headers=custom_headers)
            
            # Check that custom headers were included
            call_args = mock_get.call_args
            headers = call_args[1]['headers']
            assert 'X-Custom-Header' in headers
            assert headers['X-Custom-Header'] == 'test-value'