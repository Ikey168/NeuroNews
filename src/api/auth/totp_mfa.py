"""
TOTP-based MFA for admin role — Issue #66.

Uses pyotp to generate and verify time-based one-time passwords.
Secrets stored in admin_mfa_secrets DuckDB table.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False

logger = logging.getLogger(__name__)

ISSUER = "NeuroNews"


def _get_conn():
    from src.database.local_analytics_connector import get_shared_connection
    return get_shared_connection()


def _ensure_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_mfa_secrets (
            user_id     VARCHAR PRIMARY KEY,
            totp_secret VARCHAR NOT NULL,
            enabled     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_totp(user_id: str, email: str) -> dict:
    """
    Create (or replace) a TOTP secret for user_id.

    Returns:
        totp_uri   — otpauth:// URI for QR-code generation
        secret     — base32 secret (for manual entry)
        enabled    — False until the user verifies a valid code
    """
    if not PYOTP_AVAILABLE:
        raise RuntimeError("pyotp is not installed (pip install pyotp)")

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=email, issuer_name=ISSUER)
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_conn()
    _ensure_table(conn)
    conn.execute(
        """
        INSERT INTO admin_mfa_secrets (user_id, totp_secret, enabled, created_at)
        VALUES (?, ?, FALSE, ?)
        ON CONFLICT (user_id)
        DO UPDATE SET totp_secret = excluded.totp_secret,
                      enabled     = FALSE,
                      created_at  = excluded.created_at
        """,
        [user_id, secret, now],
    )
    logger.info("TOTP secret created for user %s (not yet enabled)", user_id)
    return {"totp_uri": uri, "secret": secret, "enabled": False}


# ---------------------------------------------------------------------------
# Verification / activation
# ---------------------------------------------------------------------------

def verify_totp(user_id: str, code: str) -> bool:
    """
    Verify a TOTP code for user_id and, if correct, mark MFA as enabled.

    Returns True if the code is valid (within a 1-step window).
    """
    if not PYOTP_AVAILABLE:
        return False

    conn = _get_conn()
    _ensure_table(conn)
    row = conn.execute(
        "SELECT totp_secret FROM admin_mfa_secrets WHERE user_id = ?", [user_id]
    ).fetchone()
    if not row:
        return False

    secret = row[0]
    totp = pyotp.TOTP(secret)
    valid = totp.verify(code, valid_window=1)
    if valid:
        conn.execute(
            "UPDATE admin_mfa_secrets SET enabled = TRUE WHERE user_id = ?", [user_id]
        )
        logger.info("MFA enabled for user %s after successful verification", user_id)
    return valid


def is_mfa_enabled(user_id: str) -> bool:
    """Return True if the user has MFA enabled."""
    conn = _get_conn()
    _ensure_table(conn)
    row = conn.execute(
        "SELECT enabled FROM admin_mfa_secrets WHERE user_id = ?", [user_id]
    ).fetchone()
    return bool(row and row[0])


def check_totp(user_id: str, code: str) -> bool:
    """Verify a TOTP code for login (does not change enabled state)."""
    if not PYOTP_AVAILABLE:
        return False
    conn = _get_conn()
    _ensure_table(conn)
    row = conn.execute(
        "SELECT totp_secret, enabled FROM admin_mfa_secrets WHERE user_id = ?",
        [user_id],
    ).fetchone()
    if not row or not row[1]:  # no secret or not enabled
        return False
    return pyotp.TOTP(row[0]).verify(code, valid_window=1)
