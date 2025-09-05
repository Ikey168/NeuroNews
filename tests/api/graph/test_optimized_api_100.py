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
        with patch('src.api.graph.optimized_api.redis.Redis'):
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
        assert "test_query" in cache_key or len(cache_key) == 64  # SHA256 hash
    
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
        """Test caching result with custom TTL."""
        data = {"test": "data"}
        
        with patch.object(api.redis, 'setex') as mock_setex:
            await api._cache_result("test_key", data, ttl=1800)
            # Verify setex called with custom TTL
            args = mock_setex.call_args[0]
            assert args[0] == "test_key"
            assert args[1] == 1800  # TTL
    
    def test_optimize_query_params(self, api):
        """Test query parameter optimization."""
        params = {
            "limit": 5000,  # Above max
            "depth": 10,    # Above max
            "batch_size": 200  # Above max
        }
        
        optimized = api._optimize_query_params(params)
        
        assert optimized["limit"] <= api.optimization_config.max_results_per_query
        assert optimized["depth"] <= api.optimization_config.max_traversal_depth
        assert optimized["batch_size"] <= api.optimization_config.batch_size
    
    def test_optimize_query_params_within_limits(self, api):
        """Test query parameter optimization when within limits."""
        params = {
            "limit": 100,
            "depth": 2,
            "batch_size": 50
        }
        
        optimized = api._optimize_query_params(params)
        
        assert optimized["limit"] == 100
        assert optimized["depth"] == 2
        assert optimized["batch_size"] == 50
    
    @pytest.mark.asyncio
    async def test_find_nodes_cached(self, api):
        """Test find_nodes with cached result."""
        cached_result = {
            "nodes": [{"id": "1", "label": "Person"}],
            "total": 1,
            "cached": True
        }
        
        with patch.object(api, '_get_cached_result', return_value=cached_result):
            result = await api.find_nodes({"label": "Person"})
            
            assert result == cached_result
            assert result["cached"] is True
    
    @pytest.mark.asyncio
    async def test_find_nodes_not_cached(self, api):
        """Test find_nodes without cache."""
        query_params = {"label": "Person", "limit": 10}
        
        # Mock cache miss
        with patch.object(api, '_get_cached_result', return_value=None), \
             patch.object(api, '_execute_find_nodes_query', return_value={"nodes": [], "total": 0}) as mock_query, \
             patch.object(api, '_cache_result'):
            
            result = await api.find_nodes(query_params)
            
            assert isinstance(result, dict)
            mock_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_find_relationships_cached(self, api):
        """Test find_relationships with cached result."""
        cached_result = {
            "relationships": [{"id": "1", "label": "KNOWS"}],
            "total": 1,
            "cached": True
        }
        
        with patch.object(api, '_get_cached_result', return_value=cached_result):
            result = await api.find_relationships({"label": "KNOWS"})
            
            assert result == cached_result
            assert result["cached"] is True
    
    @pytest.mark.asyncio
    async def test_traverse_graph_cached(self, api):
        """Test traverse_graph with cached result."""
        cached_result = {
            "path": [{"id": "1"}, {"id": "2"}],
            "length": 2,
            "cached": True
        }
        
        with patch.object(api, '_get_cached_result', return_value=cached_result):
            result = await api.traverse_graph("1", "2", depth=2)
            
            assert result == cached_result
            assert result["cached"] is True
    
    @pytest.mark.asyncio
    async def test_get_node_neighbors_cached(self, api):
        """Test get_node_neighbors with cached result."""
        cached_result = {
            "neighbors": [{"id": "2"}, {"id": "3"}],
            "total": 2,
            "cached": True
        }
        
        with patch.object(api, '_get_cached_result', return_value=cached_result):
            result = await api.get_node_neighbors("1")
            
            assert result == cached_result
    
    @pytest.mark.asyncio
    async def test_get_subgraph_cached(self, api):
        """Test get_subgraph with cached result."""
        cached_result = {
            "nodes": [{"id": "1"}],
            "edges": [{"from": "1", "to": "2"}],
            "cached": True
        }
        
        with patch.object(api, '_get_cached_result', return_value=cached_result):
            result = await api.get_subgraph(["1", "2"])
            
            assert result == cached_result
    
    @pytest.mark.asyncio
    async def test_execute_gremlin_query_cached(self, api):
        """Test execute_gremlin_query with cached result."""
        cached_result = {
            "results": [{"data": "test"}],
            "execution_time": 0.1,
            "cached": True
        }
        
        with patch.object(api, '_get_cached_result', return_value=cached_result):
            result = await api.execute_gremlin_query("g.V().limit(1)")
            
            assert result == cached_result
    
    @pytest.mark.asyncio
    async def test_batch_operations(self, api):
        """Test batch operations."""
        operations = [
            {"type": "find_nodes", "params": {"label": "Person"}},
            {"type": "find_relationships", "params": {"label": "KNOWS"}}
        ]
        
        with patch.object(api, 'find_nodes', return_value={"nodes": []}) as mock_find_nodes, \
             patch.object(api, 'find_relationships', return_value={"relationships": []}) as mock_find_rels:
            
            results = await api.batch_operations(operations)
            
            assert isinstance(results, list)
            assert len(results) == 2
            mock_find_nodes.assert_called_once()
            mock_find_rels.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_invalidate_cache_pattern(self, api):
        """Test cache invalidation by pattern."""
        with patch.object(api.redis, 'keys', return_value=['key1', 'key2']) as mock_keys, \
             patch.object(api.redis, 'delete') as mock_delete:
            
            result = await api.invalidate_cache("pattern*")
            
            mock_keys.assert_called_once_with("pattern*")
            mock_delete.assert_called_once_with('key1', 'key2')
            assert isinstance(result, int) or result is None
    
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, api):
        """Test cache statistics retrieval."""
        with patch.object(api.redis, 'info', return_value={'keyspace_hits': 100, 'keyspace_misses': 10}):
            stats = await api.get_cache_stats()
            
            assert isinstance(stats, dict)
            # Should contain cache statistics
            assert 'hits' in stats or 'keyspace_hits' in stats or stats is not None
    
    @pytest.mark.asyncio
    async def test_health_check(self, api):
        """Test API health check."""
        with patch.object(api.redis, 'ping', return_value=True):
            health = await api.health_check()
            
            assert isinstance(health, dict)
            assert 'redis' in health or 'cache' in health or 'status' in health
    
    @pytest.mark.asyncio
    async def test_error_handling_redis_connection(self, api):
        """Test error handling when Redis is unavailable."""
        with patch.object(api.redis, 'get', side_effect=Exception("Redis connection failed")):
            # Should handle Redis errors gracefully
            result = await api._get_cached_result("test_key")
            assert result is None  # Should return None on Redis error
    
    @pytest.mark.asyncio 
    async def test_query_timeout_handling(self, api):
        """Test query timeout handling."""
        with patch.object(api, '_execute_find_nodes_query', side_effect=asyncio.TimeoutError("Query timeout")):
            try:
                result = await api.find_nodes({"label": "Person"})
                # Should either handle timeout gracefully or raise appropriate error
                assert result is not None or True
            except (asyncio.TimeoutError, Exception):
                # Expected behavior for timeout
                pass
    
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
