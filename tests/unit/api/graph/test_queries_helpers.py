"""Tests for pure helper methods in src/api/graph/queries.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from api.graph.queries import GraphQueries, QueryFilter  # noqa: E402


@pytest.fixture
def gq():
    return GraphQueries()


class TestQueryIds:
    def test_query_id_deterministic_length(self, gq):
        qid = gq._generate_query_id("node", {"a": 1})
        assert len(qid) == 16

    def test_cache_key_prefix(self, gq):
        key = gq._generate_cache_key("node", {"a": 1})
        assert key.startswith("query_cache:")

    def test_cache_key_stable(self, gq):
        assert gq._generate_cache_key("node", {"a": 1}) == gq._generate_cache_key(
            "node", {"a": 1}
        )


class TestApplyFilter:
    @pytest.mark.parametrize("op,value,target,expected", [
        ("eq", 5, 5, True),
        ("ne", 5, 6, True),
        ("gt", 3, 5, True),
        ("lt", 9, 5, True),
        ("gte", 5, 5, True),
        ("lte", 5, 5, True),
        ("contains", "ell", "hello", True),
        ("in", [1, 2, 3], 2, True),
        ("eq", 5, 6, False),
    ])
    def test_operators(self, gq, op, value, target, expected):
        f = QueryFilter(property_name="x", operator=op, value=value)
        assert gq._apply_filter(target, f) is expected

    def test_unknown_operator_returns_true(self, gq):
        f = QueryFilter(property_name="x", operator="weird", value=1)
        assert gq._apply_filter(5, f) is True


class TestStats:
    def test_update_query_stats(self, gq):
        gq._update_query_stats(2.0)
        gq._update_query_stats(4.0)
        stats = gq.get_query_statistics()
        assert stats["total_queries"] == 2
        assert stats["average_execution_time"] == 3.0

    def test_get_statistics_shape(self, gq):
        stats = gq.get_query_statistics()
        assert "cache_hit_rate" in stats
        assert "last_updated" in stats


class TestOptimize:
    def test_many_filters_slow(self, gq):
        params = {"filters": [{"x": i} for i in range(6)]}
        result = gq.optimize_query("node", params)
        assert result["estimated_performance"] == "slow"
        assert result["recommendations"]

    def test_large_pagination_slow(self, gq):
        result = gq.optimize_query("node", {"pagination": {"limit": 5000}})
        assert result["estimated_performance"] == "slow"

    def test_no_filters_recommends_selectivity(self, gq):
        result = gq.optimize_query("node", {})
        assert any("filter" in r.lower() or "label" in r.lower()
                   for r in result["recommendations"])
