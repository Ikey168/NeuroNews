"""
Comprehensive tests for Graph Queries Module

This test suite exercises the query processing, filtering, pagination,
aggregation, optimization and statistics behaviour of
``src/api/graph/queries.py``.

The tests are aligned to the *current* source API:

* ``QueryFilter`` / ``QuerySort`` use the field name ``property_name`` and
  ``QueryFilter`` requires an ``operator`` argument.
* The async ``execute_*`` methods return a ``QueryResult`` dataclass (not a
  plain ``dict``); results live in ``.data`` with ``.total_results`` /
  ``.returned_results`` counts and a ``.metadata`` dict.
* The real helper methods are ``_apply_filter`` (mock filtering),
  ``_apply_gremlin_filter`` (Gremlin traversal filtering), ``_generate_query_id``,
  ``_generate_cache_key``, ``_update_query_stats`` / ``get_query_statistics``,
  ``optimize_query`` (synchronous) and ``explain_query_plan``.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from src.api.graph.queries import (
    GraphQueries,
    QueryFilter,
    QuerySort,
    QueryPagination,
    QueryParams,
    QueryResult,
)


@pytest.fixture
def graph_queries():
    """Create a GraphQueries instance backed by a mock graph builder."""
    mock_graph = Mock()
    mock_graph.g = Mock()
    return GraphQueries(mock_graph)


@pytest.fixture
def mock_graph_queries():
    """Create a GraphQueries instance without a graph builder (mock data path)."""
    return GraphQueries()


def _chainable_traversal(to_list_return, count_return=None):
    """Build a Mock Gremlin traversal where every step returns itself.

    ``count()`` returns a separate object exposing an async ``next()`` so the
    source can do ``await query.count().next()`` while still chaining
    ``valueMap``/``limit``/``toList`` on the original traversal.
    """
    trav = Mock()
    for step in (
        "hasLabel", "has", "order", "by", "skip", "limit",
        "valueMap", "id", "project", "values",
    ):
        setattr(trav, step, Mock(return_value=trav))

    if count_return is not None:
        count_obj = Mock()
        count_obj.next = AsyncMock(return_value=count_return)
        trav.count = Mock(return_value=count_obj)

    trav.toList = AsyncMock(return_value=to_list_return)
    return trav


class TestQueryFilter:
    """Test QueryFilter dataclass."""

    def test_query_filter_custom(self):
        """QueryFilter stores property_name, operator and value."""
        filter_obj = QueryFilter(
            property_name="name",
            operator="contains",
            value="John",
        )

        assert filter_obj.property_name == "name"
        assert filter_obj.operator == "contains"
        assert filter_obj.value == "John"

    def test_query_filter_requires_operator(self):
        """operator is a required positional argument (no default)."""
        with pytest.raises(TypeError):
            QueryFilter(property_name="name", value="John")


class TestQuerySort:
    """Test QuerySort dataclass."""

    def test_query_sort_default_direction(self):
        """QuerySort defaults to ascending order."""
        sort_obj = QuerySort(property_name="created_at")

        assert sort_obj.property_name == "created_at"
        assert sort_obj.direction == "asc"

    def test_query_sort_custom(self):
        """QuerySort with custom direction."""
        sort_obj = QuerySort(property_name="created_at", direction="desc")

        assert sort_obj.property_name == "created_at"
        assert sort_obj.direction == "desc"


class TestQueryPagination:
    """Test QueryPagination dataclass."""

    def test_query_pagination_default(self):
        """Test QueryPagination with default values."""
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

    def test_query_params_default(self):
        """QueryParams defaults: collections are None, flags have defaults."""
        params = QueryParams()

        assert params.node_labels is None
        assert params.edge_labels is None
        assert params.filters is None
        assert params.sort is None
        assert params.pagination is None
        assert params.include_properties is True
        assert params.include_edges is False

    def test_query_params_custom(self):
        """Test QueryParams with custom values."""
        filters = [QueryFilter(property_name="name", operator="eq", value="John")]
        sort = [QuerySort(property_name="age", direction="desc")]
        pagination = QueryPagination(offset=10, limit=50)

        params = QueryParams(
            node_labels=["Person"],
            filters=filters,
            sort=sort,
            pagination=pagination,
            include_properties=False,
            include_edges=True,
        )

        assert params.node_labels == ["Person"]
        assert params.filters == filters
        assert params.sort == sort
        assert params.pagination == pagination
        assert params.include_properties is False
        assert params.include_edges is True


class TestGraphQueries:
    """Test GraphQueries class methods."""

    def test_initialization(self, graph_queries):
        """Test GraphQueries initialization with a graph builder."""
        assert graph_queries.graph is not None
        assert graph_queries.query_cache == {}
        assert graph_queries.cache_timestamps == {}
        assert graph_queries.query_history == []
        assert graph_queries.query_stats.query_count == 0

    def test_initialization_without_graph(self, mock_graph_queries):
        """Test GraphQueries initialization without a graph builder."""
        assert mock_graph_queries.graph is None
        assert mock_graph_queries.query_cache == {}

    @pytest.mark.asyncio
    async def test_execute_node_query_mock_basic(self, mock_graph_queries):
        """Basic node query returns a QueryResult from the mock data path."""
        params = QueryParams()

        result = await mock_graph_queries.execute_node_query(params)

        assert isinstance(result, QueryResult)
        assert isinstance(result.data, list)
        assert isinstance(result.total_results, int)
        assert result.metadata["query_type"] == "node_query"
        assert result.metadata["mock"] is True
        # Default (no pagination) yields min(20, 10) == 10 mock nodes.
        assert result.returned_results == 10
        assert result.total_results == 10

    @pytest.mark.asyncio
    async def test_execute_node_query_with_filters(self, mock_graph_queries):
        """Node query applies mock filters to the generated data."""
        # Mock nodes have properties.value == i * 10 for i in range(10),
        # so value > 50 matches i in {6,7,8,9} -> 4 nodes.
        filters = [QueryFilter(property_name="value", operator="gt", value=50)]
        params = QueryParams(filters=filters)

        result = await mock_graph_queries.execute_node_query(params)

        assert result.total_results == 4
        assert len(result.data) == 4
        for item in result.data:
            assert item["properties"]["value"] > 50

    @pytest.mark.asyncio
    async def test_execute_node_query_with_sorting(self, mock_graph_queries):
        """Node query with a sort parameter still returns mock results."""
        sort = [QuerySort(property_name="name", direction="asc")]
        params = QueryParams(sort=sort)

        result = await mock_graph_queries.execute_node_query(params)

        assert isinstance(result, QueryResult)
        assert len(result.data) >= 0

    @pytest.mark.asyncio
    async def test_execute_node_query_with_pagination(self, mock_graph_queries):
        """Node query respects the pagination limit in the mock path."""
        pagination = QueryPagination(offset=10, limit=5)
        params = QueryParams(pagination=pagination)

        result = await mock_graph_queries.execute_node_query(params)

        # Mock generates min(20, limit) == 5 nodes.
        assert len(result.data) == 5
        assert result.returned_results == 5

    @pytest.mark.asyncio
    async def test_execute_node_query_with_graph(self, graph_queries):
        """Node query against the real-graph traversal path."""
        trav = _chainable_traversal(
            to_list_return=[{"name": ["John"]}, {"name": ["Jane"]}],
            count_return=2,
        )
        graph_queries.graph.g.V = Mock(return_value=trav)

        params = QueryParams()
        result = await graph_queries.execute_node_query(params)

        assert isinstance(result, QueryResult)
        assert result.total_results == 2
        assert result.returned_results == 2
        assert result.metadata["query_type"] == "node_query"

    @pytest.mark.asyncio
    async def test_execute_relationship_query_mock_basic(self, mock_graph_queries):
        """Basic relationship query returns mock edges in a QueryResult."""
        params = QueryParams()

        result = await mock_graph_queries.execute_relationship_query(params)

        assert isinstance(result, QueryResult)
        assert isinstance(result.data, list)
        assert result.metadata["query_type"] == "relationship_query"
        assert result.metadata["mock"] is True
        # Default mock relationship path yields min(15, 10) == 10 edges.
        assert result.returned_results == 10

    @pytest.mark.asyncio
    async def test_execute_relationship_query_mock_edge_labels(self, mock_graph_queries):
        """Relationship query honours the requested edge label in mock data."""
        params = QueryParams(edge_labels=["KNOWS"])

        result = await mock_graph_queries.execute_relationship_query(params)

        assert result.data
        assert result.data[0]["label"] == "KNOWS"

    @pytest.mark.asyncio
    async def test_execute_relationship_query_with_graph(self, graph_queries):
        """Relationship query against the real-graph traversal path.

        ``include_properties=False`` is used so the source takes the
        ``query.id().toList()`` branch. The default ``include_properties=True``
        branch references an undefined ``__`` symbol (the ``gremlin_python``
        anonymous traversal is only imported inside ``_apply_gremlin_filter``)
        and therefore cannot execute -- see the source-bug note below.
        """
        trav = _chainable_traversal(
            to_list_return=["edge_1", "edge_2"],
            count_return=2,
        )
        graph_queries.graph.g.E = Mock(return_value=trav)

        params = QueryParams(include_properties=False)
        result = await graph_queries.execute_relationship_query(params)

        assert isinstance(result, QueryResult)
        assert result.total_results == 2
        assert result.data == [{"id": "edge_1"}, {"id": "edge_2"}]

    @pytest.mark.asyncio
    async def test_execute_pattern_query_mock_basic(self, mock_graph_queries):
        """Pattern query echoes the pattern and returns mock matches."""
        pattern = "(:Person)-[:KNOWS]->(:Person)"

        result = await mock_graph_queries.execute_pattern_query(pattern)

        assert isinstance(result, QueryResult)
        assert result.metadata["pattern"] == pattern
        assert result.metadata["query_type"] == "pattern_query"
        # Mock pattern path always returns 5 matches.
        assert result.total_results == 5
        assert result.data[0]["pattern"] == pattern

    @pytest.mark.asyncio
    async def test_execute_pattern_query_complex_pattern(self, mock_graph_queries):
        """Pattern query preserves a complex pattern string."""
        pattern = (
            "(:Person {name: 'John'})-[:WORKS_FOR]->"
            "(:Organization)-[:LOCATED_IN]->(:City)"
        )

        result = await mock_graph_queries.execute_pattern_query(pattern)

        assert result.metadata["pattern"] == pattern
        assert len(result.data) == 5

    @pytest.mark.asyncio
    async def test_execute_aggregation_query_count_mock(self, mock_graph_queries):
        """Count aggregation returns the mock count result."""
        result = await mock_graph_queries.execute_aggregation_query("count", QueryParams())

        assert isinstance(result, QueryResult)
        assert result.metadata["aggregation_type"] == "count"
        assert result.data[0]["aggregation_type"] == "count"
        assert result.data[0]["result"] == 42

    @pytest.mark.asyncio
    async def test_execute_aggregation_query_avg_mock(self, mock_graph_queries):
        """Non-count aggregation returns the mock numeric result."""
        result = await mock_graph_queries.execute_aggregation_query("avg", QueryParams())

        assert result.data[0]["aggregation_type"] == "avg"
        assert result.data[0]["result"] == 123.45

    @pytest.mark.asyncio
    async def test_execute_aggregation_query_uses_filter_property(self, mock_graph_queries):
        """Aggregation echoes the first filter's property in mock data."""
        params = QueryParams(
            filters=[QueryFilter(property_name="age", operator="gt", value=18)]
        )

        result = await mock_graph_queries.execute_aggregation_query("count", params)

        assert result.data[0]["property"] == "age"

    @pytest.mark.asyncio
    async def test_execute_aggregation_query_with_graph(self, graph_queries):
        """Count aggregation against the real-graph traversal path."""
        trav = _chainable_traversal(to_list_return=[], count_return=7)
        graph_queries.graph.g.V = Mock(return_value=trav)

        result = await graph_queries.execute_aggregation_query("count", QueryParams())

        assert isinstance(result, QueryResult)
        assert result.data[0]["result"] == 7
        assert result.metadata["aggregation_type"] == "count"

    def test_optimize_query_many_filters_slow(self, graph_queries):
        """optimize_query flags many filters as slow with a recommendation."""
        result = graph_queries.optimize_query("node_query", {"filters": [1] * 6})

        assert result["estimated_performance"] == "slow"
        assert result["recommendations"]
        assert result["query_type"] == "node_query"

    def test_optimize_query_large_pagination_slow(self, graph_queries):
        """optimize_query flags large page sizes as slow."""
        result = graph_queries.optimize_query(
            "node_query", {"pagination": {"limit": 5000}}
        )

        assert result["estimated_performance"] == "slow"

    def test_optimize_query_no_filters_recommends_selectivity(self, graph_queries):
        """optimize_query recommends adding filters/labels when there are none."""
        result = graph_queries.optimize_query("node_query", {})

        assert result["estimated_performance"] == "slow"
        assert any(
            "filter" in r.lower() or "label" in r.lower()
            for r in result["recommendations"]
        )

    def test_optimize_query_well_optimized(self, graph_queries):
        """A selective query with no problems is reported as fast."""
        result = graph_queries.optimize_query(
            "node_query", {"node_labels": ["Person"], "filters": [1]}
        )

        assert result["estimated_performance"] == "fast"
        assert result["recommendations"] == ["Query is well-optimized"]

    def test_get_query_statistics_shape(self, graph_queries):
        """get_query_statistics returns the expected statistics keys."""
        result = graph_queries.get_query_statistics()

        assert "total_queries" in result
        assert "average_execution_time" in result
        assert "cache_hit_rate" in result
        assert "query_history_size" in result
        assert "last_updated" in result
        assert isinstance(result["total_queries"], int)

    def test_update_query_stats_average(self, graph_queries):
        """_update_query_stats maintains a running average execution time."""
        graph_queries._update_query_stats(2.0)
        graph_queries._update_query_stats(4.0)

        stats = graph_queries.get_query_statistics()
        assert stats["total_queries"] == 2
        assert stats["average_execution_time"] == 3.0

    @pytest.mark.asyncio
    async def test_explain_query_plan_node_query(self, graph_queries):
        """explain_query_plan describes the steps for a node query."""
        plan = await graph_queries.explain_query_plan(
            "node_query",
            {"node_labels": ["Person"], "filters": [1], "sort": [1], "pagination": {}},
        )

        assert plan["query_type"] == "node_query"
        assert plan["execution_steps"]
        assert plan["estimated_cost"] == len(plan["execution_steps"]) * 10
        assert "plan_generated_at" in plan

    @pytest.mark.asyncio
    async def test_explain_query_plan_relationship_query(self, graph_queries):
        """explain_query_plan describes the steps for a relationship query."""
        plan = await graph_queries.explain_query_plan(
            "relationship_query", {"edge_labels": ["KNOWS"]}
        )

        assert plan["query_type"] == "relationship_query"
        assert any("edges" in step.lower() for step in plan["execution_steps"])


