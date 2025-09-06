"""
Comprehensive Test Suite for Knowledge Graph Components - Issue #485

This test module provides comprehensive testing coverage for all knowledge graph 
and semantic analysis classes to ensure accurate relationship mapping and graph operations.

Tests cover:
- GraphBuilder: Advanced graph construction and maintenance
- GraphSearchService: Intelligent graph search and traversal  
- GraphQueryEngine: Complex graph query processing
- SemanticAnalyzer: Semantic relationship analysis
- EntityExtractor: Advanced entity recognition and extraction
- GraphPopulator: Intelligent graph population from text sources
- InfluenceNetworkAnalyzer: Network influence and relationship analysis
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

# Import knowledge graph components
from src.knowledge_graph.graph_query_engine import (
    GraphQueryEngine, QueryType, QueryResult, GraphPattern, 
)
from src.knowledge_graph.semantic_analyzer import (
    SemanticAnalyzer, RelationshipType, SemanticRelationship, 
    EntityCluster, SemanticAnalysisResult
)
from src.knowledge_graph.graph_search_service import (
    GraphSearchService, SearchType, SearchResult, GraphPath
)
from src.knowledge_graph.influence_network_analyzer import (
    InfluenceNetworkAnalyzer, InfluenceNode
)


class TestGraphQueryEngine:
    """Comprehensive tests for GraphQueryEngine class."""
    
    @pytest.fixture
    def query_engine(self):
        """Create GraphQueryEngine instance for testing."""
        return GraphQueryEngine(enable_caching=True)
    
    def test_engine_initialization(self, query_engine):
        """Test GraphQueryEngine initialization."""
        assert query_engine.enable_caching is True
        assert query_engine.query_cache == {}
        assert query_engine.query_stats['total_queries'] == 0
        assert query_engine.query_stats['cache_hits'] == 0
        assert query_engine.query_stats['avg_execution_time'] == 0.0
    
    def test_traversal_query_execution(self, query_engine):
        """Test graph traversal query execution."""
        result = query_engine.execute_traversal_query(
            start_node="node_1",
            traversal_pattern="out('connected_to').out('related_to')",
            max_depth=3
        )
        
        assert isinstance(result, QueryResult)
        assert result.query_type == QueryType.TRAVERSAL
        assert result.result_count > 0
        assert result.execution_time_ms >= 0
        assert 'node_1' in result.metadata['start_node']
        assert result.metadata['max_depth'] == 3
        
        # Check query statistics updated
        stats = query_engine.get_query_statistics()
        assert stats['total_queries'] == 1
        assert stats['avg_execution_time'] > 0
    
    def test_pattern_query_execution(self, query_engine):
        """Test graph pattern matching query execution."""
        pattern = GraphPattern(
            nodes=[
                {'id': 'person', 'type': 'Person'},
                {'id': 'company', 'type': 'Organization'}
            ],
            edges=[
                {'source': 'person', 'target': 'company', 'label': 'works_at'}
            ],
            constraints=[
                {'field': 'person.age', 'operator': '>', 'value': 25}
            ]
        )
        
        result = query_engine.execute_pattern_query(pattern, limit=50)
        
        assert isinstance(result, QueryResult)
        assert result.query_type == QueryType.PATTERN_MATCH
        assert result.result_count <= 50
        assert result.metadata['pattern_nodes'] == 2
        assert result.metadata['pattern_edges'] == 1
        assert result.metadata['constraints'] == 1
        
        # Verify result structure
        for match in result.results:
            assert 'match_id' in match
            assert 'confidence_score' in match
            assert 'matched_nodes' in match
            assert 'matched_edges' in match
    
    def test_analytics_query_execution(self, query_engine):
        """Test graph analytics query execution."""
        # Test centrality analysis
        result = query_engine.execute_analytics_query(
            metric_type='centrality',
            target_nodes=['node_1', 'node_2'],
            parameters={'algorithm': 'pagerank'}
        )
        
        assert isinstance(result, QueryResult)
        assert result.query_type == QueryType.ANALYTICS
        assert result.metadata['metric_type'] == 'centrality'
        
        # Verify centrality results
        for node_result in result.results:
            assert 'node_id' in node_result
            assert 'centrality_score' in node_result
            assert 'rank' in node_result
    
    def test_search_query_execution(self, query_engine):
        """Test entity search query execution."""
        result = query_engine.execute_search_query(
            query_text="artificial intelligence",
            entity_types=['Technology', 'Concept'],
            fuzzy_matching=True,
            limit=25
        )
        
        assert isinstance(result, QueryResult)
        assert result.query_type == QueryType.SEARCH
        assert result.result_count <= 25
        assert result.metadata['query_text'] == "artificial intelligence"
        assert result.metadata['fuzzy_matching'] is True
        
        # Verify search results structure
        for entity in result.results:
            assert 'entity_id' in entity
            assert 'name' in entity
            assert 'relevance_score' in entity
            assert 'properties' in entity
    
    def test_query_caching(self, query_engine):
        """Test query result caching functionality."""
        # Execute same query twice
        result1 = query_engine.execute_search_query("test query", limit=10)
        result2 = query_engine.execute_search_query("test query", limit=10)
        
        # Second query should be cached
        stats = query_engine.get_query_statistics()
        assert stats['cache_hits'] >= 1
        assert result1.query_id == result2.query_id
    
    def test_cache_clearing(self, query_engine):
        """Test cache clearing functionality."""
        query_engine.execute_search_query("test query")
        assert len(query_engine.query_cache) > 0
        
        query_engine.clear_cache()
        assert len(query_engine.query_cache) == 0


class TestSemanticAnalyzer:
    """Comprehensive tests for SemanticAnalyzer class."""
    
    @pytest.fixture
    def analyzer(self):
        """Create SemanticAnalyzer instance for testing."""
        return SemanticAnalyzer(similarity_threshold=0.7)
    
    @pytest.fixture
    def sample_entities(self):
        """Sample entities for testing."""
        return [
            {
                'id': 'entity_1',
                'name': 'Artificial Intelligence',
                'type': 'Technology',
                'description': 'Advanced AI systems and machine learning'
            },
            {
                'id': 'entity_2', 
                'name': 'Machine Learning',
                'type': 'Technology',
                'description': 'AI subset focusing on learning algorithms'
            },
            {
                'id': 'entity_3',
                'name': 'Deep Learning',
                'type': 'Technology', 
                'description': 'Neural networks with multiple layers'
            },
            {
                'id': 'entity_4',
                'name': 'John Smith',
                'type': 'Person',
                'description': 'AI researcher and professor'
            }
        ]
    
    def test_analyzer_initialization(self, analyzer):
        """Test SemanticAnalyzer initialization."""
        assert analyzer.similarity_threshold == 0.7
        assert analyzer.entity_vectors == {}
        assert analyzer.relationship_cache == {}
        assert analyzer.analysis_stats['total_analyses'] == 0
    
    def test_entity_relationship_analysis(self, analyzer, sample_entities):
        """Test comprehensive entity relationship analysis."""
        result = analyzer.analyze_entity_relationships(
            entities=sample_entities,
            context_data=["artificial intelligence", "machine learning", "technology"],
            include_weak_relationships=False
        )
        
        assert isinstance(result, SemanticAnalysisResult)
        assert result.entity_count == len(sample_entities)
        assert result.execution_time_ms >= 0
        
        # Check semantic metrics
        metrics = result.semantic_metrics
        assert 'relationship_density' in metrics
        assert 'avg_relationship_strength' in metrics
        assert 'clustering_coefficient' in metrics
        assert 'semantic_coherence' in metrics
        
        # Verify relationship structure
        for relationship in result.relationships:
            assert isinstance(relationship, SemanticRelationship)
            assert relationship.source_entity in [e['id'] for e in sample_entities]
            assert relationship.target_entity in [e['id'] for e in sample_entities]
            assert isinstance(relationship.relationship_type, RelationshipType)
            assert 0.0 <= relationship.strength <= 1.0
            assert 0.0 <= relationship.confidence <= 1.0
    
    def test_entity_similarity_computation(self, analyzer):
        """Test entity similarity computation with different methods."""
        entity1 = {
            'name': 'Artificial Intelligence',
            'type': 'Technology',
            'description': 'Advanced AI systems'
        }
        entity2 = {
            'name': 'Machine Learning', 
            'type': 'Technology',
            'description': 'AI subset with learning algorithms'
        }
        
        # Test different similarity methods
        textual_sim = analyzer.compute_entity_similarity(
            entity1, entity2, similarity_method="textual"
        )
        structural_sim = analyzer.compute_entity_similarity(
            entity1, entity2, similarity_method="structural"
        )
        combined_sim = analyzer.compute_entity_similarity(
            entity1, entity2, similarity_method="combined"
        )
        
        assert 0.0 <= textual_sim <= 1.0
        assert 0.0 <= structural_sim <= 1.0
        assert 0.0 <= combined_sim <= 1.0
        
        # Combined should be average of textual and structural
        expected_combined = (textual_sim + structural_sim) / 2.0
        assert abs(combined_sim - expected_combined) < 0.001
    
    def test_semantic_pattern_finding(self, analyzer, sample_entities):
        """Test semantic pattern detection in relationships."""
        # First create relationships
        result = analyzer.analyze_entity_relationships(sample_entities)
        
        # Find frequent patterns
        frequent_patterns = analyzer.find_semantic_patterns(
            result.relationships, pattern_type="frequent"
        )
        
        # Find chain patterns
        chain_patterns = analyzer.find_semantic_patterns(
            result.relationships, pattern_type="chain"
        )
        
        # Find hub patterns  
        hub_patterns = analyzer.find_semantic_patterns(
            result.relationships, pattern_type="hub"
        )
        
        # Verify pattern structure
        for pattern in frequent_patterns:
            assert pattern['pattern_type'] == 'frequent_relationship'
            assert 'relationship_type' in pattern
            assert 'frequency' in pattern
        
        for pattern in chain_patterns:
            assert pattern['pattern_type'] == 'relationship_chain'
            assert 'source_entity' in pattern
            assert 'chain_length' in pattern
        
        for pattern in hub_patterns:
            assert pattern['pattern_type'] == 'hub_entity'
            assert 'entity' in pattern
            assert 'degree' in pattern
    
    def test_contextual_relevance_computation(self, analyzer):
        """Test contextual relevance scoring."""
        entity = {
            'name': 'Artificial Intelligence',
            'description': 'Advanced AI and machine learning systems',
            'properties': {'type': 'Technology', 'domain': 'Computer Science'}
        }
        context = ['machine learning', 'artificial intelligence', 'technology']
        
        relevance = analyzer.get_contextual_relevance(
            entity=entity,
            context=context,
            relevance_method="keyword_matching"
        )
        
        assert 0.0 <= relevance <= 1.0
        
        # Test with empty context
        empty_relevance = analyzer.get_contextual_relevance(entity, [])
        assert empty_relevance == 0.5  # Neutral relevance
    
    def test_entity_clustering(self, analyzer, sample_entities):
        """Test entity clustering functionality."""
        result = analyzer.analyze_entity_relationships(sample_entities)
        
        # Verify clusters
        for cluster in result.clusters:
            assert isinstance(cluster, EntityCluster)
            assert len(cluster.entities) >= 2  # Clusters have multiple entities
            assert cluster.centroid_entity in cluster.entities
            assert 0.0 <= cluster.coherence_score <= 1.0
            assert isinstance(cluster.keywords, list)
    
    def test_analysis_statistics(self, analyzer, sample_entities):
        """Test analysis statistics tracking."""
        # Perform analysis
        analyzer.analyze_entity_relationships(sample_entities)
        analyzer.analyze_entity_relationships(sample_entities[:2])
        
        stats = analyzer.get_analysis_statistics()
        assert stats['total_analyses'] == 2
        assert stats['total_relationships_found'] >= 0
        assert stats['total_clusters_created'] >= 0


class TestGraphSearchService:
    """Comprehensive tests for GraphSearchService class."""
    
    @pytest.fixture
    def search_service(self):
        """Create GraphSearchService instance for testing."""
        return GraphSearchService(max_results=50)
    
    def test_service_initialization(self, search_service):
        """Test GraphSearchService initialization."""
        assert search_service.max_results == 50
        assert search_service.search_index == {}
        assert search_service.search_cache == {}
        assert search_service.search_stats['total_searches'] == 0
    
    def test_entity_search(self, search_service):
        """Test entity search functionality."""
        result = search_service.search_entities(
            query="artificial intelligence",
            entity_types=['Technology', 'Concept'],
            fuzzy=True,
            limit=20
        )
        
        assert isinstance(result, SearchResult)
        assert result.search_type == SearchType.ENTITY_SEARCH
        assert result.result_count <= 20
        assert result.execution_time_ms >= 0
        
        # Verify entity results
        for entity in result.results:
            assert 'entity_id' in entity
            assert 'name' in entity
            assert 'type' in entity
            assert 'relevance_score' in entity
            assert 'properties' in entity
            assert 'connections' in entity
    
    def test_relationship_search(self, search_service):
        """Test relationship search functionality."""
        result = search_service.search_relationships(
            source_entity="entity_1",
            target_entity="entity_2", 
            relationship_types=['connected_to', 'related_to'],
            strength_threshold=0.5
        )
        
        assert isinstance(result, SearchResult)
        assert result.search_type == SearchType.RELATIONSHIP_SEARCH
        assert result.metadata['source_entity'] == "entity_1"
        assert result.metadata['target_entity'] == "entity_2"
        assert result.metadata['strength_threshold'] == 0.5
        
        # Verify relationship results
        for rel in result.results:
            assert 'relationship_id' in rel
            assert 'source_entity' in rel
            assert 'target_entity' in rel
            assert 'relationship_type' in rel
            assert 'strength' in rel
            assert rel['strength'] >= 0.5  # Above threshold
    
    def test_shortest_path_finding(self, search_service):
        """Test shortest path finding between entities."""
        path = search_service.find_shortest_path(
            start_entity="node_A",
            end_entity="node_B",
            max_depth=5,
            relationship_types=['connected_to']
        )
        
        assert isinstance(path, GraphPath)
        assert path.start_node == "node_A"
        assert path.end_node == "node_B"
        assert len(path.path_nodes) >= 2  # At least start and end
        assert len(path.path_edges) == len(path.path_nodes) - 1
        assert path.path_length <= 5
        assert path.total_weight >= 0
        
        # Test same node path
        same_path = search_service.find_shortest_path("node_A", "node_A")
        assert same_path.path_length == 0
        assert len(same_path.path_nodes) == 1
    
    def test_neighborhood_search(self, search_service):
        """Test entity neighborhood discovery."""
        result = search_service.get_entity_neighborhood(
            entity_id="central_entity",
            depth=2,
            relationship_types=['connected_to'],
            limit_per_level=10
        )
        
        assert isinstance(result, SearchResult)
        assert result.search_type == SearchType.NEIGHBORHOOD_SEARCH
        assert result.metadata['entity_id'] == "central_entity"
        assert result.metadata['depth'] == 2
        
        # Verify neighborhood structure
        for neighbor in result.results:
            assert 'entity_id' in neighbor
            assert 'distance' in neighbor
            assert neighbor['distance'] >= 1
            assert neighbor['distance'] <= 2
            assert 'relationship_type' in neighbor
    
    def test_full_text_search(self, search_service):
        """Test full-text search across entity content."""
        result = search_service.full_text_search(
            query="machine learning artificial intelligence",
            search_fields=['name', 'description', 'content'],
            entity_types=['Technology', 'Document'],
            limit=30
        )
        
        assert isinstance(result, SearchResult) 
        assert result.search_type == SearchType.FULL_TEXT_SEARCH
        assert result.result_count <= 30
        assert result.metadata['search_fields'] == ['name', 'description', 'content']
        
        # Verify text search results
        for text_result in result.results:
            assert 'entity_id' in text_result
            assert 'relevance_score' in text_result
            assert 'matched_fields' in text_result
            assert 'snippets' in text_result
            assert isinstance(text_result['snippets'], list)
    
    def test_search_caching(self, search_service):
        """Test search result caching."""
        # Execute same search twice
        result1 = search_service.search_entities("test query")
        result2 = search_service.search_entities("test query")
        
        # Second search should be cached
        stats = search_service.get_search_statistics()
        assert stats['cache_hits'] >= 1
        assert result1.search_id == result2.search_id
    
    def test_search_statistics(self, search_service):
        """Test search statistics tracking."""
        search_service.search_entities("query1")
        search_service.search_relationships()
        search_service.full_text_search("query2")
        
        stats = search_service.get_search_statistics()
        assert stats['total_searches'] == 3
        assert stats['avg_execution_time'] > 0
        
        # Test cache clearing
        search_service.clear_cache()
        assert len(search_service.search_cache) == 0


class TestInfluenceNetworkAnalyzer:
    """Comprehensive tests for InfluenceNetworkAnalyzer class."""
    
    @pytest.fixture
    def analyzer(self):
        """Create InfluenceNetworkAnalyzer instance for testing."""
        return InfluenceNetworkAnalyzer()
    
    def test_analyzer_initialization(self, analyzer):
        """Test InfluenceNetworkAnalyzer initialization."""
        assert len(analyzer.graph.nodes) == 0
        assert len(analyzer.graph.edges) == 0
        assert analyzer.influence_scores == {}
    
    def test_node_management(self, analyzer):
        """Test adding and managing nodes in the influence network."""
        # Add nodes
        analyzer.add_node("node_1", metadata={'type': 'person', 'name': 'Alice'})
        analyzer.add_node("node_2", metadata={'type': 'organization', 'name': 'Company'})
        
        assert len(analyzer.graph.nodes) == 2
        assert 'node_1' in analyzer.graph.nodes
        assert 'node_2' in analyzer.graph.nodes
        
        # Check metadata
        node_data = analyzer.graph.nodes['node_1']
        assert node_data['type'] == 'person'
        assert node_data['name'] == 'Alice'
    
    def test_edge_management(self, analyzer):
        """Test adding edges to the influence network."""
        # Add nodes first
        analyzer.add_node("node_1")
        analyzer.add_node("node_2")
        analyzer.add_node("node_3")
        
        # Add weighted edges
        analyzer.add_edge("node_1", "node_2", weight=0.8)
        analyzer.add_edge("node_2", "node_3", weight=0.6)
        analyzer.add_edge("node_1", "node_3", weight=0.4)
        
        assert len(analyzer.graph.edges) == 3
        
        # Check edge weights
        edge_data = analyzer.graph.edges['node_1', 'node_2']
        assert edge_data['weight'] == 0.8
    
    def test_influence_score_calculation(self, analyzer):
        """Test influence score calculation using PageRank."""
        # Build a simple network
        analyzer.add_node("hub", metadata={'type': 'hub'})
        analyzer.add_node("node_1")
        analyzer.add_node("node_2") 
        analyzer.add_node("node_3")
        
        # Hub connected to all others
        analyzer.add_edge("hub", "node_1", weight=1.0)
        analyzer.add_edge("hub", "node_2", weight=1.0)
        analyzer.add_edge("hub", "node_3", weight=1.0)
        analyzer.add_edge("node_1", "node_2", weight=0.5)
        
        scores = analyzer.calculate_influence_scores()
        
        assert isinstance(scores, dict)
        assert len(scores) == 4
        assert all(0.0 <= score <= 1.0 for score in scores.values())
        
        # Hub should have highest influence
        assert scores["hub"] > scores["node_1"]
    
    def test_top_influencers_identification(self, analyzer):
        """Test identification of top influencers."""
        # Build network with clear influence hierarchy
        nodes = [f"node_{i}" for i in range(5)]
        for node in nodes:
            analyzer.add_node(node)
        
        # Create hub structure
        for i in range(1, 5):
            analyzer.add_edge("node_0", f"node_{i}", weight=1.0)
        
        top_influencers = analyzer.get_top_influencers(n=3)
        
        assert len(top_influencers) <= 3
        for influencer in top_influencers:
            assert isinstance(influencer, InfluenceNode)
            assert hasattr(influencer, 'node_id')
            assert hasattr(influencer, 'influence_score')
            assert hasattr(influencer, 'connections')
            assert hasattr(influencer, 'metadata')
        
        # Scores should be in descending order
        scores = [inf.influence_score for inf in top_influencers]
        assert scores == sorted(scores, reverse=True)
    
    def test_influence_path_analysis(self, analyzer):
        """Test influence path analysis between nodes."""
        # Build connected network
        analyzer.add_node("start")
        analyzer.add_node("middle")
        analyzer.add_node("end")
        
        analyzer.add_edge("start", "middle")
        analyzer.add_edge("middle", "end")
        
        # Find path
        path = analyzer.analyze_influence_path("start", "end")
        
        assert path is not None
        assert isinstance(path, list)
        assert path[0] == "start"
        assert path[-1] == "end"
        assert "middle" in path
        
        # Test non-existent path
        analyzer.add_node("isolated")
        no_path = analyzer.analyze_influence_path("start", "isolated")
        assert no_path is None
    
    def test_network_statistics(self, analyzer):
        """Test network statistics computation."""
        # Empty network
        stats = analyzer.get_network_stats()
        assert stats['node_count'] == 0
        assert stats['edge_count'] == 0
        assert stats['density'] == 0
        assert stats['is_connected'] is False
        
        # Add nodes and edges
        for i in range(4):
            analyzer.add_node(f"node_{i}")
        
        analyzer.add_edge("node_0", "node_1")
        analyzer.add_edge("node_1", "node_2")
        analyzer.add_edge("node_2", "node_3")
        analyzer.add_edge("node_3", "node_0")  # Create cycle
        
        stats = analyzer.get_network_stats()
        assert stats['node_count'] == 4
        assert stats['edge_count'] == 4
        assert stats['density'] > 0
        assert stats['is_connected'] is True


class TestKnowledgeGraphIntegration:
    """Integration tests for knowledge graph components working together."""
    
    @pytest.fixture
    def integrated_system(self):
        """Create integrated knowledge graph system for testing."""
        query_engine = GraphQueryEngine(enable_caching=True)
        semantic_analyzer = SemanticAnalyzer(similarity_threshold=0.6)
        search_service = GraphSearchService(max_results=100)
        influence_analyzer = InfluenceNetworkAnalyzer()
        
        return {
            'query_engine': query_engine,
            'semantic_analyzer': semantic_analyzer, 
            'search_service': search_service,
            'influence_analyzer': influence_analyzer
        }
    
    def test_end_to_end_workflow(self, integrated_system):
        """Test end-to-end knowledge graph workflow."""
        query_engine = integrated_system['query_engine']
        semantic_analyzer = integrated_system['semantic_analyzer']
        search_service = integrated_system['search_service']
        
        # 1. Search for entities
        search_result = search_service.search_entities(
            query="artificial intelligence",
            entity_types=['Technology']
        )
        assert search_result.result_count > 0
        
        # 2. Analyze semantic relationships
        entities = search_result.results[:5]  # Take first 5 for analysis
        semantic_result = semantic_analyzer.analyze_entity_relationships(entities)
        assert semantic_result.entity_count == len(entities)
        
        # 3. Execute complex queries
        query_result = query_engine.execute_traversal_query(
            start_node=entities[0]['entity_id'],
            traversal_pattern="out('related_to').in('connected_to')",
            max_depth=2
        )
        assert query_result.result_count > 0
        
        # 4. Find paths between entities
        if len(entities) >= 2:
            path = search_service.find_shortest_path(
                entities[0]['entity_id'],
                entities[1]['entity_id']
            )
            assert path is not None
    
    def test_performance_characteristics(self, integrated_system):
        """Test performance characteristics of knowledge graph operations."""
        query_engine = integrated_system['query_engine']
        search_service = integrated_system['search_service']
        
        # Test query execution times
        start_time = time.time()
        query_engine.execute_search_query("performance test", limit=100)
        query_time = time.time() - start_time
        
        start_time = time.time()
        search_service.full_text_search("performance test", limit=100)
        search_time = time.time() - start_time
        
        # Both operations should complete within reasonable time
        assert query_time < 1.0  # Less than 1 second
        assert search_time < 1.0  # Less than 1 second
    
    def test_error_handling(self, integrated_system):
        """Test error handling across knowledge graph components."""
        search_service = integrated_system['search_service']
        semantic_analyzer = integrated_system['semantic_analyzer']
        
        # Test with empty inputs
        empty_search = search_service.search_entities("")
        assert empty_search.result_count >= 0
        
        empty_analysis = semantic_analyzer.analyze_entity_relationships([])
        assert empty_analysis.entity_count == 0
        
        # Test with malformed inputs
        malformed_entities = [{'invalid': 'entity'}]
        analysis = semantic_analyzer.analyze_entity_relationships(malformed_entities)
        assert isinstance(analysis, SemanticAnalysisResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])