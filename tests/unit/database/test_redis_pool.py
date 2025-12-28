import sys
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import pytest

# Mock gremlin_python before importing modules that use it
sys.modules["gremlin_python"] = MagicMock()
sys.modules["gremlin_python.process"] = MagicMock()
sys.modules["gremlin_python.process.graph_traversal"] = MagicMock()
sys.modules["gremlin_python.process.traversal"] = MagicMock()

# Mock redis.asyncio
sys.modules["redis"] = MagicMock()
sys.modules["redis.asyncio"] = MagicMock()

# Mock fastapi
sys.modules["fastapi"] = MagicMock()
sys.modules["fastapi.security"] = MagicMock()
sys.modules["fastapi.responses"] = MagicMock()
sys.modules["pydantic"] = MagicMock()
sys.modules["jwt"] = MagicMock()
sys.modules["boto3"] = MagicMock()
sys.modules["bcrypt"] = MagicMock()
sys.modules["psycopg2"] = MagicMock()
sys.modules["psycopg2.extras"] = MagicMock()

# Mock api_key_routes to avoid typing issues with Mocks
sys.modules["src.neuronews.api.routes.api_key_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.article_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.auth_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.event_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.event_timeline_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.knowledge_graph_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.sentiment_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.graph_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.search_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.sentiment_trends_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.topic_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.summary_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.user_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.veracity_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.visualization_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.enhanced_kg_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.health_routes"] = MagicMock()
sys.modules["src.neuronews.api.routes.metrics_routes"] = MagicMock()
sys.modules["torch"] = MagicMock()
sys.modules["starlette"] = MagicMock()
sys.modules["starlette.status"] = MagicMock()

# Mock GraphBuilder to avoid gremlin_python dependencies
sys.modules["src.knowledge_graph.graph_builder"] = MagicMock()

from src.neuronews.api.routes.optimized_api import OptimizedGraphAPI, CacheConfig

class TestRedisPool:
    """Test Redis connection pooling in OptimizedGraphAPI."""

    def setup_method(self):
        self.graph_builder = MagicMock()
        self.cache_config = CacheConfig(
            redis_host="localhost",
            redis_port=6379
        )
        self.api = OptimizedGraphAPI(self.graph_builder, self.cache_config)

    def test_initialize_pool(self):
        """Test Redis pool initialization."""
        async def run_test():
            with patch("src.neuronews.api.routes.optimized_api.redis.ConnectionPool") as mock_pool_cls, \
                 patch("src.neuronews.api.routes.optimized_api.redis.Redis") as mock_redis_cls:
                
                mock_pool = MagicMock()
                mock_pool_cls.return_value = mock_pool
                
                mock_client = AsyncMock()
                mock_redis_cls.return_value = mock_client
                
                result = await self.api.initialize()
                
                assert result is True
                assert self.api.redis_pool == mock_pool
                assert self.api.redis_client == mock_client
                
                mock_pool_cls.assert_called_once()
                call_args = mock_pool_cls.call_args[1]
                assert call_args["host"] == "localhost"
                assert call_args["port"] == 6379
                assert call_args["max_connections"] == 20
                
                mock_client.ping.assert_called_once()
        
        asyncio.run(run_test())

    def test_initialize_failure(self):
        """Test Redis initialization failure."""
        async def run_test():
            with patch("src.neuronews.api.routes.optimized_api.redis.ConnectionPool") as mock_pool_cls:
                mock_pool_cls.side_effect = Exception("Connection failed")
                
                result = await self.api.initialize()
                
                assert result is False
                assert self.api.redis_client is None
        
        asyncio.run(run_test())

    def test_close(self):
        """Test closing Redis connection."""
        async def run_test():
            self.api.redis_client = AsyncMock()
            self.api.redis_pool = MagicMock()
            
            await self.api.close()
            
            self.api.redis_client.close.assert_called_once()
        
        asyncio.run(run_test())
