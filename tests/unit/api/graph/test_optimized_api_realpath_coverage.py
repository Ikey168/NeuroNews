"""Coverage tests for src/api/graph/optimized_api.py remaining lines.

Instantiates OptimizedGraphAPI directly with a mocked graph_builder whose
``_execute_traversal`` is an AsyncMock. Targets the lines the existing
optimized_api suites leave uncovered:

* 194-195   memory-cache LRU eviction when the cache is full
* 393-395   per-result formatting error in get_related_entities_optimized
* 405-408   outer error -> HTTPException 500 in get_related_entities_optimized
* 520-522   per-event formatting error in get_event_timeline_optimized
* 535-538   outer error -> HTTPException 500 in get_event_timeline_optimized
* 642-644   per-result formatting error in search_entities_optimized
* 657-660   outer error -> HTTPException 500 in search_entities_optimized
* 685       word-boundary branch in _calculate_relevance

KNOWN SOURCE BUG (not fixed, only worked around): the timeline/search query
builders call ``P.containing(...)`` but the installed gremlin_python exposes
``containing`` on ``TextP`` not ``P``; the real path therefore raises
AttributeError. For the formatting-line tests we patch the module-level ``P``
and ``__`` with mocks so the query build succeeds and results flow into the
formatting loops. The 500-path tests instead let a mocked failure propagate.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import src.api.graph.optimized_api as mod
from src.api.graph.optimized_api import (
    CacheConfig,
    OptimizedGraphAPI,
    QueryOptimizationConfig,
)


def _make_api(cache_config=None, opt_config=None):
    builder = MagicMock()
    builder.g = MagicMock()
    builder._execute_traversal = AsyncMock(return_value=[])
    api = OptimizedGraphAPI(
        graph_builder=builder,
        cache_config=cache_config or CacheConfig(),
        optimization_config=opt_config or QueryOptimizationConfig(),
    )
    # Ensure no redis path so memory cache branches run.
    api.redis_client = None
    return api


@pytest.fixture(autouse=True)
def patch_gremlin(monkeypatch):
    """Patch P / __ so query building never trips the P.containing bug."""
    fake_P = MagicMock()
    fake_P.eq = MagicMock(return_value="P.eq")
    fake_P.gte = MagicMock(return_value="P.gte")
    fake_P.lte = MagicMock(return_value="P.lte")
    fake_P.containing = MagicMock(return_value="P.containing")
    monkeypatch.setattr(mod, "P", fake_P)

    fake_anon = MagicMock()
    fake_anon.has = MagicMock(return_value="anon.has")
    monkeypatch.setattr(mod, "__", fake_anon)
    return fake_P


# --- 194-195: memory cache LRU eviction ---------------------------------

@pytest.mark.asyncio
async def test_store_in_cache_evicts_oldest_when_full():
    from datetime import datetime, timedelta

    api = _make_api(cache_config=CacheConfig(max_cache_size=10))
    # Fill the cache to capacity with timestamped entries.
    base = datetime(2020, 1, 1)
    for i in range(10):
        key = "graph_api:{0}".format(i)
        api.memory_cache[key] = {"v": i}
        api.cache_timestamps[key] = base + timedelta(seconds=i)

    assert len(api.memory_cache) == 10
    stored = await api._store_in_cache("graph_api:new", {"v": "new"})
    assert stored is True
    # The oldest 10% (1 entry: key "graph_api:0") was evicted.
    assert "graph_api:0" not in api.memory_cache
    assert "graph_api:new" in api.memory_cache


# --- 393-395 / 405-408: related entities formatting + outer error -------

@pytest.mark.asyncio
async def test_related_entities_result_formatting_error_skipped(monkeypatch):
    api = _make_api()
    # One good result, one that raises during _extract_entity_name.
    good = {"name": ["Acme"]}
    bad = {"name": ["Boom"]}

    def extract(r):
        if r is bad:
            raise RuntimeError("format boom")
        return "Acme"

    monkeypatch.setattr(api, "_extract_entity_name", extract)
    api._execute_optimized_query = AsyncMock(return_value=[good, bad])

    result = await api.get_related_entities_optimized("Acme", use_cache=False)
    # Bad result skipped via the per-result try/except -> only one entity.
    assert result["total_related"] == 2
    assert len(result["related_entities"]) == 1
    assert result["related_entities"][0]["name"] == "Acme"


@pytest.mark.asyncio
async def test_related_entities_outer_error_500():
    api = _make_api()
    # _execute_optimized_query raises a non-HTTPException -> outer handler -> 500
    api._execute_optimized_query = AsyncMock(side_effect=RuntimeError("query failed"))
    with pytest.raises(HTTPException) as exc:
        await api.get_related_entities_optimized("X", use_cache=False)
    assert exc.value.status_code == 500
    assert "Failed to retrieve related entities" in exc.value.detail
    assert api.metrics["errors_total"] >= 1


@pytest.mark.asyncio
async def test_related_entities_httpexception_propagates():
    api = _make_api()
    api._execute_optimized_query = AsyncMock(
        side_effect=HTTPException(status_code=408, detail="timeout")
    )
    with pytest.raises(HTTPException) as exc:
        await api.get_related_entities_optimized("X", use_cache=False)
    assert exc.value.status_code == 408


# --- 520-522 / 535-538: timeline formatting + outer error ---------------

@pytest.mark.asyncio
async def test_event_timeline_formatting_error_skipped(monkeypatch):
    api = _make_api()

    # A result whose .get raises to trip the per-event try/except (520-522),
    # alongside a good event that formats fine.
    class _BadRow:
        def get(self, *a, **k):
            raise RuntimeError("row boom")

    good_row = {
        "event_name": "Launch",
        "date": "2021-01-01",
        "location": "NYC",
        "description": "desc",
    }
    api._execute_optimized_query = AsyncMock(return_value=[good_row, _BadRow()])

    timeline = await api.get_event_timeline_optimized("topic", use_cache=False)
    assert timeline["total_events"] == 2
    assert len(timeline["events"]) == 1
    assert timeline["events"][0]["name"] == "Launch"


@pytest.mark.asyncio
async def test_event_timeline_outer_error_500():
    api = _make_api()
    api._execute_optimized_query = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(HTTPException) as exc:
        await api.get_event_timeline_optimized("topic", use_cache=False)
    assert exc.value.status_code == 500
    assert "Failed to retrieve event timeline" in exc.value.detail


@pytest.mark.asyncio
async def test_event_timeline_with_dates_and_cache():
    from datetime import datetime

    api = _make_api()
    api._execute_optimized_query = AsyncMock(return_value=[])
    timeline = await api.get_event_timeline_optimized(
        "topic",
        start_date=datetime(2021, 1, 1),
        end_date=datetime(2021, 12, 31),
        limit=10,
        use_cache=True,
    )
    assert timeline["topic"] == "topic"
    assert timeline["start_date"] == "2021-01-01T00:00:00"
    # Result was cached.
    assert len(api.memory_cache) == 1


# --- 642-644 / 657-660: search formatting + outer error -----------------

@pytest.mark.asyncio
async def test_search_entities_result_formatting_error_skipped(monkeypatch):
    api = _make_api()
    good = {"name": ["Acme"]}
    bad = {"name": ["Boom"]}

    def extract(r):
        if r is bad:
            raise RuntimeError("format boom")
        return "Acme"

    monkeypatch.setattr(api, "_extract_entity_name", extract)
    api._execute_optimized_query = AsyncMock(return_value=[good, bad])

    result = await api.search_entities_optimized("acme", use_cache=False)
    assert result["total_results"] == 2
    assert len(result["entities"]) == 1
    assert result["entities"][0]["name"] == "Acme"


@pytest.mark.asyncio
async def test_search_entities_outer_error_500():
    api = _make_api()
    api._execute_optimized_query = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(HTTPException) as exc:
        await api.search_entities_optimized("acme", use_cache=False)
    assert exc.value.status_code == 500
    assert "Entity search failed" in exc.value.detail


@pytest.mark.asyncio
async def test_search_entities_too_short_400():
    api = _make_api()
    with pytest.raises(HTTPException) as exc:
        await api.search_entities_optimized("a", use_cache=False)
    assert exc.value.status_code == 400


# --- 685: _calculate_relevance word-boundary branch ---------------------

def test_calculate_relevance_reachable_branches():
    # NOTE: the 0.4 "word boundary" return (source line 685) is dead code:
    # any word that startswith(term) also makes ``term in name`` true, so the
    # 0.6 "contains" branch always returns first. We therefore assert only the
    # reachable branches with real inputs.
    api = _make_api()
    # exact match
    assert api._calculate_relevance("acme", "acme") == 1.0
    # starts-with (whole name begins with the term but is longer)
    assert api._calculate_relevance("acme corp", "acme") == 0.8
    # contains (term appears mid-string)
    assert api._calculate_relevance("the acme", "acme") == 0.6
    # default low relevance (term absent entirely)
    assert api._calculate_relevance("xyz", "beta") == 0.1
