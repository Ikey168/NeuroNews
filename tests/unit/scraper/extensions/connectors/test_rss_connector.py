"""
Test cases for RSS connector functionality.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
import feedparser
from aioresponses import aioresponses

from src.scraper.extensions.connectors.rss_connector import RSSConnector
from src.scraper.extensions.connectors.base import ConnectionError, DataFormatError


class TestRSSConnector:
    """Test cases for RSSConnector class."""

    def test_init(self):
        """Test RSS connector initialization."""
        config = {"url": "https://example.com/rss.xml"}
        auth_config = {"username": "test_user"}
        
        connector = RSSConnector(config, auth_config)
        
        assert connector.config == config
        assert connector.auth_config == auth_config
        assert connector._session is None

    def test_validate_config_success(self):
        """Test successful config validation."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_missing_url(self):
        """Test config validation with missing URL."""
        config = {}
        connector = RSSConnector(config)
        
        result = connector.validate_config()
        assert result is False

    def test_validate_config_invalid_url(self):
        """Test config validation with invalid URL."""
        config = {"url": "invalid-url"}
        connector = RSSConnector(config)
        
        result = connector.validate_config()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful RSS connection."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=200, payload="RSS content")
            
            result = await connector.connect()
            
            assert result is True
            assert connector.is_connected
            assert connector._session is not None

    @pytest.mark.asyncio
    async def test_connect_http_error(self):
        """Test RSS connection with HTTP error."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=404)
            
            result = await connector.connect()
            
            assert result is False
            assert not connector.is_connected
            assert connector.last_error is not None

    @pytest.mark.asyncio
    async def test_connect_network_error(self):
        """Test RSS connection with network error."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", exception=aiohttp.ClientError("Network error"))
            
            result = await connector.connect()
            
            assert result is False
            assert not connector.is_connected
            assert connector.last_error is not None

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test RSS disconnection."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.closed = False
        connector._session = mock_session
        connector._connected = True
        
        await connector.disconnect()
        
        assert not connector.is_connected
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_data_success(self):
        """Test successful RSS data fetching."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        rss_content = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test RSS</title>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article1</link>
                    <description>Test description</description>
                    <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>"""
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=200, body=rss_content)
            
            await connector.connect()
            data = await connector.fetch_data()
            
            assert len(data) == 1
            assert data[0]["title"] == "Test Article"
            assert data[0]["link"] == "https://example.com/article1"
            assert data[0]["source"] == "https://example.com/rss.xml"

    @pytest.mark.asyncio
    async def test_fetch_data_with_limit(self):
        """Test RSS data fetching with limit."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        rss_content = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test RSS</title>
                <item>
                    <title>Article 1</title>
                    <link>https://example.com/article1</link>
                    <description>Description 1</description>
                </item>
                <item>
                    <title>Article 2</title>
                    <link>https://example.com/article2</link>
                    <description>Description 2</description>
                </item>
            </channel>
        </rss>"""
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=200, body=rss_content)
            
            await connector.connect()
            data = await connector.fetch_data(limit=1)
            
            assert len(data) == 1
            assert data[0]["title"] == "Article 1"

    @pytest.mark.asyncio
    async def test_fetch_data_not_connected(self):
        """Test fetching data when not connected."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to RSS feed"):
            await connector.fetch_data()

    @pytest.mark.asyncio
    async def test_fetch_data_http_error(self):
        """Test fetching data with HTTP error."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=200, payload="OK")  # For connect
            m.get("https://example.com/rss.xml", status=404)  # For fetch_data
            
            await connector.connect()
            
            with pytest.raises(ConnectionError, match="HTTP 404"):
                await connector.fetch_data()

    def test_validate_data_format_success(self):
        """Test successful data format validation."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        data = {
            "title": "Test Article",
            "link": "https://example.com/article1",
            "source": "https://example.com/rss.xml"
        }
        
        result = connector.validate_data_format(data)
        assert result is True

    def test_validate_data_format_missing_required_fields(self):
        """Test data format validation with missing required fields."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        data = {"description": "Test description"}
        
        result = connector.validate_data_format(data)
        assert result is False

    def test_validate_data_format_non_dict(self):
        """Test data format validation with non-dictionary data."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        result = connector.validate_data_format("not a dict")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_feed_info_success(self):
        """Test successful feed info retrieval."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        rss_content = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test RSS Feed</title>
                <description>Test feed description</description>
                <link>https://example.com</link>
                <language>en-us</language>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article1</link>
                </item>
            </channel>
        </rss>"""
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=200, body=rss_content)
            
            await connector.connect()
            feed_info = await connector.get_feed_info()
            
            assert feed_info["title"] == "Test RSS Feed"
            assert feed_info["description"] == "Test feed description"
            assert feed_info["link"] == "https://example.com"
            assert feed_info["language"] == "en-us"
            assert feed_info["entries_count"] == 1

    @pytest.mark.asyncio
    async def test_get_feed_info_not_connected(self):
        """Test getting feed info when not connected."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to RSS feed"):
            await connector.get_feed_info()

    @pytest.mark.asyncio
    async def test_check_feed_validity_success(self):
        """Test successful feed validity check."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        rss_content = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Valid RSS</title>
                <item>
                    <title>Article</title>
                </item>
            </channel>
        </rss>"""
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=200, body=rss_content, repeat=True)
            
            result = await connector.check_feed_validity()
            
            assert result is True

    @pytest.mark.asyncio
    async def test_check_feed_validity_invalid_rss(self):
        """Test feed validity check with invalid RSS."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=200, body="Not valid RSS", repeat=True)
            
            result = await connector.check_feed_validity()
            
            assert result is False

    @pytest.mark.asyncio
    async def test_check_feed_validity_http_error(self):
        """Test feed validity check with HTTP error."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=404, repeat=True)
            
            result = await connector.check_feed_validity()
            
            assert result is False

    @pytest.mark.asyncio
    async def test_fetch_data_with_malformed_rss(self):
        """Test fetching data with malformed RSS that feedparser can handle."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        # Malformed RSS but parseable
        rss_content = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test RSS</title>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article1</link>
                    <!-- Missing closing tag for item -->
            </channel>
        </rss>"""
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=200, body=rss_content)
            
            await connector.connect()
            
            # Should handle gracefully with feedparser's bozo detection
            data = await connector.fetch_data()
            
            # Should still parse what it can
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_connect_with_existing_session(self):
        """Test connecting when session already exists."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        # Create existing session
        mock_session = AsyncMock()
        mock_session.closed = False
        connector._session = mock_session
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected

    def test_validate_config_with_timeout(self):
        """Test config validation with timeout setting."""
        config = {
            "url": "https://example.com/rss.xml",
            "timeout": 30
        }
        connector = RSSConnector(config)
        
        result = connector.validate_config()
        assert result is True

    @pytest.mark.asyncio
    async def test_fetch_data_with_tags(self):
        """Test fetching RSS data with tags."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        rss_content = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test RSS</title>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article1</link>
                    <description>Test description</description>
                    <category>Technology</category>
                    <category>News</category>
                </item>
            </channel>
        </rss>"""
        
        with aioresponses() as m:
            m.get("https://example.com/rss.xml", status=200, body=rss_content)
            
            await connector.connect()
            data = await connector.fetch_data()
            
            assert len(data) == 1
            # Tags should be processed from categories
            assert isinstance(data[0]["tags"], list)

    @pytest.mark.asyncio
    async def test_disconnect_with_no_session(self):
        """Test disconnecting when no session exists."""
        config = {"url": "https://example.com/rss.xml"}
        connector = RSSConnector(config)
        
        # Should not raise error
        await connector.disconnect()
        
        assert not connector.is_connected
