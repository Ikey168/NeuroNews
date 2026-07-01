"""Coverage tests for src/api/routes/influence_routes.py.

Covers every endpoint and each uncovered branch:
- /stats success + 500
- /top-influencers success, limit clamp (>100 and <1), 500
- /path success, 404 (no path), 500
- POST /nodes success, 400 (missing node_id), 500
- POST /edges success, 400 (missing source/target), 500
- POST /calculate-scores success + 500
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.influence_routes as mod


@pytest.fixture
def analyzer(monkeypatch):
    a = MagicMock()
    a.get_network_stats.return_value = {"nodes": 3, "edges": 2}
    a.get_top_influencers.return_value = [
        SimpleNamespace(
            node_id="n1", influence_score=0.9, connections=4, metadata={"k": "v"}
        ),
        SimpleNamespace(
            node_id="n2", influence_score=0.5, connections=2, metadata={}
        ),
    ]
    a.analyze_influence_path.return_value = ["n1", "nx", "n2"]
    a.add_node.return_value = None
    a.add_edge.return_value = None
    a.calculate_influence_scores.return_value = {"n1": 0.9, "n2": 0.5}
    monkeypatch.setattr(mod, "analyzer", a)
    return a


@pytest.fixture
def client(analyzer):
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# /health
# --------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/api/influence/health")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "healthy",
        "service": "influence_network_analyzer",
    }


# --------------------------------------------------------------------------
# /stats
# --------------------------------------------------------------------------

def test_stats_success(client, analyzer):
    resp = client.get("/api/influence/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == {"nodes": 3, "edges": 2}


def test_stats_error_500(client, analyzer):
    analyzer.get_network_stats.side_effect = RuntimeError("stats boom")
    resp = client.get("/api/influence/stats")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "stats boom"


# --------------------------------------------------------------------------
# /top-influencers
# --------------------------------------------------------------------------

def test_top_influencers_success(client, analyzer):
    resp = client.get("/api/influence/top-influencers", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["data"]) == 2
    assert body["data"][0] == {
        "node_id": "n1",
        "influence_score": 0.9,
        "connections": 4,
        "metadata": {"k": "v"},
    }
    analyzer.get_top_influencers.assert_called_once_with(n=5)


def test_top_influencers_clamped_high(client, analyzer):
    resp = client.get("/api/influence/top-influencers", params={"limit": 500})
    assert resp.status_code == 200
    analyzer.get_top_influencers.assert_called_once_with(n=100)


def test_top_influencers_clamped_low(client, analyzer):
    resp = client.get("/api/influence/top-influencers", params={"limit": 0})
    assert resp.status_code == 200
    analyzer.get_top_influencers.assert_called_once_with(n=1)


def test_top_influencers_error_500(client, analyzer):
    analyzer.get_top_influencers.side_effect = ValueError("influencer boom")
    resp = client.get("/api/influence/top-influencers")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "influencer boom"


# --------------------------------------------------------------------------
# /path/{source}/{target}
# --------------------------------------------------------------------------

def test_path_success(client, analyzer):
    resp = client.get("/api/influence/path/n1/n2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["source"] == "n1"
    assert body["data"]["target"] == "n2"
    assert body["data"]["path"] == ["n1", "nx", "n2"]
    assert body["data"]["path_length"] == 2  # len(path) - 1


def test_path_not_found_404(client, analyzer):
    analyzer.analyze_influence_path.return_value = None
    resp = client.get("/api/influence/path/a/b")
    assert resp.status_code == 404
    assert "No path found between a and b" in resp.json()["detail"]


def test_path_error_500(client, analyzer):
    analyzer.analyze_influence_path.side_effect = RuntimeError("path boom")
    resp = client.get("/api/influence/path/a/b")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "path boom"


# --------------------------------------------------------------------------
# POST /nodes
# --------------------------------------------------------------------------

def test_add_node_success(client, analyzer):
    resp = client.post(
        "/api/influence/nodes", json={"node_id": "n9", "metadata": {"x": 1}}
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert "n9" in resp.json()["message"]
    analyzer.add_node.assert_called_once_with("n9", {"x": 1})


def test_add_node_missing_id_400(client, analyzer):
    resp = client.post("/api/influence/nodes", json={"metadata": {}})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "node_id is required"
    analyzer.add_node.assert_not_called()


def test_add_node_error_500(client, analyzer):
    analyzer.add_node.side_effect = RuntimeError("node boom")
    resp = client.post("/api/influence/nodes", json={"node_id": "n9"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "node boom"


# --------------------------------------------------------------------------
# POST /edges
# --------------------------------------------------------------------------

def test_add_edge_success(client, analyzer):
    resp = client.post(
        "/api/influence/edges",
        json={"source": "a", "target": "b", "weight": 2.5},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    analyzer.add_edge.assert_called_once_with("a", "b", 2.5)


def test_add_edge_default_weight(client, analyzer):
    resp = client.post("/api/influence/edges", json={"source": "a", "target": "b"})
    assert resp.status_code == 200
    analyzer.add_edge.assert_called_once_with("a", "b", 1.0)


def test_add_edge_missing_target_400(client, analyzer):
    resp = client.post("/api/influence/edges", json={"source": "a"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Both source and target are required"
    analyzer.add_edge.assert_not_called()


def test_add_edge_error_500(client, analyzer):
    analyzer.add_edge.side_effect = RuntimeError("edge boom")
    resp = client.post("/api/influence/edges", json={"source": "a", "target": "b"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "edge boom"


# --------------------------------------------------------------------------
# POST /calculate-scores
# --------------------------------------------------------------------------

def test_calculate_scores_success(client, analyzer):
    resp = client.post("/api/influence/calculate-scores")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["node_count"] == 2
    assert body["data"]["scores"] == {"n1": 0.9, "n2": 0.5}


def test_calculate_scores_error_500(client, analyzer):
    analyzer.calculate_influence_scores.side_effect = RuntimeError("score boom")
    resp = client.post("/api/influence/calculate-scores")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "score boom"
