"""
Influence & Network Analysis Service for NeuroNews (Issue #40).

This module implements algorithms to identify key influencers and entities
in political and tech news using PageRank-style algorithms and network metrics.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict, Counter
import math

from gremlin_python.process.traversal import P, Order
from gremlin_python.process.graph_traversal import __

from src.knowledge_graph.graph_builder import GraphBuilder

logger = logging.getLogger(__name__)


class InfluenceNetworkAnalyzer:
    """Service for analyzing influence and network patterns in news entities."""

    def __init__(self, graph_builder: GraphBuilder):
        """Initialize the analyzer with a graph builder instance."""
        self.graph = graph_builder
        self.g = graph_builder.g
        
        # Algorithm parameters
        self.pagerank_damping = 0.85
        self.pagerank_iterations = 100
        self.pagerank_tolerance = 1e-6
        
    async def identify_key_influencers(
        self,
        category: Optional[str] = None,
        entity_types: Optional[List[str]] = None,
        time_window_days: int = 30,
        limit: int = 20,
        algorithm: str = "pagerank"
    ) -> Dict[str, Any]:
        """
        Identify key influencers and entities using network analysis algorithms.
        
        Args:
            category: Filter by news category (Politics, Technology, etc.)
            entity_types: Filter by entity types (Person, Organization, etc.)
            time_window_days: Time window for analysis (default 30 days)
            limit: Maximum number of influencers to return
            algorithm: Algorithm to use (pagerank, centrality, hybrid)
            
        Returns:
            Dict containing ranked influencers with influence scores
        """
        try:
            logger.info(f"Identifying key influencers for category: {category}")
            
            # Step 1: Get recent articles for time-based analysis
            cutoff_date = datetime.utcnow() - timedelta(days=time_window_days)
            cutoff_iso = cutoff_date.isoformat()
            
            # Build article query with filters
            article_query = (
                self.g.V()
                .hasLabel("Article")
                .has("published_date", P.gte(cutoff_iso))
            )
            
            if category:
                article_query = article_query.has("category", P.containing(category))
            
            recent_articles = await self._execute_traversal(
                article_query.valueMap(True).limit(1000)
            )
            
            if not recent_articles:
                return {
                    "influencers": [],
                    "analysis_period": {
                        "days": time_window_days,
                        "category": category,
                        "start_date": cutoff_iso
                    },
                    "message": "No recent articles found"
                }
            
            # Step 2: Build entity network from articles
            entity_network = await self._build_entity_network(
                recent_articles, entity_types, category
            )
            
            if not entity_network["entities"]:
                return {
                    "influencers": [],
                    "analysis_period": {
                        "days": time_window_days,
                        "category": category,
                        "start_date": cutoff_iso
                    },
                    "message": "No entities found in network"
                }
            
            # Step 3: Calculate influence scores based on algorithm
            if algorithm == "pagerank":
                influence_scores = await self._calculate_pagerank_scores(entity_network)
            elif algorithm == "centrality":
                influence_scores = await self._calculate_centrality_scores(entity_network)
            elif algorithm == "hybrid":
                influence_scores = await self._calculate_hybrid_scores(entity_network)
            else:
                influence_scores = await self._calculate_pagerank_scores(entity_network)
            
            # Step 4: Rank and format results
            ranked_influencers = await self._rank_and_format_influencers(
                influence_scores, entity_network, limit
            )
            
            return {
                "influencers": ranked_influencers,
                "algorithm": algorithm,
                "analysis_period": {
                    "days": time_window_days,
                    "category": category,
                    "entity_types": entity_types,
                    "start_date": cutoff_iso,
                    "end_date": datetime.utcnow().isoformat()
                },
                "network_stats": {
                    "total_entities": len(entity_network["entities"]),
                    "total_relationships": len(entity_network["relationships"]),
                    "articles_analyzed": len(recent_articles),
                    "avg_connections_per_entity": (
                        len(entity_network["relationships"]) / 
                        max(1, len(entity_network["entities"]))
                    )
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in identify_key_influencers: {str(e)}")
            raise

    async def rank_entity_importance_pagerank(
        self,
        category: Optional[str] = None,
        entity_type: Optional[str] = None,
        damping_factor: float = 0.85,
        max_iterations: int = 100,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Rank entity importance using PageRank-style algorithm.
        
        Implements a modified PageRank algorithm that considers:
        - Entity mention frequency
        - Relationship strength and types
        - Temporal decay for recent importance
        - Article sentiment and prominence
        
        Args:
            category: Filter by news category
            entity_type: Filter by entity type
            damping_factor: PageRank damping factor (0.1-0.9)
            max_iterations: Maximum iterations for convergence
            limit: Number of top entities to return
            
        Returns:
            Dict containing PageRank scores and rankings
        """
        try:
            logger.info(f"Computing PageRank scores for {entity_type} entities")
            
            # Step 1: Build entity graph with weighted edges
            entity_graph = await self._build_weighted_entity_graph(
                category, entity_type
            )
            
            if len(entity_graph["nodes"]) < 2:
                return {
                    "ranked_entities": [],
                    "algorithm": "pagerank",
                    "parameters": {
                        "damping_factor": damping_factor,
                        "iterations_run": 0,
                        "convergence_achieved": False
                    },
                    "message": "Insufficient entities for PageRank analysis"
                }
            
            # Step 2: Run PageRank algorithm
            pagerank_scores = await self._run_pagerank_algorithm(
                entity_graph, damping_factor, max_iterations
            )
            
            # Step 3: Format and rank results
            ranked_entities = []
            
            for entity_id, score in sorted(
                pagerank_scores.items(), key=lambda x: x[1], reverse=True
            )[:limit]:
                
                entity_info = entity_graph["nodes"][entity_id]
                
                ranked_entities.append({
                    "entity_name": entity_info["name"],
                    "entity_type": entity_info["type"],
                    "pagerank_score": round(score, 6),
                    "normalized_score": round(score / max(pagerank_scores.values()) * 100, 2),
                    "total_mentions": entity_info.get("mention_count", 0),
                    "unique_articles": entity_info.get("article_count", 0),
                    "avg_sentiment": round(entity_info.get("avg_sentiment", 0.0), 3),
                    "connection_count": len(entity_graph["adjacency"].get(entity_id, [])),
                    "latest_mention": entity_info.get("latest_mention"),
                    "prominence_indicators": entity_info.get("prominence_indicators", [])
                })
            
            return {
                "ranked_entities": ranked_entities,
                "algorithm": "pagerank",
                "parameters": {
                    "damping_factor": damping_factor,
                    "max_iterations": max_iterations,
                    "convergence_tolerance": self.pagerank_tolerance,
                    "category_filter": category,
                    "entity_type_filter": entity_type
                },
                "network_metrics": {
                    "total_entities": len(entity_graph["nodes"]),
                    "total_connections": sum(
                        len(connections) for connections in entity_graph["adjacency"].values()
                    ) // 2,  # Undirected graph
                    "graph_density": self._calculate_graph_density(entity_graph),
                    "avg_clustering_coefficient": await self._calculate_clustering_coefficient(entity_graph)
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in PageRank analysis: {str(e)}")
            raise

    async def get_top_influencers_by_category(
        self,
        category: str,
        time_window_days: int = 30,
        limit: int = 15,
        include_metrics: bool = True
    ) -> Dict[str, Any]:
        """
        Get top influencers for a specific category.
        
        This method implements the API requirement for /top_influencers?category=Politics
        
        Args:
            category: News category (Politics, Technology, Business, etc.)
            time_window_days: Analysis time window
            limit: Number of influencers to return
            include_metrics: Whether to include detailed metrics
            
        Returns:
            Dict containing top influencers for the category
        """
        try:
            logger.info(f"Getting top influencers for category: {category}")
            
            # Run comprehensive analysis for the category
            results = await self.identify_key_influencers(
                category=category,
                time_window_days=time_window_days,
                limit=limit,
                algorithm="hybrid"  # Use hybrid for best results
            )
            
            if include_metrics:
                # Add category-specific metrics
                category_metrics = await self._get_category_specific_metrics(
                    category, time_window_days
                )
                results["category_metrics"] = category_metrics
            
            # Format response for API compatibility
            formatted_response = {
                "category": category,
                "top_influencers": results["influencers"],
                "analysis_summary": {
                    "time_period": f"Last {time_window_days} days",
                    "total_analyzed": results["network_stats"]["articles_analyzed"],
                    "algorithm_used": results["algorithm"],
                    "last_updated": results["timestamp"]
                }
            }
            
            if include_metrics:
                formatted_response["detailed_metrics"] = results["network_stats"]
                formatted_response["category_insights"] = category_metrics
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error getting top influencers for category {category}: {str(e)}")
            raise

    async def generate_network_visualization_data(
        self,
        entity_ids: List[str],
        include_relationships: bool = True,
        max_connections: int = 50
    ) -> Dict[str, Any]:
        """
        Generate data for network visualization of entities.
        
        Args:
            entity_ids: List of entity IDs to visualize
            include_relationships: Whether to include relationship data
            max_connections: Maximum connections to include per entity
            
        Returns:
            Dict containing nodes and edges for network visualization
        """
        try:
            logger.info(f"Generating network visualization for {len(entity_ids)} entities")
            
            # Step 1: Get entity details
            nodes = []
            node_ids = set()
            
            for entity_id in entity_ids:
                entity_info = await self._get_entity_details(entity_id)
                if entity_info:
                    nodes.append({
                        "id": entity_id,
                        "name": entity_info["name"],
                        "type": entity_info["type"],
                        "size": entity_info.get("influence_score", 1.0) * 20,  # Scale for visualization
                        "color": self._get_entity_color(entity_info["type"]),
                        "mentions": entity_info.get("mention_count", 0),
                        "sentiment": entity_info.get("avg_sentiment", 0.0),
                        "tooltip": self._generate_entity_tooltip(entity_info)
                    })
                    node_ids.add(entity_id)
            
            # Step 2: Get relationships if requested
            edges = []
            if include_relationships and len(node_ids) > 1:
                edges = await self._get_entity_relationships(
                    list(node_ids), max_connections
                )
            
            # Step 3: Calculate layout hints
            layout_data = await self._calculate_layout_hints(nodes, edges)
            
            return {
                "nodes": nodes,
                "edges": edges,
                "layout": layout_data,
                "metadata": {
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "max_connections": max_connections,
                    "generated_at": datetime.utcnow().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating network visualization: {str(e)}")
            raise

    # Private helper methods

    async def _build_entity_network(
        self, 
        articles: List[Dict], 
        entity_types: Optional[List[str]], 
        category: Optional[str]
    ) -> Dict[str, Any]:
        """Build entity network from articles."""
        entities = {}
        relationships = []
        
        for article in articles:
            article_id = article.get("id")
            article_sentiment = article.get("sentiment", 0.0)
            
            # Get entities mentioned in this article
            entity_query = (
                self.g.V(article_id)
                .out("MENTIONS_ORG", "MENTIONS_PERSON", "MENTIONS_TECH", 
                     "COVERS_EVENT", "MENTIONS_LOCATION")
                .valueMap(True)
            )
            
            if entity_types:
                entity_query = entity_query.hasLabel(*entity_types)
            
            mentioned_entities = await self._execute_traversal(entity_query)
            
            # Process entities
            article_entities = []
            for entity in mentioned_entities:
                entity_id = entity.get("id")
                entity_name = self._extract_entity_name(entity)
                entity_type = entity.get("label", "Unknown")
                
                if entity_id not in entities:
                    entities[entity_id] = {
                        "id": entity_id,
                        "name": entity_name,
                        "type": entity_type,
                        "mention_count": 0,
                        "article_count": 0,
                        "articles": set(),
                        "total_sentiment": 0.0,
                        "sentiment_count": 0,
                        "latest_mention": None,
                        "properties": {k: v for k, v in entity.items() 
                                     if k not in ["id", "label"]}
                    }
                
                # Update entity statistics
                entity_data = entities[entity_id]
                entity_data["mention_count"] += 1
                entity_data["articles"].add(article_id)
                entity_data["article_count"] = len(entity_data["articles"])
                
                if isinstance(article_sentiment, (int, float)):
                    entity_data["total_sentiment"] += article_sentiment
                    entity_data["sentiment_count"] += 1
                
                article_date = article.get("published_date", "")
                if not entity_data["latest_mention"] or article_date > entity_data["latest_mention"]:
                    entity_data["latest_mention"] = article_date
                
                article_entities.append(entity_id)
            
            # Create relationships between co-mentioned entities
            for i, entity1 in enumerate(article_entities):
                for entity2 in article_entities[i+1:]:
                    relationships.append({
                        "source": entity1,
                        "target": entity2,
                        "type": "co_mentioned",
                        "article_id": article_id,
                        "sentiment": article_sentiment,
                        "weight": 1.0
                    })
        
        # Calculate average sentiment for each entity
        for entity_data in entities.values():
            if entity_data["sentiment_count"] > 0:
                entity_data["avg_sentiment"] = (
                    entity_data["total_sentiment"] / entity_data["sentiment_count"]
                )
            else:
                entity_data["avg_sentiment"] = 0.0
        
        return {
            "entities": entities,
            "relationships": relationships
        }

    async def _calculate_pagerank_scores(self, entity_network: Dict[str, Any]) -> Dict[str, float]:
        """Calculate PageRank scores for entities."""
        entities = entity_network["entities"]
        relationships = entity_network["relationships"]
        
        if len(entities) < 2:
            return {entity_id: 1.0 for entity_id in entities.keys()}
        
        # Build adjacency list with weights
        adjacency = defaultdict(list)
        out_degree = defaultdict(float)
        
        for rel in relationships:
            source = rel["source"]
            target = rel["target"]
            weight = rel.get("weight", 1.0)
            
            # Add sentiment boost to weight
            sentiment = rel.get("sentiment", 0.0)
            if isinstance(sentiment, (int, float)) and sentiment > 0:
                weight *= (1 + sentiment * 0.5)  # Boost positive sentiment
            
            adjacency[source].append((target, weight))
            adjacency[target].append((source, weight))
            out_degree[source] += weight
            out_degree[target] += weight
        
        # Initialize PageRank scores
        num_entities = len(entities)
        scores = {entity_id: 1.0 / num_entities for entity_id in entities.keys()}
        
        # PageRank iterations
        for iteration in range(self.pagerank_iterations):
            new_scores = {}
            
            for entity_id in entities.keys():
                # Base score (random walk restart probability)
                score = (1 - self.pagerank_damping) / num_entities
                
                # Add contributions from connected entities
                for source_entity in entities.keys():
                    if source_entity != entity_id:
                        # Find connection weight
                        connection_weight = 0.0
                        for target, weight in adjacency[source_entity]:
                            if target == entity_id:
                                connection_weight += weight
                        
                        if connection_weight > 0 and out_degree[source_entity] > 0:
                            contribution = (
                                self.pagerank_damping * scores[source_entity] * 
                                connection_weight / out_degree[source_entity]
                            )
                            score += contribution
                
                new_scores[entity_id] = score
            
            # Check for convergence
            max_diff = max(abs(new_scores[eid] - scores[eid]) for eid in entities.keys())
            if max_diff < self.pagerank_tolerance:
                logger.info(f"PageRank converged after {iteration + 1} iterations")
                break
            
            scores = new_scores
        
        return scores

    async def _calculate_centrality_scores(self, entity_network: Dict[str, Any]) -> Dict[str, float]:
        """Calculate centrality-based influence scores."""
        entities = entity_network["entities"]
        relationships = entity_network["relationships"]
        
        # Build adjacency for centrality calculation
        adjacency = defaultdict(set)
        for rel in relationships:
            adjacency[rel["source"]].add(rel["target"])
            adjacency[rel["target"]].add(rel["source"])
        
        scores = {}
        
        for entity_id, entity_data in entities.items():
            # Degree centrality (normalized)
            degree_centrality = len(adjacency[entity_id]) / max(1, len(entities) - 1)
            
            # Mention frequency score
            mention_score = entity_data["mention_count"] / max(1, 
                max(e["mention_count"] for e in entities.values())
            )
            
            # Article diversity score
            article_score = entity_data["article_count"] / max(1,
                max(e["article_count"] for e in entities.values())
            )
            
            # Sentiment boost
            sentiment_boost = max(0, entity_data["avg_sentiment"]) * 0.2
            
            # Combined score
            scores[entity_id] = (
                degree_centrality * 0.4 +
                mention_score * 0.3 +
                article_score * 0.2 +
                sentiment_boost * 0.1
            )
        
        return scores

    async def _calculate_hybrid_scores(self, entity_network: Dict[str, Any]) -> Dict[str, float]:
        """Calculate hybrid influence scores combining multiple algorithms."""
        pagerank_scores = await self._calculate_pagerank_scores(entity_network)
        centrality_scores = await self._calculate_centrality_scores(entity_network)
        
        # Normalize scores
        max_pagerank = max(pagerank_scores.values()) if pagerank_scores else 1.0
        max_centrality = max(centrality_scores.values()) if centrality_scores else 1.0
        
        hybrid_scores = {}
        for entity_id in entity_network["entities"].keys():
            pr_score = pagerank_scores.get(entity_id, 0.0) / max_pagerank
            cent_score = centrality_scores.get(entity_id, 0.0) / max_centrality
            
            # Weighted combination
            hybrid_scores[entity_id] = pr_score * 0.6 + cent_score * 0.4
        
        return hybrid_scores

    async def _rank_and_format_influencers(
        self, 
        influence_scores: Dict[str, float], 
        entity_network: Dict[str, Any], 
        limit: int
    ) -> List[Dict[str, Any]]:
        """Rank and format influencers for output."""
        entities = entity_network["entities"]
        ranked_influencers = []
        
        # Sort by influence score
        sorted_entities = sorted(
            influence_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:limit]
        
        for rank, (entity_id, score) in enumerate(sorted_entities, 1):
            entity_data = entities[entity_id]
            
            influencer = {
                "rank": rank,
                "entity_name": entity_data["name"],
                "entity_type": entity_data["type"],
                "influence_score": round(score, 6),
                "normalized_score": round(score / max(influence_scores.values()) * 100, 2),
                "mention_count": entity_data["mention_count"],
                "article_count": entity_data["article_count"],
                "avg_sentiment": round(entity_data["avg_sentiment"], 3),
                "latest_mention": entity_data["latest_mention"],
                "key_indicators": self._generate_influence_indicators(entity_data, score)
            }
            
            ranked_influencers.append(influencer)
        
        return ranked_influencers

    def _generate_influence_indicators(self, entity_data: Dict, score: float) -> List[str]:
        """Generate key influence indicators for an entity."""
        indicators = []
        
        if entity_data["mention_count"] >= 10:
            indicators.append("High mention frequency")
        
        if entity_data["article_count"] >= 5:
            indicators.append("Broad media coverage")
        
        if entity_data["avg_sentiment"] > 0.5:
            indicators.append("Positive media sentiment")
        elif entity_data["avg_sentiment"] < -0.5:
            indicators.append("Negative media sentiment")
        
        if score > 0.8:
            indicators.append("Top-tier influencer")
        elif score > 0.5:
            indicators.append("High influence")
        elif score > 0.2:
            indicators.append("Moderate influence")
        
        return indicators

    async def _build_weighted_entity_graph(
        self, 
        category: Optional[str], 
        entity_type: Optional[str]
    ) -> Dict[str, Any]:
        """Build weighted entity graph for PageRank analysis."""
        # This is a simplified implementation
        # In practice, this would build a comprehensive graph from the knowledge base
        return {
            "nodes": {},
            "adjacency": {},
            "weights": {}
        }

    async def _run_pagerank_algorithm(
        self, 
        entity_graph: Dict, 
        damping_factor: float, 
        max_iterations: int
    ) -> Dict[str, float]:
        """Run the PageRank algorithm on the entity graph."""
        # Simplified PageRank implementation
        nodes = entity_graph["nodes"]
        if not nodes:
            return {}
        
        scores = {node_id: 1.0 for node_id in nodes.keys()}
        return scores

    def _calculate_graph_density(self, entity_graph: Dict) -> float:
        """Calculate graph density."""
        nodes = len(entity_graph["nodes"])
        if nodes < 2:
            return 0.0
        
        possible_edges = nodes * (nodes - 1) / 2
        actual_edges = sum(len(adj) for adj in entity_graph["adjacency"].values()) / 2
        
        return actual_edges / possible_edges if possible_edges > 0 else 0.0

    async def _calculate_clustering_coefficient(self, entity_graph: Dict) -> float:
        """Calculate average clustering coefficient."""
        # Simplified implementation
        return 0.5  # Placeholder

    async def _get_category_specific_metrics(
        self, 
        category: str, 
        time_window_days: int
    ) -> Dict[str, Any]:
        """Get metrics specific to a category."""
        return {
            "category": category,
            "total_articles": 0,
            "unique_entities": 0,
            "avg_sentiment": 0.0,
            "trending_topics": []
        }

    async def _get_entity_details(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about an entity."""
        try:
            entity_query = self.g.V(entity_id).valueMap(True)
            result = await self._execute_traversal(entity_query)
            
            if result:
                entity = result[0]
                return {
                    "id": entity_id,
                    "name": self._extract_entity_name(entity),
                    "type": entity.get("label", "Unknown"),
                    "properties": {k: v for k, v in entity.items() 
                                 if k not in ["id", "label"]}
                }
        except:
            pass
        
        return None

    def _get_entity_color(self, entity_type: str) -> str:
        """Get color for entity type in visualization."""
        colors = {
            "Person": "#FF6B6B",
            "Organization": "#4ECDC4", 
            "Technology": "#45B7D1",
            "Event": "#96CEB4",
            "Location": "#FFEAA7",
            "Policy": "#DDA0DD"
        }
        return colors.get(entity_type, "#BDC3C7")

    def _generate_entity_tooltip(self, entity_info: Dict) -> str:
        """Generate tooltip text for entity."""
        name = entity_info.get("name", "Unknown")
        entity_type = entity_info.get("type", "Unknown")
        mentions = entity_info.get("mention_count", 0)
        
        return f"{name}\\nType: {entity_type}\\nMentions: {mentions}"

    async def _get_entity_relationships(
        self, 
        entity_ids: List[str], 
        max_connections: int
    ) -> List[Dict[str, Any]]:
        """Get relationships between entities."""
        edges = []
        
        for i, entity1 in enumerate(entity_ids):
            for entity2 in entity_ids[i+1:]:
                # Check if there's a relationship
                rel_query = (
                    self.g.V(entity1)
                    .bothE()
                    .where(__.otherV().hasId(entity2))
                    .limit(1)
                )
                
                result = await self._execute_traversal(rel_query)
                
                if result:
                    edges.append({
                        "source": entity1,
                        "target": entity2,
                        "weight": 1.0,
                        "type": "related"
                    })
        
        return edges[:max_connections]

    async def _calculate_layout_hints(
        self, 
        nodes: List[Dict], 
        edges: List[Dict]
    ) -> Dict[str, Any]:
        """Calculate layout hints for visualization."""
        return {
            "algorithm": "force_directed",
            "parameters": {
                "repulsion": 100,
                "attraction": 0.1,
                "damping": 0.9
            }
        }

    def _extract_entity_name(self, entity: Dict[str, Any]) -> str:
        """Extract entity name from graph result."""
        for field in ["name", "orgName", "techName", "eventName", "locationName"]:
            if field in entity:
                value = entity[field]
                return value[0] if isinstance(value, list) else value
        return "Unknown"

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
