"""Coverage tests for src/api/routes/entity_correction_routes.py.

Mounts the router on a fresh FastAPI app, overrides ``require_auth`` via
``app.dependency_overrides`` and patches the lazy ``_store`` / ``_kg_store``
loaders with mocks.  Exercises every endpoint plus the auth (403), validation
(422), not-found (404) and conflict (409) branches.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import src.api.routes.entity_correction_routes as mod  # noqa: E402
from src.knowledge_graph.entity_corrections import (  # noqa: E402
    CorrectionStatus,
    CorrectionType,
    EntityCorrection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_correction(
    correction_id="c-1",
    entity_id="person:abc123def456",
    correction_type=CorrectionType.RENAME,
    status=CorrectionStatus.PENDING,
):
    return EntityCorrection(
        correction_id=correction_id,
        entity_id=entity_id,
        correction_type=correction_type,
        payload={"new_name": "New Name"},
        reason="a good reason",
        submitted_by="user-1",
        submitted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        version=1,
        status=status,
    )


def _make_node():
    node = MagicMock()
    node.to_dict.return_value = {
        "id": "person:abc123def456",
        "name": "Alice",
        "type": "PERSON",
    }
    return node


def _build_client(user_role="admin"):
    """Build a TestClient with require_auth overridden to a user of given role."""
    app = FastAPI()
    app.include_router(mod.router)

    async def _fake_auth():
        return {"sub": "tester", "user_id": "tester", "role": user_role}

    app.dependency_overrides[mod.require_auth] = _fake_auth
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def store():
    s = MagicMock()
    return s


@pytest.fixture
def kg_store():
    return MagicMock()


@pytest.fixture(autouse=True)
def _patch_stores(monkeypatch, store, kg_store):
    monkeypatch.setattr(mod, "_store", lambda: store)
    monkeypatch.setattr(mod, "_kg_store", lambda: kg_store)
    yield


# ---------------------------------------------------------------------------
# GET /entities/{entity_id}
# ---------------------------------------------------------------------------

class TestGetEntity:
    def test_found(self, kg_store):
        kg_store.get_node.return_value = _make_node()
        client = _build_client(user_role="free")  # any authenticated user
        resp = client.get("/entities/person:abc123def456")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "person:abc123def456"
        assert body["name"] == "Alice"
        kg_store.get_node.assert_called_once_with("person:abc123def456")

    def test_not_found(self, kg_store):
        kg_store.get_node.return_value = None
        client = _build_client(user_role="free")
        resp = client.get("/entities/person:missing")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /entities/{entity_id}/corrections
# ---------------------------------------------------------------------------

class TestSubmitCorrection:
    def test_success(self, store, kg_store):
        kg_store.get_node.return_value = _make_node()
        store.submit.return_value = _make_correction()
        client = _build_client(user_role="premium")
        resp = client.post(
            "/entities/person:abc123def456/corrections",
            json={
                "correction_type": "rename",
                "payload": {"new_name": "Alice Smith"},
                "reason": "correct spelling",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["correction_id"] == "c-1"
        assert body["status"] == "pending"
        # entity existence checked, then submitted
        kg_store.get_node.assert_called_once()
        store.submit.assert_called_once()

    def test_forbidden_for_non_trusted(self, kg_store):
        kg_store.get_node.return_value = _make_node()
        client = _build_client(user_role="free")
        resp = client.post(
            "/entities/person:abc123def456/corrections",
            json={
                "correction_type": "rename",
                "payload": {"new_name": "X"},
                "reason": "some reason",
            },
        )
        assert resp.status_code == 403
        assert "Premium or Admin" in resp.json()["detail"]

    def test_unknown_correction_type(self, kg_store):
        kg_store.get_node.return_value = _make_node()
        client = _build_client(user_role="premium")
        resp = client.post(
            "/entities/person:abc123def456/corrections",
            json={
                "correction_type": "not_a_real_type",
                "payload": {},
                "reason": "some reason",
            },
        )
        assert resp.status_code == 422
        assert "Unknown correction_type" in resp.json()["detail"]

    def test_entity_not_found(self, kg_store):
        kg_store.get_node.return_value = None
        client = _build_client(user_role="premium")
        resp = client.post(
            "/entities/person:missing/corrections",
            json={
                "correction_type": "rename",
                "payload": {"new_name": "X"},
                "reason": "some reason",
            },
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_merge_skips_entity_check(self, store, kg_store):
        # MERGE type must NOT check kg_store.get_node for the target
        store.submit.return_value = _make_correction(
            correction_type=CorrectionType.MERGE
        )
        client = _build_client(user_role="admin")
        resp = client.post(
            "/entities/person:abc123def456/corrections",
            json={
                "correction_type": "merge",
                "payload": {"merge_from": "person:other"},
                "reason": "duplicate entity",
            },
        )
        assert resp.status_code == 201
        kg_store.get_node.assert_not_called()

    def test_store_value_error_maps_422(self, store, kg_store):
        kg_store.get_node.return_value = _make_node()
        store.submit.side_effect = ValueError("bad payload")
        client = _build_client(user_role="premium")
        resp = client.post(
            "/entities/person:abc123def456/corrections",
            json={
                "correction_type": "rename",
                "payload": {"new_name": "X"},
                "reason": "some reason",
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "bad payload"

    def test_reason_too_short_pydantic_422(self, kg_store):
        kg_store.get_node.return_value = _make_node()
        client = _build_client(user_role="premium")
        resp = client.post(
            "/entities/person:abc123def456/corrections",
            json={
                "correction_type": "rename",
                "payload": {"new_name": "X"},
                "reason": "x",  # < 5 chars
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /entities/{entity_id}/corrections
# ---------------------------------------------------------------------------

class TestListEntityCorrections:
    def test_no_filter(self, store):
        store.list_corrections.return_value = [_make_correction()]
        client = _build_client(user_role="free")
        resp = client.get("/entities/person:abc123def456/corrections")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        _, kwargs = store.list_corrections.call_args
        assert kwargs["status"] is None

    def test_valid_status_filter(self, store):
        store.list_corrections.return_value = []
        client = _build_client(user_role="free")
        resp = client.get(
            "/entities/person:abc123def456/corrections",
            params={"status": "approved"},
        )
        assert resp.status_code == 200
        _, kwargs = store.list_corrections.call_args
        assert kwargs["status"] == CorrectionStatus.APPROVED

    def test_invalid_status_filter(self, store):
        client = _build_client(user_role="free")
        resp = client.get(
            "/entities/person:abc123def456/corrections",
            params={"status": "bogus"},
        )
        assert resp.status_code == 422
        assert "Unknown status" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /admin/entity-corrections
# ---------------------------------------------------------------------------

class TestListAllCorrections:
    def test_default_pending(self, store):
        store.list_corrections.return_value = [_make_correction()]
        client = _build_client(user_role="admin")
        resp = client.get("/admin/entity-corrections")
        assert resp.status_code == 200
        _, kwargs = store.list_corrections.call_args
        assert kwargs["status"] == CorrectionStatus.PENDING

    def test_status_all(self, store):
        store.list_corrections.return_value = []
        client = _build_client(user_role="admin")
        resp = client.get("/admin/entity-corrections", params={"status": "all"})
        assert resp.status_code == 200
        _, kwargs = store.list_corrections.call_args
        assert kwargs["status"] is None

    def test_invalid_status(self, store):
        client = _build_client(user_role="admin")
        resp = client.get(
            "/admin/entity-corrections", params={"status": "nope"}
        )
        assert resp.status_code == 422
        assert "Unknown status" in resp.json()["detail"]

    def test_forbidden_for_premium(self):
        client = _build_client(user_role="premium")
        resp = client.get("/admin/entity-corrections")
        assert resp.status_code == 403
        assert "Admin privileges required" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /admin/entity-corrections/{correction_id}
# ---------------------------------------------------------------------------

class TestGetCorrection:
    def test_found(self, store):
        store.get.return_value = _make_correction()
        client = _build_client(user_role="administrator")
        resp = client.get("/admin/entity-corrections/c-1")
        assert resp.status_code == 200
        assert resp.json()["correction_id"] == "c-1"

    def test_not_found(self, store):
        store.get.return_value = None
        client = _build_client(user_role="admin")
        resp = client.get("/admin/entity-corrections/missing")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST approve / reject
# ---------------------------------------------------------------------------

class TestApprove:
    def test_success(self, store):
        store.approve.return_value = _make_correction(
            status=CorrectionStatus.APPROVED
        )
        client = _build_client(user_role="admin")
        resp = client.post(
            "/admin/entity-corrections/c-1/approve", json="looks good"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        _, kwargs = store.approve.call_args
        assert kwargs["review_note"] == "looks good"

    def test_not_found_keyerror(self, store):
        store.approve.side_effect = KeyError("Correction 'c-x' not found")
        client = _build_client(user_role="admin")
        resp = client.post("/admin/entity-corrections/c-x/approve")
        assert resp.status_code == 404

    def test_conflict_valueerror(self, store):
        store.approve.side_effect = ValueError("already approved")
        client = _build_client(user_role="admin")
        resp = client.post("/admin/entity-corrections/c-1/approve")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "already approved"

    def test_forbidden(self):
        client = _build_client(user_role="premium")
        resp = client.post("/admin/entity-corrections/c-1/approve")
        assert resp.status_code == 403


class TestReject:
    def test_success(self, store):
        store.reject.return_value = _make_correction(
            status=CorrectionStatus.REJECTED
        )
        client = _build_client(user_role="admin")
        resp = client.post(
            "/admin/entity-corrections/c-1/reject", json="not valid"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
        _, kwargs = store.reject.call_args
        assert kwargs["review_note"] == "not valid"

    def test_not_found_keyerror(self, store):
        store.reject.side_effect = KeyError("Correction 'c-x' not found")
        client = _build_client(user_role="admin")
        resp = client.post("/admin/entity-corrections/c-x/reject")
        assert resp.status_code == 404

    def test_conflict_valueerror(self, store):
        store.reject.side_effect = ValueError("already rejected")
        client = _build_client(user_role="admin")
        resp = client.post("/admin/entity-corrections/c-1/reject")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "already rejected"
