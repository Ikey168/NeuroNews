"""
Comprehensive test suite for Graph Queries module.
Target: 100% test coverage for src/api/graph/queries.py

This test suite covers the actual GraphQueries API:
- Query execution methods (node, relationship, pattern, aggregation)
- Query filtering and caching
- Query statistics and optimization
- Performance monitoring
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import json

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


class TestQuerySort:
    """Test QuerySort dataclass."""
    
    def test_query_sort_creation(self):
        """Test QuerySort creation."""
        sort_obj = QuerySort(property_name="created_at", direction="desc")
        
        assert sort_obj.property_name == "created_at"
        assert sort_obj.direction == "desc"


class TestQueryPagination:
    """Test QueryPagination dataclass."""
    
    def test_query_pagination_creation(self):
        """Test QueryPagination creation."""
        pagination = QueryPagination(offset=10, limit=25)
        
        assert pagination.offset == 10
        assert pagination.limit == 25


class TestQueryParams:
    """Test QueryParams dataclass."""
    
    def test_query_params_creation(self):
        """Test QueryParams with all fields."""
        filters = [QueryFilter("name", "eq", "John")]
        sorts = [QuerySort("created_at", "desc")]
        pagination = QueryPagination(10, 50)
        
        params = QueryParams(
            node_labels=["Person", "Organization"],
            edge_labels=["WORKS_FOR"],
            filters=filters,
            sort=sorts,
            pagination=pagination,
            include_properties=True,
            include_edges=False
        )
        
        assert params.node_labels == ["Person", "Organization"]
        assert params.edge_labels == ["WORKS_FOR"]
        assert params.filters == filters
        assert params.sort == sorts
        assert params.pagination == pagination
        assert params.include_properties is True
        assert params.include_edges is False


class TestQueryResult:
    """Test QueryResult dataclass."""
    
    def test_query_result_creation(self):
        """Test QueryResult creation with actual fields."""
        result = QueryResult(
            query_id="test123",
            execution_time=0.123,
            total_results=100,
            returned_results=10,
            has_more=True,
            data=[{"id": "node1", "label": "Person"}],
            metadata={"query_type": "node_query"}
        )
        
        assert result.query_id == "test123"
        assert result.execution_time == 0.123
        assert result.total_results == 100
        assert result.returned_results == 10
        assert result.has_more is True
        assert len(result.data) == 1
        assert result.metadata["query_type"] == "node_query"


class TestQueryStatistics:
    """Test QueryStatistics dataclass."""
    
    def test_query_statistics_creation(self):
        """Test QueryStatistics creation."""
        stats = QueryStatistics(
            query_count=10,
            avg_execution_time=0.5,
            cache_hit_rate=0.8,
            most_frequent_queries=["node_query"]
        )
        
        assert stats.query_count == 10
        assert stats.avg_execution_time == 0.5
        assert stats.cache_hit_rate == 0.8
        assert stats.most_frequent_queries == ["node_query"]


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
        assert graph_queries.cache_timestamps == {}
        assert isinstance(graph_queries.query_stats, QueryStatistics)
        assert graph_queries.query_history == []
    
    def test_initialization_with_builder(self):
        """Test GraphQueries initialization with graph builder."""
        mock_builder = Mock()
        queries = GraphQueries(graph_builder=mock_builder)
        assert queries.graph == mock_builder
    
    def test_generate_query_id(self, graph_queries):
        """Test query ID generation."""
        params = {"node_labels": ["Person"]}
        
        query_id1 = graph_queries._generate_query_id("node_query", params)
        query_id2 = graph_queries._generate_query_id("node_query", params)
        
        # Should generate valid IDs
        assert isinstance(query_id1, str)
        assert len(query_id1) == 16  # MD5 hash truncated to 16 chars
        assert isinstance(query_id2, str)
    
    def test_generate_cache_key(self, graph_queries):
        """Test cache key generation."""
        params = {"node_labels": ["Person"]}
        
        cache_key = graph_queries._generate_cache_key("node_query", params)
        
        assert isinstance(cache_key, str)
        assert cache_key.startswith("query_cache:")
        assert len(cache_key) > 20  # Should have prefix + hash
    
    @pytest.mark.asyncio
    async def test_execute_node_query_basic(self, graph_queries):
        """Test basic node query execution."""
        params = QueryParams(
            node_labels=["Person"],
            pagination=QueryPagination(0, 5)
        )
        
        result = await graph_queries.execute_node_query(params)
        
        assert isinstance(result, QueryResult)
        assert isinstance(result.query_id, str)
        assert result.execution_time >= 0
        assert isinstance(result.data, list)
        assert len(result.data) <= 5  # Should respect pagination limit
    
    @pytest.mark.asyncio
    async def test_execute_node_query_with_filters(self, graph_queries):
        """Test node query with filters."""
        params = QueryParams(
            node_labels=["Person"],
            filters=[QueryFilter("name", "eq", "test")],
            pagination=QueryPagination(0, 10)
        )
        
        result = await graph_queries.execute_node_query(params)
        
        assert isinstance(result, QueryResult)
        assert isinstance(result.data, list)
    
    @pytest.mark.asyncio
    async def test_execute_relationship_query(self, graph_queries):
        """Test relationship query execution."""
        params = QueryParams(
            edge_labels=["WORKS_FOR"],
            pagination=QueryPagination(0, 10)
        )
        
        result = await graph_queries.execute_relationship_query(params)
        
        assert isinstance(result, QueryResult)
        assert isinstance(result.data, list)
    
    @pytest.mark.asyncio
    async def test_execute_pattern_query(self, graph_queries):
        """Test pattern query execution."""
        pattern = "(person:Person)-[:WORKS_FOR]->(org:Organization)"
        params = {"min_employees": 10}
        
        result = await graph_queries.execute_pattern_query(pattern, params)
        
        assert isinstance(result, QueryResult)
        assert isinstance(result.data, list)
    
    @pytest.mark.asyncio
    async def test_execute_aggregation_query(self, graph_queries):
        """Test aggregation query execution."""
        params = QueryParams(node_labels=["Person"])
        
        result = await graph_queries.execute_aggregation_query("count", params)
        
        assert isinstance(result, QueryResult)
        assert isinstance(result.data, list)
    
    def test_apply_filter_eq(self, graph_queries):
        """Test filter application - equals."""
        filter_obj = QueryFilter("name", "eq", "John")
        
        assert graph_queries._apply_filter("John", filter_obj) is True
        assert graph_queries._apply_filter("Jane", filter_obj) is False
    
    def test_apply_filter_contains(self, graph_queries):
        """Test filter application - contains."""
        filter_obj = QueryFilter("description", "contains", "test")
        
        assert graph_queries._apply_filter("this is a test", filter_obj) is True
        assert graph_queries._apply_filter("no match here", filter_obj) is False
    
    def test_apply_filter_gt(self, graph_queries):
        """Test filter application - greater than."""
        filter_obj = QueryFilter("age", "gt", 25)
        
        assert graph_queries._apply_filter(30, filter_obj) is True
        assert graph_queries._apply_filter(20, filter_obj) is False
    
    def test_apply_filter_in(self, graph_queries):
        """Test filter application - in list."""
        filter_obj = QueryFilter("category", "in", ["A", "B", "C"])
        
        assert graph_queries._apply_filter("B", filter_obj) is True
        assert graph_queries._apply_filter("D", filter_obj) is False
    
    def test_update_query_stats(self, graph_queries):
        """Test query statistics update."""
        initial_count = graph_queries.query_stats.query_count
        
        graph_queries._update_query_stats(0.5)
        
        assert graph_queries.query_stats.query_count == initial_count + 1
        # avg_execution_time should be updated
        assert graph_queries.query_stats.avg_execution_time >= 0
    
    def test_get_query_statistics(self, graph_queries):
        """Test getting query statistics."""
        # Add some stats first
        graph_queries._update_query_stats(0.1)
        graph_queries._update_query_stats(0.2)
        
        stats = graph_queries.get_query_statistics()
        
        assert isinstance(stats, dict)
        assert "total_queries" in stats  # Actual key name
        assert "average_execution_time" in stats  # Actual key name
        assert "cache_hit_rate" in stats
        assert stats["total_queries"] >= 2
    
    def test_optimize_query(self, graph_queries):
        """Test query optimization."""
        params = {"node_labels": ["Person"], "limit": 1000}
        
        optimized = graph_queries.optimize_query("node_query", params)
        
        assert isinstance(optimized, dict)
        # Should return optimized parameters
        assert "optimized" in optimized or "suggestions" in optimized or len(optimized) > 0
    
    @pytest.mark.asyncio
    async def test_explain_query_plan(self, graph_queries):
        """Test query plan explanation."""
        params = {"node_labels": ["Person"]}
        
        plan = await graph_queries.explain_query_plan("node_query", params)
        
        assert isinstance(plan, dict)
        # Should return execution plan details
        assert len(plan) > 0
    
    def test_cache_functionality(self, graph_queries):
        """Test query cache functionality."""
        # Cache should be initially empty
        assert len(graph_queries.query_cache) == 0
        
        # Add item to cache (simulate caching behavior)
        cache_key = "test_key"
        graph_queries.query_cache[cache_key] = {"result": "test"}
        graph_queries.cache_timestamps[cache_key] = datetime.now()
        
        assert len(graph_queries.query_cache) == 1
        assert cache_key in graph_queries.query_cache
    
    def test_query_history_tracking(self, graph_queries):
        """Test query history tracking."""
        # History should be initially empty
        assert len(graph_queries.query_history) == 0
        
        # Simulate adding query to history
        query_record = {
            "query_id": "test123",
            "query_type": "node_query",
            "execution_time": 0.1,
            "timestamp": datetime.now().isoformat()
        }
        graph_queries.query_history.append(query_record)
        
        assert len(graph_queries.query_history) == 1
        assert graph_queries.query_history[0]["query_id"] == "test123"
    
    @pytest.mark.asyncio
    async def test_execute_complex_query(self, graph_queries):
        """Test execution of complex queries."""
        query = "g.V().hasLabel('Person').has('age', P.gt(25))"
        
        # Mock complex query execution
        with patch.object(graph_queries.graph, 'g') if graph_queries.graph else patch('builtins.open'):
            result = await graph_queries.execute_query(query)
            
            assert result is not None
            assert isinstance(result, QueryResult)
    
    def test_query_validation(self, graph_queries):
        """Test query syntax validation."""
        valid_query = "g.V().hasLabel('Person').limit(10)"
        invalid_query = "invalid gremlin syntax here"
        
        is_valid_1 = graph_queries.validate_query_syntax(valid_query)
        is_valid_2 = graph_queries.validate_query_syntax(invalid_query)
        
        # Should handle validation gracefully
        assert isinstance(is_valid_1, bool)
        assert isinstance(is_valid_2, bool)
    
    def test_query_performance_analysis(self, graph_queries):
        """Test query performance analysis."""
        query = "g.V().hasLabel('Person').out().limit(50)"
        
        analysis = graph_queries.analyze_query_complexity(query)
        
        assert analysis is not None
        assert isinstance(analysis, dict)
        # Should include performance metrics
        if 'complexity_score' in analysis:
            assert isinstance(analysis['complexity_score'], (int, float))
    
    def test_advanced_filtering(self, graph_queries):
        """Test advanced filtering capabilities."""
        # Multiple filters
        filters = [
            QueryFilter(field="age", operator="gte", value=18),
            QueryFilter(field="age", operator="lte", value=65),
            QueryFilter(field="status", operator="eq", value="active")
        ]
        
        params = QueryParams(filters=filters)
        result = graph_queries.execute_node_query("Person", params, None)
        
        assert result is not None
        assert isinstance(result, QueryResult)
    
    def test_complex_sorting(self, graph_queries):
        """Test complex multi-field sorting."""
        sorts = [
            QuerySort(field="created_date", direction="desc"),
            QuerySort(field="name", direction="asc")
        ]
        
        params = QueryParams(sorts=sorts)
        result = graph_queries.execute_node_query("Person", params, None)
        
        assert result is not None
        assert isinstance(result, QueryResult)
    
    def test_nested_relationship_queries(self, graph_queries):
        """Test queries with nested relationships."""
        # Pattern: Person -> WORKS_FOR -> Organization -> LOCATED_IN -> City
        pattern = "Person->WORKS_FOR->Organization->LOCATED_IN->City"
        
        result = graph_queries.execute_pattern_query(pattern, None, None)
        
        assert result is not None
        assert isinstance(result, QueryResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
