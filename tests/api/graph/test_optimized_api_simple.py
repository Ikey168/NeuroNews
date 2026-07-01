"""
Simple test suite for Optimized Graph API module.
Target: Improve test coverage for src/api/graph/optimized_api.py
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, AsyncMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.optimized_api import (
    CacheConfig,
    QueryOptimizationConfig,
    OptimizedGraphAPI,
    create_optimized_graph_api
)


class TestCacheConfig:
    """Test CacheConfig dataclass."""
    
    def test_cache_config_defaults(self):
        """Test CacheConfig default values."""
        config = CacheConfig()
        
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.redis_db == 0
        assert config.redis_password is None
        assert config.redis_ssl is False
        assert config.default_ttl == 3600
        assert config.max_cache_size == 10000
        assert config.enable_compression is True
    
    def test_cache_config_custom(self):
        """Test CacheConfig with custom values."""
        config = CacheConfig(
            redis_host="redis-cluster",
            redis_port=6380,
            redis_db=1,
            redis_password="secret",
            redis_ssl=True,
            default_ttl=7200,
            max_cache_size=50000
        )
        
        assert config.redis_host == "redis-cluster"
        assert config.redis_port == 6380
        assert config.redis_db == 1
        assert config.redis_password == "secret"
        assert config.redis_ssl is True
        assert config.default_ttl == 7200
        assert config.max_cache_size == 50000


class TestQueryOptimizationConfig:
    """Test QueryOptimizationConfig dataclass."""
    
    def test_query_optimization_defaults(self):
        """Test QueryOptimizationConfig default values."""
        config = QueryOptimizationConfig()
        
        assert config.max_traversal_depth == 5
        assert config.max_results_per_query == 1000
        assert config.batch_size == 100
        assert config.connection_timeout == 30
        assert config.retry_attempts == 3
    
    def test_query_optimization_custom(self):
        """Test QueryOptimizationConfig with custom values."""
        config = QueryOptimizationConfig(
            max_traversal_depth=10,
            max_results_per_query=5000,
            batch_size=500,
            connection_timeout=60,
            retry_attempts=5
        )
        
        assert config.max_traversal_depth == 10
        assert config.max_results_per_query == 5000
        assert config.batch_size == 500
        assert config.connection_timeout == 60
        assert config.retry_attempts == 5


class TestOptimizedGraphAPI:
    """Test OptimizedGraphAPI class."""
    
    @pytest.fixture
    def mock_graph_builder(self):
        """Create a mock GraphBuilder."""
        return Mock()
    
    @pytest.fixture
    def api(self, mock_graph_builder):
        """Create OptimizedGraphAPI instance with mocks."""
        return OptimizedGraphAPI(
            graph_builder=mock_graph_builder,
            cache_config=CacheConfig(),
            optimization_config=QueryOptimizationConfig()
        )

    def test_api_initialization(self, api):
        """Test OptimizedGraphAPI initialization."""
        assert api.graph is not None
        assert api.cache_config is not None
        assert api.optimization_config is not None
        # Redis client starts unset until initialize() runs
        assert hasattr(api, 'redis_client')
        # In-memory cache fallback is always present
        assert hasattr(api, 'memory_cache')

    def test_generate_cache_key(self, api):
        """Test cache key generation."""
        query_type = "search_entities"
        params = {"limit": 10}

        cache_key = api._generate_cache_key(query_type, params)

        assert cache_key is not None
        assert isinstance(cache_key, str)
        assert len(cache_key) > 0

        # Same query type and params should generate same key
        cache_key2 = api._generate_cache_key(query_type, params)
        assert cache_key == cache_key2

        # Different params should generate different key
        different_params = {"limit": 20}
        cache_key3 = api._generate_cache_key(query_type, different_params)
        assert cache_key != cache_key3

    @pytest.mark.asyncio
    async def test_get_from_cache_redis(self, api):
        """Test getting cached results from Redis."""
        cache_key = "test_key"

        # Mock redis client; get returns None (cache miss)
        api.redis_client = AsyncMock()
        api.redis_client.get = AsyncMock(return_value=None)
        result = await api._get_from_cache(cache_key)
        assert result is None

        # Mock redis get to return cached JSON data (stored as JSON string)
        cached_data = '{"nodes": [], "edges": []}'
        api.redis_client.get = AsyncMock(return_value=cached_data)
        result = await api._get_from_cache(cache_key)
        assert result is not None
        assert "nodes" in result
        assert "edges" in result

    @pytest.mark.asyncio
    async def test_store_in_cache_redis(self, api):
        """Test caching query results via Redis."""
        cache_key = "test_key"
        data = {"nodes": [{"id": "1"}], "edges": []}

        # Mock redis client with setex
        api.redis_client = AsyncMock()
        api.redis_client.setex = AsyncMock(return_value=True)
        stored = await api._store_in_cache(cache_key, data)

        assert stored is True
        # Should have called setex with key, ttl, then serialized payload
        api.redis_client.setex.assert_called_once()
        args = api.redis_client.setex.call_args
        assert args[0][0] == cache_key
        assert args[0][1] == api.cache_config.default_ttl

    @pytest.mark.asyncio
    async def test_store_in_cache_memory_fallback(self, api):
        """Test caching falls back to in-memory store when Redis is absent."""
        cache_key = "mem_key"
        data = {"value": 123}

        # No redis_client -> memory cache fallback
        api.redis_client = None
        stored = await api._store_in_cache(cache_key, data)

        assert stored is True
        assert api.memory_cache[cache_key] == data
        assert cache_key in api.cache_timestamps

    @pytest.mark.asyncio
    async def test_get_from_cache_memory_fallback(self, api):
        """Test retrieving from in-memory cache when Redis is absent."""
        cache_key = "mem_key2"
        data = {"value": 456}

        api.redis_client = None
        await api._store_in_cache(cache_key, data)
        result = await api._get_from_cache(cache_key)
        assert result == data

    @pytest.mark.asyncio
    async def test_execute_optimized_query_basic(self, api):
        """Test basic optimized query execution."""
        traversal = Mock()

        # Source delegates to graph._execute_traversal (awaited)
        mock_result = [{"id": "test_node", "label": "Person"}]
        api.graph._execute_traversal = AsyncMock(return_value=mock_result)

        result = await api._execute_optimized_query(traversal, "test query")

        assert result is not None
        assert isinstance(result, list)
        assert result == mock_result

    @pytest.mark.asyncio
    async def test_execute_optimized_query_limits_results(self, api):
        """Test optimized query execution truncates oversized result sets."""
        traversal = Mock()
        api.optimization_config.max_results_per_query = 2

        oversized = [{"id": str(i)} for i in range(5)]
        api.graph._execute_traversal = AsyncMock(return_value=oversized)

        result = await api._execute_optimized_query(traversal, "test query")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_clear_cache(self, api):
        """Test cache clearing returns a structured result."""
        # Without redis_client, clear_cache empties the in-memory cache
        api.redis_client = None
        api.memory_cache = {"graph_api:abc": {"x": 1}}
        api.cache_timestamps = {"graph_api:abc": None}

        result = await api.clear_cache()

        assert result["status"] == "success"
        assert result["cleared_entries"] >= 1
        assert api.memory_cache == {}

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, api):
        """Test cache statistics retrieval."""
        # No redis_client -> stats come purely from in-memory metrics
        api.redis_client = None
        api.metrics["cache_hits"] = 100
        api.metrics["cache_misses"] = 20

        stats = await api.get_cache_stats()

        assert stats is not None
        assert "cache" in stats
        assert "performance" in stats
        assert "configuration" in stats
        assert stats["cache"]["hits"] == 100
        assert stats["cache"]["misses"] == 20

    def test_extract_entity_name(self, api):
        """Test entity name extraction from a value map result."""
        # 'name' field given as a list (Gremlin valueMap style)
        assert api._extract_entity_name({"name": ["Acme"]}) == "Acme"
        # Falls back to alternate name fields
        assert api._extract_entity_name({"orgName": "OrgCo"}) == "OrgCo"
        # Unknown when no name-like field present
        assert api._extract_entity_name({"foo": "bar"}) == "Unknown"

    def test_calculate_relevance(self, api):
        """Test relevance scoring for search results."""
        # Exact match scores highest
        assert api._calculate_relevance("Tesla", "tesla") == 1.0
        # Prefix match scores high
        assert api._calculate_relevance("Tesla Motors", "tesla") == 0.8
        # Substring match scores medium
        assert api._calculate_relevance("The Tesla", "tesla") == 0.6
        # No match scores low default
        assert api._calculate_relevance("Apple", "tesla") == 0.1


class TestCreateOptimizedGraphAPI:
    """Test the factory function."""
    
    def test_create_optimized_graph_api(self):
        """Test creating OptimizedGraphAPI instance."""
        neptune_endpoint = "ws://localhost:8182/gremlin"

        # GraphBuilder is imported into the optimized_api module namespace,
        # so patch it where it is looked up.
        with patch('api.graph.optimized_api.GraphBuilder'):
            api = create_optimized_graph_api(neptune_endpoint)

            assert api is not None
            assert isinstance(api, OptimizedGraphAPI)
            # Source stores the builder on the `graph` attribute
            assert api.graph is not None
            assert api.cache_config is not None
            assert api.optimization_config is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
