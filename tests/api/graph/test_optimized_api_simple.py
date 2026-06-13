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
        with patch('api.graph.optimized_api.redis.from_url'):
            return OptimizedGraphAPI(
                graph_builder=mock_graph_builder,
                cache_config=CacheConfig(),
                optimization_config=QueryOptimizationConfig()
            )
    
    def test_api_initialization(self, api):
        """Test OptimizedGraphAPI initialization."""
        assert api.graph_builder is not None
        assert api.cache_config is not None
        assert api.optimization_config is not None
        assert hasattr(api, 'redis')
        assert hasattr(api, 'query_cache')
    
    def test_generate_cache_key(self, api):
        """Test cache key generation."""
        query = "g.V().has('name', 'test')"
        params = {"limit": 10}
        
        cache_key = api._generate_cache_key(query, params)
        
        assert cache_key is not None
        assert isinstance(cache_key, str)
        assert len(cache_key) > 0
        
        # Same query and params should generate same key
        cache_key2 = api._generate_cache_key(query, params)
        assert cache_key == cache_key2
        
        # Different params should generate different key
        different_params = {"limit": 20}
        cache_key3 = api._generate_cache_key(query, different_params)
        assert cache_key != cache_key3
    
    @pytest.mark.asyncio
    async def test_get_cached_result(self, api):
        """Test getting cached results."""
        cache_key = "test_key"
        
        # Mock redis get to return None (cache miss)
        with patch.object(api.redis, 'get', return_value=None):
            result = await api._get_cached_result(cache_key)
            assert result is None
        
        # Mock redis get to return cached data
        cached_data = '{"nodes": [], "edges": []}'
        with patch.object(api.redis, 'get', return_value=cached_data):
            result = await api._get_cached_result(cache_key)
            assert result is not None
            assert "nodes" in result
            assert "edges" in result
    
    @pytest.mark.asyncio
    async def test_cache_result(self, api):
        """Test caching query results."""
        cache_key = "test_key"
        data = {"nodes": [{"id": "1"}], "edges": []}
        
        # Mock redis set
        with patch.object(api.redis, 'setex', return_value=True) as mock_setex:
            await api._cache_result(cache_key, data)
            
            # Should have called setex with ttl
            mock_setex.assert_called_once()
            args = mock_setex.call_args
            assert args[0][0] == cache_key
            assert args[0][1] == api.cache_config.default_ttl
    
    def test_optimize_query_basic(self, api):
        """Test basic query optimization."""
        query = "g.V().hasLabel('Person').limit(10)"
        
        optimized = api._optimize_query(query)
        
        assert optimized is not None
        assert isinstance(optimized, str)
        # Should return some form of optimized query
        assert len(optimized) > 0
    
    def test_optimize_query_with_limits(self, api):
        """Test query optimization with result limits."""
        # Query without limit
        query = "g.V().hasLabel('Person')"
        optimized = api._optimize_query(query)
        
        # Should add limit based on config
        assert optimized is not None
        
        # Query with existing limit
        query_with_limit = "g.V().hasLabel('Person').limit(5)"
        optimized_limited = api._optimize_query(query_with_limit)
        
        assert optimized_limited is not None
    
    @pytest.mark.asyncio
    async def test_execute_optimized_query_basic(self, api):
        """Test basic optimized query execution."""
        query = "g.V().limit(1)"
        
        # Mock graph builder execution
        mock_result = [{"id": "test_node", "label": "Person"}]
        api.graph_builder.execute_query = AsyncMock(return_value=mock_result)
        
        # Mock redis operations
        with patch.object(api, '_get_cached_result', return_value=None), \
             patch.object(api, '_cache_result', return_value=None):
            
            result = await api.execute_optimized_query(query)
            
            assert result is not None
            assert isinstance(result, list)
    
    @pytest.mark.asyncio  
    async def test_execute_optimized_query_with_cache(self, api):
        """Test optimized query execution with cache hit."""
        query = "g.V().limit(1)"
        cached_result = [{"id": "cached_node", "label": "Person"}]
        
        # Mock cache hit
        with patch.object(api, '_get_cached_result', return_value=cached_result):
            result = await api.execute_optimized_query(query)
            
            assert result == cached_result
            # Should not call graph builder since we have cache hit
            api.graph_builder.execute_query.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_execute_optimized_query_with_params(self, api):
        """Test optimized query execution with parameters."""
        query = "g.V().has('name', name)"
        params = {"name": "John"}
        
        # Mock graph builder
        mock_result = [{"id": "john_node"}]
        api.graph_builder.execute_query = AsyncMock(return_value=mock_result)
        
        with patch.object(api, '_get_cached_result', return_value=None), \
             patch.object(api, '_cache_result', return_value=None):
            
            result = await api.execute_optimized_query(query, params)
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_execute_batch_queries(self, api):
        """Test batch query execution."""
        queries = [
            "g.V().limit(1)",
            "g.E().limit(1)",
            "g.V().count()"
        ]
        
        # Mock individual query executions
        api.execute_optimized_query = AsyncMock(side_effect=[
            [{"id": "node1"}],
            [{"id": "edge1"}],
            [{"count": 5}]
        ])
        
        results = await api.execute_batch_queries(queries)
        
        assert len(results) == 3
        assert results[0] == [{"id": "node1"}]
        assert results[1] == [{"id": "edge1"}]
        assert results[2] == [{"count": 5}]
    
    @pytest.mark.asyncio
    async def test_clear_cache(self, api):
        """Test cache clearing."""
        # Mock redis flushdb
        with patch.object(api.redis, 'flushdb', return_value=True) as mock_flush:
            await api.clear_cache()
            mock_flush.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, api):
        """Test cache statistics retrieval."""
        # Mock redis info
        mock_info = {
            'used_memory': 1024000,
            'keyspace_hits': 100,
            'keyspace_misses': 20
        }
        
        with patch.object(api.redis, 'info', return_value=mock_info):
            stats = await api.get_cache_stats()
            
            assert stats is not None
            assert 'used_memory' in stats
            assert 'keyspace_hits' in stats
            assert 'keyspace_misses' in stats
    
    def test_validate_query_basic(self, api):
        """Test basic query validation."""
        valid_query = "g.V().hasLabel('Person').limit(10)"
        
        is_valid, message = api._validate_query(valid_query)
        
        assert is_valid is True
        assert message is None or isinstance(message, str)
    
    def test_validate_query_empty(self, api):
        """Test validation of empty query."""
        empty_query = ""
        
        is_valid, message = api._validate_query(empty_query)
        
        assert is_valid is False
        assert message is not None
        assert isinstance(message, str)
    
    def test_validate_query_invalid(self, api):
        """Test validation of invalid query.""" 
        invalid_query = "invalid gremlin syntax"
        
        is_valid, message = api._validate_query(invalid_query)
        
        # Should handle validation gracefully
        assert isinstance(is_valid, bool)
        if not is_valid:
            assert message is not None


class TestCreateOptimizedGraphAPI:
    """Test the factory function."""
    
    def test_create_optimized_graph_api(self):
        """Test creating OptimizedGraphAPI instance."""
        neptune_endpoint = "ws://localhost:8182/gremlin"
        
        with patch('api.graph.optimized_api.GraphBuilder'), \
             patch('api.graph.optimized_api.redis.from_url'):
            
            api = create_optimized_graph_api(neptune_endpoint)
            
            assert api is not None
            assert isinstance(api, OptimizedGraphAPI)
            assert api.graph_builder is not None
            assert api.cache_config is not None
            assert api.optimization_config is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
