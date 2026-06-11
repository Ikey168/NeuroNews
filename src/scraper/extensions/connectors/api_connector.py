"""
API connectors for REST and GraphQL data sources.
"""

import aiohttp
import asyncio
from typing import Any, Dict, List, Optional, Union
import json
from urllib.parse import urljoin, urlparse
from .base import BaseConnector, ConnectionError, DataFormatError, AuthenticationError


class APIConnector(BaseConnector):
    """
    Base API connector for HTTP-based APIs.
    """

    def __init__(self, config: Dict[str, Any], auth_config: Optional[Dict[str, Any]] = None):
        """
        Initialize API connector.
        
        Args:
            config: API configuration containing base_url and other settings
            auth_config: Authentication configuration
        """
        super().__init__(config, auth_config)
        self._session = None
        self._headers = {}

    def validate_config(self) -> bool:
        """Validate API connector configuration."""
        required_fields = ['base_url']
        
        for field in required_fields:
            if field not in self.config:
                return False
                
        # Validate URL format
        try:
            result = urlparse(self.config['base_url'])
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    async def connect(self) -> bool:
        """Establish HTTP session for API requests."""
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
            
            # Add custom headers if provided
            if 'headers' in self.config:
                self._headers.update(self.config['headers'])
            
            # Authenticate if required
            if self.auth_config:
                if not await self.authenticate():
                    return False
            
            self._connected = True
            return True
                    
        except Exception as e:
            self._last_error = ConnectionError(f"Failed to connect to API: {e}")
            return False

    async def disconnect(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._connected = False

    async def authenticate(self) -> bool:
        """Authenticate with API using provided auth configuration."""
        auth_type = self.auth_config.get('type', 'none')
        
        try:
            if auth_type == 'api_key':
                key_header = self.auth_config.get('header', 'X-API-Key')
                api_key = self.auth_config.get('key')
                if not api_key:
                    raise AuthenticationError("API key not provided")
                self._headers[key_header] = api_key
                
            elif auth_type == 'bearer':
                token = self.auth_config.get('token')
                if not token:
                    raise AuthenticationError("Bearer token not provided")
                self._headers['Authorization'] = f'Bearer {token}'
                
            elif auth_type == 'basic':
                username = self.auth_config.get('username')
                password = self.auth_config.get('password')
                if not username or not password:
                    raise AuthenticationError("Username or password not provided")
                
                import base64
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                self._headers['Authorization'] = f'Basic {credentials}'
                
            elif auth_type == 'oauth':
                # OAuth implementation would go here
                raise NotImplementedError("OAuth authentication not yet implemented")
                
            return True
            
        except Exception as e:
            self._last_error = AuthenticationError(f"Authentication failed: {e}")
            return False

    async def fetch_data(self, endpoint: str, method: str = 'GET', params: Optional[Dict] = None, 
                        data: Optional[Union[Dict, str]] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch data from API endpoint.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method
            params: Query parameters
            data: Request body data
            
        Returns:
            List of data records
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to API")

        try:
            url = urljoin(self.config['base_url'], endpoint)
            
            request_kwargs = {
                'headers': self._headers,
                'params': params,
            }
            
            if data:
                if isinstance(data, dict):
                    request_kwargs['json'] = data
                else:
                    request_kwargs['data'] = data
            
            async with self._session.request(method, url, **request_kwargs) as response:
                if response.status == 401:
                    raise AuthenticationError("Authentication failed")
                elif response.status == 403:
                    raise AuthenticationError("Access forbidden")
                elif response.status not in [200, 201]:
                    raise ConnectionError(f"HTTP {response.status}: {response.reason}")
                
                response_data = await response.json()
                
                # Handle different response formats
                if isinstance(response_data, list):
                    return response_data
                elif isinstance(response_data, dict):
                    # Look for common data containers
                    for key in ['data', 'results', 'items', 'records']:
                        if key in response_data and isinstance(response_data[key], list):
                            return response_data[key]
                    # If no container found, wrap single object
                    return [response_data]
                else:
                    return [{'data': response_data}]
                    
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to fetch API data: {e}")

    def validate_data_format(self, data: Any) -> bool:
        """
        Validate API response data format.
        
        Args:
            data: API response data to validate
            
        Returns:
            True if data format is valid
        """
        # Basic validation - should be JSON serializable
        try:
            json.dumps(data)
            return True
        except (TypeError, ValueError):
            return False


class RESTConnector(APIConnector):
    """
    REST API connector with additional REST-specific functionality.
    """

    async def get(self, endpoint: str, params: Optional[Dict] = None, **kwargs) -> List[Dict[str, Any]]:
        """GET request to REST endpoint."""
        return await self.fetch_data(endpoint, 'GET', params=params, **kwargs)

    async def post(self, endpoint: str, data: Optional[Union[Dict, str]] = None, **kwargs) -> List[Dict[str, Any]]:
        """POST request to REST endpoint."""
        return await self.fetch_data(endpoint, 'POST', data=data, **kwargs)

    async def put(self, endpoint: str, data: Optional[Union[Dict, str]] = None, **kwargs) -> List[Dict[str, Any]]:
        """PUT request to REST endpoint."""
        return await self.fetch_data(endpoint, 'PUT', data=data, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> List[Dict[str, Any]]:
        """DELETE request to REST endpoint."""
        return await self.fetch_data(endpoint, 'DELETE', **kwargs)


class GraphQLConnector(APIConnector):
    """
    GraphQL API connector.
    """

    def __init__(self, config: Dict[str, Any], auth_config: Optional[Dict[str, Any]] = None):
        """
        Initialize GraphQL connector.
        
        Args:
            config: GraphQL configuration containing endpoint URL
            auth_config: Authentication configuration
        """
        super().__init__(config, auth_config)
        self.endpoint = config.get('endpoint', '/graphql')

    async def query(self, query: str, variables: Optional[Dict] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Execute GraphQL query.
        
        Args:
            query: GraphQL query string
            variables: Query variables
            
        Returns:
            List of data records from query result
        """
        payload = {
            'query': query,
            'variables': variables or {}
        }
        
        try:
            response_data = await self.fetch_data(self.endpoint, 'POST', data=payload, **kwargs)
            
            # GraphQL typically returns a single response object
            if response_data and isinstance(response_data, list) and len(response_data) > 0:
                graphql_response = response_data[0]
            else:
                graphql_response = response_data
            
            # Check for GraphQL errors
            if isinstance(graphql_response, dict):
                if 'errors' in graphql_response:
                    error_msg = '; '.join([err.get('message', str(err)) for err in graphql_response['errors']])
                    raise ConnectionError(f"GraphQL errors: {error_msg}")
                
                # Extract data
                if 'data' in graphql_response:
                    data = graphql_response['data']
                    if isinstance(data, dict):
                        # Try to find list values in the data
                        for value in data.values():
                            if isinstance(value, list):
                                return value
                        # If no lists found, return the data object wrapped
                        return [data]
                    elif isinstance(data, list):
                        return data
                    else:
                        return [{'data': data}]
            
            return response_data
            
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to execute GraphQL query: {e}")

    async def mutation(self, mutation: str, variables: Optional[Dict] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Execute GraphQL mutation.
        
        Args:
            mutation: GraphQL mutation string
            variables: Mutation variables
            
        Returns:
            List of data records from mutation result
        """
        return await self.query(mutation, variables, **kwargs)

    def validate_query(self, query: str) -> bool:
        """
        Basic validation of GraphQL query syntax.
        
        Args:
            query: GraphQL query string
            
        Returns:
            True if query appears valid
        """
        if not query or not isinstance(query, str):
            return False
            
        # Basic checks for GraphQL syntax
        query = query.strip()
        if not query:
            return False
            
        # Should contain query/mutation keyword or start with {
        return any(keyword in query.lower() for keyword in ['query', 'mutation', 'subscription']) or query.startswith('{')
