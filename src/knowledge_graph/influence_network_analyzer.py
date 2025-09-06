"""
Influence Network Analyzer for Knowledge Graph

This module provides functionality to analyze influence networks and relationships
within the knowledge graph structure.
"""

from typing import Dict, List, Optional, Set
import networkx as nx
from dataclasses import dataclass


@dataclass
class InfluenceNode:
    """Represents a node in the influence network."""
    node_id: str
    influence_score: float
    connections: List[str]
    metadata: Dict


class InfluenceNetworkAnalyzer:
    """Analyzer for influence networks in knowledge graphs."""
    
    def __init__(self):
        """Initialize the influence network analyzer."""
        self.graph = nx.DiGraph()
        self.influence_scores = {}
        
    def add_node(self, node_id: str, metadata: Optional[Dict] = None):
        """Add a node to the influence network."""
        if metadata is None:
            metadata = {}
        self.graph.add_node(node_id, **metadata)
        
    def add_edge(self, source: str, target: str, weight: float = 1.0):
        """Add an edge to the influence network."""
        self.graph.add_edge(source, target, weight=weight)
        
    def calculate_influence_scores(self) -> Dict[str, float]:
        """Calculate influence scores for all nodes."""
        if len(self.graph.nodes) == 0:
            return {}
            
        # Use PageRank algorithm for influence scoring
        try:
            scores = nx.pagerank(self.graph)
            self.influence_scores = scores
            return scores
        except:
            # Fallback to simple degree centrality
            scores = nx.degree_centrality(self.graph)
            self.influence_scores = scores
            return scores
            
    def get_top_influencers(self, n: int = 10) -> List[InfluenceNode]:
        """Get the top N most influential nodes."""
        if not self.influence_scores:
            self.calculate_influence_scores()
            
        sorted_nodes = sorted(
            self.influence_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]
        
        result = []
        for node_id, score in sorted_nodes:
            connections = list(self.graph.neighbors(node_id))
            metadata = self.graph.nodes.get(node_id, {})
            result.append(InfluenceNode(
                node_id=node_id,
                influence_score=score,
                connections=connections,
                metadata=metadata
            ))
            
        return result
        
    def analyze_influence_path(self, source: str, target: str) -> Optional[List[str]]:
        """Analyze the influence path between two nodes."""
        try:
            if source in self.graph and target in self.graph:
                return nx.shortest_path(self.graph, source, target)
        except:
            pass
        return None
        
    def get_network_stats(self) -> Dict:
        """Get basic network statistics."""
        return {
            'node_count': len(self.graph.nodes),
            'edge_count': len(self.graph.edges),
            'density': nx.density(self.graph) if len(self.graph.nodes) > 0 else 0,
            'is_connected': nx.is_weakly_connected(self.graph) if len(self.graph.nodes) > 0 else False
        }
