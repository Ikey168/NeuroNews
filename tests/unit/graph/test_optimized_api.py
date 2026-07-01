import asyncio

from unittest.mock import MagicMock

from src.api.graph.optimized_api import (
    OptimizedGraphAPI,
    CacheConfig,
    QueryOptimizationConfig,
)


def test_optimized_graph_api_methods():
    """Exercise the current OptimizedGraphAPI methods to boost coverage.

    The current source is a gremlin/Redis-backed API (not networkx/Neo4j). It
    requires a ``graph_builder`` and exposes caching helpers plus a handful of
    async stats/cache methods. This test drives the methods that do not depend
    on a live graph backend and asserts their real return shapes.
    """
    graph_builder = MagicMock()
    api = OptimizedGraphAPI(graph_builder=graph_builder)

    # Construction wiring.
    assert api.graph is graph_builder
    assert isinstance(api.cache_config, CacheConfig)
    assert isinstance(api.optimization_config, QueryOptimizationConfig)

    # Deterministic cache key generation (sync).
    key1 = api._generate_cache_key("query", {"param": "value"})
    key2 = api._generate_cache_key("query", {"param": "value"})
    key3 = api._generate_cache_key("query", {"param": "other"})
    assert key1 == key2
    assert key1 != key3
    assert key1.startswith("graph_api:")

    async def _exercise_async():
        # Force the in-memory cache path (no Redis).
        api.redis_client = None

        # Store then retrieve from the memory cache.
        stored = await api._store_in_cache("k", {"v": 1})
        assert stored is True
        assert await api._get_from_cache("k") == {"v": 1}

        # Cache stats report the structured metrics dict.
        stats = await api.get_cache_stats()
        assert isinstance(stats, dict)
        assert "cache" in stats
        assert "performance" in stats

        # Clearing the cache returns a success status and empties memory cache.
        cleared = await api.clear_cache()
        assert cleared["status"] == "success"
        assert api.memory_cache == {}

    asyncio.run(_exercise_async())
