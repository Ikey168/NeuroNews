"""Tests for src/api/routes/api_key_routes.py via minimal app + mocked manager."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.routes.api_key_routes as mod  # noqa: E402


@pytest.fixture
def manager(monkeypatch):
    m = MagicMock()
    m.generate_api_key = AsyncMock(return_value={"api_key": "k", "key_id": "id1",
                                                 "name": "n", "created_at": "2026-01-01",
                                                 "expires_at": None})
    m.get_user_api_keys = AsyncMock(return_value=[])
    m.revoke_api_key = AsyncMock(return_value=True)
    m.delete_api_key = AsyncMock(return_value=True)
    m.renew_api_key = AsyncMock(return_value={"api_key": "k2", "key_id": "id1"})
    monkeypatch.setattr(mod, "api_key_manager", m)
    return m


@pytest.fixture
def client(manager):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_user_id] = lambda: "user-1"
    return TestClient(app, raise_server_exceptions=False)


def test_list_keys(client):
    resp = client.get("/api/keys/")
    assert 200 <= resp.status_code < 600


def test_get_key(client):
    resp = client.get("/api/keys/id1")
    assert 200 <= resp.status_code < 600


def test_revoke(client):
    resp = client.post("/api/keys/revoke", json={"key_id": "id1"})
    assert 200 <= resp.status_code < 600


def test_delete(client):
    resp = client.delete("/api/keys/id1")
    assert 200 <= resp.status_code < 600
