"""
RSS feed connector for data sources.
"""

import aiohttp
import asyncio
from typing import Any, Dict, List, Optional
import feedparser
from urllib.parse import urlparse
from .base import BaseConnector, ConnectionError, DataFormatError


class RSSConnector(BaseConnector):
    """
    Connector for RSS feed data sources.
    """

    def __init__(self, config: Dict[str, Any], auth_config: Optional[Dict[str, Any]] = None):
        """
        Initialize RSS connector.
        
        Args:
            config: RSS configuration containing 'url' and optional settings
            auth_config: Authentication configuration (if needed)
        """
        super().__init__(config, auth_config)
        self._session = None

    def validate_config(self) -> bool:
        """Validate RSS connector configuration."""
        required_fields = ['url']
        
        for field in required_fields:
            if field not in self.config:
                return False
                
        # Validate URL format
        try:
            result = urlparse(self.config['url'])
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    async def connect(self) -> bool:
        """Establish HTTP session for RSS fetching."""
        try:
            if self._session and not self._session.closed:
                self._connected = True
                return True
                
            timeout = aiohttp.ClientTimeout(total=self.config.get('timeout', 30))
            self._session = aiohttp.ClientSession(timeout=timeout)
            
            # Test connection
            async with self._session.get(self.config['url']) as response:
                if response.status == 200:
                    self._connected = True
                    return True
                else:
                    self._last_error = ConnectionError(f"HTTP {response.status}: {response.reason}")
                    return False
                    
        except Exception as e:
            self._last_error = ConnectionError(f"Failed to connect to RSS feed: {e}")
            return False

    async def disconnect(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._connected = False

    async def fetch_data(self, limit: Optional[int] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch data from RSS feed.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of RSS entry dictionaries
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to RSS feed")

        try:
            async with self._session.get(self.config['url']) as response:
                if response.status != 200:
                    raise ConnectionError(f"HTTP {response.status}: {response.reason}")
                
                content = await response.text()
                
            # Parse RSS feed
            feed = feedparser.parse(content)
            
            if feed.bozo and feed.bozo_exception:
                self.logger.warning(f"RSS parsing warning: {feed.bozo_exception}")
            
            entries = []
            for entry in feed.entries[:limit] if limit else feed.entries:
                entry_data = {
                    'title': entry.get('title', ''),
                    'link': entry.get('link', ''),
                    'description': entry.get('description', ''),
                    'published': entry.get('published', ''),
                    'published_parsed': entry.get('published_parsed'),
                    'author': entry.get('author', ''),
                    'tags': [tag.get('term', '') for tag in entry.get('tags', [])],
                    'source': self.config['url'],
                    'entry_id': entry.get('id', entry.get('link', '')),
                }
                
                if self.validate_data_format(entry_data):
                    entries.append(entry_data)
                    
            return entries
            
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to fetch RSS data: {e}")

    def validate_data_format(self, data: Any) -> bool:
        """
        Validate RSS entry data format.
        
        Args:
            data: RSS entry data to validate
            
        Returns:
            True if data format is valid
        """
        if not isinstance(data, dict):
            return False
            
        required_fields = ['title', 'link', 'source']
        
        for field in required_fields:
            if field not in data or not data[field]:
                return False
                
        return True

    async def get_feed_info(self) -> Dict[str, Any]:
        """
        Get RSS feed metadata.
        
        Returns:
            Dictionary containing feed information
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to RSS feed")

        try:
            async with self._session.get(self.config['url']) as response:
                content = await response.text()
                
            feed = feedparser.parse(content)
            
            return {
                'title': feed.feed.get('title', ''),
                'description': feed.feed.get('description', ''),
                'link': feed.feed.get('link', ''),
                'language': feed.feed.get('language', ''),
                'updated': feed.feed.get('updated', ''),
                'updated_parsed': feed.feed.get('updated_parsed'),
                'entries_count': len(feed.entries),
                'version': feed.version,
            }
            
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to get feed info: {e}")

    async def check_feed_validity(self) -> bool:
        """
        Check if RSS feed is valid and accessible.
        
        Returns:
            True if feed is valid
        """
        try:
            if not await self.connect():
                return False
                
            async with self._session.get(self.config['url']) as response:
                if response.status != 200:
                    return False
                    
                content = await response.text()
                
            feed = feedparser.parse(content)
            return not feed.bozo or feed.bozo_exception is None
            
        except Exception:
            return False
