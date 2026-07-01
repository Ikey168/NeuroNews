"""Coverage tests for src/api/auth/local_api_keys.py.

Uses a REAL in-memory DuckDB connection so the CREATE TABLE / INSERT / SELECT /
UPDATE SQL actually executes, and REAL bcrypt hashing/verification. The module
looks up ``get_shared_connection`` lazily inside ``_get_conn`` via
``from src.database.local_analytics_connector import get_shared_connection``,
so we patch that symbol on the connector module.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import src.api.auth.local_api_keys as lak
import src.database.local_analytics_connector as connector


@pytest.fixture
def duck(monkeypatch):
    import duckdb

    conn = duckdb.connect(":memory:")
    monkeypatch.setattr(connector, "get_shared_connection", lambda: conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# _ensure_table / _get_conn
# ---------------------------------------------------------------------------

def test_get_conn_returns_patched_connection(duck):
    assert lak._get_conn() is duck


def test_ensure_table_creates_schema(duck):
    lak._ensure_table(duck)
    tables = {
        r[0]
        for r in duck.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    assert "local_api_keys" in tables


# ---------------------------------------------------------------------------
# create_api_key
# ---------------------------------------------------------------------------

def test_create_api_key_returns_plaintext_and_persists(duck):
    result = lak.create_api_key("ci-token", role="admin", expires_in_days=30)

    assert set(result) == {"key_id", "raw_key", "key_prefix", "name", "role", "expires_at"}
    assert result["name"] == "ci-token"
    assert result["role"] == "admin"
    # raw key is 64 hex chars (32 bytes) and prefix is its first 8 chars
    assert len(result["raw_key"]) == 64
    assert result["key_prefix"] == result["raw_key"][:8]
    assert result["expires_at"] is not None

    # Row persisted with a bcrypt hash that is NOT the plaintext.
    row = duck.execute(
        "SELECT key_hash, key_prefix, name, role, status FROM local_api_keys WHERE key_id = ?",
        [result["key_id"]],
    ).fetchone()
    assert row is not None
    key_hash, prefix, name, role, status = row
    assert key_hash != result["raw_key"]
    assert key_hash.startswith("$2")  # bcrypt hash marker
    assert prefix == result["key_prefix"]
    assert name == "ci-token"
    assert role == "admin"
    assert status == "active"


def test_create_api_key_no_expiry(duck):
    result = lak.create_api_key("perm", expires_in_days=None)
    assert result["expires_at"] is None
    assert result["role"] == "viewer"  # default role


def test_create_api_key_default_role_is_viewer(duck):
    result = lak.create_api_key("plain")
    assert result["role"] == "viewer"


# ---------------------------------------------------------------------------
# verify_api_key
# ---------------------------------------------------------------------------

def test_verify_api_key_valid(duck):
    created = lak.create_api_key("valid", role="editor", expires_in_days=365)

    record = lak.verify_api_key(created["raw_key"])
    assert record is not None
    assert record["key_id"] == created["key_id"]
    assert record["name"] == "valid"
    assert record["role"] == "editor"
    assert record["status"] == "active"

    # usage_count incremented and last_used_at set.
    usage, last_used = duck.execute(
        "SELECT usage_count, last_used_at FROM local_api_keys WHERE key_id = ?",
        [created["key_id"]],
    ).fetchone()
    assert usage == 1
    assert last_used is not None


def test_verify_api_key_wrong_key_same_prefix_returns_none(duck):
    created = lak.create_api_key("real", expires_in_days=365)
    # Same 8-char prefix so the prefix filter matches, but the remainder differs,
    # so bcrypt.checkpw must fail and we fall through to None.
    forged = created["raw_key"][:8] + ("f" * (64 - 8))
    assert forged != created["raw_key"]
    assert lak.verify_api_key(forged) is None


def test_verify_api_key_unknown_prefix_returns_none(duck):
    lak.create_api_key("real", expires_in_days=365)
    assert lak.verify_api_key("00000000" + "a" * 56) is None


def test_verify_api_key_expired_returns_none(duck):
    created = lak.create_api_key("expiring", expires_in_days=365)
    # Force the row to be expired in the past.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    duck.execute(
        "UPDATE local_api_keys SET expires_at = ? WHERE key_id = ?",
        [past, created["key_id"]],
    )
    assert lak.verify_api_key(created["raw_key"]) is None


def test_verify_api_key_naive_expiry_treated_as_utc(duck):
    created = lak.create_api_key("naive", expires_in_days=365)
    # Naive (no tzinfo) future timestamp exercises the tzinfo-None branch.
    future_naive = (datetime.now(timezone.utc) + timedelta(days=10)).replace(tzinfo=None).isoformat()
    duck.execute(
        "UPDATE local_api_keys SET expires_at = ? WHERE key_id = ?",
        [future_naive, created["key_id"]],
    )
    record = lak.verify_api_key(created["raw_key"])
    assert record is not None
    assert record["key_id"] == created["key_id"]


def test_verify_api_key_revoked_not_returned(duck):
    created = lak.create_api_key("revoke-me", expires_in_days=365)
    lak.revoke_api_key(created["key_id"])
    # status != 'active' filters it out of the verify SELECT.
    assert lak.verify_api_key(created["raw_key"]) is None


# ---------------------------------------------------------------------------
# revoke_api_key
# ---------------------------------------------------------------------------

def test_revoke_api_key_existing_returns_true(duck):
    created = lak.create_api_key("to-revoke", expires_in_days=365)
    assert lak.revoke_api_key(created["key_id"]) is True

    status = duck.execute(
        "SELECT status FROM local_api_keys WHERE key_id = ?", [created["key_id"]]
    ).fetchone()[0]
    assert status == "revoked"


def test_revoke_api_key_missing_returns_false(duck):
    lak._ensure_table(duck)
    assert lak.revoke_api_key("does-not-exist") is False


# ---------------------------------------------------------------------------
# list_api_keys
# ---------------------------------------------------------------------------

def test_list_api_keys_empty(duck):
    lak._ensure_table(duck)
    assert lak.list_api_keys() == []


def test_list_api_keys_returns_all_without_hash(duck):
    lak.create_api_key("first", expires_in_days=365)
    lak.create_api_key("second", expires_in_days=None)

    keys = lak.list_api_keys()
    assert len(keys) == 2
    names = {k["name"] for k in keys}
    assert names == {"first", "second"}
    for k in keys:
        assert "key_hash" not in k
        assert set(k) == {
            "key_id", "key_prefix", "name", "role", "status", "created_at",
            "expires_at", "last_used_at", "usage_count",
        }


# ---------------------------------------------------------------------------
# get_api_key
# ---------------------------------------------------------------------------

def test_get_api_key_found(duck):
    created = lak.create_api_key("lookup", role="admin", expires_in_days=365)
    record = lak.get_api_key(created["key_id"])
    assert record is not None
    assert record["key_id"] == created["key_id"]
    assert record["name"] == "lookup"
    assert record["role"] == "admin"
    assert "key_hash" not in record


def test_get_api_key_missing_returns_none(duck):
    lak._ensure_table(duck)
    assert lak.get_api_key("nope") is None
