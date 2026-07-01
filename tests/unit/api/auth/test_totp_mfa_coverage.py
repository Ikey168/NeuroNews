"""Coverage tests for src/api/auth/totp_mfa.py.

Exercises the real generation / verification / activation / login-check paths
against a REAL in-memory DuckDB connection and a REAL pyotp TOTP so the SQL
(CREATE TABLE / INSERT ... ON CONFLICT / SELECT / UPDATE) and the actual
time-based OTP arithmetic run for real.

The module resolves the connection lazily inside ``_get_conn`` via
``from src.database.local_analytics_connector import get_shared_connection``,
so we patch that symbol on the connector module.

pyotp is an optional dependency — importorskip skips the whole module when it
is absent rather than asserting on a stubbed value.
"""
from __future__ import annotations

import pytest

pyotp = pytest.importorskip("pyotp")

import src.api.auth.totp_mfa as totp_mfa
import src.database.local_analytics_connector as connector


@pytest.fixture
def duck(monkeypatch):
    """Isolated in-memory DuckDB wired into totp_mfa._get_conn()."""
    import duckdb

    conn = duckdb.connect(":memory:")
    monkeypatch.setattr(connector, "get_shared_connection", lambda: conn)
    # Guard: the module must genuinely see pyotp as available for these tests.
    assert totp_mfa.PYOTP_AVAILABLE is True
    yield conn
    conn.close()


def _current_code(secret: str) -> str:
    return pyotp.TOTP(secret).now()


# ---------------------------------------------------------------------------
# _get_conn / _ensure_table
# ---------------------------------------------------------------------------

def test_get_conn_returns_patched_connection(duck):
    assert totp_mfa._get_conn() is duck


