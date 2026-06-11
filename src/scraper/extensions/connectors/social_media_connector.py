"""
Social media connectors for various platforms.
"""

import aiohttp
import asyncio
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
from .base import BaseConnector, ConnectionError, DataFormatError, AuthenticationError


class SocialMediaConnector(BaseConnector):
    """
    Base social media connector with common functionality.
    """

    def __init__(self, config: Dict[str, Any], auth_config: Optional[Dict[str, Any]] = None):
        """
        Initialize social media connector.
        
        Args:
            config: Social media configuration containing platform and settings
            auth_config: Authentication configuration (required for most platforms)
        """
        super().__init__(config, auth_config)
        self._session = None
        self._headers = {}
        self.platform = config.get('platform', '').lower()

    def validate_config(self) -> bool:
        """Validate social media connector configuration."""
        required_fields = ['platform']
        
        for field in required_fields:
            if field not in self.config:
                return False
                
        # Platform-specific validation
        if self.platform in ['twitter', 'x']:
            return 'bearer_token' in self.auth_config or 'api_key' in self.auth_config
        elif self.platform == 'reddit':
            return all(key in self.auth_config for key in ['client_id', 'client_secret'])
        elif self.platform == 'facebook':
            return 'access_token' in self.auth_config
        elif self.platform == 'instagram':
            return 'access_token' in self.auth_config
        elif self.platform == 'linkedin':
            return 'access_token' in self.auth_config
                
        return True

    async def connect(self) -> bool:
        """Establish connection to social media platform."""
        try:
            if self._session and not self._session.closed:
                self._connected = True
                return True
                
            timeout = aiohttp.ClientTimeout(total=self.config.get('timeout', 30))
            self._session = aiohttp.ClientSession(timeout=timeout)
            
            # Set up headers
            self._headers = {
                'User-Agent': self.config.get('user_agent', 'NeuroNews-Scraper/1.0'),
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }
            
            # Platform-specific setup
            if not await self._setup_platform():
                return False
            
            self._connected = True
            return True
                    
        except Exception as e:
            self._last_error = ConnectionError(f"Failed to connect to {self.platform}: {e}")
            return False

    async def _setup_platform(self) -> bool:
        """Setup platform-specific authentication and headers."""
        try:
            if self.platform in ['twitter', 'x']:
                return await self._setup_twitter()
            elif self.platform == 'reddit':
                return await self._setup_reddit()
            elif self.platform == 'facebook':
                return await self._setup_facebook()
            elif self.platform == 'instagram':
                return await self._setup_instagram()
            elif self.platform == 'linkedin':
                return await self._setup_linkedin()
            else:
                raise ConnectionError(f"Unsupported platform: {self.platform}")
                
        except Exception as e:
            self._last_error = AuthenticationError(f"Platform setup failed: {e}")
            return False

    async def _setup_twitter(self) -> bool:
        """Setup Twitter API authentication."""
        if 'bearer_token' in self.auth_config:
            self._headers['Authorization'] = f"Bearer {self.auth_config['bearer_token']}"
        elif 'api_key' in self.auth_config:
            # OAuth 1.0a would go here - simplified for demo
            self._headers['Authorization'] = f"Bearer {self.auth_config['api_key']}"
        else:
            raise AuthenticationError("No valid Twitter credentials provided")
            
        return True

    async def _setup_reddit(self) -> bool:
        """Setup Reddit API authentication."""
        # Get OAuth token
        auth_data = {
            'grant_type': 'client_credentials',
            'scope': 'read'
        }
        
        import base64
        credentials = base64.b64encode(
            f"{self.auth_config['client_id']}:{self.auth_config['client_secret']}".encode()
        ).decode()
        
        auth_headers = {
            'Authorization': f'Basic {credentials}',
            'User-Agent': self._headers['User-Agent']
        }
        
        async with self._session.post(
            'https://www.reddit.com/api/v1/access_token',
            data=auth_data,
            headers=auth_headers
        ) as response:
            if response.status == 200:
                token_data = await response.json()
                self._headers['Authorization'] = f"Bearer {token_data['access_token']}"
                return True
            else:
                raise AuthenticationError("Failed to get Reddit access token")

    async def _setup_facebook(self) -> bool:
        """Setup Facebook Graph API authentication."""
        self._headers['Authorization'] = f"Bearer {self.auth_config['access_token']}"
        return True

    async def _setup_instagram(self) -> bool:
        """Setup Instagram Basic Display API authentication."""
        self._headers['Authorization'] = f"Bearer {self.auth_config['access_token']}"
        return True

    async def _setup_linkedin(self) -> bool:
        """Setup LinkedIn API authentication."""
        self._headers['Authorization'] = f"Bearer {self.auth_config['access_token']}"
        return True

    async def disconnect(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._connected = False

    async def fetch_data(self, query: str = "", limit: int = 100, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch data from social media platform.
        
        Args:
            query: Search query or filter
            limit: Maximum number of posts to return
            
        Returns:
            List of social media posts
        """
        if not self.is_connected:
            raise ConnectionError(f"Not connected to {self.platform}")

        try:
            if self.platform in ['twitter', 'x']:
                return await self._fetch_twitter_data(query, limit, **kwargs)
            elif self.platform == 'reddit':
                return await self._fetch_reddit_data(query, limit, **kwargs)
            elif self.platform == 'facebook':
                return await self._fetch_facebook_data(query, limit, **kwargs)
            elif self.platform == 'instagram':
                return await self._fetch_instagram_data(query, limit, **kwargs)
            elif self.platform == 'linkedin':
                return await self._fetch_linkedin_data(query, limit, **kwargs)
            else:
                raise ConnectionError(f"Unsupported platform: {self.platform}")
                
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to fetch {self.platform} data: {e}")

    async def _fetch_twitter_data(self, query: str, limit: int, **kwargs) -> List[Dict[str, Any]]:
        """Fetch data from Twitter API."""
        # Twitter API v2 search endpoint
        url = "https://api.twitter.com/2/tweets/search/recent"
        params = {
            'query': query or 'lang:en -is:retweet',
            'max_results': min(limit, 100),
            'tweet.fields': 'created_at,author_id,public_metrics,lang,context_annotations',
            'user.fields': 'username,name,verified',
            'expansions': 'author_id'
        }
        
        async with self._session.get(url, headers=self._headers, params=params) as response:
            if response.status == 401:
                raise AuthenticationError("Twitter authentication failed")
            elif response.status != 200:
                raise ConnectionError(f"Twitter API error: {response.status}")
                
            data = await response.json()
            
            posts = []
            tweets = data.get('data', [])
            users = {user['id']: user for user in data.get('includes', {}).get('users', [])}
            
            for tweet in tweets:
                user = users.get(tweet.get('author_id'), {})
                post = {
                    'id': tweet['id'],
                    'text': tweet['text'],
                    'created_at': tweet.get('created_at'),
                    'author_id': tweet.get('author_id'),
                    'author_username': user.get('username'),
                    'author_name': user.get('name'),
                    'author_verified': user.get('verified'),
                    'metrics': tweet.get('public_metrics', {}),
                    'language': tweet.get('lang'),
                    'platform': 'twitter',
                    'url': f"https://twitter.com/{user.get('username', 'unknown')}/status/{tweet['id']}"
                }
                posts.append(post)
            
            return posts

    async def _fetch_reddit_data(self, query: str, limit: int, **kwargs) -> List[Dict[str, Any]]:
        """Fetch data from Reddit API."""
        subreddit = kwargs.get('subreddit', 'all')
        sort = kwargs.get('sort', 'hot')  # hot, new, rising, top
        
        url = f"https://oauth.reddit.com/r/{subreddit}/{sort}"
        params = {
            'limit': min(limit, 100),
            'raw_json': 1
        }
        
        if query:
            url = f"https://oauth.reddit.com/r/{subreddit}/search"
            params['q'] = query
            params['sort'] = 'relevance'
            params['restrict_sr'] = 'true'
        
        async with self._session.get(url, headers=self._headers, params=params) as response:
            if response.status == 401:
                raise AuthenticationError("Reddit authentication failed")
            elif response.status != 200:
                raise ConnectionError(f"Reddit API error: {response.status}")
                
            data = await response.json()
            
            posts = []
            for item in data.get('data', {}).get('children', []):
                post_data = item.get('data', {})
                post = {
                    'id': post_data.get('id'),
                    'title': post_data.get('title'),
                    'text': post_data.get('selftext'),
                    'created_at': datetime.fromtimestamp(post_data.get('created_utc', 0)).isoformat(),
                    'author': post_data.get('author'),
                    'subreddit': post_data.get('subreddit'),
                    'score': post_data.get('score'),
                    'num_comments': post_data.get('num_comments'),
                    'upvote_ratio': post_data.get('upvote_ratio'),
                    'platform': 'reddit',
                    'url': f"https://reddit.com{post_data.get('permalink', '')}"
                }
                posts.append(post)
            
            return posts

    async def _fetch_facebook_data(self, query: str, limit: int, **kwargs) -> List[Dict[str, Any]]:
        """Fetch data from Facebook Graph API."""
        # Note: Facebook's API has strict limitations for public content
        page_id = kwargs.get('page_id')
        if not page_id:
            raise ConnectionError("Facebook requires page_id parameter")
            
        url = f"https://graph.facebook.com/v18.0/{page_id}/posts"
        params = {
            'limit': min(limit, 100),
            'fields': 'id,message,created_time,likes.summary(true),comments.summary(true),shares'
        }
        
        async with self._session.get(url, headers=self._headers, params=params) as response:
            if response.status == 401:
                raise AuthenticationError("Facebook authentication failed")
            elif response.status != 200:
                raise ConnectionError(f"Facebook API error: {response.status}")
                
            data = await response.json()
            
            posts = []
            for post_data in data.get('data', []):
                post = {
                    'id': post_data.get('id'),
                    'text': post_data.get('message', ''),
                    'created_at': post_data.get('created_time'),
                    'likes': post_data.get('likes', {}).get('summary', {}).get('total_count', 0),
                    'comments': post_data.get('comments', {}).get('summary', {}).get('total_count', 0),
                    'shares': post_data.get('shares', {}).get('count', 0),
                    'platform': 'facebook',
                    'url': f"https://facebook.com/{post_data.get('id', '')}"
                }
                posts.append(post)
            
            return posts

    async def _fetch_instagram_data(self, query: str, limit: int, **kwargs) -> List[Dict[str, Any]]:
        """Fetch data from Instagram Basic Display API."""
        # Note: Instagram's API is very limited for public content
        url = "https://graph.instagram.com/me/media"
        params = {
            'limit': min(limit, 100),
            'fields': 'id,caption,media_type,media_url,thumbnail_url,timestamp,username'
        }
        
        async with self._session.get(url, headers=self._headers, params=params) as response:
            if response.status == 401:
                raise AuthenticationError("Instagram authentication failed")
            elif response.status != 200:
                raise ConnectionError(f"Instagram API error: {response.status}")
                
            data = await response.json()
            
            posts = []
            for post_data in data.get('data', []):
                post = {
                    'id': post_data.get('id'),
                    'text': post_data.get('caption', ''),
                    'media_type': post_data.get('media_type'),
                    'media_url': post_data.get('media_url'),
                    'thumbnail_url': post_data.get('thumbnail_url'),
                    'created_at': post_data.get('timestamp'),
                    'username': post_data.get('username'),
                    'platform': 'instagram',
                    'url': f"https://instagram.com/p/{post_data.get('id', '')}"
                }
                posts.append(post)
            
            return posts

    async def _fetch_linkedin_data(self, query: str, limit: int, **kwargs) -> List[Dict[str, Any]]:
        """Fetch data from LinkedIn API."""
        # Note: LinkedIn's API is very restricted for public content
        url = "https://api.linkedin.com/v2/shares"
        params = {
            'count': min(limit, 100),
            'q': 'owners',
            'owners': kwargs.get('person_urn', 'urn:li:person:current')
        }
        
        async with self._session.get(url, headers=self._headers, params=params) as response:
            if response.status == 401:
                raise AuthenticationError("LinkedIn authentication failed")
            elif response.status != 200:
                raise ConnectionError(f"LinkedIn API error: {response.status}")
                
            data = await response.json()
            
            posts = []
            for post_data in data.get('elements', []):
                post = {
                    'id': post_data.get('id'),
                    'text': post_data.get('text', {}).get('text', ''),
                    'created_at': datetime.fromtimestamp(post_data.get('created', {}).get('time', 0) / 1000).isoformat(),
                    'author': post_data.get('author'),
                    'platform': 'linkedin',
                    'url': f"https://linkedin.com/feed/update/{post_data.get('id', '')}"
                }
                posts.append(post)
            
            return posts

    def validate_data_format(self, data: Any) -> bool:
        """
        Validate social media post data format.
        
        Args:
            data: Social media post data to validate
            
        Returns:
            True if data format is valid
        """
        if not isinstance(data, dict):
            return False
            
        # Should have at least id, text/title, and platform
        required_fields = ['id', 'platform']
        for field in required_fields:
            if field not in data:
                return False
                
        # Should have some content
        return any(data.get(field) for field in ['text', 'title', 'message'])

    async def get_platform_info(self) -> Dict[str, Any]:
        """
        Get platform-specific information and limits.
        
        Returns:
            Dictionary containing platform information
        """
        platform_info = {
            'twitter': {
                'rate_limit': '300 requests per 15 minutes',
                'max_results_per_request': 100,
                'supported_fields': ['text', 'author', 'created_at', 'metrics']
            },
            'reddit': {
                'rate_limit': '60 requests per minute',
                'max_results_per_request': 100,
                'supported_fields': ['title', 'text', 'author', 'subreddit', 'score']
            },
            'facebook': {
                'rate_limit': '200 calls per hour per user',
                'max_results_per_request': 100,
                'supported_fields': ['message', 'created_time', 'likes', 'comments']
            },
            'instagram': {
                'rate_limit': '200 calls per hour per user',
                'max_results_per_request': 100,
                'supported_fields': ['caption', 'media_type', 'timestamp']
            },
            'linkedin': {
                'rate_limit': '100 calls per user per day',
                'max_results_per_request': 100,
                'supported_fields': ['text', 'author', 'created_time']
            }
        }
        
        return platform_info.get(self.platform, {})
