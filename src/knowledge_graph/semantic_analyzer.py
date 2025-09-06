"""
Semantic Analyzer for Knowledge Graph

This module provides semantic relationship analysis capabilities for the knowledge graph,
including entity relationship detection, semantic similarity computation, and contextual
analysis of graph data.

Key Features:
- Semantic relationship extraction and classification
- Entity similarity and clustering analysis  
- Contextual relevance scoring
- Relationship strength computation
- Semantic pattern recognition
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
import math
import json

logger = logging.getLogger(__name__)


class RelationshipType(Enum):
    """Types of semantic relationships."""
    CAUSAL = "causal"
    TEMPORAL = "temporal"
    HIERARCHICAL = "hierarchical"
    ASSOCIATIVE = "associative"
    SIMILARITY = "similarity"
    OPPOSITION = "opposition"
    PART_OF = "part_of"
    INSTANCE_OF = "instance_of"


class SemanticStrength(Enum):
    """Strength levels for semantic relationships."""
    VERY_WEAK = "very_weak"
    WEAK = "weak" 
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


@dataclass
class SemanticRelationship:
    """Represents a semantic relationship between entities."""
    source_entity: str
    target_entity: str
    relationship_type: RelationshipType
    strength: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    context: List[str]
    properties: Dict[str, Any]


@dataclass
class EntityCluster:
    """Represents a cluster of semantically similar entities."""
    cluster_id: str
    entities: List[str]
    centroid_entity: str
    coherence_score: float
    keywords: List[str]
    cluster_type: str


@dataclass
class SemanticAnalysisResult:
    """Result of semantic analysis operation."""
    analysis_id: str
    entity_count: int
    relationship_count: int
    clusters: List[EntityCluster]
    relationships: List[SemanticRelationship]
    semantic_metrics: Dict[str, float]
    execution_time_ms: float


class SemanticAnalyzer:
    """
    Advanced semantic relationship analysis for knowledge graph entities.
    
    Provides comprehensive semantic analysis including relationship detection,
    entity clustering, similarity computation, and contextual analysis.
    """
    
    def __init__(self, similarity_threshold: float = 0.7):
        """
        Initialize the semantic analyzer.
        
        Args:
            similarity_threshold: Minimum threshold for considering entities similar
        """
        self.similarity_threshold = similarity_threshold
        self.entity_vectors = {}  # Mock vector storage
        self.relationship_cache = {}
        self.analysis_stats = {
            'total_analyses': 0,
            'total_relationships_found': 0,
            'total_clusters_created': 0
        }
        
    def analyze_entity_relationships(
        self,
        entities: List[Dict[str, Any]],
        context_data: Optional[List[str]] = None,
        include_weak_relationships: bool = False
    ) -> SemanticAnalysisResult:
        """
        Analyze semantic relationships between a set of entities.
        
        Args:
            entities: List of entity dictionaries with properties
            context_data: Additional context for relationship analysis
            include_weak_relationships: Whether to include weak relationships
            
        Returns:
            SemanticAnalysisResult with detected relationships and clusters
        """
        import time
        start_time = time.time()
        
        analysis_id = f"analysis_{hash(json.dumps(entities, sort_keys=True))}"
        
        # Extract relationships
        relationships = self._extract_relationships(
            entities, 
            context_data or [],
            include_weak_relationships
        )
        
        # Create entity clusters
        clusters = self._create_entity_clusters(entities)
        
        # Calculate semantic metrics
        metrics = self._calculate_semantic_metrics(entities, relationships, clusters)
        
        execution_time = (time.time() - start_time) * 1000
        
        result = SemanticAnalysisResult(
            analysis_id=analysis_id,
            entity_count=len(entities),
            relationship_count=len(relationships),
            clusters=clusters,
            relationships=relationships,
            semantic_metrics=metrics,
            execution_time_ms=execution_time
        )
        
        # Update statistics
        self.analysis_stats['total_analyses'] += 1
        self.analysis_stats['total_relationships_found'] += len(relationships)
        self.analysis_stats['total_clusters_created'] += len(clusters)
        
        return result
    
    def compute_entity_similarity(
        self,
        entity1: Dict[str, Any],
        entity2: Dict[str, Any],
        similarity_method: str = "combined"
    ) -> float:
        """
        Compute semantic similarity between two entities.
        
        Args:
            entity1: First entity dictionary
            entity2: Second entity dictionary
            similarity_method: Method to use ('textual', 'structural', 'combined')
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        # Mock similarity computation
        entity1_name = entity1.get('name', '').lower()
        entity2_name = entity2.get('name', '').lower()
        
        if similarity_method == "textual":
            return self._compute_textual_similarity(entity1_name, entity2_name)
        elif similarity_method == "structural":
            return self._compute_structural_similarity(entity1, entity2)
        else:  # combined
            textual_sim = self._compute_textual_similarity(entity1_name, entity2_name)
            structural_sim = self._compute_structural_similarity(entity1, entity2)
            return (textual_sim + structural_sim) / 2.0
    
    def find_semantic_patterns(
        self,
        relationships: List[SemanticRelationship],
        pattern_type: str = "frequent"
    ) -> List[Dict[str, Any]]:
        """
        Find semantic patterns in relationships.
        
        Args:
            relationships: List of semantic relationships to analyze
            pattern_type: Type of patterns to find ('frequent', 'chain', 'hub')
            
        Returns:
            List of detected patterns with metadata
        """
        patterns = []
        
        if pattern_type == "frequent":
            # Find frequently occurring relationship types
            type_counts = {}
            for rel in relationships:
                rel_type = rel.relationship_type.value
                type_counts[rel_type] = type_counts.get(rel_type, 0) + 1
            
            for rel_type, count in type_counts.items():
                if count >= 3:  # Threshold for "frequent"
                    patterns.append({
                        'pattern_type': 'frequent_relationship',
                        'relationship_type': rel_type,
                        'frequency': count,
                        'relative_frequency': count / len(relationships)
                    })
        
        elif pattern_type == "chain":
            # Find relationship chains (A->B->C)
            entity_connections = {}
            for rel in relationships:
                if rel.source_entity not in entity_connections:
                    entity_connections[rel.source_entity] = []
                entity_connections[rel.source_entity].append(rel.target_entity)
            
            for source, targets in entity_connections.items():
                if len(targets) >= 2:
                    patterns.append({
                        'pattern_type': 'relationship_chain',
                        'source_entity': source,
                        'chain_length': len(targets),
                        'target_entities': targets[:5]  # Limit for display
                    })
        
        elif pattern_type == "hub":
            # Find hub entities (highly connected)
            entity_degrees = {}
            for rel in relationships:
                entity_degrees[rel.source_entity] = entity_degrees.get(rel.source_entity, 0) + 1
                entity_degrees[rel.target_entity] = entity_degrees.get(rel.target_entity, 0) + 1
            
            avg_degree = sum(entity_degrees.values()) / len(entity_degrees) if entity_degrees else 0
            
            for entity, degree in entity_degrees.items():
                if degree > avg_degree * 2:  # Significantly above average
                    patterns.append({
                        'pattern_type': 'hub_entity',
                        'entity': entity,
                        'degree': degree,
                        'centrality_score': degree / max(entity_degrees.values())
                    })
        
        return patterns
    
    def get_contextual_relevance(
        self,
        entity: Dict[str, Any],
        context: List[str],
        relevance_method: str = "keyword_matching"
    ) -> float:
        """
        Compute contextual relevance of an entity given a context.
        
        Args:
            entity: Entity dictionary
            context: List of context strings
            relevance_method: Method for computing relevance
            
        Returns:
            Relevance score between 0.0 and 1.0
        """
        if not context:
            return 0.5  # Neutral relevance with no context
        
        if relevance_method == "keyword_matching":
            entity_text = f"{entity.get('name', '')} {entity.get('description', '')}".lower()
            context_text = " ".join(context).lower()
            
            # Simple keyword overlap
            entity_words = set(entity_text.split())
            context_words = set(context_text.split())
            
            if not entity_words or not context_words:
                return 0.0
            
            overlap = len(entity_words.intersection(context_words))
            union = len(entity_words.union(context_words))
            
            return overlap / union if union > 0 else 0.0
        
        # Default: mock relevance based on entity properties
        return min(1.0, len(entity.get('properties', {})) * 0.2)
    
    def get_analysis_statistics(self) -> Dict[str, Any]:
        """Get semantic analysis statistics."""
        return self.analysis_stats.copy()
    
    def _extract_relationships(
        self,
        entities: List[Dict[str, Any]],
        context: List[str],
        include_weak: bool
    ) -> List[SemanticRelationship]:
        """Extract semantic relationships between entities."""
        relationships = []
        
        for i, entity1 in enumerate(entities):
            for j, entity2 in enumerate(entities[i+1:], i+1):
                similarity = self.compute_entity_similarity(entity1, entity2)
                
                if similarity > (0.3 if include_weak else self.similarity_threshold):
                    # Determine relationship type based on entity properties
                    rel_type = self._determine_relationship_type(entity1, entity2)
                    
                    relationship = SemanticRelationship(
                        source_entity=entity1.get('id', f'entity_{i}'),
                        target_entity=entity2.get('id', f'entity_{j}'),
                        relationship_type=rel_type,
                        strength=similarity,
                        confidence=min(1.0, similarity + 0.1),
                        context=context[:3],  # Limit context size
                        properties={
                            'similarity_score': similarity,
                            'method': 'semantic_analysis'
                        }
                    )
                    relationships.append(relationship)
        
        return relationships
    
    def _create_entity_clusters(
        self,
        entities: List[Dict[str, Any]]
    ) -> List[EntityCluster]:
        """Create clusters of semantically similar entities."""
        clusters = []
        used_entities = set()
        
        for i, entity in enumerate(entities):
            if entity.get('id', f'entity_{i}') in used_entities:
                continue
                
            cluster_entities = [entity]
            entity_id = entity.get('id', f'entity_{i}')
            used_entities.add(entity_id)
            
            # Find similar entities
            for j, other_entity in enumerate(entities[i+1:], i+1):
                other_id = other_entity.get('id', f'entity_{j}')
                if other_id in used_entities:
                    continue
                    
                similarity = self.compute_entity_similarity(entity, other_entity)
                if similarity > self.similarity_threshold:
                    cluster_entities.append(other_entity)
                    used_entities.add(other_id)
            
            if len(cluster_entities) > 1:
                cluster = EntityCluster(
                    cluster_id=f'cluster_{len(clusters)}',
                    entities=[e.get('id', f'entity_{idx}') for idx, e in enumerate(cluster_entities)],
                    centroid_entity=entity_id,
                    coherence_score=self._calculate_cluster_coherence(cluster_entities),
                    keywords=self._extract_cluster_keywords(cluster_entities),
                    cluster_type=entity.get('type', 'unknown')
                )
                clusters.append(cluster)
        
        return clusters
    
    def _calculate_semantic_metrics(
        self,
        entities: List[Dict[str, Any]],
        relationships: List[SemanticRelationship],
        clusters: List[EntityCluster]
    ) -> Dict[str, float]:
        """Calculate overall semantic metrics for the analysis."""
        metrics = {}
        
        # Relationship density
        total_possible = len(entities) * (len(entities) - 1) / 2
        metrics['relationship_density'] = len(relationships) / total_possible if total_possible > 0 else 0.0
        
        # Average relationship strength
        if relationships:
            metrics['avg_relationship_strength'] = sum(r.strength for r in relationships) / len(relationships)
        else:
            metrics['avg_relationship_strength'] = 0.0
        
        # Clustering coefficient
        metrics['clustering_coefficient'] = len(clusters) / len(entities) if entities else 0.0
        
        # Semantic coherence (average cluster coherence)
        if clusters:
            metrics['semantic_coherence'] = sum(c.coherence_score for c in clusters) / len(clusters)
        else:
            metrics['semantic_coherence'] = 0.0
            
        return metrics
    
    def _compute_textual_similarity(self, text1: str, text2: str) -> float:
        """Compute textual similarity between two strings."""
        if not text1 or not text2:
            return 0.0
            
        # Simple Jaccard similarity
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _compute_structural_similarity(self, entity1: Dict, entity2: Dict) -> float:
        """Compute structural similarity between entity properties."""
        props1 = set(entity1.keys())
        props2 = set(entity2.keys())
        
        if not props1 and not props2:
            return 1.0
        
        intersection = len(props1.intersection(props2))
        union = len(props1.union(props2))
        
        return intersection / union if union > 0 else 0.0
    
    def _determine_relationship_type(self, entity1: Dict, entity2: Dict) -> RelationshipType:
        """Determine the type of relationship between two entities."""
        # Mock relationship type determination based on entity properties
        type1 = entity1.get('type', '').lower()
        type2 = entity2.get('type', '').lower()
        
        if type1 == type2:
            return RelationshipType.SIMILARITY
        elif 'person' in type1 and 'organization' in type2:
            return RelationshipType.ASSOCIATIVE
        elif 'event' in type1 or 'event' in type2:
            return RelationshipType.TEMPORAL
        else:
            return RelationshipType.ASSOCIATIVE
    
    def _calculate_cluster_coherence(self, cluster_entities: List[Dict]) -> float:
        """Calculate coherence score for a cluster of entities."""
        if len(cluster_entities) < 2:
            return 1.0
            
        # Calculate average pairwise similarity within cluster
        total_similarity = 0.0
        pairs = 0
        
        for i, entity1 in enumerate(cluster_entities):
            for entity2 in cluster_entities[i+1:]:
                similarity = self.compute_entity_similarity(entity1, entity2)
                total_similarity += similarity
                pairs += 1
        
        return total_similarity / pairs if pairs > 0 else 0.0
    
    def _extract_cluster_keywords(self, cluster_entities: List[Dict]) -> List[str]:
        """Extract keywords that represent the cluster."""
        keywords = set()
        
        for entity in cluster_entities:
            name = entity.get('name', '')
            description = entity.get('description', '')
            text = f"{name} {description}".lower()
            
            # Extract significant words (simple approach)
            words = [word for word in text.split() if len(word) > 3]
            keywords.update(words[:3])  # Limit keywords per entity
        
        return list(keywords)[:10]  # Return top 10 keywords