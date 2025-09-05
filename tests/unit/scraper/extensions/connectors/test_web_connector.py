"""
Test cases for web scraping connector functionality.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from aioresponses import aioresponses

from src.scraper.extensions.connectors.web_connector import WebScrapingConnector
from src.scraper.extensions.connectors.base import ConnectionError


class TestWebScrapingConnector:
    """Test cases for WebScrapingConnector class."""

    def test_init(self):
        """Test web scraping connector initialization."""
        config = {"base_url": "https://example.com"}
        auth_config = {"username": "test_user"}
        
        connector = WebScrapingConnector(config, auth_config)
        
        assert connector.config == config
        assert connector.auth_config == auth_config
        assert connector._session is None
        assert connector._headers == {}

    def test_validate_config_success(self):
        """Test successful config validation."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_missing_url(self):
        """Test config validation with missing URL."""
        config = {}
        connector = WebScrapingConnector(config)
        
        result = connector.validate_config()
        assert result is False

    def test_validate_config_invalid_url(self):
        """Test config validation with invalid URL."""
        config = {"base_url": "invalid-url"}
        connector = WebScrapingConnector(config)
        
        result = connector.validate_config()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful web connection."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com", status=200, payload="OK")
            
            result = await connector.connect()
            
            assert result is True
            assert connector.is_connected
            assert connector._session is not None
            assert "User-Agent" in connector._headers

    @pytest.mark.asyncio
    async def test_connect_with_custom_headers(self):
        """Test connection with custom headers."""
        config = {
            "base_url": "https://example.com",
            "headers": {"Custom-Header": "custom-value"}
        }
        connector = WebScrapingConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com", status=200, payload="OK")
            
            result = await connector.connect()
            
            assert result is True
            assert connector._headers["Custom-Header"] == "custom-value"

    @pytest.mark.asyncio
    async def test_connect_forbidden_still_succeeds(self):
        """Test connection with 403 status (bot detection) still succeeds."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com", status=403)
            
            result = await connector.connect()
            
            assert result is True
            assert connector.is_connected

    @pytest.mark.asyncio
    async def test_connect_http_error(self):
        """Test connection with HTTP error."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com", status=500)
            
            result = await connector.connect()
            
            assert result is False
            assert not connector.is_connected
            assert connector.last_error is not None

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test web disconnection."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.closed = False
        connector._session = mock_session
        connector._connected = True
        
        await connector.disconnect()
        
        assert not connector.is_connected
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_data_with_container_selector(self):
        """Test fetching data using container selector."""
        config = {
            "base_url": "https://example.com",
            "selectors": {
                "container": ".article",
                "title": "h2",
                "content": "p"
            }
        }
        connector = WebScrapingConnector(config)
        
        html_content = """
        <html>
            <body>
                <div class="article">
                    <h2>Article 1 Title</h2>
                    <p>Article 1 content</p>
                </div>
                <div class="article">
                    <h2>Article 2 Title</h2>
                    <p>Article 2 content</p>
                </div>
            </body>
        </html>
        """
        
        with aioresponses() as m:
            m.get("https://example.com", status=200, body=html_content, repeat=True)
            
            await connector.connect()
            data = await connector.fetch_data()
            
            assert len(data) == 2
            assert data[0]["title"] == "Article 1 Title"
            assert data[0]["content"] == "Article 1 content"
            assert data[1]["title"] == "Article 2 Title"
            assert "source_url" in data[0]

    @pytest.mark.asyncio
    async def test_fetch_data_single_item_extraction(self):
        """Test fetching data without container selector."""
        config = {
            "base_url": "https://example.com"
        }
        connector = WebScrapingConnector(config)
        
        html_content = """
        <html>
            <body>
                <h1>Main Title</h1>
                <p>Main content</p>
            </body>
        </html>
        """
        
        selectors = {
            "title": "h1",
            "content": "p"
        }
        
        with aioresponses() as m:
            m.get("https://example.com/page", status=200, body=html_content)
            
            await connector.connect()
            data = await connector.fetch_data("page", selectors=selectors)
            
            assert len(data) == 1
            assert data[0]["title"] == "Main Title"
            assert data[0]["content"] == "Main content"

    @pytest.mark.asyncio
    async def test_fetch_data_with_attributes(self):
        """Test fetching data with attribute extraction."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        html_content = """
        <html>
            <body>
                <a href="https://example.com/link1" title="Link 1">Link text</a>
                <img src="image.jpg" alt="Image description">
            </body>
        </html>
        """
        
        selectors = {
            "link_url": {"selector": "a", "attribute": "href"},
            "link_title": {"selector": "a", "attribute": "title"},
            "image_src": {"selector": "img", "attribute": "src"},
            "image_alt": {"selector": "img", "attribute": "alt"}
        }
        
        with aioresponses() as m:
            m.get("https://example.com/page", status=200, body=html_content)
            
            await connector.connect()
            data = await connector.fetch_data("page", selectors=selectors)
            
            assert len(data) == 1
            assert data[0]["link_url"] == "https://example.com/link1"
            assert data[0]["link_title"] == "Link 1"
            assert data[0]["image_src"] == "image.jpg"
            assert data[0]["image_alt"] == "Image description"

    @pytest.mark.asyncio
    async def test_fetch_data_multiple_elements(self):
        """Test fetching data with multiple matching elements."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        html_content = """
        <html>
            <body>
                <p>Paragraph 1</p>
                <p>Paragraph 2</p>
                <p>Paragraph 3</p>
            </body>
        </html>
        """
        
        selectors = {
            "paragraphs": "p"
        }
        
        with aioresponses() as m:
            m.get("https://example.com/page", status=200, body=html_content)
            
            await connector.connect()
            data = await connector.fetch_data("page", selectors=selectors)
            
            assert len(data) == 1
            assert isinstance(data[0]["paragraphs"], list)
            assert len(data[0]["paragraphs"]) == 3
            assert "Paragraph 1" in data[0]["paragraphs"]

    @pytest.mark.asyncio
    async def test_fetch_data_not_connected(self):
        """Test fetching data when not connected."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to web source"):
            await connector.fetch_data()

    @pytest.mark.asyncio
    async def test_fetch_data_http_error(self):
        """Test fetching data with HTTP error."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com", status=200, payload="OK")  # For connect
            m.get("https://example.com/page", status=404)  # For fetch_data
            
            await connector.connect()
            data = await connector.fetch_data("page")
            
            # Should return empty list on HTTP error
            assert data == []

    def test_validate_data_format_success(self):
        """Test successful data format validation."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        data = {
            "source_url": "https://example.com/page",
            "title": "Test Title"
        }
        
        result = connector.validate_data_format(data)
        assert result is True

    def test_validate_data_format_missing_required_fields(self):
        """Test data format validation with missing required fields."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        data = {"title": "Test Title"}  # Missing source_url
        
        result = connector.validate_data_format(data)
        assert result is False

    def test_validate_data_format_non_dict(self):
        """Test data format validation with non-dictionary data."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        result = connector.validate_data_format("not a dict")
        assert result is False

    @pytest.mark.asyncio
    async def test_extract_links(self):
        """Test link extraction functionality."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        html_content = """
        <html>
            <body>
                <a href="/relative-link">Relative Link</a>
                <a href="https://example.com/absolute-link">Absolute Link</a>
                <a href="https://other.com/external-link">External Link</a>
                <a href="/duplicate-link">Link 1</a>
                <a href="/duplicate-link">Link 2</a>
            </body>
        </html>
        """
        
        with aioresponses() as m:
            m.get("https://example.com", status=200, payload="OK")  # For connect
            m.get("https://example.com/page", status=200, body=html_content)
            
            await connector.connect()
            links = await connector.extract_links("page")
            
            assert len(links) == 4  # Duplicates should be removed
            assert "https://example.com/relative-link" in links
            assert "https://example.com/absolute-link" in links
            assert "https://other.com/external-link" in links

    @pytest.mark.asyncio
    async def test_extract_links_not_connected(self):
        """Test link extraction when not connected."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to web source"):
            await connector.extract_links()

    @pytest.mark.asyncio
    async def test_check_robots_txt_exists(self):
        """Test robots.txt checking when it exists."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        robots_content = """
        User-agent: *
        Disallow: /admin/
        Disallow: /private/
        Allow: /public/
        Crawl-delay: 1
        """
        
        with aioresponses() as m:
            m.get("https://example.com", status=200, payload="OK")  # For connect
            m.get("https://example.com/robots.txt", status=200, body=robots_content)
            
            await connector.connect()
            robots_info = await connector.check_robots_txt()
            
            assert robots_info["exists"] is True
            assert "/admin/" in robots_info["disallowed_paths"]
            assert "/public/" in robots_info["allowed_paths"]
            assert robots_info["crawl_delay"] == 1.0

    @pytest.mark.asyncio
    async def test_check_robots_txt_not_exists(self):
        """Test robots.txt checking when it doesn't exist."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com", status=200, payload="OK")  # For connect
            m.get("https://example.com/robots.txt", status=404)
            
            await connector.connect()
            robots_info = await connector.check_robots_txt()
            
            assert robots_info["exists"] is False

    @pytest.mark.asyncio
    async def test_fetch_data_with_delay(self):
        """Test fetching data with rate limiting delay."""
        config = {
            "base_url": "https://example.com",
            "delay": 0.1  # Small delay for testing
        }
        connector = WebScrapingConnector(config)
        
        html_content = "<html><body><p>Test</p></body></html>"
        
        with aioresponses() as m:
            m.get("https://example.com", status=200, body=html_content, repeat=True)
            
            await connector.connect()
            
            import time
            start_time = time.time()
            data = await connector.fetch_data(max_pages=2)
            end_time = time.time()
            
            # Should take at least the delay time
            assert (end_time - start_time) >= 0.1

    @pytest.mark.asyncio
    async def test_fetch_data_with_pagination(self):
        """Test fetching data with pagination following."""
        config = {"base_url": "https://example.com"}
        connector = WebScrapingConnector(config)
        
        page1_html = """
        <html>
            <body>
                <div class="article">
                    <h2>Article 1</h2>
                </div>
                <a href="/page2" class="next">Next</a>
            </body>
        </html>
        """
        
        page2_html = """
        <html>
            <body>
                <div class="article">
                    <h2>Article 2</h2>
                </div>
            </body>
        </html>
        """
        
        selectors = {
            "container": ".article",
            "title": "h2",
            "next_page": ".next"
        }
        
        with aioresponses() as m:
            m.get("https://example.com", status=200, body=page1_html, repeat=True)
            m.get("https://example.com/page", status=200, body=page1_html)
            m.get("https://example.com/page2", status=200, body=page2_html)
            
            await connector.connect()
            data = await connector.fetch_data("page", selectors=selectors, 
                                            follow_links=True, max_pages=2)
            
            assert len(data) == 2  # Should have articles from both pages
            assert any("Article 1" in item.get("title", "") for item in data)
            assert any("Article 2" in item.get("title", "") for item in data)