def test_ensure_table_creates_schema(duck):
    totp_mfa._ensure_table(duck)
    tables = {
        r[0]
        for r in duck.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    assert "admin_mfa_secrets" in tables


# ---------------------------------------------------------------------------
# setup_totp
# ---------------------------------------------------------------------------

def test_setup_totp_returns_uri_secret_and_persists_disabled(duck):
    result = totp_mfa.setup_totp("user-1", "alice@example.com")

    assert set(result) == {"totp_uri", "secret", "enabled"}
    assert result["enabled"] is False
    # base32 secret and a valid otpauth provisioning URI.
    assert isinstance(result["secret"], str) and len(result["secret"]) >= 16
    assert result["totp_uri"].startswith("otpauth://totp/")
    assert "issuer=NeuroNews" in result["totp_uri"]
    assert "alice%40example.com" in result["totp_uri"] or "alice@example.com" in result["totp_uri"]

    row = duck.execute(
        "SELECT totp_secret, enabled FROM admin_mfa_secrets WHERE user_id = ?",
        ["user-1"],
    ).fetchone()
    assert row is not None
    assert row[0] == result["secret"]
    assert bool(row[1]) is False


def test_setup_totp_upsert_replaces_secret_and_resets_enabled(duck):
    first = totp_mfa.setup_totp("user-2", "bob@example.com")
    # Enable it, then re-run setup and confirm it is disabled + secret replaced.
    duck.execute(
        "UPDATE admin_mfa_secrets SET enabled = TRUE WHERE user_id = ?", ["user-2"]
    )
    second = totp_mfa.setup_totp("user-2", "bob@example.com")

    assert second["secret"] != first["secret"]
    assert second["enabled"] is False
    secret, enabled = duck.execute(
        "SELECT totp_secret, enabled FROM admin_mfa_secrets WHERE user_id = ?",
        ["user-2"],
    ).fetchone()
    assert secret == second["secret"]
    assert bool(enabled) is False
    # Still exactly one row for the user (ON CONFLICT updated, did not insert).
    count = duck.execute(
        "SELECT COUNT(*) FROM admin_mfa_secrets WHERE user_id = ?", ["user-2"]
    ).fetchone()[0]
    assert count == 1


def test_setup_totp_raises_when_pyotp_unavailable(duck, monkeypatch):
    monkeypatch.setattr(totp_mfa, "PYOTP_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="pyotp"):
        totp_mfa.setup_totp("user-x", "x@example.com")


# ---------------------------------------------------------------------------
# verify_totp
# ---------------------------------------------------------------------------

def test_verify_totp_valid_code_enables_mfa(duck):
    setup = totp_mfa.setup_totp("user-3", "carol@example.com")
    assert totp_mfa.is_mfa_enabled("user-3") is False

    code = _current_code(setup["secret"])
    assert totp_mfa.verify_totp("user-3", code) is True

    # enabled flag flipped to TRUE in the table.
    enabled = duck.execute(
        "SELECT enabled FROM admin_mfa_secrets WHERE user_id = ?", ["user-3"]
    ).fetchone()[0]
    assert bool(enabled) is True
    assert totp_mfa.is_mfa_enabled("user-3") is True


def test_verify_totp_wrong_code_returns_false_and_stays_disabled(duck):
    totp_mfa.setup_totp("user-4", "dave@example.com")
    assert totp_mfa.verify_totp("user-4", "000000") is False
    enabled = duck.execute(
        "SELECT enabled FROM admin_mfa_secrets WHERE user_id = ?", ["user-4"]
    ).fetchone()[0]
    assert bool(enabled) is False


def test_verify_totp_unknown_user_returns_false(duck):
    totp_mfa._ensure_table(duck)
    assert totp_mfa.verify_totp("no-such-user", "123456") is False


def test_verify_totp_returns_false_when_pyotp_unavailable(duck, monkeypatch):
    monkeypatch.setattr(totp_mfa, "PYOTP_AVAILABLE", False)
    assert totp_mfa.verify_totp("user-any", "123456") is False


# ---------------------------------------------------------------------------
# is_mfa_enabled
# ---------------------------------------------------------------------------

def test_is_mfa_enabled_false_for_unknown_user(duck):
    totp_mfa._ensure_table(duck)
    assert totp_mfa.is_mfa_enabled("ghost") is False


def test_is_mfa_enabled_true_after_verification(duck):
    setup = totp_mfa.setup_totp("user-5", "erin@example.com")
    totp_mfa.verify_totp("user-5", _current_code(setup["secret"]))
    assert totp_mfa.is_mfa_enabled("user-5") is True


# ---------------------------------------------------------------------------
# check_totp
# ---------------------------------------------------------------------------

def test_check_totp_valid_when_enabled(duck):
    setup = totp_mfa.setup_totp("user-6", "frank@example.com")
    totp_mfa.verify_totp("user-6", _current_code(setup["secret"]))
    assert totp_mfa.is_mfa_enabled("user-6") is True

    # A fresh current code validates for login without changing state.
    assert totp_mfa.check_totp("user-6", _current_code(setup["secret"])) is True


def test_check_totp_false_when_not_enabled(duck):
    setup = totp_mfa.setup_totp("user-7", "grace@example.com")
    # Secret exists but MFA never verified/enabled -> check_totp short-circuits.
    assert totp_mfa.check_totp("user-7", _current_code(setup["secret"])) is False


def test_check_totp_false_for_unknown_user(duck):
    totp_mfa._ensure_table(duck)
    assert totp_mfa.check_totp("nobody", "123456") is False


def test_check_totp_wrong_code_when_enabled_returns_false(duck):
    setup = totp_mfa.setup_totp("user-8", "heidi@example.com")
    totp_mfa.verify_totp("user-8", _current_code(setup["secret"]))
    assert totp_mfa.check_totp("user-8", "000000") is False


def test_check_totp_returns_false_when_pyotp_unavailable(duck, monkeypatch):
    monkeypatch.setattr(totp_mfa, "PYOTP_AVAILABLE", False)
    assert totp_mfa.check_totp("user-any", "123456") is False
