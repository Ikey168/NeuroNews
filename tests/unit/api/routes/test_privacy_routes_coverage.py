"""Coverage tests for src/api/routes/privacy_routes.py.

Exercises every endpoint (DELETE /user/data, GET /user/data/export,
GET /user/privacy, PATCH /user/privacy) plus the exception-tolerant
branches (missing tables), the 422 validation branch on PATCH, and the
_ensure_prefs_table / _get_conn helpers.

_get_conn is monkeypatched to return a fresh in-memory DuckDB connection so
no shared warehouse file is touched.
"""
import os
import sys
import zipfile
import io
import json

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")
duckdb = pytest.importorskip("duckdb")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import src.api.routes.privacy_routes as mod  # noqa: E402
from src.api.auth.jwt_auth import require_auth  # noqa: E402


@pytest.fixture
def conn():
    """A fresh in-memory DuckDB connection wired into the module."""
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def client(conn, monkeypatch):
    monkeypatch.setattr(mod, "_get_conn", lambda: conn)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[require_auth] = lambda: {"sub": "u1", "role": "free"}
    return TestClient(app, raise_server_exceptions=False)


def _seed_erasable(conn):
    """Create two erasable tables with a couple of rows each."""
    conn.execute("CREATE TABLE news_articles (id INTEGER, title VARCHAR)")
    conn.execute("INSERT INTO news_articles VALUES (1, 'a'), (2, 'b')")
    conn.execute("CREATE TABLE source_stances (id INTEGER)")
    conn.execute("INSERT INTO source_stances VALUES (10), (20), (30)")


# --------------------------------------------------------------------------
# DELETE /user/data
# --------------------------------------------------------------------------

def test_delete_user_data_counts_and_clears(client, conn):
    """Existing tables are counted then emptied; absent tables record 0."""
    _seed_erasable(conn)
    resp = client.delete("/user/data")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tables"]["news_articles"] == 2
    assert body["tables"]["source_stances"] == 3
    # Tables that do not exist are tolerated and reported as 0.
    assert body["tables"]["claim_evidence"] == 0
    assert body["total_rows_deleted"] == 5
    assert "off-device" in body["note"]
    assert "deleted_at" in body
    # Rows really were deleted.
    assert conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0] == 0


def test_delete_user_data_all_missing_tables(client):
    """With no tables present the receipt is all-zero (exception branch)."""
    resp = client.delete("/user/data")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_rows_deleted"] == 0
    assert all(v == 0 for v in body["tables"].values())
    assert set(body["tables"].keys()) == set(mod._ERASABLE_TABLES)


# --------------------------------------------------------------------------
# GET /user/data/export
# --------------------------------------------------------------------------

def test_export_user_data_zip_contents(client, conn):
    """The export streams a ZIP with one JSON per export table + a manifest."""
    _seed_erasable(conn)
    resp = client.get("/user/data/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert ".zip" in resp.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    # One JSON per export table plus a manifest.
    for table in mod._EXPORT_TABLES:
        assert f"{table}.json" in names
    assert "manifest.json" in names

    # Seeded data is present in the archive.
    articles = json.loads(zf.read("news_articles.json"))
    assert len(articles) == 2
    # Missing tables serialize to an empty list.
    empty = json.loads(zf.read("claim_evidence.json"))
    assert empty == []

    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["tables"] == mod._EXPORT_TABLES
    assert "off-device" in manifest["note"]


# --------------------------------------------------------------------------
# GET /user/privacy
# --------------------------------------------------------------------------

def test_get_privacy_prefs_empty(client, conn):
    """With no stored prefs the table is created on demand and prefs are {}."""
    resp = client.get("/user/privacy")
    assert resp.status_code == 200
    assert resp.json() == {"preferences": {}}
    # _ensure_prefs_table should have created the table.
    tbls = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
    assert "user_privacy_prefs" in tbls


def test_get_privacy_prefs_returns_stored(client, conn):
    mod._ensure_prefs_table(conn)
    conn.execute(
        "INSERT INTO user_privacy_prefs (pref_key, pref_value) VALUES ('telemetry', 'off')"
    )
    resp = client.get("/user/privacy")
    assert resp.status_code == 200
    prefs = resp.json()["preferences"]
    assert prefs["telemetry"]["value"] == "off"
    assert "updated_at" in prefs["telemetry"]


# --------------------------------------------------------------------------
# PATCH /user/privacy
# --------------------------------------------------------------------------

def test_update_privacy_prefs_upsert(client, conn):
    """Upsert inserts then updates the same key."""
    resp = client.patch("/user/privacy", json={"preferences": {"theme": "dark"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == ["theme"]
    assert "updated_at" in body
    stored = conn.execute(
        "SELECT pref_value FROM user_privacy_prefs WHERE pref_key = 'theme'"
    ).fetchone()[0]
    assert stored == "dark"

    # Second call updates the existing row (ON CONFLICT path).
    resp2 = client.patch("/user/privacy", json={"preferences": {"theme": "light"}})
    assert resp2.status_code == 200
    stored2 = conn.execute(
        "SELECT pref_value FROM user_privacy_prefs WHERE pref_key = 'theme'"
    ).fetchone()[0]
    assert stored2 == "light"
    # Still exactly one row for that key.
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM user_privacy_prefs WHERE pref_key = 'theme'"
        ).fetchone()[0]
        == 1
    )


def test_update_privacy_prefs_multiple_keys(client):
    resp = client.patch(
        "/user/privacy",
        json={"preferences": {"a": "1", "b": "2"}},
    )
    assert resp.status_code == 200
    assert set(resp.json()["updated"]) == {"a", "b"}


def test_update_privacy_prefs_empty_key_422(client):
    """An empty pref_key trips the 422 validation branch."""
    resp = client.patch("/user/privacy", json={"preferences": {"": "value"}})
    assert resp.status_code == 422
    assert "Invalid pref_key" in resp.json()["detail"]


def test_update_privacy_prefs_too_long_key_422(client):
    long_key = "k" * 129
    resp = client.patch("/user/privacy", json={"preferences": {long_key: "v"}})
    assert resp.status_code == 422
    assert "Invalid pref_key" in resp.json()["detail"]


def test_update_privacy_prefs_missing_body_422(client):
    """The pydantic body model is required."""
    resp = client.patch("/user/privacy", json={})
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def test_ensure_prefs_table_idempotent(conn):
    mod._ensure_prefs_table(conn)
    mod._ensure_prefs_table(conn)  # CREATE ... IF NOT EXISTS -> no error
    cols = [r[0] for r in conn.execute("DESCRIBE user_privacy_prefs").fetchall()]
    assert set(cols) == {"pref_key", "pref_value", "updated_at"}


def test_get_conn_delegates_to_shared_connection(monkeypatch):
    """_get_conn imports and returns the shared warehouse connection."""
    import src.database.local_analytics_connector as lac

    sentinel = object()
    monkeypatch.setattr(lac, "get_shared_connection", lambda: sentinel)
    assert mod._get_conn() is sentinel
