"""Real-graph-path coverage tests for src/api/graph/queries.py.

Calls GraphQueries directly with a mocked graph_builder whose ``.g`` returns a
chainable traversal. Exercises the branches the existing tests leave
uncovered: node/relationship sort + pagination + id-only paths, the
pattern-query real branches, the aggregation sum/avg/min/max branches, the
remaining _apply_gremlin_filter operators, and the optimize/explain edge cases.

NOTE (known source bug, not fixed): the relationship_query real path with
include_properties=True references a bare ``__`` (gremlin anonymous traversal)
that is never imported in queries.py -> NameError. We therefore only exercise
the include_properties=False (id) branch of relationship_query on the real path.
"""
import pytest

from src.api.graph.queries import (
    GraphQueries,
    QueryFilter,
    QuerySort,
    QueryPagination,
    QueryParams,
)


class _Traversal:
    """Chainable gremlin-like traversal.

    Every step method returns ``self`` so a chain like
    ``g.V().hasLabel(...).order().by(...).skip(...).limit(...).valueMap(True)``
    works. ``count()`` returns an object whose ``next()`` is awaitable, and
    ``toList``/``next`` are awaitable terminals.
    """

    def __init__(self, to_list=None, count_value=0, next_value=None):
        self._to_list = to_list if to_list is not None else []
        self._count_value = count_value
        self._next_value = next_value

    # chain steps
    def hasLabel(self, *a, **k):
        return self

    def has(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def by(self, *a, **k):
        return self

    def skip(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def valueMap(self, *a, **k):
        return self

    def id(self, *a, **k):
        return self

    def values(self, *a, **k):
        return self

    def both(self, *a, **k):
        return self

    def outE(self, *a, **k):
        return self

    def inV(self, *a, **k):
        return self

    def path(self, *a, **k):
        return self

    # count().next() branch
    def count(self):
        return _AwaitableNext(self._count_value)

    def sum(self):
        return _AwaitableNext(self._next_value)

    def mean(self):
        return _AwaitableNext(self._next_value)

    def min(self):
        return _AwaitableNext(self._next_value)

    def max(self):
        return _AwaitableNext(self._next_value)

    # terminals
    async def toList(self):
        return self._to_list

    async def next(self):
        return self._next_value


class _AwaitableNext:
    def __init__(self, value):
        self._value = value

    async def next(self):
        return self._value


class _FakePath:
    def __init__(self, objects):
        self.objects = objects


def _make_queries(trav):
    class _G:
        pass

    g = _G()
    g.V = lambda *a, **k: trav
    g.E = lambda *a, **k: trav
    builder = _G()
    builder.g = g
    return GraphQueries(graph_builder=builder)


# --- execute_node_query real path (sort + pagination + id-only) ---------

@pytest.mark.asyncio
async def test_node_query_real_sort_pagination_valuemap():
    trav = _Traversal(to_list=[{"name": ["A"], "id": 1}], count_value=3)
    q = _make_queries(trav)
    params = QueryParams(
        node_labels=["Person"],
        filters=None,
        sort=[QuerySort("name", "desc"), QuerySort("age", "asc")],
        pagination=QueryPagination(offset=5, limit=2),
        include_properties=True,
    )
    result = await q.execute_node_query(params)
    assert result.total_results == 3
    assert result.returned_results == 1
    assert result.has_more is True  # 3 > 1
    assert result.data == [{"name": ["A"], "id": 1}]
    assert result.metadata["query_type"] == "node_query"


@pytest.mark.asyncio
async def test_node_query_real_id_only_no_pagination():
    trav = _Traversal(to_list=["n1", "n2"], count_value=2)
    q = _make_queries(trav)
    params = QueryParams(
        node_labels=None,
        pagination=None,  # -> default limit(100) branch
        include_properties=False,  # -> id().toList() branch + {'id': result} format
    )
    result = await q.execute_node_query(params)
    assert result.returned_results == 2
    assert result.data == [{"id": "n1"}, {"id": "n2"}]
    assert result.has_more is False  # 2 > 2 is False


# --- execute_relationship_query real path (id-only avoids __ bug) -------

@pytest.mark.asyncio
async def test_relationship_query_real_id_path_sort_pagination():
    trav = _Traversal(to_list=["e1", "e2"], count_value=5)
    q = _make_queries(trav)
    params = QueryParams(
        edge_labels=["KNOWS"],
        filters=[QueryFilter("weight", "gt", 0.5)],
        sort=[QuerySort("weight", "desc"), QuerySort("ts", "asc")],
        pagination=QueryPagination(offset=1, limit=2),
        include_properties=False,  # avoids the bare __ NameError branch
    )
    result = await q.execute_relationship_query(params)
    assert result.total_results == 5
    assert result.data == [{"id": "e1"}, {"id": "e2"}]
    assert result.has_more is True


# --- execute_pattern_query real path ------------------------------------

@pytest.mark.asyncio
async def test_pattern_query_real_person_knows_branch():
    paths = [_FakePath(objects=["p1", "p2"]), _FakePath(objects=["p3", "p4"])]
    trav = _Traversal(to_list=paths)
    q = _make_queries(trav)
    result = await q.execute_pattern_query("(p:Person)-[:KNOWS]->(q:Person)")
    assert result.total_results == 2
    assert result.data[0]["match_id"] == "match_0"
    assert result.data[0]["path"] == ["p1", "p2"]
    assert result.metadata["pattern"].startswith("(p:Person)")


@pytest.mark.asyncio
async def test_pattern_query_real_generic_branch_no_objects():
    # generic branch (no Person/KNOWS) + a path object without .objects attr
    trav = _Traversal(to_list=["rawpath1"])
    q = _make_queries(trav)
    result = await q.execute_pattern_query("(a)-->(b)")
    assert result.total_results == 1
    assert result.data[0]["path"] == ["rawpath1"]


# --- execute_aggregation_query real path (sum/avg/min/max/count) --------

@pytest.mark.asyncio
async def test_aggregation_count_real_no_filters():
    trav = _Traversal(count_value=42)
    q = _make_queries(trav)
    params = QueryParams(node_labels=["Person"], filters=None)
    result = await q.execute_aggregation_query("count", params)
    assert result.data[0]["result"] == 42
    assert result.data[0]["property"] is None


@pytest.mark.asyncio
async def test_aggregation_sum_real():
    trav = _Traversal(next_value=100.0)
    q = _make_queries(trav)
    params = QueryParams(filters=[QueryFilter("value", "gt", 0)])
    result = await q.execute_aggregation_query("sum", params)
    assert result.data[0]["result"] == 100.0
    assert result.data[0]["property"] == "value"


@pytest.mark.asyncio
async def test_aggregation_avg_min_max_real():
    for agg, val in [("avg", 12.5), ("min", 1), ("max", 99)]:
        trav = _Traversal(next_value=val)
        q = _make_queries(trav)
        params = QueryParams(filters=[QueryFilter("value", "gt", 0)])
        result = await q.execute_aggregation_query(agg, params)
        assert result.data[0]["result"] == val
        assert result.metadata["aggregation_type"] == agg


@pytest.mark.asyncio
async def test_aggregation_unknown_type_falls_back_to_count():
    trav = _Traversal(count_value=7)
    q = _make_queries(trav)
    params = QueryParams(filters=None)  # unknown agg + no filters -> else count()
    result = await q.execute_aggregation_query("median", params)
    assert result.data[0]["result"] == 7


# --- _apply_gremlin_filter remaining operators --------------------------

@pytest.mark.asyncio
async def test_apply_gremlin_filter_remaining_operators():
    # NOTE: the 'contains' operator maps to P.containing which does not exist
    # on the installed gremlin_python P (it lives on TextP) -> AttributeError.
    # That is a latent source bug (same family as the optimized_api one), so we
    # exercise every other remaining operator instead.
    q = _make_queries(_Traversal())

    class _Q:
        def __init__(self):
            self.calls = []

        def has(self, prop, predicate):
            self.calls.append((prop, predicate))
            return ("has", prop, predicate)

    for op in ["ne", "gte", "lte", "in"]:
        query = _Q()
        f = QueryFilter("prop", op, "val" if op != "in" else ["a", "b"])
        out = q._apply_gremlin_filter(query, f)
        assert out[0] == "has"
        assert query.calls[0][0] == "prop"


@pytest.mark.asyncio
async def test_apply_gremlin_filter_contains_is_source_buggy():
    # Documents the known source bug: contains -> P.containing raises.
    q = _make_queries(_Traversal())

    class _Q:
        def has(self, prop, predicate):
            return ("has", prop, predicate)

    f = QueryFilter("prop", "contains", "val")
    with pytest.raises(AttributeError):
        q._apply_gremlin_filter(_Q(), f)


# --- optimize_query large-pagination + explain_query_plan sort ----------

def test_optimize_query_large_limit_slow():
    q = _make_queries(_Traversal())
    rec = q.optimize_query(
        "node_query",
        {
            "pagination": {"limit": 5000},
            "node_labels": ["Person"],
            "sort": [{"property_name": "name"}],  # hits the index-hint branch
        },
    )
    assert rec["estimated_performance"] == "slow"
    assert any("smaller page sizes" in r for r in rec["recommendations"])
    assert any("indexes exist" in r for r in rec["recommendations"])


def test_optimize_query_well_optimized_fast():
    # A selective query with no problems -> no recommendations -> 'fast' branch.
    q = _make_queries(_Traversal())
    rec = q.optimize_query(
        "node_query",
        {
            "node_labels": ["Person"],
            "filters": [{"a": 1}, {"b": 2}],  # <=5 filters, present
            "pagination": {"limit": 50},  # small page
        },
    )
    assert rec["estimated_performance"] == "fast"
    assert rec["recommendations"] == ["Query is well-optimized"]


@pytest.mark.asyncio
async def test_explain_query_plan_node_query_with_sort_and_pagination():
    q = _make_queries(_Traversal())
    plan = await q.explain_query_plan(
        "node_query",
        {
            "node_labels": ["Person"],
            "filters": [{"a": 1}],
            "sort": [{"property_name": "name"}],
            "pagination": {"limit": 10},
        },
    )
    steps = " ".join(plan["execution_steps"])
    assert "Sort results" in steps
    assert "Apply pagination" in steps
    assert plan["estimated_cost"] == len(plan["execution_steps"]) * 10
