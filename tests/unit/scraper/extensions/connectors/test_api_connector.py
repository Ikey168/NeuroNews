"""
Test cases for API connector functionality.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
import json
from aioresponses import aioresponses

from src.scraper.extensions.connectors.api_connector import (
    APIConnector, 
    RESTConnector, 
    GraphQLConnector
)
from src.scraper.extensions.connectors.base import (
    ConnectionError, 
    AuthenticationError
)


class TestAPIConnector:
    """Test cases for APIConnector class."""

    def test_init(self):
        """Test API connector initialization."""
        config = {"base_url": "https://api.example.com"}
        auth_config = {"type": "api_key", "key": "test_key"}
        
        connector = APIConnector(config, auth_config)
        
        assert connector.config == config
        assert connector.auth_config == auth_config
        assert connector._session is None
        assert connector._headers == {}

    def test_validate_config_success(self):
        """Test successful config validation."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        result = connector.validate_config()
        assert result is True

    def test_validate_config_missing_url(self):
        """Test config validation with missing base URL."""
        config = {}
        connector = APIConnector(config)
        
        result = connector.validate_config()
        assert result is False

    def test_validate_config_invalid_url(self):
        """Test config validation with invalid URL."""
        config = {"base_url": "invalid-url"}
        connector = APIConnector(config)
        
        result = connector.validate_config()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_success_without_auth(self):
        """Test successful connection without authentication."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected
        assert connector._session is not None
        assert "User-Agent" in connector._headers

    @pytest.mark.asyncio
    async def test_connect_success_with_api_key_auth(self):
        """Test successful connection with API key authentication."""
        config = {"base_url": "https://api.example.com"}
        auth_config = {"type": "api_key", "key": "test_key"}
        connector = APIConnector(config, auth_config)
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected
        assert "X-API-Key" in connector._headers
        assert connector._headers["X-API-Key"] == "test_key"

    @pytest.mark.asyncio
    async def test_connect_success_with_bearer_auth(self):
        """Test successful connection with bearer token authentication."""
        config = {"base_url": "https://api.example.com"}
        auth_config = {"type": "bearer", "token": "test_token"}
        connector = APIConnector(config, auth_config)
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected
        assert "Authorization" in connector._headers
        assert connector._headers["Authorization"] == "Bearer test_token"

    @pytest.mark.asyncio
    async def test_connect_success_with_basic_auth(self):
        """Test successful connection with basic authentication."""
        config = {"base_url": "https://api.example.com"}
        auth_config = {"type": "basic", "username": "user", "password": "pass"}
        connector = APIConnector(config, auth_config)
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected
        assert "Authorization" in connector._headers
        assert connector._headers["Authorization"].startswith("Basic ")

    @pytest.mark.asyncio
    async def test_connect_with_oauth_not_implemented(self):
        """Test connection with OAuth (not implemented)."""
        config = {"base_url": "https://api.example.com"}
        auth_config = {"type": "oauth", "client_id": "test_id"}
        connector = APIConnector(config, auth_config)
        
        result = await connector.connect()
        
        assert result is False
        assert isinstance(connector.last_error, AuthenticationError)

    @pytest.mark.asyncio
    async def test_authenticate_missing_api_key(self):
        """Test authentication failure with missing API key."""
        config = {"base_url": "https://api.example.com"}
        auth_config = {"type": "api_key"}  # No key provided
        connector = APIConnector(config, auth_config)
        
        result = await connector.authenticate()
        
        assert result is False
        assert isinstance(connector.last_error, AuthenticationError)

    @pytest.mark.asyncio
    async def test_authenticate_missing_bearer_token(self):
        """Test authentication failure with missing bearer token."""
        config = {"base_url": "https://api.example.com"}
        auth_config = {"type": "bearer"}  # No token provided
        connector = APIConnector(config, auth_config)
        
        result = await connector.authenticate()
        
        assert result is False
        assert isinstance(connector.last_error, AuthenticationError)

    @pytest.mark.asyncio
    async def test_authenticate_missing_basic_credentials(self):
        """Test authentication failure with missing basic auth credentials."""
        config = {"base_url": "https://api.example.com"}
        auth_config = {"type": "basic", "username": "user"}  # No password
        connector = APIConnector(config, auth_config)
        
        result = await connector.authenticate()
        
        assert result is False
        assert isinstance(connector.last_error, AuthenticationError)

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test API disconnection."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.closed = False
        connector._session = mock_session
        connector._connected = True
        
        await connector.disconnect()
        
        assert not connector.is_connected
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_data_success_list_response(self):
        """Test successful data fetching with list response."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        response_data = [
            {"id": 1, "name": "Item 1"},
            {"id": 2, "name": "Item 2"}
        ]
        
        with aioresponses() as m:
            m.get("https://api.example.com/items", status=200, payload=response_data)
            
            await connector.connect()
            data = await connector.fetch_data("items")
            
            assert len(data) == 2
            assert data[0]["id"] == 1
            assert data[1]["name"] == "Item 2"

    @pytest.mark.asyncio
    async def test_fetch_data_success_dict_with_data_key(self):
        """Test successful data fetching with dict response containing 'data' key."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        response_data = {
            "data": [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2"}
            ],
            "total": 2
        }
        
        with aioresponses() as m:
            m.get("https://api.example.com/items", status=200, payload=response_data)
            
            await connector.connect()
            data = await connector.fetch_data("items")
            
            assert len(data) == 2
            assert data[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_fetch_data_success_single_object(self):
        """Test successful data fetching with single object response."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        response_data = {"id": 1, "name": "Single Item"}
        
        with aioresponses() as m:
            m.get("https://api.example.com/item", status=200, payload=response_data)
            
            await connector.connect()
            data = await connector.fetch_data("item")
            
            assert len(data) == 1
            assert data[0]["id"] == 1
            assert data[0]["name"] == "Single Item"

    @pytest.mark.asyncio
    async def test_fetch_data_not_connected(self):
        """Test fetching data when not connected."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to API"):
            await connector.fetch_data("items")

    @pytest.mark.asyncio
    async def test_fetch_data_auth_error(self):
        """Test fetching data with authentication error."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        with aioresponses() as m:
            m.get("https://api.example.com/items", status=401)
            
            await connector.connect()
            
            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await connector.fetch_data("items")

    @pytest.mark.asyncio
    async def test_fetch_data_forbidden_error(self):
        """Test fetching data with forbidden error."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        with aioresponses() as m:
            m.get("https://api.example.com/items", status=403)
            
            await connector.connect()
            
            with pytest.raises(AuthenticationError, match="Access forbidden"):
                await connector.fetch_data("items")

    @pytest.mark.asyncio
    async def test_fetch_data_http_error(self):
        """Test fetching data with HTTP error."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        with aioresponses() as m:
            m.get("https://api.example.com/items", status=500)
            
            await connector.connect()
            
            with pytest.raises(ConnectionError, match="HTTP 500"):
                await connector.fetch_data("items")

    @pytest.mark.asyncio
    async def test_fetch_data_with_query_params(self):
        """Test fetching data with query parameters."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        response_data = [{"id": 1, "name": "Filtered Item"}]
        
        with aioresponses() as m:
            m.get("https://api.example.com/items?filter=active", status=200, payload=response_data)
            
            await connector.connect()
            data = await connector.fetch_data("items", params={"filter": "active"})
            
            assert len(data) == 1
            assert data[0]["name"] == "Filtered Item"

    @pytest.mark.asyncio
    async def test_fetch_data_post_with_json_data(self):
        """Test POST request with JSON data."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        response_data = {"id": 1, "status": "created"}
        post_data = {"name": "New Item"}
        
        with aioresponses() as m:
            m.post("https://api.example.com/items", status=201, payload=response_data)
            
            await connector.connect()
            data = await connector.fetch_data("items", method="POST", data=post_data)
            
            assert len(data) == 1
            assert data[0]["status"] == "created"

    @pytest.mark.asyncio
    async def test_fetch_data_post_with_string_data(self):
        """Test POST request with string data."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        response_data = {"status": "processed"}
        
        with aioresponses() as m:
            m.post("https://api.example.com/process", status=200, payload=response_data)
            
            await connector.connect()
            data = await connector.fetch_data("process", method="POST", data="raw data")
            
            assert len(data) == 1
            assert data[0]["status"] == "processed"

    def test_validate_data_format_success(self):
        """Test successful data format validation."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        data = {"id": 1, "name": "Test Item"}
        
        result = connector.validate_data_format(data)
        assert result is True

    def test_validate_data_format_failure(self):
        """Test failed data format validation."""
        config = {"base_url": "https://api.example.com"}
        connector = APIConnector(config)
        
        # Non-JSON serializable data
        import datetime
        data = {"id": 1, "date": datetime.datetime.now()}
        
        result = connector.validate_data_format(data)
        assert result is False


