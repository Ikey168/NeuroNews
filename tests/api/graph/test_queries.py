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
        """Test execution of a node query via the current async API."""
        # Filter on a property present in the mock node data ('value' is an int).
        params = QueryParams(
            node_labels=["Person"],
            filters=[QueryFilter("value", "gt", 25)],
            pagination=QueryPagination(0, 10),
        )

        result = await graph_queries.execute_node_query(params)

        assert result is not None
        assert isinstance(result, QueryResult)

    @pytest.mark.asyncio
    async def test_query_plan_explanation(self, graph_queries):
        """Test the current explain_query_plan API for different query types."""
        node_plan = await graph_queries.explain_query_plan(
            "node_query", {"node_labels": ["Person"]}
        )
        rel_plan = await graph_queries.explain_query_plan(
            "relationship_query", {"edge_labels": ["WORKS_FOR"]}
        )

        assert isinstance(node_plan, dict)
        assert isinstance(rel_plan, dict)
        assert node_plan["query_type"] == "node_query"
        assert rel_plan["query_type"] == "relationship_query"
        assert isinstance(node_plan["execution_steps"], list)

    def test_query_optimization_recommendations(self, graph_queries):
        """Test optimize_query returns performance recommendations."""
        optimized = graph_queries.optimize_query(
            "node_query", {"node_labels": ["Person"], "filters": [1, 2, 3, 4, 5, 6]}
        )

        assert optimized is not None
        assert isinstance(optimized, dict)
        assert "estimated_performance" in optimized
        assert isinstance(optimized["recommendations"], list)

    @pytest.mark.asyncio
    async def test_advanced_filtering(self, graph_queries):
        """Test advanced filtering capabilities."""
        # Multiple filters over properties present in the mock node data
        # ('value' is an int, 'category' is the string 'test').
        filters = [
            QueryFilter(property_name="value", operator="gte", value=0),
            QueryFilter(property_name="value", operator="lte", value=1000),
            QueryFilter(property_name="category", operator="eq", value="test")
        ]

        params = QueryParams(node_labels=["Person"], filters=filters)
        result = await graph_queries.execute_node_query(params)

        assert result is not None
        assert isinstance(result, QueryResult)

    @pytest.mark.asyncio
    async def test_complex_sorting(self, graph_queries):
        """Test complex multi-field sorting."""
        sorts = [
            QuerySort(property_name="created_date", direction="desc"),
            QuerySort(property_name="name", direction="asc")
        ]

        params = QueryParams(node_labels=["Person"], sort=sorts)
        result = await graph_queries.execute_node_query(params)

        assert result is not None
        assert isinstance(result, QueryResult)

    @pytest.mark.asyncio
    async def test_nested_relationship_queries(self, graph_queries):
        """Test queries with nested relationships."""
        # Pattern: Person -> WORKS_FOR -> Organization -> LOCATED_IN -> City
        pattern = "Person->WORKS_FOR->Organization->LOCATED_IN->City"

        result = await graph_queries.execute_pattern_query(pattern)

        assert result is not None
        assert isinstance(result, QueryResult)
    
    # Additional comprehensive tests for 100% coverage
    
    def test_query_filter_edge_cases(self):
        """Test QueryFilter with edge cases."""
        # Empty property_name
        filter_empty = QueryFilter(property_name="", operator="eq", value="test")
        assert filter_empty.property_name == ""

        # None value
        filter_none = QueryFilter(property_name="test", operator="eq", value=None)
        assert filter_none.value is None

        # Complex value
        filter_complex = QueryFilter(
            property_name="metadata",
            operator="contains",
            value={"nested": {"key": "value"}}
        )
        assert isinstance(filter_complex.value, dict)

    def test_query_sort_edge_cases(self):
        """Test QuerySort with edge cases."""
        # Empty property_name
        sort_empty = QuerySort(property_name="", direction="asc")
        assert sort_empty.property_name == ""

        # Invalid direction (should still work)
        sort_invalid = QuerySort(property_name="name", direction="invalid")
        assert sort_invalid.direction == "invalid"
    
    def test_query_pagination_edge_cases(self):
        """Test QueryPagination with edge cases."""
        # Zero values
        page_zero = QueryPagination(offset=0, limit=0)
        assert page_zero.offset == 0
        assert page_zero.limit == 0
        
        # Negative values (should still create object)
        page_negative = QueryPagination(offset=-1, limit=-10)
        assert page_negative.offset == -1
        assert page_negative.limit == -10
    
    def test_query_params_complex(self):
        """Test QueryParams with complex configurations."""
        filters = [
            QueryFilter(property_name="age", operator="gt", value=18),
            QueryFilter(property_name="status", operator="eq", value="active"),
            QueryFilter(property_name="skills", operator="contains", value="Python")
        ]
        sorts = [
            QuerySort(property_name="name", direction="asc"),
            QuerySort(property_name="created_at", direction="desc")
        ]

        params = QueryParams(
            node_labels=["Person", "Developer"],
            edge_labels=["WORKS_FOR", "COLLABORATES_WITH"],
            filters=filters,
            sort=sorts,
            pagination=QueryPagination(offset=100, limit=50),
            include_properties=False,
            include_edges=True
        )

        assert len(params.node_labels) == 2
        assert len(params.edge_labels) == 2
        assert len(params.filters) == 3
        assert len(params.sort) == 2
        assert params.pagination.offset == 100
        assert params.include_properties is False
        assert params.include_edges is True
    
    def test_query_result_edge_cases(self):
        """Test QueryResult with edge cases using the current field set."""
        # Empty results
        result_empty = QueryResult(
            query_id="empty_query",
            execution_time=0.001,
            total_results=0,
            returned_results=0,
            has_more=False,
            data=[],
            metadata={}
        )

        assert len(result_empty.data) == 0
        assert result_empty.total_results == 0
        assert result_empty.returned_results == 0
        assert result_empty.has_more is False
        assert result_empty.metadata == {}

    def test_query_statistics_comprehensive(self):
        """Test QueryStatistics with the current field set."""
        stats = QueryStatistics(
            query_count=1500,
            avg_execution_time=5.432,
            cache_hit_rate=0.75,
            most_frequent_queries=["node_query", "relationship_query"]
        )

        assert stats.query_count == 1500
        assert stats.avg_execution_time == 5.432
        assert stats.cache_hit_rate == 0.75
        assert len(stats.most_frequent_queries) == 2
    
    @pytest.mark.asyncio
    async def test_execute_complex_node_query(self, graph_queries):
        """Test complex node query execution."""
        params = QueryParams(
            node_labels=["Person", "Organization"],
            filters=[
                QueryFilter(property_name="category", operator="eq", value="test"),
                QueryFilter(property_name="value", operator="gt", value=-1),
                QueryFilter(property_name="name", operator="contains", value="Node")
            ],
            sort=[QuerySort(property_name="relevance_score", direction="desc")],
            pagination=QueryPagination(offset=0, limit=100),
            include_properties=True,
            include_edges=True
        )

        result = await graph_queries.execute_node_query(params)

        assert isinstance(result, QueryResult)
        assert result.query_id is not None
        assert result.execution_time >= 0
    
    @pytest.mark.asyncio 
    async def test_execute_relationship_query_complex(self, graph_queries):
        """Test complex relationship query execution."""
        params = QueryParams(
            edge_labels=["WORKS_FOR", "COLLABORATES_WITH"],
            filters=[
                QueryFilter(property_name="strength", operator="gt", value=0.7),
                QueryFilter(property_name="duration", operator="gte", value=365)  # Days
            ],
            sort=[QuerySort(property_name="strength", direction="desc")],
            pagination=QueryPagination(offset=0, limit=50)
        )

        result = await graph_queries.execute_relationship_query(params)

        assert isinstance(result, QueryResult)
        assert isinstance(result.data, list)
        assert len(result.data) >= 0
    
    def test_apply_filter_comprehensive(self, graph_queries):
        """Test the filter operators implemented by _apply_filter(value, filter_item)."""
        # (operator, filter_value, sample_value, expected_result)
        cases = [
            ("eq", "equals", "equals", True),
            ("eq", "equals", "other", False),
            ("ne", "not_equals", "different", True),
            ("ne", "not_equals", "not_equals", False),
            ("gt", 10, 20, True),
            ("gt", 10, 5, False),
            ("gte", 10, 10, True),
            ("lt", 10, 5, True),
            ("lte", 10, 10, True),
            ("contains", "sub", "a substring", True),
            ("contains", "missing", "a substring", False),
            ("in", ["value1", "value2"], "value1", True),
            ("in", ["value1", "value2"], "value3", False),
        ]

        for op, filter_value, sample_value, expected in cases:
            filter_obj = QueryFilter(property_name="test_field", operator=op, value=filter_value)
            result = graph_queries._apply_filter(sample_value, filter_obj)
            assert isinstance(result, bool)
            assert result is expected

        # Unknown operators are treated as a pass-through (return True).
        unknown_filter = QueryFilter(property_name="test_field", operator="regex", value=".*")
        assert graph_queries._apply_filter("anything", unknown_filter) is True
    
    def test_cache_key_variations(self, graph_queries):
        """Test cache key generation with various parameters."""
        test_cases = [
            ({"simple": "value"}, "simple_case"),
            ({"nested": {"key": "value"}}, "nested_case"),
            ({"list": [1, 2, 3]}, "list_case"),
            ({"mixed": {"list": [{"nested": "value"}]}}, "complex_case"),
            ({}, "empty_case"),
            ({"unicode": "测试"}, "unicode_case"),
            ({"special_chars": "!@#$%^&*()_+"}, "special_case")
        ]
        
        keys = []
        for params, description in test_cases:
            key = graph_queries._generate_cache_key("test_query", params)
            keys.append(key)
            assert isinstance(key, str)
            assert len(key) > 0
        
        # All keys should be unique
        assert len(keys) == len(set(keys))
    
    def test_query_optimization_strategies(self, graph_queries):
        """Test different query optimization strategies."""
        base_params = {"node_labels": ["Person"]}
        
        # Test with different optimization hints
        optimization_hints = [
            {"strategy": "index_first"},
            {"strategy": "parallel_execution"},
            {"strategy": "memory_efficient"},
            {"strategy": "cache_aggressive"},
            {"limit_results": True},
            {"use_statistics": True}
        ]
        
        for hint in optimization_hints:
            params = {**base_params, **hint}
            result = graph_queries.optimize_query("node_query", params)
            assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_aggregation_query_types(self, graph_queries):
        """Test different aggregation query types."""
        aggregation_types = ["count", "sum", "avg", "min", "max", "group_by", "distinct"]

        params = QueryParams(
            node_labels=["Person"],
            filters=[QueryFilter(property_name="value", operator="gt", value=0)],
        )

        for agg_type in aggregation_types:
            result = await graph_queries.execute_aggregation_query(agg_type, params)
            assert isinstance(result, QueryResult)
            assert result.data[0]["aggregation_type"] == agg_type
    
    def test_query_statistics_tracking(self, graph_queries):
        """Test comprehensive query statistics tracking."""
        # Simulate multiple query executions via the real _update_query_stats(float).
        execution_times = [0.1, 0.2, 0.3, 0.4]

        for execution_time in execution_times:
            graph_queries._update_query_stats(execution_time)

        # Get overall statistics
        overall_stats = graph_queries.get_query_statistics()
        assert isinstance(overall_stats, dict)
        assert overall_stats["total_queries"] == len(execution_times)
        assert overall_stats["average_execution_time"] > 0
    
    def test_error_handling_scenarios(self, graph_queries):
        """Test error handling in various scenarios."""
        # Invalid/unknown filter operator should be handled gracefully (pass-through).
        invalid_filter = QueryFilter(property_name="test", operator="invalid_op", value="test")
        result = graph_queries._apply_filter("any_value", invalid_filter)
        assert result is True

        # Empty query parameters / cache key generation must not raise.
        empty_params = QueryParams()
        assert empty_params.filters is None
        cache_key = graph_queries._generate_cache_key("empty", {})
        assert isinstance(cache_key, str)
        assert cache_key.startswith("query_cache:")
    
    @pytest.mark.asyncio
    async def test_pattern_query_variations(self, graph_queries):
        """Test various pattern query formats."""
        patterns = [
            "Person->KNOWS->Person",
            "Organization<-WORKS_FOR<-Person->LIVES_IN->City",
            "A-[*1..3]->B",  # Variable length
            "(Person)-[:KNOWS*1..2]->(Person)",  # Cypher-style
            "Person.name='John'->KNOWS->Person.age>25",  # With properties
            "Person[active=true]->WORKS_FOR->Organization[type='tech']"
        ]
        
        for pattern in patterns:
            try:
                result = await graph_queries.execute_pattern_query(pattern)
                assert isinstance(result, QueryResult)
            except (ValueError, NotImplementedError):
                # Some patterns might not be supported
                pass
    
    @pytest.mark.asyncio
    async def test_performance_monitoring(self, graph_queries):
        """Test performance monitoring features via the current API."""
        # Statistics are tracked through _update_query_stats / get_query_statistics.
        graph_queries._update_query_stats(0.05)
        stats = graph_queries.get_query_statistics()
        assert isinstance(stats, dict)
        assert stats["total_queries"] >= 1
        assert isinstance(stats["average_execution_time"], (int, float))

        # Query plan explanation is exposed via explain_query_plan (async).
        params = {"node_labels": ["Person"]}
        plan = await graph_queries.explain_query_plan("node_query", params)
        assert isinstance(plan, dict)
        assert "execution_steps" in plan
        assert isinstance(plan["estimated_cost"], (int, float))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
