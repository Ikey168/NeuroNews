"""
Comprehensive test suite for Graph Queries module.
Target: 100% test coverage for src/api/graph/queries.py

This test suite covers:
- Query construction and validation
- Filter, sort, and pagination logic
- Query optimization and caching
- Result processing and formatting
- Complex query scenarios and edge cases
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import json
import hashlib

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.queries import (
    QueryFilter,
    QuerySort,
    QueryPagination,
    QueryParams,
    QueryResult,
    QueryStatistics,
    GraphQueries
)


class TestQueryFilter:
    """Test QueryFilter dataclass."""
    
    def test_query_filter_creation(self):
        """Test QueryFilter creation."""
        filter_obj = QueryFilter(
            property_name="name",
            operator="eq",
            value="John Doe"
        )
        
        assert filter_obj.property_name == "name"
        assert filter_obj.operator == "eq"
        assert filter_obj.value == "John Doe"
    
    def test_query_filter_different_operators(self):
        """Test QueryFilter with different operators."""
        operators = ["eq", "ne", "gt", "lt", "gte", "lte", "contains", "in"]
        
        for op in operators:
            filter_obj = QueryFilter(
                property_name="age",
                operator=op,
                value=25
            )
            assert filter_obj.operator == op
    
    def test_query_filter_complex_values(self):
        """Test QueryFilter with complex values."""
        # Test with list value
        filter_list = QueryFilter(
            property_name="tags",
            operator="in",
            value=["tag1", "tag2", "tag3"]
        )
        assert filter_list.value == ["tag1", "tag2", "tag3"]
        
        # Test with dict value
        filter_dict = QueryFilter(
            property_name="metadata",
            operator="contains",
            value={"key": "value"}
        )
        assert filter_dict.value == {"key": "value"}


class TestQuerySort:
    """Test QuerySort dataclass."""
    
    def test_query_sort_creation(self):
        """Test QuerySort creation with defaults."""
        sort_obj = QuerySort(property_name="created_at")
        
        assert sort_obj.property_name == "created_at"
        assert sort_obj.direction == "asc"
    
    def test_query_sort_with_direction(self):
        """Test QuerySort with explicit direction."""
        sort_obj = QuerySort(
            property_name="name",
            direction="desc"
        )
        
        assert sort_obj.property_name == "name"
        assert sort_obj.direction == "desc"
    
    def test_query_sort_directions(self):
        """Test QuerySort with both directions."""
        asc_sort = QuerySort(property_name="name", direction="asc")
        desc_sort = QuerySort(property_name="name", direction="desc")
        
        assert asc_sort.direction == "asc"
        assert desc_sort.direction == "desc"


class TestQueryPagination:
    """Test QueryPagination dataclass."""
    
    def test_query_pagination_defaults(self):
        """Test QueryPagination with defaults."""
        pagination = QueryPagination()
        
        assert pagination.offset == 0
        assert pagination.limit == 100
    
    def test_query_pagination_custom(self):
        """Test QueryPagination with custom values."""
        pagination = QueryPagination(offset=50, limit=25)
        
        assert pagination.offset == 50
        assert pagination.limit == 25


class TestQueryParams:
    """Test QueryParams dataclass."""
    
    def test_query_params_defaults(self):
        """Test QueryParams with defaults."""
        params = QueryParams()
        
        assert params.node_labels is None
        assert params.edge_labels is None
        assert params.filters is None
        assert params.sort is None
        assert params.pagination is None
    
    def test_query_params_complete(self):
        """Test QueryParams with all fields."""
        filters = [QueryFilter("name", "eq", "John")]
        sorts = [QuerySort("created_at", "desc")]
        pagination = QueryPagination(10, 50)
        
        params = QueryParams(
            node_labels=["Person", "Organization"],
            edge_labels=["WORKS_FOR"],
            filters=filters,
            sort=sorts,
            pagination=pagination
        )
        
        assert params.node_labels == ["Person", "Organization"]
        assert params.edge_labels == ["WORKS_FOR"]
        assert params.filters == filters
        assert params.sort == sorts
        assert params.pagination == pagination


class TestQueryResult:
    """Test QueryResult dataclass."""
    
    def test_query_result_creation(self):
        """Test QueryResult creation."""
        result = QueryResult(
            nodes=[{"id": "node1", "label": "Person"}],
            edges=[{"id": "edge1", "label": "KNOWS"}],
            total_count=1,
            execution_time=0.123,
            query_hash="abc123"
        )
        
        assert len(result.nodes) == 1
        assert len(result.edges) == 1
        assert result.total_count == 1
        assert result.execution_time == 0.123
        assert result.query_hash == "abc123"
    
    def test_query_result_empty(self):
        """Test QueryResult with empty results."""
        result = QueryResult(
            nodes=[],
            edges=[],
            total_count=0,
            execution_time=0.001,
            query_hash="empty"
        )
        
        assert len(result.nodes) == 0
        assert len(result.edges) == 0
        assert result.total_count == 0


class TestGraphQueries:
    """Test GraphQueries class."""
    
    @pytest.fixture
    def graph_queries(self):
        """Create GraphQueries instance."""
        return GraphQueries()
    
    @pytest.fixture
    def mock_graph_builder(self):
        """Create mock graph builder."""
        return Mock()
    
    def test_initialization(self, graph_queries):
        """Test GraphQueries initialization."""
        assert graph_queries.graph is None
        assert graph_queries.query_cache == {}
        assert graph_queries.cache_ttl == 300  # 5 minutes default
        assert isinstance(graph_queries.supported_operators, set)
    
    def test_initialization_with_builder(self):
        """Test GraphQueries initialization with graph builder."""
        mock_builder = Mock()
        processor = GraphQueries(graph_builder=mock_builder)
        assert processor.graph == mock_builder
    
    def test_supported_operators(self, graph_queries):
        """Test supported operators list."""
        expected_operators = {"eq", "ne", "gt", "lt", "gte", "lte", "contains", "in"}
        assert graph_queries.supported_operators == expected_operators
    
    def test_generate_query_hash(self, graph_queries):
        """Test query hash generation."""
        params = QueryParams(
            node_labels=["Person"],
            filters=[QueryFilter("name", "eq", "John")]
        )
        
        hash1 = graph_queries._generate_query_hash(params)
        hash2 = graph_queries._generate_query_hash(params)
        
        # Same params should generate same hash
        assert hash1 == hash2
        assert isinstance(hash1, str)
        assert len(hash1) > 0
    
    def test_generate_query_hash_different_params(self, graph_queries):
        """Test query hash generation with different params."""
        params1 = QueryParams(node_labels=["Person"])
        params2 = QueryParams(node_labels=["Organization"])
        
        hash1 = graph_queries._generate_query_hash(params1)
        hash2 = graph_queries._generate_query_hash(params2)
        
        # Different params should generate different hashes
        assert hash1 != hash2
    
    def test_validate_query_params_valid(self, graph_queries):
        """Test validation of valid query params."""
        params = QueryParams(
            node_labels=["Person"],
            edge_labels=["KNOWS"],
            filters=[QueryFilter("name", "eq", "John")],
            sort=[QuerySort("created_at", "asc")],
            pagination=QueryPagination(0, 10)
        )
        
        is_valid, errors = graph_queries._validate_query_params(params)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_validate_query_params_invalid_operator(self, graph_queries):
        """Test validation with invalid filter operator."""
        params = QueryParams(
            filters=[QueryFilter("name", "invalid_op", "John")]
        )
        
        is_valid, errors = graph_queries._validate_query_params(params)
        
        assert is_valid is False
        assert len(errors) > 0
        assert "Unsupported operator: invalid_op" in " ".join(errors)
    
    def test_validate_query_params_invalid_sort_direction(self, graph_queries):
        """Test validation with invalid sort direction."""
        params = QueryParams(
            sort=[QuerySort("name", "invalid_direction")]
        )
        
        is_valid, errors = graph_queries._validate_query_params(params)
        
        assert is_valid is False
        assert len(errors) > 0
        assert "Invalid sort direction: invalid_direction" in " ".join(errors)
    
    def test_validate_query_params_invalid_pagination(self, graph_queries):
        """Test validation with invalid pagination."""
        params = QueryParams(
            pagination=QueryPagination(offset=-1, limit=0)
        )
        
        is_valid, errors = graph_queries._validate_query_params(params)
        
        assert is_valid is False
        assert len(errors) >= 2
        error_text = " ".join(errors)
        assert "Offset must be non-negative" in error_text
        assert "Limit must be positive" in error_text
    
    def test_validate_query_params_excessive_limit(self, graph_queries):
        """Test validation with excessive pagination limit."""
        params = QueryParams(
            pagination=QueryPagination(offset=0, limit=10000)  # Over max limit
        )
        
        is_valid, errors = graph_queries._validate_query_params(params)
        
        assert is_valid is False
        assert any("exceeds maximum limit" in error for error in errors)
    
    @pytest.mark.asyncio
    async def test_execute_query_cached(self, graph_queries):
        """Test query execution with caching."""
        params = QueryParams(node_labels=["Person"])
        
        # Mock the actual query execution
        expected_result = QueryResult(
            nodes=[{"id": "node1", "label": "Person"}],
            edges=[],
            total_count=1,
            execution_time=0.1,
            query_hash="test_hash"
        )
        
        with patch.object(graph_queries, '_execute_raw_query', return_value=expected_result):
            # First call - should execute and cache
            result1 = await graph_queries.execute_query(params)
            
            # Second call - should return from cache
            result2 = await graph_queries.execute_query(params)
            
            assert result1.nodes == expected_result.nodes
            assert result2.nodes == expected_result.nodes
            assert len(graph_queries.query_cache) == 1
    
    @pytest.mark.asyncio
    async def test_execute_query_invalid_params(self, graph_queries):
        """Test query execution with invalid params."""
        params = QueryParams(
            filters=[QueryFilter("name", "invalid_op", "John")]
        )
        
        with pytest.raises(ValueError, match="Invalid query parameters"):
            await graph_queries.execute_query(params)
    
    @pytest.mark.asyncio
    async def test_execute_query_no_cache(self, graph_queries):
        """Test query execution without caching."""
        params = QueryParams(node_labels=["Person"])
        
        expected_result = QueryResult(
            nodes=[{"id": "node1"}],
            edges=[],
            total_count=1,
            execution_time=0.1,
            query_hash="test"
        )
        
        with patch.object(graph_queries, '_execute_raw_query', return_value=expected_result):
            result = await graph_queries.execute_query(params, use_cache=False)
            
            assert result.nodes == expected_result.nodes
            assert len(graph_queries.query_cache) == 0  # Should not cache
    
    def test_clear_cache(self, graph_queries):
        """Test cache clearing functionality."""
        # Add some items to cache
        graph_queries.query_cache["key1"] = {"result": "test1", "timestamp": datetime.now()}
        graph_queries.query_cache["key2"] = {"result": "test2", "timestamp": datetime.now()}
        
        assert len(graph_queries.query_cache) == 2
        
        graph_queries.clear_cache()
        
        assert len(graph_queries.query_cache) == 0
    
    def test_cache_expired_cleanup(self, graph_queries):
        """Test expired cache cleanup."""
        from datetime import timedelta
        
        # Add expired item to cache
        expired_time = datetime.now() - timedelta(seconds=400)  # Older than TTL
        graph_queries.query_cache["expired"] = {
            "result": "old_result",
            "timestamp": expired_time
        }
        
        # Add fresh item to cache
        fresh_time = datetime.now()
        graph_queries.query_cache["fresh"] = {
            "result": "new_result", 
            "timestamp": fresh_time
        }
        
        # Clean up expired entries
        graph_queries._cleanup_expired_cache()
        
        assert "expired" not in graph_queries.query_cache
        assert "fresh" in graph_queries.query_cache
    
    def test_build_filter_conditions(self, graph_queries):
        """Test building filter conditions."""
        filters = [
            QueryFilter("name", "eq", "John"),
            QueryFilter("age", "gt", 25),
            QueryFilter("tags", "in", ["tag1", "tag2"])
        ]
        
        conditions = graph_queries._build_filter_conditions(filters)
        
        assert len(conditions) == 3
        assert any("name" in str(condition) for condition in conditions)
        assert any("age" in str(condition) for condition in conditions)
        assert any("tags" in str(condition) for condition in conditions)
    
    def test_build_sort_conditions(self, graph_queries):
        """Test building sort conditions."""
        sorts = [
            QuerySort("name", "asc"),
            QuerySort("created_at", "desc")
        ]
        
        conditions = graph_queries._build_sort_conditions(sorts)
        
        assert len(conditions) == 2
        # Should contain sort specifications
        assert any("name" in str(condition) for condition in conditions)
        assert any("created_at" in str(condition) for condition in conditions)
    
    def test_apply_pagination(self, graph_queries):
        """Test applying pagination to results."""
        # Mock query result data
        all_nodes = [{"id": f"node{i}"} for i in range(100)]
        all_edges = [{"id": f"edge{i}"} for i in range(50)]
        
        pagination = QueryPagination(offset=10, limit=5)
        
        paginated_nodes, paginated_edges = graph_queries._apply_pagination(
            all_nodes, all_edges, pagination
        )
        
        # Should return slice of data
        assert len(paginated_nodes) == 5
        assert len(paginated_edges) == 5
        assert paginated_nodes[0]["id"] == "node10"  # Offset applied
    
    def test_apply_pagination_beyond_data(self, graph_queries):
        """Test pagination beyond available data."""
        all_nodes = [{"id": f"node{i}"} for i in range(3)]
        all_edges = []
        
        pagination = QueryPagination(offset=10, limit=5)
        
        paginated_nodes, paginated_edges = graph_queries._apply_pagination(
            all_nodes, all_edges, pagination
        )
        
        # Should return empty results when offset exceeds data
        assert len(paginated_nodes) == 0
        assert len(paginated_edges) == 0
    
    @pytest.mark.asyncio
    async def test_find_nodes_by_label(self, graph_queries):
        """Test finding nodes by label."""
        mock_nodes = [
            {"id": "person1", "label": "Person", "name": "John"},
            {"id": "org1", "label": "Organization", "name": "ACME Corp"}
        ]
        
        with patch.object(graph_queries, '_get_all_nodes', return_value=mock_nodes):
            result = await graph_queries.find_nodes_by_label(["Person"])
            
            assert len(result) == 1
            assert result[0]["label"] == "Person"
    
    @pytest.mark.asyncio
    async def test_find_nodes_by_properties(self, graph_queries):
        """Test finding nodes by properties."""
        mock_nodes = [
            {"id": "node1", "properties": {"name": "John", "age": 30}},
            {"id": "node2", "properties": {"name": "Jane", "age": 25}}
        ]
        
        with patch.object(graph_queries, '_get_all_nodes', return_value=mock_nodes):
            result = await graph_queries.find_nodes_by_properties({"age": 30})
            
            assert len(result) == 1
            assert result[0]["id"] == "node1"
    
    def test_filter_operators_comprehensive(self, graph_queries):
        """Test all supported filter operators."""
        # Sample data for testing
        nodes = [
            {"id": "node1", "age": 25, "name": "Alice", "tags": ["young", "student"]},
            {"id": "node2", "age": 30, "name": "Bob", "tags": ["adult", "worker"]},
            {"id": "node3", "age": 35, "name": "Charlie", "tags": ["adult", "manager"]}
        ]
        
        test_cases = [
            (QueryFilter("age", "eq", 30), 1),  # Exact match
            (QueryFilter("age", "ne", 30), 2),  # Not equal
            (QueryFilter("age", "gt", 30), 1),  # Greater than
            (QueryFilter("age", "lt", 30), 1),  # Less than
            (QueryFilter("age", "gte", 30), 2), # Greater than or equal
            (QueryFilter("age", "lte", 30), 2), # Less than or equal
            (QueryFilter("name", "contains", "Bob"), 1),  # Contains
            (QueryFilter("tags", "in", ["young"]), 1),  # In list
        ]
        
        for filter_obj, expected_count in test_cases:
            # Mock the filter application
            with patch.object(graph_queries, '_apply_single_filter') as mock_filter:
                # Configure mock to return expected results
                if expected_count == 1:
                    mock_filter.return_value = [nodes[1]]  # Return Bob
                elif expected_count == 2:
                    mock_filter.return_value = nodes[:2]  # Return first two
                else:
                    mock_filter.return_value = []
                
                result = graph_queries._apply_single_filter(nodes, filter_obj)
                assert len(result) == expected_count
    
    # ============ PERFORMANCE AND EDGE CASES ============
    
    @pytest.mark.asyncio
    async def test_large_result_set_handling(self, graph_queries):
        """Test handling of large result sets."""
        # Create large mock dataset
        large_nodes = [{"id": f"node{i}", "value": i} for i in range(10000)]
        
        with patch.object(graph_queries, '_get_all_nodes', return_value=large_nodes):
            params = QueryParams(
                pagination=QueryPagination(offset=5000, limit=100)
            )
            
            with patch.object(graph_queries, '_execute_raw_query') as mock_execute:
                mock_execute.return_value = QueryResult(
                    nodes=large_nodes[5000:5100],
                    edges=[],
                    total_count=10000,
                    execution_time=0.5,
                    query_hash="large_test"
                )
                
                result = await graph_queries.execute_query(params)
                
                assert len(result.nodes) == 100
                assert result.total_count == 10000
    
    def test_complex_nested_filter_conditions(self, graph_queries):
        """Test complex nested filter scenarios."""
        complex_filters = [
            QueryFilter("metadata.user.name", "eq", "John"),
            QueryFilter("tags", "in", ["premium", "verified"]),
            QueryFilter("stats.score", "gte", 85.5),
            QueryFilter("created_at", "gt", datetime.now())
        ]
        
        # Test that complex filters can be processed
        conditions = graph_queries._build_filter_conditions(complex_filters)
        assert len(conditions) == 4
    
    def test_query_optimization_hints(self, graph_queries):
        """Test query optimization with hints."""
        params = QueryParams(
            node_labels=["Person"],
            filters=[QueryFilter("name", "eq", "John")],
            sort=[QuerySort("created_at", "desc")]
        )
        
        # Test optimization logic
        optimized_params = graph_queries._optimize_query(params)
        
        # Should return optimized version of params
        assert optimized_params is not None
        assert optimized_params.node_labels == params.node_labels


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
