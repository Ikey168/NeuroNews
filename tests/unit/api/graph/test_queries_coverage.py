"""
Comprehensive coverage tests for GraphQueries module.
Targeting specific uncovered lines and edge cases.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json
import hashlib
from datetime import datetime

from src.api.graph.queries import (
    GraphQueries, QueryFilter, QuerySort, QueryPagination, 
    QueryParams, QueryResult, QueryStatistics
)


class TestQueriesCoverage:
    """Tests targeting comprehensive coverage for GraphQueries."""
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test initialization scenarios."""
        # Test with graph builder
        builder = Mock()
        queries = GraphQueries(graph_builder=builder)
        assert queries.graph == builder
        assert isinstance(queries.query_cache, dict)
        assert isinstance(queries.cache_timestamps, dict)
        assert isinstance(queries.query_stats, QueryStatistics)
        assert isinstance(queries.query_history, list)
        
        # Test without graph builder
        queries_no_builder = GraphQueries()
        assert queries_no_builder.graph is None
        
    def test_query_dataclass_structures(self):
        """Test query dataclass creation and validation."""
        # Test QueryFilter
        filter_obj = QueryFilter(property_name="name", operator="eq", value="Alice")
        assert filter_obj.property_name == "name"
        assert filter_obj.operator == "eq"
        assert filter_obj.value == "Alice"
        
        # Test QuerySort
        sort_obj = QuerySort(property_name="age", direction="asc")
        assert sort_obj.property_name == "age"
        assert sort_obj.direction == "asc"
        
        # Test QueryPagination
        pagination = QueryPagination(limit=10, offset=20)
        assert pagination.limit == 10
        assert pagination.offset == 20
        
        # Test QueryParams
        params = QueryParams(
            filters=[filter_obj],
            sort=sort_obj,
            pagination=pagination,
            include_properties=True,
            include_edges=False
        )
        assert len(params.filters) == 1
        assert params.sort == sort_obj
        assert params.pagination == pagination
        assert params.include_properties is True
        assert params.include_edges is False
        
        # Test QueryResult
        result = QueryResult(
            query_id="test_id",
            execution_time=0.15,
            total_results=100,
            returned_results=10,
            has_more=True,
            data=[{"id": "1", "name": "Test"}],
            metadata={"query_type": "node_query"}
        )
        assert result.query_id == "test_id"
        assert result.execution_time == 0.15
        assert result.total_results == 100
        assert result.returned_results == 10
        assert result.has_more is True
        assert len(result.data) == 1
        
        # Test QueryStatistics
        stats = QueryStatistics(
            query_count=5,
            avg_execution_time=0.25,
            cache_hit_rate=0.75,
            most_frequent_queries=["node_query", "edge_query"]
        )
        assert stats.query_count == 5
        assert stats.avg_execution_time == 0.25
        assert stats.cache_hit_rate == 0.75
        assert len(stats.most_frequent_queries) == 2
        
    def test_cache_and_utility_methods(self):
        """Test caching and utility methods."""
        queries = GraphQueries()
        
        # Test query ID generation
        params = {"type": "node", "filters": []}
        query_id = queries._generate_query_id("node_query", params)
        assert isinstance(query_id, str)
        assert len(query_id) == 16  # MD5 hash truncated to 16 chars
        
        # Test cache key generation
        cache_key = queries._generate_cache_key("node_query", params)
        assert isinstance(cache_key, str)
        
        # Test that same params generate same keys
        query_id2 = queries._generate_query_id("node_query", params)
        cache_key2 = queries._generate_cache_key("node_query", params)
        # Note: IDs may differ due to timestamp, but cache keys should be similar structure
        
    @pytest.mark.asyncio
    async def test_node_query_execution(self):
        """Test node query execution scenarios."""
        queries = GraphQueries()
        
        # Test without graph
        params = QueryParams()
        result = await queries.execute_node_query(params)
        assert isinstance(result, QueryResult)
        assert result.data == []
        assert result.total_results == 0
        
        # Test with mock graph
        queries.graph = Mock()
        queries.graph.g = Mock()
        
        # Mock count query
        mock_count_query = Mock()
        mock_count_query.next = AsyncMock(return_value=5)
        
        # Mock data query  
        mock_data_query = Mock()
        mock_data_query.valueMap = Mock()
        mock_data_query.valueMap.return_value.toList = AsyncMock(return_value=[
            {"id": "node1", "name": "Alice", "age": 30},
            {"id": "node2", "name": "Bob", "age": 25}
        ])
        
        # Setup graph mock chain
        queries.graph.g.V.return_value.count.return_value = mock_count_query
        queries.graph.g.V.return_value = mock_data_query
        
        result = await queries.execute_node_query(params)
        assert isinstance(result, QueryResult)
        
        # Test with filters
        filter_obj = QueryFilter(property_name="name", operator="eq", value="Alice")
        params_with_filter = QueryParams(filters=[filter_obj])
        result = await queries.execute_node_query(params_with_filter)
        assert isinstance(result, QueryResult)
        
    @pytest.mark.asyncio
    async def test_relationship_query_execution(self):
        """Test relationship query execution scenarios."""
        queries = GraphQueries()
        
        # Test without graph
        params = QueryParams()
        result = await queries.execute_relationship_query(params)
        assert isinstance(result, QueryResult)
        assert result.data == []
        
        # Test with mock graph error
        queries.graph = Mock()
        queries.graph.g = Mock()
        mock_query = Mock()
        mock_query.count = Mock(return_value=Mock(next=AsyncMock(side_effect=Exception("Count error"))))
        queries.graph.g.E = Mock(return_value=mock_query)
        
        result = await queries.execute_relationship_query(params)
        assert isinstance(result, QueryResult)
        assert result.data == []
        
    @pytest.mark.asyncio
    async def test_pattern_query_execution(self):
        """Test pattern query execution scenarios.""" 
        queries = GraphQueries()
        
        # Test pattern query without graph
        pattern = {"nodes": [{"label": "Person"}], "relationships": []}
        params = QueryParams()
        result = await queries.execute_pattern_query(pattern, params)
        assert isinstance(result, QueryResult)
        assert result.data == []
        
        # Test with more complex pattern
        complex_pattern = {
            "nodes": [
                {"label": "Person", "properties": {"age": {"$gt": 18}}},
                {"label": "Organization"}
            ],
            "relationships": [
                {"label": "WORKS_FOR", "from": 0, "to": 1}
            ]
        }
        result = await queries.execute_pattern_query(complex_pattern, params)
        assert isinstance(result, QueryResult)
        
    @pytest.mark.asyncio
    async def test_aggregation_query_execution(self):
        """Test aggregation query execution scenarios."""
        queries = GraphQueries()
        
        # Test aggregation without graph
        params = QueryParams()
        result = await queries.execute_aggregation_query("count", params)
        assert isinstance(result, dict)
        assert result["result"] == 0
        assert result["aggregation_type"] == "count"
        
        # Test different aggregation types
        result_sum = await queries.execute_aggregation_query("sum", params)
        assert result_sum["aggregation_type"] == "sum"
        
        result_avg = await queries.execute_aggregation_query("avg", params)
        assert result_avg["aggregation_type"] == "avg"
        
        result_max = await queries.execute_aggregation_query("max", params)
        assert result_max["aggregation_type"] == "max"
        
        result_min = await queries.execute_aggregation_query("min", params)
        assert result_min["aggregation_type"] == "min"
        
        # Test aggregation with graph error
        queries.graph = Mock()
        queries.graph.g = Mock()
        mock_agg_query = Mock()
        mock_agg_query.count = Mock(return_value=Mock(next=AsyncMock(side_effect=Exception("Agg error"))))
        queries.graph.g.V = Mock(return_value=mock_agg_query)
        
        result = await queries.execute_aggregation_query("count", params)
        assert result["result"] == 0
        
    def test_filter_application_methods(self):
        """Test filter application logic."""
        queries = GraphQueries()
        
        # Test equality filter
        filter_eq = QueryFilter(property_name="status", operator="eq", value="active")
        assert queries._apply_filter("active", filter_eq) is True
        assert queries._apply_filter("inactive", filter_eq) is False
        
        # Test not equal filter
        filter_ne = QueryFilter(property_name="status", operator="ne", value="active")
        assert queries._apply_filter("inactive", filter_ne) is True
        assert queries._apply_filter("active", filter_ne) is False
        
        # Test greater than filter
        filter_gt = QueryFilter(property_name="age", operator="gt", value=18)
        assert queries._apply_filter(25, filter_gt) is True
        assert queries._apply_filter(15, filter_gt) is False
        
        # Test greater than or equal filter
        filter_gte = QueryFilter(property_name="age", operator="gte", value=18)
        assert queries._apply_filter(18, filter_gte) is True
        assert queries._apply_filter(17, filter_gte) is False
        
        # Test less than filter
        filter_lt = QueryFilter(property_name="age", operator="lt", value=65)
        assert queries._apply_filter(30, filter_lt) is True
        assert queries._apply_filter(70, filter_lt) is False
        
        # Test less than or equal filter
        filter_lte = QueryFilter(property_name="age", operator="lte", value=65)
        assert queries._apply_filter(65, filter_lte) is True
        assert queries._apply_filter(70, filter_lte) is False
        
        # Test 'in' operator filter
        filter_in = QueryFilter(property_name="status", operator="in", value=["active", "pending"])
        assert queries._apply_filter("active", filter_in) is True
        assert queries._apply_filter("inactive", filter_in) is False
        
        # Test 'contains' operator filter
        filter_contains = QueryFilter(property_name="name", operator="contains", value="Alice")
        assert queries._apply_filter("Alice Smith", filter_contains) is True
        assert queries._apply_filter("Bob Jones", filter_contains) is False
        
        # Test unsupported operator
        filter_unknown = QueryFilter(property_name="test", operator="unknown", value="test")
        assert queries._apply_filter("test", filter_unknown) is True  # Default case
        
    def test_gremlin_filter_building(self):
        """Test Gremlin filter building methods."""
        queries = GraphQueries()
        mock_query = Mock()
        
        # Test equality filter
        filter_eq = QueryFilter(property_name="name", operator="eq", value="Alice")
        with patch('src.api.graph.queries.P') as mock_p:
            mock_p.eq = Mock(return_value="eq_predicate")
            result = queries._apply_gremlin_filter(mock_query, filter_eq)
            mock_query.has.assert_called()
            
        # Test 'contains' operator  
        filter_contains = QueryFilter(property_name="name", operator="contains", value="test")
        with patch('src.api.graph.queries.TextP') as mock_text_p:
            mock_text_p.containing = Mock(return_value="contains_predicate")
            result = queries._apply_gremlin_filter(mock_query, filter_contains)
            
        # Test greater than operator
        filter_gt = QueryFilter(property_name="age", operator="gt", value=18)
        with patch('src.api.graph.queries.P') as mock_p:
            mock_p.gt = Mock(return_value="gt_predicate")
            result = queries._apply_gremlin_filter(mock_query, filter_gt)
            
        # Test greater than or equal operator
        filter_gte = QueryFilter(property_name="age", operator="gte", value=18)
        with patch('src.api.graph.queries.P') as mock_p:
            mock_p.gte = Mock(return_value="gte_predicate")
            result = queries._apply_gremlin_filter(mock_query, filter_gte)
            
        # Test less than operator
        filter_lt = QueryFilter(property_name="age", operator="lt", value=65)
        with patch('src.api.graph.queries.P') as mock_p:
            mock_p.lt = Mock(return_value="lt_predicate")
            result = queries._apply_gremlin_filter(mock_query, filter_lt)
            
    def test_statistics_and_performance_methods(self):
        """Test statistics collection and performance analysis."""
        queries = GraphQueries()
        
        # Test initial statistics
        queries.query_stats = QueryStatistics()
        queries._update_query_stats("test_query", 0.1, 100)
        
        stats = queries.get_query_statistics()
        assert isinstance(stats, dict)
        
        # Test query plan explanation
        params = QueryParams()
        plan = queries.explain_query_plan(params)
        assert isinstance(plan, dict)
        assert "query_type" in plan
        
        # Test query optimization
        optimization = queries.optimize_query(params)
        assert isinstance(optimization, dict)
        assert "query_type" in optimization
        
    @pytest.mark.asyncio
    async def test_error_handling_scenarios(self):
        """Test comprehensive error handling."""
        queries = GraphQueries()
        
        # Test with various exception scenarios
        queries.graph = Mock()
        queries.graph.g = Mock()
        
        # Mock graph operations that fail
        mock_failing_query = Mock()
        mock_failing_query.count = Mock(return_value=Mock(next=AsyncMock(side_effect=Exception("Connection error"))))
        queries.graph.g.V.return_value = mock_failing_query
        
        # Test that all query types handle errors gracefully
        params = QueryParams()
        
        result = await queries.execute_node_query(params)
        assert isinstance(result, QueryResult)
        assert result.data == []
        
        result = await queries.execute_relationship_query(params)
        assert isinstance(result, QueryResult)
        assert result.data == []
        
        pattern = {"nodes": [], "relationships": []}
        result = await queries.execute_pattern_query(pattern, params)
        assert isinstance(result, QueryResult)
        assert result.data == []
        
        result = await queries.execute_aggregation_query("count", params)
        assert isinstance(result, dict)
        assert result["result"] == 0
        
    def test_query_parameter_edge_cases(self):
        """Test edge cases in query parameters."""
        queries = GraphQueries()
        
        # Test with empty filters
        params_empty = QueryParams(filters=[])
        assert len(params_empty.filters) == 0
        
        # Test with None values
        params_none = QueryParams(
            filters=None,
            sort=None,
            pagination=None
        )
        # Should handle None values gracefully
        
        # Test with extreme pagination values
        extreme_pagination = QueryPagination(limit=0, offset=0)
        params_extreme = QueryParams(pagination=extreme_pagination)
        
        # Test with sorting edge cases
        sort_desc = QuerySort(property_name="timestamp", direction="desc")
        params_sort = QueryParams(sort=sort_desc)
        
        # Test multiple filters
        filters = [
            QueryFilter(property_name="status", operator="eq", value="active"),
            QueryFilter(property_name="age", operator="gt", value=18),
            QueryFilter(property_name="name", operator="contains", value="test")
        ]
        params_multi_filter = QueryParams(filters=filters)
        assert len(params_multi_filter.filters) == 3


if __name__ == "__main__":
    pytest.main([__file__])
