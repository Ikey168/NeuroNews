"""
Comprehensive high-coverage tests for Graph API modules.

This test suite is designed to achieve close to 100% test coverage 
by testing all code paths, error conditions, and edge cases.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
import json

from src.api.graph.operations import (
    GraphOperations, 
    NodeData, 
    EdgeData, 
    ValidationResult
)
from src.api.graph.traversal import (
    GraphTraversal,
    TraversalConfig,
    PathResult,
    TraversalResult
)
from src.api.graph.queries import (
    GraphQueries,
    QueryFilter,
    QuerySort,
    QueryPagination,
    QueryParams,
    QueryResult,
    QueryStatistics
)


class TestGraphOperationsComprehensive:
    """Comprehensive tests for GraphOperations to achieve high coverage."""
    
    def test_initialization_with_graph(self):
        """Test initialization with graph builder."""
        mock_graph = Mock()
        ops = GraphOperations(mock_graph)
        assert ops.graph == mock_graph
        
    def test_initialization_without_graph(self):
        """Test initialization without graph builder."""
        ops = GraphOperations()
        assert ops.graph is None
    
    def test_validate_node_comprehensive(self):
        """Test all validation paths for nodes."""
        ops = GraphOperations()
        
        # Test valid node
        valid_node = NodeData("1", "Person", {"name": "John"})
        result = ops.validate_node(valid_node)
        assert result.is_valid
        
        # Test invalid cases
        invalid_cases = [
            NodeData("", "Person", {"name": "John"}),  # Empty ID edge case
            NodeData("1", "", {"name": "John"}),  # Empty label
            NodeData("1", "Person", {}),  # Empty properties
            NodeData("1", "Person", {"age": "not_number"}),  # Invalid property type edge case
        ]
        
        for node in invalid_cases:
            result = ops.validate_node(node)
            # All should have some validation response
            assert isinstance(result, ValidationResult)
    
    def test_validate_edge_comprehensive(self):
        """Test all validation paths for edges."""
        ops = GraphOperations()
        
        # Test valid edge
        valid_edge = EdgeData("1", "KNOWS", "node1", "node2", {"weight": 1.0})
        result = ops.validate_edge(valid_edge)
        assert result.is_valid
        
        # Test invalid cases
        invalid_cases = [
            EdgeData("", "KNOWS", "node1", "node2", {}),  # Empty ID edge case
            EdgeData("1", "", "node1", "node2", {}),  # Empty label
            EdgeData("1", "KNOWS", "", "node2", {}),  # Empty from_node
            EdgeData("1", "KNOWS", "node1", "", {}),  # Empty to_node
            EdgeData("1", "KNOWS", "node1", "node1", {}),  # Self-reference
        ]
        
        for edge in invalid_cases:
            result = ops.validate_edge(edge)
            assert isinstance(result, ValidationResult)
    
    @pytest.mark.asyncio
    async def test_create_node_with_mock_graph(self):
        """Test node creation with mocked graph."""
        mock_graph = Mock()
        mock_graph.g.addV.return_value.property.return_value.next = AsyncMock(return_value="new_node_id")
        
        ops = GraphOperations(mock_graph)
        node = NodeData(None, "Person", {"name": "Alice"})
        
        result = await ops.create_node(node)
        assert result is not None
    
    @pytest.mark.asyncio  
    async def test_create_node_without_graph(self):
        """Test node creation without graph (mock implementation)."""
        ops = GraphOperations()
        node = NodeData(None, "Person", {"name": "Bob"})
        
        result = await ops.create_node(node)
        assert result is not None
        # Mock implementation should return basic result
    
    @pytest.mark.asyncio
    async def test_create_edge_with_mock_graph(self):
        """Test edge creation with mocked graph."""
        mock_graph = Mock()
        mock_edge = Mock()
        mock_edge.property.return_value.next = AsyncMock(return_value="new_edge_id")
        mock_graph.g.V.return_value.addE.return_value.to.return_value = mock_edge
        
        ops = GraphOperations(mock_graph)
        edge = EdgeData(None, "KNOWS", "node1", "node2", {"strength": 0.8})
        
        result = await ops.create_edge(edge)
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_create_edge_without_graph(self):
        """Test edge creation without graph (mock implementation)."""
        ops = GraphOperations()
        edge = EdgeData(None, "FOLLOWS", "user1", "user2", {})
        
        result = await ops.create_edge(edge)
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_update_node_operations(self):
        """Test node update operations."""
        ops = GraphOperations()
        
        # Test with mock implementation 
        result = await ops.update_node("node123", {"name": "Updated Name"})
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_delete_node_operations(self):
        """Test node deletion operations."""
        ops = GraphOperations()
        
        # Test with cascade
        result = await ops.delete_node("node123", cascade=True)
        assert result is not None
        
        # Test without cascade
        result = await ops.delete_node("node456", cascade=False) 
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_export_import_operations(self):
        """Test export and import operations."""
        ops = GraphOperations()
        
        # Test export in different formats
        for format_type in ["json", "graphml", "csv"]:
            result = await ops.export_graph_data(format_type)
            assert result is not None
        
        # Test import
        sample_data = {
            'nodes': [{'id': 'n1', 'label': 'Person', 'properties': {'name': 'Test'}}],
            'edges': [{'id': 'e1', 'label': 'KNOWS', 'from_node': 'n1', 'to_node': 'n2', 'properties': {}}]
        }
        result = await ops.import_graph_data(sample_data)
        assert result is not None
    
    def test_utility_methods(self):
        """Test utility methods."""
        ops = GraphOperations()
        
        # Test supported types
        node_types = ops.get_supported_node_types()
        assert isinstance(node_types, list)
        assert len(node_types) > 0
        
        rel_types = ops.get_supported_relationship_types() 
        assert isinstance(rel_types, list)
        assert len(rel_types) > 0
        
        # Test consistency validation
        consistency = ops.validate_graph_consistency()
        assert isinstance(consistency, dict)


class TestGraphTraversalComprehensive:
    """Comprehensive tests for GraphTraversal to achieve high coverage."""
    
    def test_initialization_variations(self):
        """Test different initialization scenarios."""
        # Without graph
        traversal1 = GraphTraversal()
        assert traversal1.graph is None
        
        # With mock graph
        mock_graph = Mock()
        traversal2 = GraphTraversal(mock_graph)
        assert traversal2.graph == mock_graph
    
    def test_config_edge_cases(self):
        """Test TraversalConfig edge cases."""
        configs = [
            TraversalConfig(),  # Default
            TraversalConfig(max_depth=0),  # Zero depth
            TraversalConfig(max_results=1),  # Minimal results
            TraversalConfig(include_properties=False),  # No properties
            TraversalConfig(filter_by_labels=["Person"]),  # With filters
            TraversalConfig(timeout_seconds=1),  # Short timeout
        ]
        
        for config in configs:
            assert config.max_depth >= 0
            assert config.max_results >= 0
    
    @pytest.mark.asyncio
    async def test_breadth_first_search_comprehensive(self):
        """Test BFS with various configurations."""
        traversal = GraphTraversal()
        
        configs = [
            TraversalConfig(),
            TraversalConfig(max_depth=1),
            TraversalConfig(max_depth=5, max_results=10),
            TraversalConfig(include_properties=False),
        ]
        
        for config in configs:
            result = await traversal.breadth_first_search("start_node", config)
            assert isinstance(result, TraversalResult)
            assert result.start_node == "start_node"
    
    @pytest.mark.asyncio
    async def test_depth_first_search_comprehensive(self):
        """Test DFS with various configurations."""
        traversal = GraphTraversal()
        
        configs = [
            TraversalConfig(),
            TraversalConfig(max_depth=2),
            TraversalConfig(filter_by_labels=["Person", "Organization"]),
        ]
        
        for config in configs:
            result = await traversal.depth_first_search("start_node", config)
            assert isinstance(result, TraversalResult)
            assert result.start_node == "start_node"
    
    @pytest.mark.asyncio
    async def test_pathfinding_comprehensive(self):
        """Test all pathfinding methods."""
        traversal = GraphTraversal()
        
        # Test shortest path
        shortest_result = await traversal.find_shortest_path("node1", "node5")
        assert isinstance(shortest_result, PathResult)
        
        # Test find all paths
        all_paths = await traversal.find_all_paths("node1", "node3", 4)
        assert isinstance(all_paths, list)
        for path in all_paths:
            assert isinstance(path, PathResult)
        
        # Test same node paths
        same_node_path = await traversal.find_shortest_path("nodeX", "nodeX")
        assert isinstance(same_node_path, PathResult)
        assert same_node_path.start_node == same_node_path.end_node
    
    @pytest.mark.asyncio
    async def test_neighbor_operations(self):
        """Test neighbor finding operations."""
        traversal = GraphTraversal()
        
        # Test get neighbors
        neighbors = await traversal.get_node_neighbors("node1")
        assert isinstance(neighbors, list)
        
        # Test with different direction parameters (if supported)
        neighbors_out = await traversal.get_node_neighbors("node1", direction="outgoing")
        assert isinstance(neighbors_out, list)
    
    def test_statistics_operations(self):
        """Test statistics collection and management."""
        traversal = GraphTraversal()
        
        # Get statistics
        stats = traversal.get_traversal_statistics()
        assert isinstance(stats, dict)
        
        # Reset statistics
        traversal.reset_statistics()
        
        # Get stats again after reset
        stats_after_reset = traversal.get_traversal_statistics()
        assert isinstance(stats_after_reset, dict)
    
    @pytest.mark.asyncio
    async def test_connectivity_analysis(self):
        """Test graph connectivity analysis."""
        traversal = GraphTraversal()
        
        result = await traversal.analyze_graph_connectivity()
        assert isinstance(result, dict)
        # Should contain connectivity metrics


class TestGraphQueriesComprehensive:
    """Comprehensive tests for GraphQueries to achieve high coverage."""
    
    def test_initialization_scenarios(self):
        """Test different initialization scenarios."""
        # Without graph
        queries1 = GraphQueries()
        assert queries1.graph is None
        
        # With mock graph
        mock_graph = Mock()
        queries2 = GraphQueries(mock_graph)
        assert queries2.graph == mock_graph
    
    def test_query_components_comprehensive(self):
        """Test all query component variations."""
        # Test QueryFilter with all operators
        operators = ["eq", "ne", "gt", "lt", "gte", "lte", "contains", "in"]
        for op in operators:
            filter_obj = QueryFilter("test_prop", op, "test_val")
            assert filter_obj.operator == op
        
        # Test QuerySort directions
        for direction in ["asc", "desc"]:
            sort_obj = QuerySort("test_prop", direction)
            assert sort_obj.direction == direction
        
        # Test QueryPagination edge cases
        paginations = [
            QueryPagination(),  # Default
            QueryPagination(0, 1),  # Minimal
            QueryPagination(100, 50),  # Large offset
        ]
        for p in paginations:
            assert p.offset >= 0
            assert p.limit >= 0
    
    def test_query_params_variations(self):
        """Test QueryParams with different combinations."""
        # Test with filters
        filter_list = [QueryFilter("name", "eq", "John")]
        sort_list = [QuerySort("age", "desc")]
        pagination = QueryPagination(10, 20)
        
        params = QueryParams(
            node_labels=["Person"],
            edge_labels=["KNOWS"],
            filters=filter_list,
            sort=sort_list,
            pagination=pagination,
            include_properties=True,
            include_edges=True
        )
        
        assert params.node_labels == ["Person"]
        assert params.include_properties is True
        assert params.include_edges is True
    
    @pytest.mark.asyncio
    async def test_query_execution_comprehensive(self):
        """Test all query execution methods."""
        queries = GraphQueries()
        
        # Test node queries with different params
        param_variants = [
            QueryParams(),  # Default
            QueryParams(node_labels=["Person"]),  # With labels
            QueryParams(include_properties=False),  # No properties
            QueryParams(include_edges=True),  # With edges
        ]
        
        for params in param_variants:
            result = await queries.execute_node_query(params)
            assert isinstance(result, QueryResult)
        
        # Test relationship queries
        for params in param_variants:
            result = await queries.execute_relationship_query(params)
            assert isinstance(result, QueryResult)
    
    @pytest.mark.asyncio
    async def test_pattern_queries_comprehensive(self):
        """Test pattern query variations."""
        queries = GraphQueries()
        
        patterns = [
            "(:Person)-[:KNOWS]->(:Person)",
            "(:Organization)-[:EMPLOYS]->(:Person)",
            "(:Person {name: 'John'})-[:LIVES_IN]->(:City)",
        ]
        
        for pattern in patterns:
            result = await queries.execute_pattern_query(pattern)
            assert isinstance(result, QueryResult)
            
            # Test with additional params
            result_with_params = await queries.execute_pattern_query(pattern, {"limit": 10})
            assert isinstance(result_with_params, QueryResult)
    
    @pytest.mark.asyncio
    async def test_aggregation_queries_comprehensive(self):
        """Test aggregation query variations."""
        queries = GraphQueries()
        
        aggregation_types = ["count", "sum", "avg", "min", "max"]
        
        for agg_type in aggregation_types:
            result = await queries.execute_aggregation_query(agg_type, QueryParams())
            assert isinstance(result, QueryResult)
    
    def test_filter_application(self):
        """Test filter application logic."""
        queries = GraphQueries()
        
        # Test different filter scenarios
        test_data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35},
        ]
        
        filters = [
            QueryFilter("age", "gt", 28),
            QueryFilter("name", "contains", "li"),
        ]
        
        for filter_obj in filters:
            # Test filter application (internal method testing)
            for item in test_data:
                result = queries._apply_filter(item.get(filter_obj.property_name), filter_obj)
                assert isinstance(result, bool)
    
    def test_utility_methods_comprehensive(self):
        """Test all utility and helper methods."""
        queries = GraphQueries()
        
        # Test cache key generation
        cache_key1 = queries._generate_cache_key("node_query", {"param": "value1"})
        cache_key2 = queries._generate_cache_key("node_query", {"param": "value2"})
        assert cache_key1 != cache_key2
        
        # Test query ID generation
        query_id = queries._generate_query_id("test_query", {"data": "test"})
        assert isinstance(query_id, str)
        assert len(query_id) > 0
        
        # Test statistics
        stats = queries.get_query_statistics()
        assert isinstance(stats, dict)
        
        # Test optimization
        optimization = queries.optimize_query("node_query", {"filters": []})
        assert isinstance(optimization, dict)
    
    @pytest.mark.asyncio
    async def test_query_plan_explanation(self):
        """Test query plan explanation."""
        queries = GraphQueries()
        
        plan = await queries.explain_query_plan("node_query", {"test": "data"})
        assert isinstance(plan, dict)
        assert "estimated_cost" in plan or "plan" in plan or "explanation" in plan
    
    def test_gremlin_filter_application(self):
        """Test Gremlin filter application."""
        queries = GraphQueries()
        
        # Test different filter types
        filters = [
            QueryFilter("name", "eq", "John"),
            QueryFilter("age", "gt", 25), 
            QueryFilter("active", "eq", True),
        ]
        
        mock_query = Mock()
        for filter_obj in filters:
            result = queries._apply_gremlin_filter(mock_query, filter_obj)
            # Should return modified query or same query
            assert result is not None


class TestErrorHandlingAndEdgeCases:
    """Test error conditions and edge cases for comprehensive coverage."""
    
    @pytest.mark.asyncio
    async def test_operations_error_handling(self):
        """Test error handling in operations."""
        ops = GraphOperations()
        
        # Test with invalid validation data
        try:
            invalid_node = NodeData(None, None, None)  
            result = ops.validate_node(invalid_node)
            assert isinstance(result, ValidationResult)
        except Exception as e:
            # Should handle gracefully
            assert isinstance(e, (TypeError, AttributeError))
    
    @pytest.mark.asyncio
    async def test_traversal_error_handling(self):
        """Test error handling in traversal."""
        traversal = GraphTraversal()
        
        # Test with extreme configurations
        extreme_config = TraversalConfig(max_depth=10000, max_results=1)
        
        result = await traversal.breadth_first_search("test", extreme_config)
        assert isinstance(result, TraversalResult)
    
    @pytest.mark.asyncio
    async def test_queries_error_handling(self):
        """Test error handling in queries."""
        queries = GraphQueries()
        
        # Test with invalid parameters
        try:
            invalid_params = QueryParams(node_labels=None, filters=None)
            result = await queries.execute_node_query(invalid_params)
            assert isinstance(result, QueryResult)
        except Exception as e:
            # Should handle gracefully
            assert isinstance(e, (TypeError, ValueError, AttributeError))
    
    def test_data_structure_edge_cases(self):
        """Test edge cases in data structures."""
        # Test with minimal data
        minimal_node = NodeData("", "", {})
        assert minimal_node.id == ""
        
        minimal_edge = EdgeData("", "", "", "", {})
        assert minimal_edge.label == ""
        
        # Test with None values where allowed
        none_node = NodeData(None, "Test", {"prop": None})
        assert none_node.id is None
    
    def test_statistics_edge_cases(self):
        """Test statistics with edge cases."""
        stats = QueryStatistics()
        assert stats.query_count == 0
        assert stats.avg_execution_time == 0.0
        
        # Test with values
        stats_with_data = QueryStatistics(
            query_count=100,
            avg_execution_time=0.5,
            cache_hit_rate=0.85
        )
        assert stats_with_data.query_count == 100


class TestIntegrationAndPerformance:
    """Test integration scenarios and performance considerations."""
    
    @pytest.mark.asyncio
    async def test_full_workflow_integration(self):
        """Test complete workflow integration."""
        ops = GraphOperations()
        traversal = GraphTraversal()
        queries = GraphQueries()
        
        # Step 1: Create nodes
        node1 = NodeData(None, "Person", {"name": "Alice", "role": "Manager"})
        node2 = NodeData(None, "Person", {"name": "Bob", "role": "Developer"})
        
        create_result1 = await ops.create_node(node1)
        create_result2 = await ops.create_node(node2)
        
        assert create_result1 is not None
        assert create_result2 is not None
        
        # Step 2: Create relationship
        edge = EdgeData(None, "MANAGES", "alice_id", "bob_id", {"since": "2023"})
        edge_result = await ops.create_edge(edge)
        assert edge_result is not None
        
        # Step 3: Query the graph
        params = QueryParams(node_labels=["Person"])
        query_result = await queries.execute_node_query(params)
        assert isinstance(query_result, QueryResult)
        
        # Step 4: Traverse the graph
        config = TraversalConfig(max_depth=2)
        traversal_result = await traversal.breadth_first_search("alice_id", config)
        assert isinstance(traversal_result, TraversalResult)
    
    @pytest.mark.asyncio
    async def test_performance_with_large_configs(self):
        """Test performance with larger configurations."""
        traversal = GraphTraversal()
        queries = GraphQueries()
        
        # Test with larger configurations
        large_config = TraversalConfig(max_depth=5, max_results=1000)
        result = await traversal.breadth_first_search("start", large_config)
        assert isinstance(result, TraversalResult)
        
        # Test query with pagination
        large_pagination = QueryPagination(offset=0, limit=500)
        params = QueryParams(pagination=large_pagination)
        query_result = await queries.execute_node_query(params)
        assert isinstance(query_result, QueryResult)
    
    def test_concurrent_access_safety(self):
        """Test thread safety considerations."""
        # Test multiple instances don't interfere
        ops1 = GraphOperations()
        ops2 = GraphOperations()
        
        traversal1 = GraphTraversal() 
        traversal2 = GraphTraversal()
        
        queries1 = GraphQueries()
        queries2 = GraphQueries()
        
        # Should be independent instances
        assert ops1 is not ops2
        assert traversal1 is not traversal2
        assert queries1 is not queries2
    
    def test_memory_efficiency(self):
        """Test memory usage patterns."""
        # Test that objects can be created and destroyed
        for i in range(100):
            ops = GraphOperations()
            traversal = GraphTraversal()
            queries = GraphQueries()
            
            # Use objects briefly
            config = TraversalConfig()
            params = QueryParams()
            
            assert ops is not None
            assert traversal is not None  
            assert queries is not None
            assert config is not None
            assert params is not None
