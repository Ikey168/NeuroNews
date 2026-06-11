"""
Test cases for social media connector functionality.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from aioresponses import aioresponses

from src.scraper.extensions.connectors.social_media_connector import SocialMediaConnector
from src.scraper.extensions.connectors.base import ConnectionError, AuthenticationError


class TestSocialMediaConnector:
    """Test cases for SocialMediaConnector class."""

    def test_init(self):
        """Test social media connector initialization."""
        config = {"platform": "twitter"}
        auth_config = {"bearer_token": "test_token"}
        
        connector = SocialMediaConnector(config, auth_config)
        
        assert connector.config == config
        assert connector.auth_config == auth_config
        assert connector.platform == "twitter"
        assert connector._session is None

    def test_validate_config_twitter_success(self):
        """Test successful config validation for Twitter."""
        config = {"platform": "twitter"}
        auth_config = {"bearer_token": "test_token"}
        connector = SocialMediaConnector(config, auth_config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_reddit_success(self):
        """Test successful config validation for Reddit."""
        config = {"platform": "reddit"}
        auth_config = {"client_id": "test_id", "client_secret": "test_secret"}
        connector = SocialMediaConnector(config, auth_config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_facebook_success(self):
        """Test successful config validation for Facebook."""
        config = {"platform": "facebook"}
        auth_config = {"access_token": "test_token"}
        connector = SocialMediaConnector(config, auth_config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_missing_platform(self):
        """Test config validation with missing platform."""
        config = {}
        connector = SocialMediaConnector(config)
        
        result = connector.validate_config()
        assert result is False

    def test_validate_config_twitter_missing_auth(self):
        """Test Twitter config validation with missing auth."""
        config = {"platform": "twitter"}
        auth_config = {}
        connector = SocialMediaConnector(config, auth_config)
        
        result = connector.validate_config()
        assert result is False

    def test_validate_config_reddit_missing_auth(self):
        """Test Reddit config validation with missing auth."""
        config = {"platform": "reddit"}
        auth_config = {"client_id": "test_id"}  # Missing client_secret
        connector = SocialMediaConnector(config, auth_config)
        
        result = connector.validate_config()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_twitter_success(self):
        """Test successful Twitter connection."""
        config = {"platform": "twitter"}
        auth_config = {"bearer_token": "test_token"}
        connector = SocialMediaConnector(config, auth_config)
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected
        assert connector._headers["Authorization"] == "Bearer test_token"

    @pytest.mark.asyncio
    async def test_connect_reddit_success(self):
        """Test successful Reddit connection."""
        config = {"platform": "reddit"}
        auth_config = {"client_id": "test_id", "client_secret": "test_secret"}
        connector = SocialMediaConnector(config, auth_config)
        
        token_response = {"access_token": "reddit_token", "token_type": "bearer"}
        
        with aioresponses() as m:
            m.post("https://www.reddit.com/api/v1/access_token", 
                   status=200, payload=token_response)
            
            result = await connector.connect()
            
            assert result is True
            assert connector.is_connected
            assert "Bearer reddit_token" in connector._headers["Authorization"]

    @pytest.mark.asyncio
    async def test_connect_reddit_auth_failure(self):
        """Test Reddit connection with authentication failure."""
        config = {"platform": "reddit"}
        auth_config = {"client_id": "test_id", "client_secret": "test_secret"}
        connector = SocialMediaConnector(config, auth_config)
        
        with aioresponses() as m:
            m.post("https://www.reddit.com/api/v1/access_token", status=401)
            
            result = await connector.connect()
            
            assert result is False
            assert not connector.is_connected
            assert isinstance(connector.last_error, ConnectionError)

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test social media disconnection."""
        config = {"platform": "twitter"}
        auth_config = {"bearer_token": "test_token"}
        connector = SocialMediaConnector(config, auth_config)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.closed = False
        connector._session = mock_session
        connector._connected = True
        
        await connector.disconnect()
        
        assert not connector.is_connected
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_data_twitter_success(self):
        """Test successful Twitter data fetching."""
        config = {"platform": "twitter"}
        auth_config = {"bearer_token": "test_token"}
        connector = SocialMediaConnector(config, auth_config)
        connector._connected = True
        connector._session = AsyncMock()
        
        twitter_response = {
            "data": [
                {
                    "id": "123",
                    "text": "Test tweet",
                    "created_at": "2024-01-01T00:00:00.000Z",
                    "author_id": "456",
                    "public_metrics": {"like_count": 10}
                }
            ],
            "includes": {
                "users": [
                    {
                        "id": "456",
                        "username": "testuser",
                        "name": "Test User",
                        "verified": False
                    }
                ]
            }
        }
        
        with aioresponses() as m:
            m.get("https://api.twitter.com/2/tweets/search/recent",
                  status=200, payload=twitter_response)
            
            data = await connector.fetch_data("test query")
            
            assert len(data) == 1
            assert data[0]["id"] == "123"
            assert data[0]["text"] == "Test tweet"
            assert data[0]["author_username"] == "testuser"
            assert data[0]["platform"] == "twitter"

    @pytest.mark.asyncio
    async def test_fetch_data_reddit_success(self):
        """Test successful Reddit data fetching."""
        config = {"platform": "reddit"}
        auth_config = {"client_id": "test_id", "client_secret": "test_secret"}
        connector = SocialMediaConnector(config, auth_config)
        connector._connected = True
        connector._session = AsyncMock()
        
        reddit_response = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "abc123",
                            "title": "Test Reddit Post",
                            "selftext": "Test content",
                            "created_utc": 1704067200,
                            "author": "testuser",
                            "subreddit": "test",
                            "score": 100,
                            "num_comments": 5,
                            "upvote_ratio": 0.95,
                            "permalink": "/r/test/comments/abc123/test_post/"
                        }
                    }
                ]
            }
        }
        
        with aioresponses() as m:
            m.get("https://oauth.reddit.com/r/all/hot",
                  status=200, payload=reddit_response)
            
            data = await connector.fetch_data()
            
            assert len(data) == 1
            assert data[0]["id"] == "abc123"
            assert data[0]["title"] == "Test Reddit Post"
            assert data[0]["author"] == "testuser"
            assert data[0]["platform"] == "reddit"

    @pytest.mark.asyncio
    async def test_fetch_data_facebook_success(self):
        """Test successful Facebook data fetching."""
        config = {"platform": "facebook"}
        auth_config = {"access_token": "test_token"}
        connector = SocialMediaConnector(config, auth_config)
        connector._connected = True
        connector._session = AsyncMock()
        
        facebook_response = {
            "data": [
                {
                    "id": "page_post_123",
                    "message": "Test Facebook post",
                    "created_time": "2024-01-01T00:00:00+0000",
                    "likes": {"summary": {"total_count": 20}},
                    "comments": {"summary": {"total_count": 3}},
                    "shares": {"count": 5}
                }
            ]
        }
        
        with aioresponses() as m:
            m.get("https://graph.facebook.com/v18.0/test_page/posts",
                  status=200, payload=facebook_response)
            
            data = await connector.fetch_data(page_id="test_page")
            
            assert len(data) == 1
            assert data[0]["id"] == "page_post_123"
            assert data[0]["text"] == "Test Facebook post"
            assert data[0]["likes"] == 20
            assert data[0]["platform"] == "facebook"

    @pytest.mark.asyncio
    async def test_fetch_data_not_connected(self):
        """Test fetching data when not connected."""
        config = {"platform": "twitter"}
        connector = SocialMediaConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to twitter"):
            await connector.fetch_data()

    @pytest.mark.asyncio
    async def test_fetch_data_auth_error(self):
        """Test fetching data with authentication error."""
        config = {"platform": "twitter"}
        auth_config = {"bearer_token": "invalid_token"}
        connector = SocialMediaConnector(config, auth_config)
        connector._connected = True
        connector._session = AsyncMock()
        
        with aioresponses() as m:
            m.get("https://api.twitter.com/2/tweets/search/recent", status=401)
            
            with pytest.raises(AuthenticationError, match="Twitter authentication failed"):
                await connector.fetch_data()

    @pytest.mark.asyncio
    async def test_fetch_data_unsupported_platform(self):
        """Test fetching data from unsupported platform."""
        config = {"platform": "unsupported"}
        connector = SocialMediaConnector(config)
        connector._connected = True
        
        with pytest.raises(ConnectionError, match="Unsupported platform"):
            await connector.fetch_data()

    def test_validate_data_format_success(self):
        """Test successful data format validation."""
        config = {"platform": "twitter"}
        connector = SocialMediaConnector(config)
        
        data = {
            "id": "123",
            "text": "Test content",
            "platform": "twitter"
        }
        
        result = connector.validate_data_format(data)
        assert result is True

    def test_validate_data_format_missing_required_fields(self):
        """Test data format validation with missing required fields."""
        config = {"platform": "twitter"}
        connector = SocialMediaConnector(config)
        
        data = {"text": "Test content"}  # Missing id and platform
        
        result = connector.validate_data_format(data)
        assert result is False

    def test_validate_data_format_no_content(self):
        """Test data format validation with no content fields."""
        config = {"platform": "twitter"}
        connector = SocialMediaConnector(config)
        
        data = {
            "id": "123",
            "platform": "twitter"
            # Missing text, title, or message
        }
        
        result = connector.validate_data_format(data)
        assert result is False

    def test_validate_data_format_non_dict(self):
        """Test data format validation with non-dictionary data."""
        config = {"platform": "twitter"}
        connector = SocialMediaConnector(config)
        
        result = connector.validate_data_format("not a dict")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_platform_info_twitter(self):
        """Test getting platform info for Twitter."""
        config = {"platform": "twitter"}
        connector = SocialMediaConnector(config)
        
        info = await connector.get_platform_info()
        
        assert "rate_limit" in info
        assert "max_results_per_request" in info
        assert info["max_results_per_request"] == 100

    @pytest.mark.asyncio
    async def test_get_platform_info_reddit(self):
        """Test getting platform info for Reddit."""
        config = {"platform": "reddit"}
        connector = SocialMediaConnector(config)
        
        info = await connector.get_platform_info()
        
        assert "rate_limit" in info
        assert "supported_fields" in info
        assert "subreddit" in info["supported_fields"]

    @pytest.mark.asyncio
    async def test_get_platform_info_unknown_platform(self):
        """Test getting platform info for unknown platform."""
        config = {"platform": "unknown"}
        connector = SocialMediaConnector(config)
        
        info = await connector.get_platform_info()
        
        assert info == {}

    @pytest.mark.asyncio
    async def test_fetch_data_with_limit(self):
        """Test fetching data with limit parameter."""
        config = {"platform": "twitter"}
        auth_config = {"bearer_token": "test_token"}
        connector = SocialMediaConnector(config, auth_config)
        connector._connected = True
        connector._session = AsyncMock()
        
        twitter_response = {
            "data": [
                {"id": "1", "text": "Tweet 1", "author_id": "user1"},
                {"id": "2", "text": "Tweet 2", "author_id": "user2"}
            ],
            "includes": {"users": []}
        }
        
        with aioresponses() as m:
            # Should respect the limit parameter
            m.get("https://api.twitter.com/2/tweets/search/recent",
                  status=200, payload=twitter_response)
            
            data = await connector.fetch_data("test", limit=50)
            
            assert len(data) == 2

    @pytest.mark.asyncio
    async def test_fetch_data_reddit_with_subreddit(self):
        """Test fetching Reddit data with specific subreddit."""
        config = {"platform": "reddit"}
        auth_config = {"client_id": "test_id", "client_secret": "test_secret"}
        connector = SocialMediaConnector(config, auth_config)
        connector._connected = True
        connector._session = AsyncMock()
        
        reddit_response = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "test123",
                            "title": "Subreddit Test Post",
                            "selftext": "Test content",
                            "created_utc": 1704067200,
                            "author": "testuser",
                            "subreddit": "python",
                            "score": 50,
                            "num_comments": 10,
                            "upvote_ratio": 0.8,
                            "permalink": "/r/python/comments/test123/test_post/"
                        }
                    }
                ]
            }
        }
        
        with aioresponses() as m:
            m.get("https://oauth.reddit.com/r/python/hot",
                  status=200, payload=reddit_response)
            
            data = await connector.fetch_data("", subreddit="python")
            
            assert len(data) == 1
            assert data[0]["subreddit"] == "python"