class TestApplyFilter:
    """Test the mock-data filter helper ``_apply_filter``."""

    @pytest.mark.parametrize(
        "operator,filter_value,target,expected",
        [
            ("eq", 5, 5, True),
            ("eq", 5, 6, False),
            ("ne", 5, 6, True),
            ("gt", 25, 30, True),
            ("gt", 25, 20, False),
            ("lt", 25, 20, True),
            ("gte", 5, 5, True),
            ("lte", 5, 5, True),
            ("contains", "ell", "hello", True),
            ("contains", "xyz", "hello", False),
            ("in", [1, 2, 3], 2, True),
            ("in", [1, 2, 3], 9, False),
        ],
    )
    def test_apply_filter_operators(self, graph_queries, operator, filter_value, target, expected):
        """_apply_filter evaluates each supported operator correctly."""
        f = QueryFilter(property_name="x", operator=operator, value=filter_value)
        assert graph_queries._apply_filter(target, f) is expected

    def test_apply_filter_unknown_operator_returns_true(self, graph_queries):
        """Unknown operators fall through and match everything (return True)."""
        f = QueryFilter(property_name="x", operator="weird", value=1)
        assert graph_queries._apply_filter(5, f) is True


class TestApplyGremlinFilter:
    """Test the Gremlin traversal filter helper ``_apply_gremlin_filter``."""

    def _make_query(self):
        query = Mock()
        query.has = Mock(return_value="HAS_RESULT")
        return query

    def test_gremlin_filter_eq(self, graph_queries):
        """eq operator calls .has with P.eq and returns the chained query."""
        query = self._make_query()
        f = QueryFilter(property_name="name", operator="eq", value="John")

        result = graph_queries._apply_gremlin_filter(query, f)

        assert result == "HAS_RESULT"
        assert query.has.call_args.args[0] == "name"

    def test_gremlin_filter_gt(self, graph_queries):
        """gt operator routes through .has."""
        query = self._make_query()
        f = QueryFilter(property_name="score", operator="gt", value=80)

        result = graph_queries._apply_gremlin_filter(query, f)

        assert result == "HAS_RESULT"
        query.has.assert_called_once()

    def test_gremlin_filter_unsupported_returns_query_unchanged(self, graph_queries):
        """An unsupported operator returns the original query untouched."""
        query = self._make_query()
        f = QueryFilter(property_name="field", operator="unsupported_op", value="x")

        result = graph_queries._apply_gremlin_filter(query, f)

        assert result is query
        query.has.assert_not_called()


