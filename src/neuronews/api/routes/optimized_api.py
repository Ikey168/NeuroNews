"""
Enhanced Knowledge Graph API with caching and optimization
Issue #75: Deploy Knowledge Graph API in Kubernetes

This module provides optimized graph database queries with caching layer
for real-time execution and improved performance.
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from fastapi import HTTPException
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import P, T

from src.knowledge_graph.graph_builder import GraphBuilder

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Configuration for Redis caching layer."""

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_ssl: bool = False
    default_ttl: int = 3600  # 1 hour
    max_cache_size: int = 10000
    enable_compression: bool = True


@dataclass
class QueryOptimizationConfig:
    """Configuration for graph query optimization."""

    max_traversal_depth: int = 5
    max_results_per_query: int = 1000
    batch_size: int = 100
    connection_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0


class OptimizedGraphAPI:
    """
    Optimized Knowledge Graph API with caching and performance enhancements.

    This class provides:
    - Redis-based caching for frequently accessed queries
    - Query optimization and result batching
    - Connection pooling and retry logic
    - Performance monitoring and metrics
    """

    def __init__(
        self,
        graph_builder: GraphBuilder,
        cache_config: Optional[CacheConfig] = None,
        optimization_config: Optional[QueryOptimizationConfig] = None,
    ):
        """
        Initialize the optimized graph API.

        Args:
            graph_builder: Neptune graph builder instance
            cache_config: Configuration for Redis caching
            optimization_config: Configuration for query optimization
        """
        self.graph = graph_builder
        self.cache_config = cache_config or CacheConfig()
        self.optimization_config = optimization_config or QueryOptimizationConfig()

        # Redis connection pool
        self.redis_pool: Optional[redis.ConnectionPool] = None
        self.redis_client: Optional[redis.Redis] = None

        # Performance metrics
        self.metrics = {
            "queries_total": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "query_time_total": 0.0,
            "errors_total": 0,
        }

        # Query result cache (in-memory fallback)
        self.memory_cache: Dict[str, Any] = {}
        self.cache_timestamps: Dict[str, datetime] = {}

        logger.info("OptimizedGraphAPI initialized")

    async def initialize(self):
        """Initialize Redis connection and prepare caching layer."""
        try:
            # Initialize Redis connection pool
            self.redis_pool = redis.ConnectionPool(
                host=self.cache_config.redis_host,
                port=self.cache_config.redis_port,
                db=self.cache_config.redis_db,
                password=self.cache_config.redis_password,
                ssl=self.cache_config.redis_ssl,
                max_connections=20,
                retry_on_timeout=True,
                health_check_interval=30,
            )

            self.redis_client = redis.Redis(connection_pool=self.redis_pool)

            # Test Redis connection
            await self.redis_client.ping()
            logger.info("Redis cache initialized successfully")

            return True

        except Exception as e:
            logger.warning("Redis initialization failed: {0}".format(e))
            logger.info("Falling back to in-memory caching")
            self.redis_client = None
            return False

    def _generate_cache_key(self, query_type: str, parameters: Dict[str, Any]) -> str:
        """Generate a cache key for the query."""
        # Create deterministic hash from query type and parameters
        param_str = json.dumps(parameters, sort_keys=True, default=str)
        key_data = "{0}:{1}".format(query_type, param_str)
        return "graph_api:{0}".format(hashlib.md5(key_data.encode()).hexdigest())

    async def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Retrieve data from cache (Redis or memory)."""
        try:
            if self.redis_client:
                # Try Redis cache first
                cached_data = await self.redis_client.get(cache_key)
                if cached_data:
                    self.metrics["cache_hits"] += 1
                    return json.loads(cached_data)

            # Fallback to memory cache
            if cache_key in self.memory_cache:
                # Check if cache entry is still valid
                if (
                    cache_key in self.cache_timestamps
                    and datetime.now() - self.cache_timestamps[cache_key]
                    < timedelta(seconds=self.cache_config.default_ttl)
                ):
                    self.metrics["cache_hits"] += 1
                    return self.memory_cache[cache_key]
                else:
                    # Remove expired entry
                    self.memory_cache.pop(cache_key, None)
                    self.cache_timestamps.pop(cache_key, None)

            self.metrics["cache_misses"] += 1
            return None

        except Exception as e:
            logger.warning("Cache retrieval error: {0}".format(e))
            self.metrics["cache_misses"] += 1
            return None

    async def _store_in_cache(
        self, cache_key: str, data: Any, ttl: Optional[int] = None
    ) -> bool:
        """Store data in cache (Redis or memory)."""
        ttl = ttl or self.cache_config.default_ttl

        try:
            if self.redis_client:
                # Store in Redis with TTL
                await self.redis_client.setex(
                    cache_key, ttl, json.dumps(data, default=str)
                )
                return True

            # Fallback to memory cache
            # Implement simple LRU by removing oldest entries if cache is full
            if len(self.memory_cache) >= self.cache_config.max_cache_size:
                # Remove oldest 10% of entries
                oldest_keys = sorted(
                    self.cache_timestamps.keys(), key=lambda k: self.cache_timestamps[k]
                )[: self.cache_config.max_cache_size // 10]

                for key in oldest_keys:
                    self.memory_cache.pop(key, None)
                    self.cache_timestamps.pop(key, None)

            self.memory_cache[cache_key] = data
            self.cache_timestamps[cache_key] = datetime.now()
            return True

        except Exception as e:
            logger.warning("Cache storage error: {0}".format(e))
            return False

    async def _execute_optimized_query(
        self, traversal_query, query_description: str = "graph query"
    ) -> List[Dict[str, Any]]:
        """
        Execute a graph query with optimization and retry logic.

        Args:
            traversal_query: Gremlin traversal query
            query_description: Description for logging

        Returns:
            List of query results
        """
        start_time = datetime.now()

        for attempt in range(self.optimization_config.retry_attempts):
            try:
                # Execute query with timeout
                results = await asyncio.wait_for(
                    self.graph._execute_traversal(traversal_query),
                    timeout=self.optimization_config.connection_timeout,
                )

                # Limit results to prevent memory issues
                if len(results) > self.optimization_config.max_results_per_query:
                    logger.warning(
                        "Query returned {0} results, limiting to {1}".format(
                            len(results), self.optimization_config.max_results_per_query
                        )
                    )
                    results = results[: self.optimization_config.max_results_per_query]

                # Update metrics
                query_time = (datetime.now() - start_time).total_seconds()
                self.metrics["queries_total"] += 1
                self.metrics["query_time_total"] += query_time

                logger.debug(
                    f"Query '{query_description}' completed in {
                        query_time}s, {
                        len(results)} results"
                )
                return results

            except asyncio.TimeoutError:
                logger.warning(
                    "Query timeout on attempt {0}/{1}".format(
                        attempt + 1, self.optimization_config.retry_attempts
                    )
                )
                if attempt < self.optimization_config.retry_attempts - 1:
                    await asyncio.sleep(
                        self.optimization_config.retry_delay * (attempt + 1)
                    )
                    continue
                else:
                    self.metrics["errors_total"] += 1
                    raise HTTPException(
                        status_code=408,
                        detail="Query timeout after {0} attempts".format(
                            self.optimization_config.retry_attempts
                        ),
                    )

            except Exception as e:
                logger.error("Query error on attempt {0}: {1}".format(attempt + 1, e))
                if attempt < self.optimization_config.retry_attempts - 1:
                    await asyncio.sleep(
                        self.optimization_config.retry_delay * (attempt + 1)
                    )
                    continue
                else:
                    self.metrics["errors_total"] += 1
                    raise HTTPException(
                        status_code=500, detail="Graph query failed: {0}".format(str(e))
                    )

    async def get_related_entities_optimized(
        self,
        entity: str,
        entity_type: Optional[str] = None,
        max_depth: int = 2,
        relationship_types: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Get related entities with caching and optimization.

        Args:
            entity: Entity name to find relationships for
            entity_type: Type of entity (Organization, Person, Event)
            max_depth: Maximum relationship depth to traverse
            relationship_types: Filter by relationship types
            use_cache: Whether to use caching

        Returns:
            Dictionary with entity and related entities
        """
        # Validate parameters
        max_depth = min(max_depth, self.optimization_config.max_traversal_depth)

        # Generate cache key
        cache_params = {
            "entity": entity,
            "entity_type": entity_type,
            "max_depth": max_depth,
            "relationship_types": (
                sorted(relationship_types) if relationship_types else None
            ),
        }
        cache_key = self._generate_cache_key("related_entities", cache_params)

        # Try cache first
        if use_cache:
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                logger.debug("Cache hit for related entities query: {0}".format(entity))
                return cached_result

        try:
            # Build optimized query
            g = self.graph.g
            query = g.V()

            # Filter by entity type if specified
            if entity_type:
                query = query.hasLabel(entity_type)

            # Find entity by name (case-insensitive search for better UX)
            query = query.has("name", P.eq(entity))

            # Build traversal path with optimizations
            path_query = query
            for i in range(max_depth):
                if relationship_types:
                    # Filter by specific relationship types
                    path_query = path_query.bothE(*relationship_types).otherV()
                else:
                    # All relationships
                    path_query = path_query.both()

                # Prevent cycles and duplicate paths
                path_query = path_query.simplePath()

                # Add deduplication except on final step
                if i < max_depth - 1:
                    path_query = path_query.dedup()

            # Final deduplication and property mapping
            final_traversal = (
                path_query.dedup()
                .limit(self.optimization_config.max_results_per_query)
                .valueMap(True)
            )

            # Execute optimized query
            results = await self._execute_optimized_query(
                final_traversal,
                "related_entities({0}, depth={1})".format(entity, max_depth),
            )

            # Format results
            formatted_results = {
                "entity": entity,
                "entity_type": entity_type,
                "max_depth": max_depth,
                "relationship_types": relationship_types,
                "total_related": len(results),
                "related_entities": [],
            }

            for r in results:
                try:
                    # Extract entity name from various possible fields
                    name = self._extract_entity_name(r)
                    entity_label = (
                        r.get(T.label, "Unknown") if T.label in r else "Unknown"
                    )

                    # Clean properties (remove system fields)
                    properties = {
                        k: v[0] if isinstance(v, list) and len(v) == 1 else v
                        for k, v in r.items()
                        if k not in [T.id, T.label]
                    }

                    formatted_results["related_entities"].append(
                        {"name": name, "type": entity_label, "properties": properties}
                    )

                except Exception as e:
                    logger.warning("Error formatting result: {0}".format(e))
                    continue

            # Cache the result
            if use_cache:
                await self._store_in_cache(cache_key, formatted_results)

            return formatted_results

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error in get_related_entities_optimized: {0}".format(e))
            self.metrics["errors_total"] += 1
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve related entities: {0}".format(str(e)),
            )

    def _extract_entity_name(self, result: Dict[str, Any]) -> str:
        """Extract entity name from query result."""
        # Try different name fields
        for field in ["name", "orgName", "eventName", "title"]:
            if field in result:
                value = result[field]
                if isinstance(value, list) and value:
                    return str(value[0])
                elif value:
                    return str(value)
        return "Unknown"

    async def get_event_timeline_optimized(
        self,
        topic: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Get event timeline with caching and optimization.

        Args:
            topic: Topic to create timeline for
            start_date: Start date for timeline
            end_date: End date for timeline
            limit: Maximum number of events
            use_cache: Whether to use caching

        Returns:
            Dictionary with timeline events
        """
        # Validate and limit parameters
        limit = min(limit, self.optimization_config.max_results_per_query)

        # Generate cache key
        cache_params = {
            "topic": topic,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "limit": limit,
        }
        cache_key = self._generate_cache_key("event_timeline", cache_params)

        # Try cache first
        if use_cache:
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                logger.debug("Cache hit for event timeline query: {0}".format(topic))
                return cached_result

        try:
            # Build optimized query
            g = self.graph.g
            query = g.V().hasLabel("Event")

            # Filter by topic (search in keywords or event name)
            query = query.or_(
                __.has("keywords", P.containing(topic)),
                __.has("eventName", P.containing(topic)),
                __.has("description", P.containing(topic)),
            )

            # Date range filtering
            if start_date:
                query = query.has("startDate", P.gte(start_date.isoformat()))
            if end_date:
                query = query.has("startDate", P.lte(end_date.isoformat()))

            # Order by date and limit results
            query = query.order().by("startDate").limit(limit)

            # Project specific fields for performance
            projected_query = (
                query.project("event_name", "date", "location", "description")
                .by("eventName")
                .by("startDate")
                .by("location")
                .by("description")
            )

            # Execute optimized query
            results = await self._execute_optimized_query(
                projected_query,
                "event_timeline({0}, {1} to {2})".format(topic, start_date, end_date),
            )

            # Format timeline
            timeline = {
                "topic": topic,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "total_events": len(results),
                "events": [],
            }

            for r in results:
                try:
                    timeline["events"].append(
                        {
                            "name": r.get("event_name", "Unknown Event"),
                            "date": r.get("date", "Unknown Date"),
                            "location": r.get("location", "Unknown Location"),
                            "description": r.get("description", ""),
                        }
                    )
                except Exception as e:
                    logger.warning("Error formatting timeline event: {0}".format(e))
                    continue

            # Sort events by date
            timeline["events"].sort(key=lambda x: x.get("date", ""))

            # Cache the result
            if use_cache:
                await self._store_in_cache(cache_key, timeline)

            return timeline

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error in get_event_timeline_optimized: {0}".format(e))
            self.metrics["errors_total"] += 1
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve event timeline: {0}".format(str(e)),
            )

    async def search_entities_optimized(
        self,
        search_term: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 50,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Search for entities by name or properties with caching.

        Args:
            search_term: Term to search for
            entity_types: Filter by entity types
            limit: Maximum number of results
            use_cache: Whether to use caching

        Returns:
            Dictionary with search results
        """
        # Validate parameters
        limit = min(limit, self.optimization_config.max_results_per_query)
        search_term = search_term.strip()

        if len(search_term) < 2:
            raise HTTPException(
                status_code=400, detail="Search term must be at least 2 characters"
            )

        # Generate cache key
        cache_params = {
            "search_term": search_term.lower(),
            "entity_types": sorted(entity_types) if entity_types else None,
            "limit": limit,
        }
        cache_key = self._generate_cache_key("search_entities", cache_params)

        # Try cache first
        if use_cache:
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                logger.debug("Cache hit for entity search: {0}".format(search_term))
                return cached_result

        try:
            # Build search query
            g = self.graph.g
            query = g.V()

            # Filter by entity types if specified
            if entity_types:
                query = query.hasLabel(*entity_types)

            # Text search in name fields (case-insensitive)
            search_conditions = [
                __.has("name", P.containing(search_term)),
                __.has("orgName", P.containing(search_term)),
                __.has("eventName", P.containing(search_term)),
            ]

            query = query.or_(*search_conditions).dedup().limit(limit).valueMap(True)

            # Execute optimized query
            results = await self._execute_optimized_query(
                query, "search_entities({0})".format(search_term)
            )

            # Format search results
            search_results = {
                "search_term": search_term,
                "entity_types": entity_types,
                "total_results": len(results),
                "entities": [],
            }

            for r in results:
                try:
                    name = self._extract_entity_name(r)
                    entity_type = (
                        r.get(T.label, "Unknown") if T.label in r else "Unknown"
                    )

                    # Calculate relevance score (simple implementation)
                    relevance = self._calculate_relevance(name, search_term)

                    properties = {
                        k: v[0] if isinstance(v, list) and len(v) == 1 else v
                        for k, v in r.items()
                        if k not in [T.id, T.label]
                    }

                    search_results["entities"].append(
                        {
                            "name": name,
                            "type": entity_type,
                            "relevance": relevance,
                            "properties": properties,
                        }
                    )

                except Exception as e:
                    logger.warning("Error formatting search result: {0}".format(e))
                    continue

            # Sort by relevance
            search_results["entities"].sort(key=lambda x: x["relevance"], reverse=True)

            # Cache the result
            if use_cache:
                await self._store_in_cache(cache_key, search_results)

            return search_results

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error in search_entities_optimized: {0}".format(e))
            self.metrics["errors_total"] += 1
            raise HTTPException(
                status_code=500, detail="Entity search failed: {0}".format(str(e))
            )

    def _calculate_relevance(self, name: str, search_term: str) -> float:
        """Calculate simple relevance score for search results."""
        name_lower = name.lower()
        search_lower = search_term.lower()

        # Exact match gets highest score
        if name_lower == search_lower:
            return 1.0

        # Starts with search term gets high score
        if name_lower.startswith(search_lower):
            return 0.8

        # Contains search term gets medium score
        if search_lower in name_lower:
            return 0.6

        # Word boundary matches get lower score
        words = name_lower.split()
        for word in words:
            if word.startswith(search_lower):
                return 0.4

        return 0.1  # Default low relevance

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get caching and performance statistics."""
        cache_hit_rate = 0.0
        if self.metrics["cache_hits"] + self.metrics["cache_misses"] > 0:
            cache_hit_rate = self.metrics["cache_hits"] / (
                self.metrics["cache_hits"] + self.metrics["cache_misses"]
            )

        avg_query_time = 0.0
        if self.metrics["queries_total"] > 0:
            avg_query_time = (
                self.metrics["query_time_total"] / self.metrics["queries_total"]
            )

        stats = {
            "cache": {
                "hit_rate": round(cache_hit_rate, 3),
                "hits": self.metrics["cache_hits"],
                "misses": self.metrics["cache_misses"],
                "memory_cache_size": len(self.memory_cache),
                "redis_connected": self.redis_client is not None,
            },
            "performance": {
                "total_queries": self.metrics["queries_total"],
                "average_query_time": round(avg_query_time, 3),
                "total_query_time": round(self.metrics["query_time_total"], 3),
                "error_rate": self.metrics["errors_total"]
                / max(self.metrics["queries_total"], 1),
            },
            "configuration": {
                "default_ttl": self.cache_config.default_ttl,
                "max_results_per_query": self.optimization_config.max_results_per_query,
                "max_traversal_depth": self.optimization_config.max_traversal_depth,
                "retry_attempts": self.optimization_config.retry_attempts,
            },
        }

        # Add Redis-specific stats if available
        if self.redis_client:
            try:
                redis_info = await self.redis_client.info()
                stats["cache"]["redis_info"] = {
                    "connected_clients": redis_info.get("connected_clients", 0),
                    "used_memory": redis_info.get("used_memory_human", "Unknown"),
                    "keyspace_hits": redis_info.get("keyspace_hits", 0),
                    "keyspace_misses": redis_info.get("keyspace_misses", 0),
                }
            except Exception as e:
                logger.warning("Failed to get Redis stats: {0}".format(e))

        return stats

    async def clear_cache(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        """Clear cache entries, optionally by pattern."""
        cleared_count = 0

        try:
            if self.redis_client:
                if pattern:
                    # Clear specific pattern from Redis
                    keys = await self.redis_client.keys(
                        "graph_api:*{0}*".format(pattern)
                    )
                    if keys:
                        cleared_count = await self.redis_client.delete(*keys)
                else:
                    # Clear all graph API cache entries
                    keys = await self.redis_client.keys("graph_api:*")
                    if keys:
                        cleared_count = await self.redis_client.delete(*keys)

            # Clear memory cache
            if pattern:
                keys_to_remove = [k for k in self.memory_cache.keys() if pattern in k]
                for key in keys_to_remove:
                    self.memory_cache.pop(key, None)
                    self.cache_timestamps.pop(key, None)
                cleared_count += len(keys_to_remove)
            else:
                cleared_count += len(self.memory_cache)
                self.memory_cache.clear()
                self.cache_timestamps.clear()

            return {
                "status": "success",
                "cleared_entries": cleared_count,
                "pattern": pattern,
            }

        except Exception as e:
            logger.error("Error clearing cache: {0}".format(e))
            return {
                "status": "error",
                "message": str(e),
                "cleared_entries": cleared_count,
            }

    async def close(self):
        """Close connections and cleanup resources."""
        try:
            if self.redis_client:
                await self.redis_client.close()
                logger.info("Redis connection closed")

            if self.redis_pool:
                await self.redis_pool.disconnect()
                logger.info("Redis connection pool closed")

        except Exception as e:
            logger.error("Error during cleanup: {0}".format(e))

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


def create_optimized_graph_api(neptune_endpoint: str) -> OptimizedGraphAPI:
    """
    Factory function to create an optimized graph API instance.

    Args:
        neptune_endpoint: Neptune cluster endpoint

    Returns:
        Configured OptimizedGraphAPI instance
    """
    # Create graph builder
    graph_builder = GraphBuilder(neptune_endpoint)

    # Create cache configuration from environment
    cache_config = CacheConfig(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        redis_db=int(os.getenv("REDIS_DB", "0")),
        redis_password=os.getenv("REDIS_PASSWORD"),
        redis_ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
        default_ttl=int(os.getenv("CACHE_TTL", "3600")),
        max_cache_size=int(os.getenv("MAX_CACHE_SIZE", "10000")),
    )

    # Create optimization configuration from environment
    optimization_config = QueryOptimizationConfig(
        max_traversal_depth=int(os.getenv("MAX_TRAVERSAL_DEPTH", "5")),
        max_results_per_query=int(os.getenv("MAX_RESULTS_PER_QUERY", "1000")),
        batch_size=int(os.getenv("QUERY_BATCH_SIZE", "100")),
        connection_timeout=int(os.getenv("QUERY_TIMEOUT", "30")),
        retry_attempts=int(os.getenv("RETRY_ATTEMPTS", "3")),
        retry_delay=float(os.getenv("RETRY_DELAY", "1.0")),
    )

    return OptimizedGraphAPI(graph_builder, cache_config, optimization_config)