class TestRESTConnector:
    """Test cases for RESTConnector class."""

    @pytest.mark.asyncio
    async def test_get_method(self):
        """Test GET method."""
        config = {"base_url": "https://api.example.com"}
        connector = RESTConnector(config)
        
        response_data = [{"id": 1, "name": "Item"}]
        
        with aioresponses() as m:
            m.get("https://api.example.com/items", status=200, payload=response_data)
            
            await connector.connect()
            data = await connector.get("items")
            
            assert len(data) == 1
            assert data[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_post_method(self):
        """Test POST method."""
        config = {"base_url": "https://api.example.com"}
        connector = RESTConnector(config)
        
        response_data = {"id": 1, "status": "created"}
        post_data = {"name": "New Item"}
        
        with aioresponses() as m:
            m.post("https://api.example.com/items", status=201, payload=response_data)
            
            await connector.connect()
            data = await connector.post("items", data=post_data)
            
            assert len(data) == 1
            assert data[0]["status"] == "created"

    @pytest.mark.asyncio
    async def test_put_method(self):
        """Test PUT method."""
        config = {"base_url": "https://api.example.com"}
        connector = RESTConnector(config)
        
        response_data = {"id": 1, "status": "updated"}
        put_data = {"name": "Updated Item"}
        
        with aioresponses() as m:
            m.put("https://api.example.com/items/1", status=200, payload=response_data)
            
            await connector.connect()
            data = await connector.put("items/1", data=put_data)
            
            assert len(data) == 1
            assert data[0]["status"] == "updated"

    @pytest.mark.asyncio
    async def test_delete_method(self):
        """Test DELETE method."""
        config = {"base_url": "https://api.example.com"}
        connector = RESTConnector(config)
        
        response_data = {"status": "deleted"}
        
        with aioresponses() as m:
            m.delete("https://api.example.com/items/1", status=200, payload=response_data)
            
            await connector.connect()
            data = await connector.delete("items/1")
            
            assert len(data) == 1
            assert data[0]["status"] == "deleted"


class TestGraphQLConnector:
    """Test cases for GraphQLConnector class."""

    def test_init(self):
        """Test GraphQL connector initialization."""
        config = {"base_url": "https://api.example.com", "endpoint": "/graphql"}
        connector = GraphQLConnector(config)
        
        assert connector.endpoint == "/graphql"

    def test_init_default_endpoint(self):
        """Test GraphQL connector initialization with default endpoint."""
        config = {"base_url": "https://api.example.com"}
        connector = GraphQLConnector(config)
        
        assert connector.endpoint == "/graphql"

    @pytest.mark.asyncio
    async def test_query_success(self):
        """Test successful GraphQL query."""
        config = {"base_url": "https://api.example.com"}
        connector = GraphQLConnector(config)
        
        query = "{ users { id name } }"
        response_data = {
            "data": {
                "users": [
                    {"id": 1, "name": "User 1"},
                    {"id": 2, "name": "User 2"}
                ]
            }
        }
        
        with aioresponses() as m:
            m.post("https://api.example.com/graphql", status=200, payload=[response_data])
            
            await connector.connect()
            data = await connector.query(query)
            
            assert len(data) == 2
            assert data[0]["id"] == 1
            assert data[1]["name"] == "User 2"

    @pytest.mark.asyncio
    async def test_query_with_variables(self):
        """Test GraphQL query with variables."""
        config = {"base_url": "https://api.example.com"}
        connector = GraphQLConnector(config)
        
        query = "query GetUser($id: ID!) { user(id: $id) { id name } }"
        variables = {"id": "1"}
        response_data = {
            "data": {
                "user": {"id": 1, "name": "User 1"}
            }
        }
        
        with aioresponses() as m:
            m.post("https://api.example.com/graphql", status=200, payload=[response_data])
            
            await connector.connect()
            data = await connector.query(query, variables)
            
            assert len(data) == 1
            assert data[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_query_with_errors(self):
        """Test GraphQL query with errors in response."""
        config = {"base_url": "https://api.example.com"}
        connector = GraphQLConnector(config)
        
        query = "{ invalidField }"
        response_data = {
            "errors": [
                {"message": "Field 'invalidField' doesn't exist"}
            ]
        }
        
        with aioresponses() as m:
            m.post("https://api.example.com/graphql", status=200, payload=[response_data])
            
            await connector.connect()
            
            with pytest.raises(ConnectionError, match="GraphQL errors"):
                await connector.query(query)

    @pytest.mark.asyncio
    async def test_mutation(self):
        """Test GraphQL mutation."""
        config = {"base_url": "https://api.example.com"}
        connector = GraphQLConnector(config)
        
        mutation = "mutation CreateUser($input: UserInput!) { createUser(input: $input) { id name } }"
        variables = {"input": {"name": "New User"}}
        response_data = {
            "data": {
                "createUser": {"id": 1, "name": "New User"}
            }
        }
        
        with aioresponses() as m:
            m.post("https://api.example.com/graphql", status=200, payload=[response_data])
            
            await connector.connect()
            data = await connector.mutation(mutation, variables)
            
            assert len(data) == 1
            assert data[0]["name"] == "New User"

    def test_validate_query_success(self):
        """Test successful query validation."""
        config = {"base_url": "https://api.example.com"}
        connector = GraphQLConnector(config)
        
        valid_queries = [
            "query { users { id } }",
            "mutation { createUser { id } }",
            "{ users { id } }",  # Simple query without keyword
            "subscription { messageAdded { id } }"
        ]
        
        for query in valid_queries:
            assert connector.validate_query(query) is True

    def test_validate_query_failure(self):
        """Test failed query validation."""
        config = {"base_url": "https://api.example.com"}
        connector = GraphQLConnector(config)
        
        invalid_queries = [
            "",
            None,
            "not a graphql query",
            123,
            "   ",  # Just whitespace
        ]
        
        for query in invalid_queries:
            assert connector.validate_query(query) is False

    @pytest.mark.asyncio
    async def test_query_with_direct_response(self):
        """Test GraphQL query with direct response (not wrapped in list)."""
        config = {"base_url": "https://api.example.com"}
        connector = GraphQLConnector(config)
        
        query = "{ user { id name } }"
        response_data = {
            "data": {
                "user": {"id": 1, "name": "User 1"}
            }
        }
        
        with aioresponses() as m:
            m.post("https://api.example.com/graphql", status=200, payload=response_data)
            
            await connector.connect()
            data = await connector.query(query)
            
            assert len(data) == 1
            assert data[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_query_with_scalar_response(self):
        """Test GraphQL query with scalar response."""
        config = {"base_url": "https://api.example.com"}
        connector = GraphQLConnector(config)
        
        query = "{ userCount }"
        response_data = {
            "data": {
                "userCount": 5
            }
        }
        
        with aioresponses() as m:
            m.post("https://api.example.com/graphql", status=200, payload=[response_data])
            
            await connector.connect()
            data = await connector.query(query)
            
            assert len(data) == 1
            assert data[0]["userCount"] == 5
