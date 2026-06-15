"""Direct tests for enhanced_kg_routes analytics helper functions."""
import os, sys
from unittest.mock import AsyncMock, MagicMock
import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
import api.routes.enhanced_kg_routes as mod


def make_populator(execute_returns):
    p = MagicMock()
    p.graph_builder = MagicMock()
    p.graph_builder.g = MagicMock()
    p.graph_builder._execute_traversal = AsyncMock(side_effect=execute_returns)
    return p


class TestOverview:
    @pytest.mark.asyncio
    async def test_overview(self):
        p = make_populator([[5], [10], [{"ORG": 3}]])
        out = await mod._get_overview_analytics(p, None)
        assert out["total_vertices"] == 5
        assert out["total_edges"] == 10
        assert out["entity_type_distribution"] == {"ORG": 3}

    @pytest.mark.asyncio
    async def test_overview_with_entity_type(self):
        p = make_populator([[2], [4], [{}]])
        out = await mod._get_overview_analytics(p, "Organization")
        assert out["total_vertices"] == 2

    @pytest.mark.asyncio
    async def test_overview_error_returns_empty(self):
        p = MagicMock()
        p.graph_builder._execute_traversal = AsyncMock(side_effect=RuntimeError("boom"))
        assert await mod._get_overview_analytics(p, None) == {}


class TestCentrality:
    @pytest.mark.asyncio
    async def test_centrality(self):
        p = make_populator([[
            {"entity": {"normalized_form": ["Google"], "entity_type": ["ORG"]}, "degree": 5},
        ]])
        out = await mod._get_centrality_analytics(p, None, 10)
        assert out["top_central_entities"][0]["entity_name"] == "Google"
        assert out["metric"] == "degree_centrality"


class TestDispatcher:
    @pytest.mark.asyncio
    async def test_overview_route(self):
        p = make_populator([[1], [2], [{}]])
        out = await mod._get_graph_analytics(p, "overview", None, 10)
        assert "total_vertices" in out

    @pytest.mark.asyncio
    async def test_unknown_metric(self):
        p = make_populator([])
        assert await mod._get_graph_analytics(p, "bogus", None, 10) == {}
