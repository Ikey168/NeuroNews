"""
Comprehensive test suite for Optimized Graph API module.
Target: 100% test coverage for src/api/graph/optimized_api.py
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.optimized_api import (
    CacheConfig,
    QueryOptimizationConfig,
    OptimizedGraphAPI
)


class TestCacheConfig:
    """Test CacheConfig dataclass."""
    
    def test_cache_config_defaults(self):
        """Test CacheConfig with default values."""
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
            redis_host="custom-redis",
            redis_port=6380,
            redis_db=1,
            redis_password="secret",
            redis_ssl=True,
            default_ttl=7200,
            max_cache_size=5000,
            enable_compression=False
        )
        
        assert config.redis_host == "custom-redis"
        assert config.redis_port == 6380
        assert config.redis_db == 1
        assert config.redis_password == "secret"
        assert config.redis_ssl is True
        assert config.default_ttl == 7200
        assert config.max_cache_size == 5000
        assert config.enable_compression is False


class TestQueryOptimizationConfig:
    """Test QueryOptimizationConfig dataclass."""
    
    def test_query_optimization_config_defaults(self):
        """Test QueryOptimizationConfig with default values."""
        config = QueryOptimizationConfig()
        
        assert config.max_traversal_depth == 5
        assert config.max_results_per_query == 1000
        assert config.batch_size == 100
        assert config.connection_timeout == 30
        assert config.retry_attempts == 3
    
    def test_query_optimization_config_custom(self):
        """Test QueryOptimizationConfig with custom values."""
        config = QueryOptimizationConfig(
            max_traversal_depth=10,
            max_results_per_query=2000,
            batch_size=50,
            connection_timeout=60,
            retry_attempts=5
        )
        
        assert config.max_traversal_depth == 10
        assert config.max_results_per_query == 2000
        assert config.batch_size == 50
        assert config.connection_timeout == 60
        assert config.retry_attempts == 5


class TestOptimizedGraphAPI:
    """Test OptimizedGraphAPI class."""
    
    @pytest.fixture
    def cache_config(self):
        """Sample cache configuration."""
        return CacheConfig(redis_host="test-redis", redis_port=6379)
    
    @pytest.fixture
    def optimization_config(self):
        """Sample optimization configuration."""
        return QueryOptimizationConfig(max_traversal_depth=3, max_results_per_query=500)
    
    @pytest.fixture
    def mock_graph_builder(self):
        """Mock graph builder."""
        mock_builder = Mock()
        mock_builder.g = Mock()
        return mock_builder
    
    @pytest.fixture
    def api(self, cache_config, optimization_config, mock_graph_builder):
        """Create OptimizedGraphAPI instance with mocked dependencies."""
        with patch('api.graph.optimized_api.redis.Redis'):
            api = OptimizedGraphAPI(
                graph_builder=mock_graph_builder,
                cache_config=cache_config,
                optimization_config=optimization_config
            )
            return api
    
    def test_api_initialization_defaults(self, mock_graph_builder):
        """Test OptimizedGraphAPI initialization with defaults."""
        with patch('api.graph.optimized_api.redis.Redis'):
            api = OptimizedGraphAPI(graph_builder=mock_graph_builder)
            
            assert api.graph == mock_graph_builder
            assert isinstance(api.cache_config, CacheConfig)
            assert isinstance(api.optimization_config, QueryOptimizationConfig)
            assert hasattr(api, 'redis_client')
    
    def test_api_initialization_with_configs(self, cache_config, optimization_config, mock_graph_builder):
        """Test OptimizedGraphAPI initialization with custom configs."""
        with patch('api.graph.optimized_api.redis.Redis'):
            api = OptimizedGraphAPI(
                graph_builder=mock_graph_builder,
                cache_config=cache_config,
                optimization_config=optimization_config
            )
            
            assert api.graph == mock_graph_builder
            assert api.cache_config == cache_config
            assert api.optimization_config == optimization_config
    
    def test_generate_cache_key(self, api):
        """Test cache key generation."""
        query_params = {"type": "person", "limit": 10}
        
        cache_key = api._generate_cache_key("test_query", query_params)

        assert isinstance(cache_key, str)
        assert len(cache_key) > 0
        # Source uses an md5 hex digest prefixed with "graph_api:"
        assert cache_key.startswith("graph_api:")
        assert len(cache_key) == len("graph_api:") + 32  # md5 hex digest
    
    def test_generate_cache_key_consistency(self, api):
        """Test that same parameters generate same cache key."""
        params = {"id": "123", "depth": 2}
        
        key1 = api._generate_cache_key("query", params)
        key2 = api._generate_cache_key("query", params)
        
        assert key1 == key2
    
    def test_generate_cache_key_different_params(self, api):
        """Test that different parameters generate different cache keys."""
        key1 = api._generate_cache_key("query", {"id": "123"})
        key2 = api._generate_cache_key("query", {"id": "456"})
        
        assert key1 != key2
    
    @pytest.mark.asyncio
    async def test_get_cached_result_miss(self, api):
        """Test cache miss scenario."""
        result = await api._get_from_cache("nonexistent_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_cached_result_hit(self, api):
        """Test cache hit scenario."""
        cached_data = {"nodes": [{"id": "1"}], "edges": []}
        
        # Add data to memory cache since Redis is not available
        cache_key = "existing_key"
        api.memory_cache[cache_key] = cached_data
        api.cache_timestamps[cache_key] = datetime.now()
        
        result = await api._get_from_cache(cache_key)
        assert result == cached_data
    
    @pytest.mark.asyncio
    async def test_cache_result(self, api):
        """Test caching result."""
        data = {"nodes": [], "edges": []}
        
        # Test in-memory caching
        await api._store_in_cache("test_key", data)
        
        # Check that data was stored
        result = await api._get_from_cache("test_key")
        assert result == data
    
    @pytest.mark.asyncio
    async def test_cache_result_with_ttl(self, api):
        """Test caching result with custom TTL via Redis backend."""
        data = {"test": "data"}

        # Inject a mock Redis client so the Redis branch of _store_in_cache runs.
        api.redis_client = AsyncMock()

        await api._store_in_cache("test_key", data, ttl=1800)

        # Verify setex called with custom TTL
        api.redis_client.setex.assert_awaited_once()
        args = api.redis_client.setex.call_args[0]
        assert args[0] == "test_key"
        assert args[1] == 1800  # TTL
    
    @pytest.mark.asyncio
    async def test_related_entities_clamps_depth(self, api):
        """Source clamps max_depth to optimization_config.max_traversal_depth."""
        # optimization_config fixture sets max_traversal_depth=3
        with patch.object(api, '_execute_optimized_query', return_value=[]):
            result = await api.get_related_entities_optimized(
                "Acme", max_depth=99, use_cache=False
            )

        assert result["max_depth"] == api.optimization_config.max_traversal_depth
        assert result["max_depth"] == 3

    @pytest.mark.asyncio
    async def test_related_entities_depth_within_limits(self, api):
        """A max_depth within configured limits is preserved unchanged."""
        with patch.object(api, '_execute_optimized_query', return_value=[]):
            result = await api.get_related_entities_optimized(
                "Acme", max_depth=2, use_cache=False
            )

        assert result["max_depth"] == 2

    @pytest.mark.asyncio
    async def test_event_timeline_clamps_limit(self, api):
        """Source clamps timeline limit to max_results_per_query.

        The clamping runs before any Gremlin query is built, so it is
        observable on the cache-key parameters. We assert on the cache key
        rather than executing the query because the source's query build for
        this method depends on ``P.containing`` (see module-level note about
        the source bug), which is unrelated to the clamping under test.
        """
        # optimization_config fixture sets max_results_per_query=500.
        captured = {}
        real_generate = api._generate_cache_key

        def spy(query_type, params):
            captured.update(params)
            return real_generate(query_type, params)

        with patch.object(api, '_generate_cache_key', side_effect=spy), \
             patch.object(api, '_get_from_cache', return_value={"cached": True}):
            result = await api.get_event_timeline_optimized(
                "election", limit=5000, use_cache=True
            )

        # Cache hit short-circuits before the (buggy) query build.
        assert result == {"cached": True}
        # The limit passed into the cache key was clamped to the configured max.
        assert captured["limit"] == api.optimization_config.max_results_per_query
        assert captured["limit"] == 500
    
    @pytest.mark.asyncio
    async def test_get_related_entities_cached(self, api):
        """Cached related-entities query returns the cached payload directly."""
        cached_result = {
            "entity": "Acme",
            "related_entities": [{"name": "Bob", "type": "Person"}],
            "total_related": 1,
        }

        with patch.object(api, '_get_from_cache', return_value=cached_result) as mock_cache, \
             patch.object(api, '_execute_optimized_query') as mock_exec:
            result = await api.get_related_entities_optimized("Acme", use_cache=True)

            assert result == cached_result
            mock_cache.assert_awaited_once()
            # On cache hit the query must NOT be executed.
            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_related_entities_not_cached(self, api):
        """On cache miss the query executes and the result is stored."""
        with patch.object(api, '_get_from_cache', return_value=None), \
             patch.object(api, '_execute_optimized_query', return_value=[]) as mock_exec, \
             patch.object(api, '_store_in_cache') as mock_store:
            result = await api.get_related_entities_optimized("Acme", use_cache=True)

            assert isinstance(result, dict)
            assert result["entity"] == "Acme"
            assert result["total_related"] == 0
            mock_exec.assert_called_once()
            mock_store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_entities_cached(self, api):
        """Cached entity search returns the cached payload directly."""
        cached_result = {
            "search_term": "acme",
            "entities": [{"name": "Acme", "type": "Organization"}],
            "total_results": 1,
        }

        with patch.object(api, '_get_from_cache', return_value=cached_result), \
             patch.object(api, '_execute_optimized_query') as mock_exec:
            result = await api.search_entities_optimized("acme", use_cache=True)

            assert result == cached_result
            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_entities_short_term_rejected(self, api):
        """A search term shorter than 2 characters raises HTTP 400."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await api.search_entities_optimized("a")

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_clear_cache_with_pattern(self, api):
        """clear_cache with a pattern removes matching memory-cache entries."""
        # No Redis client -> memory-cache-only path.
        api.redis_client = None
        api.memory_cache = {
            "graph_api:pattern_one": {"x": 1},
            "graph_api:other": {"y": 2},
        }
        api.cache_timestamps = {
            "graph_api:pattern_one": datetime.now(),
            "graph_api:other": datetime.now(),
        }

        result = await api.clear_cache("pattern")

        assert result["status"] == "success"
        assert result["pattern"] == "pattern"
        assert "graph_api:pattern_one" not in api.memory_cache
        assert "graph_api:other" in api.memory_cache

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, api):
        """Cache statistics retrieval returns the documented structure."""
        # No Redis client so we exercise the pure in-memory metrics path.
        api.redis_client = None
        api.metrics["cache_hits"] = 100
        api.metrics["cache_misses"] = 10

        stats = await api.get_cache_stats()

        assert isinstance(stats, dict)
        assert "cache" in stats
        assert stats["cache"]["hits"] == 100
        assert stats["cache"]["misses"] == 10
        assert "performance" in stats
        assert "configuration" in stats

    @pytest.mark.asyncio
    async def test_get_cache_stats_with_redis_info(self, api):
        """Cache stats include Redis info when a Redis client is present."""
        mock_redis = AsyncMock()
        mock_redis.info.return_value = {
            "connected_clients": 3,
            "used_memory_human": "1M",
            "keyspace_hits": 100,
            "keyspace_misses": 10,
        }
        api.redis_client = mock_redis

        stats = await api.get_cache_stats()

        assert stats["cache"]["redis_connected"] is True
        assert "redis_info" in stats["cache"]
        assert stats["cache"]["redis_info"]["keyspace_hits"] == 100

    @pytest.mark.asyncio
    async def test_error_handling_redis_connection(self, api):
        """_get_from_cache handles Redis errors gracefully and returns None."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis connection failed")
        api.redis_client = mock_redis

        # Should handle Redis errors gracefully and fall through to None.
        result = await api._get_from_cache("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_timeout_handling(self, api):
        """A query timeout is surfaced as an HTTP 408 after retries exhaust."""
        from fastapi import HTTPException

        # Force the underlying traversal to always time out.
        api.optimization_config.retry_attempts = 1
        api.graph._execute_traversal = AsyncMock(side_effect=asyncio.TimeoutError())

        with pytest.raises(HTTPException) as exc_info:
            await api._execute_optimized_query(Mock(), "test query")

        assert exc_info.value.status_code == 408
    
    def test_configuration_validation(self, api):
        """Test configuration validation."""
        # Test that configurations are properly set
        assert isinstance(api.cache_config, CacheConfig)
        assert isinstance(api.optimization_config, QueryOptimizationConfig)
        
        # Test configuration values are within reasonable bounds
        assert api.cache_config.default_ttl > 0
        assert api.cache_config.max_cache_size > 0
        assert api.optimization_config.max_results_per_query > 0
        assert api.optimization_config.max_traversal_depth > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
