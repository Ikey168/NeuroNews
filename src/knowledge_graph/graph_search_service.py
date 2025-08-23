"""
Graph-based search service for news trends analysis (Issue #39).

This module implements semantic search and trending topics analysis
using knowledge graph relationships and graph algorithms.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import json
import asyncio
from collections import defaultdict, Counter

from gremlin_python.process.traversal import P, Order
from gremlin_python.process.graph_traversal import __

from src.knowledge_graph.graph_builder import GraphBuilder

logger = logging.getLogger(__name__)


class GraphBasedSearchService:
    """Service for performing graph-based search and trend analysis."""

    def __init__(self, graph_builder: GraphBuilder):
        """Initialize the service with a graph builder instance."""
        self.graph = graph_builder
        self.g = graph_builder.g
        
    async def semantic_search_related_news(
        self,
        query_term: str,
        entity_types: Optional[List[str]] = None,
        relationship_depth: int = 2,
        limit: int = 20,
        include_sentiment: bool = True
    ) -> Dict[str, Any]:
        """
        Perform semantic search for news related to a query term.
        
        Uses graph relationships to find semantically related articles
        beyond simple keyword matching.
        
        Args:
            query_term: The search term or entity name
            entity_types: Filter by entity types (Organization, Person, Technology, etc.)
            relationship_depth: How deep to traverse relationships (1-3)
            limit: Maximum number of articles to return
            include_sentiment: Whether to include sentiment analysis
            
        Returns:
            Dict containing related articles and their graph connections
        """
        try:
            logger.info(f"Performing semantic search for: {query_term}")
            
            # Step 1: Find entities matching the query term
            entity_query = self.g.V()
            
            if entity_types:
                entity_query = entity_query.hasLabel(*entity_types)
                
            # Search across multiple entity name fields
            entity_query = entity_query.or_(
                __.has("name", P.eq(query_term)),
                __.has("orgName", P.eq(query_term)),
                __.has("techName", P.eq(query_term)),
                __.has("eventName", P.eq(query_term)),
                __.has("normalized_form", P.eq(query_term))
            )
            
            # Get the matching entities
            matching_entities = await self._execute_traversal(
                entity_query.valueMap(True).limit(10)
            )
            
            if not matching_entities:
                return {
                    "query": query_term,
                    "articles": [],
                    "total_found": 0,
                    "entity_matches": [],
                    "message": "No matching entities found"
                }
            
            # Step 2: Find articles through relationship traversal
            related_articles = []
            entity_connections = {}
            
            for entity in matching_entities:
                entity_id = entity.get("id")
                entity_name = self._extract_entity_name(entity)
                
                # Traverse relationships to find connected articles
                article_query = (
                    self.g.V(entity_id)
                    .repeat(
                        __.bothE().otherV().simplePath()
                    ).times(relationship_depth)
                    .hasLabel("Article")
                    .dedup()
                )
                
                if include_sentiment:
                    article_query = article_query.project(
                        "id", "title", "url", "published_date", "category", 
                        "source", "sentiment", "summary", "connection_path"
                    ).by("id").by("title").by("url").by("published_date").by("category").by("source").by("sentiment").by("summary").by(
                        __.path().by(__.valueMap("name", "orgName", "techName", "eventName"))
                    )
                else:
                    article_query = article_query.project(
                        "id", "title", "url", "published_date", "category", 
                        "source", "summary", "connection_path"
                    ).by("id").by("title").by("url").by("published_date").by("category").by("source").by("summary").by(
                        __.path().by(__.valueMap("name", "orgName", "techName", "eventName"))
                    )
                
                entity_articles = await self._execute_traversal(
                    article_query.limit(limit)
                )
                
                # Store the connection information
                entity_connections[entity_name] = {
                    "entity_type": entity.get("label", "Unknown"),
                    "articles_found": len(entity_articles),
                    "entity_properties": {k: v for k, v in entity.items() 
                                        if k not in ["id", "label"]}
                }
                
                related_articles.extend(entity_articles)
            
            # Step 3: Deduplicate and rank articles
            seen_articles = {}
            for article in related_articles:
                article_id = article.get("id")
                if article_id not in seen_articles:
                    seen_articles[article_id] = article
                    # Add relevance scoring based on connection strength
                    article["relevance_score"] = self._calculate_relevance_score(
                        article, query_term, matching_entities
                    )
            
            # Sort by relevance and published date
            final_articles = sorted(
                seen_articles.values(),
                key=lambda x: (x.get("relevance_score", 0), x.get("published_date", "")),
                reverse=True
            )[:limit]
            
            return {
                "query": query_term,
                "articles": final_articles,
                "total_found": len(final_articles),
                "entity_matches": [
                    {
                        "name": self._extract_entity_name(e),
                        "type": e.get("label", "Unknown"),
                        "confidence": 1.0  # Would be calculated based on search relevance
                    } for e in matching_entities
                ],
                "entity_connections": entity_connections,
                "search_params": {
                    "relationship_depth": relationship_depth,
                    "entity_types": entity_types,
                    "include_sentiment": include_sentiment
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in semantic search: {str(e)}")
            raise

    async def query_trending_topics_by_graph(
        self,
        category: Optional[str] = None,
        time_window_hours: int = 24,
        min_connections: int = 3,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Query trending topics based on graph relationships and activity.
        
        Analyzes entity relationships, article connections, and temporal patterns
        to identify trending topics.
        
        Args:
            category: Optional category filter (Technology, Politics, Business, etc.)
            time_window_hours: Time window for trend analysis
            min_connections: Minimum number of connections for trending topics
            limit: Maximum number of trending topics to return
            
        Returns:
            Dict containing trending topics with their graph metrics
        """
        try:
            logger.info(f"Analyzing trending topics for category: {category}")
            
            # Calculate time cutoff
            cutoff_time = datetime.utcnow() - timedelta(hours=time_window_hours)
            cutoff_iso = cutoff_time.isoformat()
            
            # Step 1: Find recent articles
            article_query = (
                self.g.V()
                .hasLabel("Article")
                .has("published_date", P.gte(cutoff_iso))
            )
            
            if category:
                article_query = article_query.has("category", P.eq(category))
            
            recent_articles = await self._execute_traversal(
                article_query.valueMap(True).limit(1000)
            )
            
            if not recent_articles:
                return {
                    "trending_topics": [],
                    "analysis_period": {
                        "hours": time_window_hours,
                        "start_time": cutoff_iso,
                        "end_time": datetime.utcnow().isoformat()
                    },
                    "message": "No recent articles found"
                }
            
            # Step 2: Analyze entity connections and frequencies
            entity_stats = defaultdict(lambda: {
                "mentions": 0,
                "articles": set(),
                "connections": set(),
                "total_sentiment": 0.0,
                "sentiment_count": 0,
                "entity_type": "Unknown",
                "latest_mention": None
            })
            
            # Process each article to gather entity statistics
            for article in recent_articles:
                article_id = article.get("id")
                article_date = article.get("published_date")
                article_sentiment = article.get("sentiment", 0.0)
                
                # Find entities mentioned in this article
                entity_query = (
                    self.g.V(article_id)
                    .out("MENTIONS_ORG", "MENTIONS_PERSON", "MENTIONS_TECH", "COVERS_EVENT")
                    .valueMap(True)
                )
                
                mentioned_entities = await self._execute_traversal(entity_query)
                
                for entity in mentioned_entities:
                    entity_name = self._extract_entity_name(entity)
                    entity_type = entity.get("label", "Unknown")
                    
                    stats = entity_stats[entity_name]
                    stats["mentions"] += 1
                    stats["articles"].add(article_id)
                    stats["entity_type"] = entity_type
                    
                    # Update sentiment tracking
                    if isinstance(article_sentiment, (int, float)):
                        stats["total_sentiment"] += article_sentiment
                        stats["sentiment_count"] += 1
                    
                    # Track latest mention
                    if not stats["latest_mention"] or article_date > stats["latest_mention"]:
                        stats["latest_mention"] = article_date
                    
                    # Find connections to other entities
                    connection_query = (
                        self.g.V(entity.get("id"))
                        .bothE()
                        .otherV()
                        .hasLabel("Organization", "Person", "Technology", "Event")
                        .values("name", "orgName", "techName", "eventName")
                        .dedup()
                    )
                    
                    connections = await self._execute_traversal(connection_query)
                    stats["connections"].update(connections)
            
            # Step 3: Calculate trending scores and rank topics
            trending_topics = []
            
            for entity_name, stats in entity_stats.items():
                if len(stats["articles"]) >= min_connections:
                    # Calculate trending score based on multiple factors
                    trending_score = self._calculate_trending_score(
                        stats, time_window_hours
                    )
                    
                    avg_sentiment = (
                        stats["total_sentiment"] / stats["sentiment_count"]
                        if stats["sentiment_count"] > 0 else 0.0
                    )
                    
                    trending_topics.append({
                        "topic": entity_name,
                        "entity_type": stats["entity_type"],
                        "trending_score": trending_score,
                        "mentions": stats["mentions"],
                        "unique_articles": len(stats["articles"]),
                        "graph_connections": len(stats["connections"]),
                        "avg_sentiment": round(avg_sentiment, 3),
                        "latest_mention": stats["latest_mention"],
                        "velocity": stats["mentions"] / time_window_hours,  # mentions per hour
                        "connection_diversity": len(stats["connections"]) / max(1, stats["mentions"])
                    })
            
            # Sort by trending score
            trending_topics.sort(key=lambda x: x["trending_score"], reverse=True)
            
            return {
                "trending_topics": trending_topics[:limit],
                "analysis_period": {
                    "hours": time_window_hours,
                    "start_time": cutoff_iso,
                    "end_time": datetime.utcnow().isoformat(),
                    "category_filter": category
                },
                "criteria": {
                    "min_connections": min_connections,
                    "total_entities_analyzed": len(entity_stats),
                    "qualifying_topics": len(trending_topics)
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in trending topics analysis: {str(e)}")
            raise

    async def cache_frequent_queries(
        self,
        popular_queries: List[str],
        cache_duration_hours: int = 6
    ) -> Dict[str, Any]:
        """
        Pre-compute and cache results for frequent queries.
        
        Args:
            popular_queries: List of frequently searched terms
            cache_duration_hours: How long to cache results
            
        Returns:
            Dict with cache statistics and operations performed
        """
        try:
            logger.info(f"Caching {len(popular_queries)} frequent queries")
            
            cache_results = {
                "cached_queries": [],
                "cache_duration_hours": cache_duration_hours,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            for query in popular_queries:
                try:
                    # Pre-compute semantic search results
                    search_results = await self.semantic_search_related_news(
                        query_term=query,
                        limit=50,
                        include_sentiment=True
                    )
                    
                    # Pre-compute trending analysis if applicable
                    trending_results = None
                    if query.lower() in ["technology", "politics", "business", "health"]:
                        trending_results = await self.query_trending_topics_by_graph(
                            category=query,
                            time_window_hours=24
                        )
                    
                    cache_entry = {
                        "query": query,
                        "search_results_count": search_results.get("total_found", 0),
                        "trending_analysis": trending_results is not None,
                        "cache_timestamp": datetime.utcnow().isoformat(),
                        "expires_at": (
                            datetime.utcnow() + timedelta(hours=cache_duration_hours)
                        ).isoformat()
                    }
                    
                    cache_results["cached_queries"].append(cache_entry)
                    
                    # Simulate cache storage (would use Redis in production)
                    logger.info(f"Cached results for query: {query}")
                    
                except Exception as e:
                    logger.warning(f"Failed to cache query '{query}': {str(e)}")
                    
                # Add small delay to avoid overwhelming the graph database
                await asyncio.sleep(0.1)
            
            cache_results["total_cached"] = len(cache_results["cached_queries"])
            cache_results["status"] = "completed"
            
            return cache_results
            
        except Exception as e:
            logger.error(f"Error in cache operation: {str(e)}")
            raise

    def _extract_entity_name(self, entity: Dict[str, Any]) -> str:
        """Extract the display name from an entity."""
        for field in ["name", "orgName", "techName", "eventName", "locationName"]:
            if field in entity:
                value = entity[field]
                return value[0] if isinstance(value, list) else value
        return "Unknown"

    def _calculate_relevance_score(
        self,
        article: Dict[str, Any],
        query_term: str,
        matching_entities: List[Dict[str, Any]]
    ) -> float:
        """Calculate relevance score for an article."""
        score = 0.0
        
        # Base score for being connected to matching entities
        score += 1.0
        
        # Boost for title mentions
        title = article.get("title", "").lower()
        if query_term.lower() in title:
            score += 2.0
        
        # Boost for recent articles
        pub_date = article.get("published_date", "")
        try:
            article_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            days_old = (datetime.utcnow() - article_date.replace(tzinfo=None)).days
            recency_boost = max(0, 1.0 - (days_old / 30))  # Decay over 30 days
            score += recency_boost
        except:
            pass
        
        # Boost for positive sentiment
        sentiment = article.get("sentiment", 0.0)
        if isinstance(sentiment, (int, float)) and sentiment > 0:
            score += sentiment * 0.5
        
        return round(score, 3)

    def _calculate_trending_score(
        self,
        entity_stats: Dict[str, Any],
        time_window_hours: int
    ) -> float:
        """Calculate trending score for an entity."""
        # Base factors
        mention_count = entity_stats["mentions"]
        article_count = len(entity_stats["articles"])
        connection_count = len(entity_stats["connections"])
        
        # Velocity (mentions per hour)
        velocity = mention_count / max(1, time_window_hours)
        
        # Connection diversity (how well connected the entity is)
        diversity = connection_count / max(1, mention_count)
        
        # Recency boost based on latest mention
        recency_factor = 1.0
        if entity_stats["latest_mention"]:
            try:
                latest = datetime.fromisoformat(
                    entity_stats["latest_mention"].replace("Z", "+00:00")
                )
                hours_since = (
                    datetime.utcnow() - latest.replace(tzinfo=None)
                ).total_seconds() / 3600
                recency_factor = max(0.1, 1.0 - (hours_since / time_window_hours))
            except:
                pass
        
        # Calculate composite score
        trending_score = (
            mention_count * 0.3 +           # Raw mention frequency
            article_count * 0.25 +          # Article diversity
            velocity * 20 * 0.2 +           # Velocity (scaled)
            diversity * 5 * 0.15 +          # Connection diversity (scaled)
            recency_factor * 0.1            # Recency boost
        )
        
        return round(trending_score, 3)

    async def _execute_traversal(self, traversal):
        """Execute a Gremlin traversal with error handling."""
        try:
            if hasattr(traversal, 'toList'):
                return traversal.toList()
            else:
                return await self.graph._execute_traversal(traversal)
        except Exception as e:
            logger.error(f"Error executing traversal: {str(e)}")
            return []
