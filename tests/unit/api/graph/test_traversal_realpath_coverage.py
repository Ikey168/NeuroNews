"""Real-graph-path coverage tests for src/api/graph/traversal.py.

Calls GraphTraversal directly with a mocked graph_builder whose ``.g`` returns
chainable traversals. Exercises the branches the existing traversal tests leave
uncovered: BFS/DFS label + property neighbour filters and their outer
exception handlers, the shortest-path depth/visited guards and outer error,
find_all_paths depth guard + outer error, get_node_neighbors in/hasLabel
branches, the statistics average-computation branch, and the real
analyze_graph_connectivity path.
"""
import pytest

from src.api.graph.traversal import GraphTraversal, TraversalConfig


class _Terminal:
    """A gremlin step object whose ``toList``/``next`` are awaitable."""

    def __init__(self, to_list=None, next_value=None, raise_on_list=None):
        self._to_list = to_list if to_list is not None else []
        self._next_value = next_value
        self._raise = raise_on_list

    def id(self):
        return self

    def valueMap(self, *a, **k):
        return self

    def hasLabel(self, *a, **k):
        return self

    def has(self, *a, **k):
        return self

    def both(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def out(self, *a, **k):
        return self

    def bothE(self, *a, **k):
        return self

    def count(self):
        return self

    async def toList(self):
        if self._raise:
            raise self._raise
        return self._to_list

    async def next(self):
        return self._next_value


def _builder_with_g(g):
    class _B:
        pass

    b = _B()
    b.g = g
    return b


# --- BFS real path: label + property filters ----------------------------

@pytest.mark.asyncio
async def test_bfs_real_with_label_and_property_filters():
    # valueMap(True).next() -> node props ; both()... .id().toList() -> neighbors
    class _G:
        def V(self, *a, **k):
            return _Terminal(to_list=["node_b"], next_value={"name": ["A"]})

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    config = TraversalConfig(
        max_depth=2,
        max_results=10,
        include_properties=True,
        filter_by_labels=["Person"],
        filter_by_properties={"active": True},
    )
    result = await trav.breadth_first_search("node_a", config)
    assert result.start_node == "node_a"
    assert "node_a" in result.visited_nodes
    assert trav.traversal_stats["total_traversals"] == 1
    # A neighbor path was created
    assert any(p.end_node == "node_b" for p in result.paths)


@pytest.mark.asyncio
async def test_bfs_real_outer_exception_reraises():
    class _G:
        def V(self, *a, **k):
            raise RuntimeError("graph exploded")

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    # include_properties False so first failure happens at neighbours query,
    # but the whole while-body is wrapped; a raise from V() inside the loop is
    # caught by the inner handler. To hit the OUTER handler, make the loop setup
    # raise before the try: use a builder whose ``.g`` access raises.
    class _BadBuilder:
        @property
        def g(self):
            raise RuntimeError("no g")

    trav.graph = _BadBuilder()
    with pytest.raises(RuntimeError):
        await trav.breadth_first_search("x", TraversalConfig(include_properties=False))


# --- DFS real path: label + property filters + outer exception ----------

@pytest.mark.asyncio
async def test_dfs_real_with_filters():
    class _G:
        def V(self, *a, **k):
            return _Terminal(to_list=["n2"], next_value={"name": ["A"]})

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    config = TraversalConfig(
        max_depth=2,
        include_properties=True,
        filter_by_labels=["Person"],
        filter_by_properties={"active": True},
    )
    result = await trav.depth_first_search("n1", config)
    assert "n1" in result.visited_nodes
    assert any(p.end_node == "n2" for p in result.paths)


@pytest.mark.asyncio
async def test_dfs_real_outer_exception_reraises():
    class _BadBuilder:
        @property
        def g(self):
            raise RuntimeError("no g")

    trav = GraphTraversal(graph_builder=object())
    trav.graph = _BadBuilder()
    with pytest.raises(RuntimeError):
        await trav.depth_first_search("x", TraversalConfig(include_properties=False))


# --- find_shortest_path real path ---------------------------------------

@pytest.mark.asyncio
async def test_shortest_path_real_found_via_neighbor():
    # start -> mid -> end. First expansion yields "end" as neighbor.
    class _G:
        def V(self, node, *a, **k):
            return _Terminal(to_list=["end"])

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    result = await trav.find_shortest_path("start", "end", max_depth=5)
    assert result is not None
    assert result.path == ["start", "end"]
    assert result.properties["algorithm"] == "bfs_shortest_path"


@pytest.mark.asyncio
async def test_shortest_path_real_depth_exceeded_returns_none():
    # neighbors keep returning new nodes but max_depth=0 stops expansion.
    class _G:
        def V(self, node, *a, **k):
            return _Terminal(to_list=["other"])

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    result = await trav.find_shortest_path("start", "unreachable", max_depth=0)
    assert result is None


@pytest.mark.asyncio
async def test_shortest_path_real_visited_guard_and_none():
    # Diamond graph: start->A, start->B, A->C, B->C. C gets queued from both A
    # and B before it is popped, so the second pop finds it already visited and
    # exercises the ``if current_node in visited: continue`` guard. Target "end"
    # is never reached -> returns None.
    neighbors = {
        "start": ["A", "B"],
        "A": ["C"],
        "B": ["C"],
        "C": [],
    }

    class _G:
        def V(self, node, *a, **k):
            return _Terminal(to_list=neighbors.get(node, []))

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    result = await trav.find_shortest_path("start", "end", max_depth=5)
    assert result is None


@pytest.mark.asyncio
async def test_shortest_path_real_outer_exception():
    class _BadBuilder:
        @property
        def g(self):
            raise RuntimeError("boom")

    trav = GraphTraversal(graph_builder=object())
    trav.graph = _BadBuilder()
    with pytest.raises(RuntimeError):
        await trav.find_shortest_path("a", "b")


# --- find_all_paths real path -------------------------------------------

@pytest.mark.asyncio
async def test_all_paths_real_depth_guard_and_collect():
    # start -> end directly, plus a longer branch pruned by max_depth.
    class _G:
        def V(self, node, *a, **k):
            return _Terminal(to_list=["end"])

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    paths = await trav.find_all_paths("start", "end", max_depth=3, max_paths=5)
    assert len(paths) >= 1
    assert paths[0].path[0] == "start"
    assert paths[0].path[-1] == "end"


@pytest.mark.asyncio
async def test_all_paths_real_depth_guard_continue():
    # Force path length to exceed max_depth quickly so the continue at the
    # depth guard is exercised (neighbors always new nodes, tiny max_depth).
    counter = {"n": 0}

    class _G:
        def V(self, node, *a, **k):
            counter["n"] += 1
            return _Terminal(to_list=[f"n{counter['n']}"])

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    paths = await trav.find_all_paths("start", "never", max_depth=1, max_paths=3)
    assert paths == []


@pytest.mark.asyncio
async def test_all_paths_real_outer_exception():
    class _BadBuilder:
        @property
        def g(self):
            raise RuntimeError("boom")

    trav = GraphTraversal(graph_builder=object())
    trav.graph = _BadBuilder()
    with pytest.raises(RuntimeError):
        await trav.find_all_paths("a", "b")


# --- get_node_neighbors real path: in / out / hasLabel ------------------

@pytest.mark.asyncio
async def test_get_neighbors_real_in_direction_with_labels():
    class _G:
        def V(self, node, *a, **k):
            return _Terminal(to_list=[{"name": ["N1"]}, {"name": ["N2"]}])

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    neighbors = await trav.get_node_neighbors("n1", direction="in", labels=["Person"])
    assert len(neighbors) == 2
    assert neighbors[0]["name"] == ["N1"]


@pytest.mark.asyncio
async def test_get_neighbors_real_out_direction():
    class _G:
        def V(self, node, *a, **k):
            return _Terminal(to_list=[{"name": ["Out"]}])

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    neighbors = await trav.get_node_neighbors("n1", direction="out")
    assert neighbors == [{"name": ["Out"]}]


# --- statistics average branch ------------------------------------------

def test_statistics_average_branch():
    trav = GraphTraversal(graph_builder=None)
    trav.traversal_stats["total_traversals"] = 4
    trav.traversal_stats["total_nodes_visited"] = 20
    stats = trav.get_traversal_statistics()
    assert stats["avg_execution_time"] == 5.0  # 20 / 4


# --- analyze_graph_connectivity real path -------------------------------

@pytest.mark.asyncio
async def test_analyze_connectivity_real_path():
    class _G:
        def V(self, *a, **k):
            # V().count().next() -> node_count ; V().bothE().count().toList() -> degrees
            return _Terminal(to_list=[2, 4, 6], next_value=3)

        def E(self, *a, **k):
            return _Terminal(next_value=5)

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    result = await trav.analyze_graph_connectivity()
    assert result["total_nodes"] == 3
    assert result["total_edges"] == 5
    assert result["average_degree"] == (2 + 4 + 6) / 3
    assert result["max_degree"] == 6
    assert result["diameter"] is None


@pytest.mark.asyncio
async def test_analyze_connectivity_real_empty_degrees():
    class _G:
        def V(self, *a, **k):
            return _Terminal(to_list=[], next_value=0)

        def E(self, *a, **k):
            return _Terminal(next_value=0)

    trav = GraphTraversal(graph_builder=_builder_with_g(_G()))
    result = await trav.analyze_graph_connectivity()
    assert result["average_degree"] == 0
    assert result["max_degree"] == 0


@pytest.mark.asyncio
async def test_analyze_connectivity_real_outer_exception():
    class _BadBuilder:
        @property
        def g(self):
            raise RuntimeError("boom")

    trav = GraphTraversal(graph_builder=object())
    trav.graph = _BadBuilder()
    with pytest.raises(RuntimeError):
        await trav.analyze_graph_connectivity()