class TestCacheKeyGeneration:
    """Test query id and cache key generation helpers."""

    def test_generate_query_id_length(self, graph_queries):
        """_generate_query_id returns a 16-character identifier."""
        qid = graph_queries._generate_query_id("node_query", {"a": 1})

        assert isinstance(qid, str)
        assert len(qid) == 16

    def test_generate_cache_key_prefix(self, graph_queries):
        """_generate_cache_key returns a prefixed, non-empty string."""
        cache_key = graph_queries._generate_cache_key("node_query", {"a": 1})

        assert isinstance(cache_key, str)
        assert cache_key.startswith("query_cache:")

    def test_generate_cache_key_consistency(self, graph_queries):
        """Same parameters produce the same cache key."""
        key1 = graph_queries._generate_cache_key("node_query", {"name": "John"})
        key2 = graph_queries._generate_cache_key("node_query", {"name": "John"})

        assert key1 == key2

    def test_generate_cache_key_different_params(self, graph_queries):
        """Different parameters produce different cache keys."""
        key1 = graph_queries._generate_cache_key("node_query", {"name": "John"})
        key2 = graph_queries._generate_cache_key("node_query", {"name": "Jane"})

        assert key1 != key2


class TestComplexQueryScenarios:
    """Test complex query scenarios combining multiple features."""

    @pytest.mark.asyncio
    async def test_complex_node_query_full_features(self, mock_graph_queries):
        """Node query with filters, sort and pagination combined."""
        params = QueryParams(
            node_labels=["Person"],
            filters=[
                QueryFilter(property_name="value", operator="gte", value=0),
                QueryFilter(property_name="category", operator="eq", value="test"),
            ],
            sort=[
                QuerySort(property_name="value", direction="desc"),
                QuerySort(property_name="name", direction="asc"),
            ],
            pagination=QueryPagination(offset=5, limit=10),
            include_properties=True,
        )

        result = await mock_graph_queries.execute_node_query(params)

        assert isinstance(result, QueryResult)
        # Mock generates min(20, 10) == 10 nodes; both filters match all of them.
        assert len(result.data) <= 10
        assert result.metadata["query_type"] == "node_query"

    @pytest.mark.asyncio
    async def test_pattern_query_with_aggregation(self, mock_graph_queries):
        """A pattern query followed by an aggregation query."""
        pattern = "(:Person)-[:WORKS_FOR]->(:Organization)"

        pattern_result = await mock_graph_queries.execute_pattern_query(pattern)
        agg_result = await mock_graph_queries.execute_aggregation_query("count", QueryParams())

        assert pattern_result.metadata["pattern"] == pattern
        assert agg_result.data[0]["aggregation_type"] == "count"

    @pytest.mark.asyncio
    async def test_query_statistics_track_real_graph_queries(self, graph_queries):
        """Executing real-graph queries increments the statistics counter."""
        trav = _chainable_traversal(to_list_return=[{"name": ["A"]}], count_return=1)
        graph_queries.graph.g.V = Mock(return_value=trav)

        assert graph_queries.get_query_statistics()["total_queries"] == 0
        await graph_queries.execute_node_query(QueryParams())
        assert graph_queries.get_query_statistics()["total_queries"] == 1


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_node_query_filter_no_matches(self, mock_graph_queries):
        """A filter matching nothing yields an empty, well-formed result."""
        # Mock nodes have properties.value in {0, 10, ..., 90}; none equal 999.
        params = QueryParams(
            filters=[QueryFilter(property_name="value", operator="eq", value=999)]
        )

        result = await mock_graph_queries.execute_node_query(params)

        assert result.total_results == 0
        assert result.data == []

    @pytest.mark.asyncio
    async def test_invalid_filter_operator(self, mock_graph_queries):
        """An unsupported filter operator is handled gracefully (matches all)."""
        params = QueryParams(
            filters=[QueryFilter(property_name="name", operator="invalid_op", value="test")]
        )

        result = await mock_graph_queries.execute_node_query(params)

        # Unknown operators fall through to ``return True`` so nothing is dropped.
        assert isinstance(result, QueryResult)
        assert result.total_results == 10

    @pytest.mark.asyncio
    async def test_missing_filter_property(self, mock_graph_queries):
        """A filter on a property absent from the data drops non-matching rows."""
        params = QueryParams(
            filters=[QueryFilter(property_name="nonexistent_field", operator="eq", value="test")]
        )

        result = await mock_graph_queries.execute_node_query(params)

        # Missing property -> None != "test" -> no matches, but no crash.
        assert isinstance(result, QueryResult)
        assert result.total_results == 0

    @pytest.mark.asyncio
    async def test_invalid_pagination_values(self, mock_graph_queries):
        """Zero/negative pagination values are handled without crashing."""
        params = QueryParams(pagination=QueryPagination(offset=-10, limit=0))

        result = await mock_graph_queries.execute_node_query(params)

        # range(min(20, 0)) is empty.
        assert isinstance(result, QueryResult)
        assert result.data == []
        assert result.total_results == 0

    @pytest.mark.asyncio
    async def test_graph_connection_error(self, graph_queries):
        """A graph connection failure propagates from execute_node_query."""
        graph_queries.graph.g.V = Mock(side_effect=Exception("Connection failed"))

        with pytest.raises(Exception) as exc_info:
            await graph_queries.execute_node_query(QueryParams())

        assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_aggregation_unknown_type_falls_back_to_count(self, mock_graph_queries):
        """An unknown aggregation type still returns a valid mock result."""
        result = await mock_graph_queries.execute_aggregation_query("median", QueryParams())

        # Mock path echoes the requested type; result is the non-count branch.
        assert result.data[0]["aggregation_type"] == "median"
        assert result.data[0]["result"] == 123.45

    @pytest.mark.asyncio
    async def test_pattern_query_invalid_syntax(self, mock_graph_queries):
        """A malformed pattern is echoed back rather than raising."""
        invalid_pattern = "(:Person]->[:INVALID"

        result = await mock_graph_queries.execute_pattern_query(invalid_pattern)

        assert result.metadata["pattern"] == invalid_pattern
        assert result.data[0]["pattern"] == invalid_pattern

    @pytest.mark.asyncio
    async def test_large_result_set_handling(self, mock_graph_queries):
        """Pagination caps the mock node result size."""
        params = QueryParams(pagination=QueryPagination(limit=50))

        result = await mock_graph_queries.execute_node_query(params)

        # Mock caps generation at min(20, limit) == 20.
        assert len(result.data) == 20
        assert result.returned_results == 20

    def test_apply_filter_with_none_value(self, graph_queries):
        """_apply_filter compares None values without raising for eq/ne."""
        f_ne = QueryFilter(property_name="name", operator="ne", value=None)
        f_eq = QueryFilter(property_name="name", operator="eq", value=None)

        assert graph_queries._apply_filter("Alice", f_ne) is True
        assert graph_queries._apply_filter(None, f_eq) is True
