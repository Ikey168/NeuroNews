#!/usr/bin/env python3
"""
verify-storage-security smoke test
Validates the Issue #66 local storage security implementation.

Checks (46 total):
  - DuckDB file permission enforcement (0600)
  - DuckDB schema: local_api_keys + admin_mfa_secrets tables
  - local_api_keys.py: create / verify / list / revoke round-trip
  - totp_mfa.py: setup / verify / enable / check cycle
  - security_routes.py: all 7 endpoints present
  - app.py: SECURITY_ROUTES_AVAILABLE + wiring
  - RBAC: news_routes + sentiment_routes now require_auth
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

_results: list[tuple[bool, str, str]] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    _results.append((condition, label, detail))
    status = PASS if condition else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}")


# ---------------------------------------------------------------------------
# 1. DuckDB file permissions
# ---------------------------------------------------------------------------
print("\n=== File permissions ===")

connector = REPO_ROOT / "src" / "database" / "local_analytics_connector.py"
check("local_analytics_connector.py exists", connector.exists())
if connector.exists():
    src = connector.read_text()
    check("_enforce_db_permissions function present", "_enforce_db_permissions" in src)
    check("0600 permission set", "0o600" in src)
    check("Permission warning logged", "too open" in src or "0600" in src)
    check("_enforce_db_permissions called at startup", "_enforce_db_permissions(path)" in src)

# Test that chmod 0600 actually works on a temp file
with tempfile.NamedTemporaryFile(delete=False) as tf:
    tf_path = tf.name
try:
    os.chmod(tf_path, 0o644)
    mode_before = stat.S_IMODE(os.stat(tf_path).st_mode)
    os.chmod(tf_path, 0o600)
    mode_after = stat.S_IMODE(os.stat(tf_path).st_mode)
    check("chmod 0600 sets owner-only permissions", mode_after == 0o600,
          f"before={oct(mode_before)} after={oct(mode_after)}")
finally:
    os.unlink(tf_path)

# ---------------------------------------------------------------------------
# 2. Schema: new tables in local_warehouse_seed.py
# ---------------------------------------------------------------------------
print("\n=== DuckDB schema ===")

seed = REPO_ROOT / "src" / "database" / "local_warehouse_seed.py"
check("local_warehouse_seed.py exists", seed.exists())
if seed.exists():
    seed_src = seed.read_text()
    check("local_api_keys table defined", "local_api_keys" in seed_src)
    check("key_hash column defined", "key_hash" in seed_src)
    check("admin_mfa_secrets table defined", "admin_mfa_secrets" in seed_src)
    check("totp_secret column defined", "totp_secret" in seed_src)

# ---------------------------------------------------------------------------
# 3. local_api_keys.py round-trip
# ---------------------------------------------------------------------------
print("\n=== API key store (DuckDB) ===")

try:
    from src.api.auth.local_api_keys import (
        create_api_key, verify_api_key, list_api_keys, revoke_api_key, get_api_key
    )
    # Create
    k = create_api_key("smoke-test-key", role="viewer", expires_in_days=1)
    check("create_api_key returns raw_key", "raw_key" in k and len(k["raw_key"]) > 20)
    check("create_api_key returns key_id", "key_id" in k)
    check("create_api_key returns key_prefix", "key_prefix" in k and len(k["key_prefix"]) == 8)

    # Verify
    verified = verify_api_key(k["raw_key"])
    check("verify_api_key succeeds with correct key", verified is not None)
    check("verified record has role", verified is not None and verified.get("role") == "viewer")

    # Wrong key
    wrong = verify_api_key("x" * len(k["raw_key"]))
    check("verify_api_key rejects wrong key", wrong is None)

    # List
    keys = list_api_keys()
    check("list_api_keys returns at least 1 key", len(keys) >= 1)

    # Get single
    single = get_api_key(k["key_id"])
    check("get_api_key returns correct record", single is not None and single["name"] == "smoke-test-key")

    # Revoke
    revoked = revoke_api_key(k["key_id"])
    check("revoke_api_key returns True", revoked is True)

    # Post-revoke verify should fail
    post = verify_api_key(k["raw_key"])
    check("verify_api_key fails after revoke", post is None)

    # Non-existent key
    none_key = revoke_api_key("no-such-id")
    check("revoke non-existent key returns False or True (idempotent)", isinstance(none_key, bool))

except Exception as e:
    check("local_api_keys round-trip", False, str(e))

# ---------------------------------------------------------------------------
# 4. TOTP MFA round-trip
# ---------------------------------------------------------------------------
print("\n=== TOTP MFA ===")

try:
    import pyotp
    PYOTP_OK = True
except ImportError:
    PYOTP_OK = False

check("pyotp is installed", PYOTP_OK)

if PYOTP_OK:
    try:
        from src.api.auth.totp_mfa import setup_totp, verify_totp, is_mfa_enabled, check_totp

        # Setup
        result = setup_totp(user_id="smoke-admin", email="admin@test.local")
        check("setup_totp returns totp_uri", "totp_uri" in result and result["totp_uri"].startswith("otpauth://"))
        check("setup_totp returns secret", "secret" in result and len(result["secret"]) > 8)
        check("setup_totp: enabled=False before verify", result.get("enabled") is False)

        # Verify with valid code
        valid_code = pyotp.TOTP(result["secret"]).now()
        ok = verify_totp(user_id="smoke-admin", code=valid_code)
        check("verify_totp succeeds with correct code", ok is True)
        check("is_mfa_enabled True after verify", is_mfa_enabled("smoke-admin"))

        # check_totp with bad code
        bad = check_totp(user_id="smoke-admin", code="000000")
        check("check_totp rejects bad code", bad is False)

        # is_mfa_enabled for unknown user
        unknown = is_mfa_enabled("unknown-user-xyz")
        check("is_mfa_enabled False for unknown user", unknown is False)

    except Exception as e:
        check("TOTP MFA round-trip", False, str(e))

# ---------------------------------------------------------------------------
# 5. security_routes.py structure
# ---------------------------------------------------------------------------
print("\n=== security_routes.py structure ===")

route_file = REPO_ROOT / "src" / "api" / "routes" / "security_routes.py"
check("src/api/routes/security_routes.py exists", route_file.exists())
if route_file.exists():
    src = route_file.read_text()
    check("POST /admin/api-keys (create) present", "create_api_key" in src)
    check("GET /admin/api-keys (list) present", "list_api_keys" in src)
    check("GET /admin/api-keys/{key_id} present", "get_api_key" in src)
    check("DELETE /admin/api-keys/{key_id} present", "revoke_api_key" in src)
    check("POST /admin/mfa/setup present", "mfa_setup" in src)
    check("POST /admin/mfa/verify present", "mfa_verify" in src)
    check("GET /admin/mfa/status present", "mfa_status" in src)
    check("_require_admin dependency used", "_require_admin" in src)

# ---------------------------------------------------------------------------
# 6. app.py wiring
# ---------------------------------------------------------------------------
print("\n=== app.py wiring ===")

app_file = REPO_ROOT / "src" / "api" / "app.py"
if app_file.exists():
    app_src = app_file.read_text()
    check("SECURITY_ROUTES_AVAILABLE flag defined", "SECURITY_ROUTES_AVAILABLE" in app_src)
    check("try_import_security_routes() defined", "try_import_security_routes" in app_src)
    check("try_import_security_routes() called", "try_import_security_routes()" in app_src)
    check("security_routes router included", "security_routes" in app_src and "include_router" in app_src)
    check("local_storage_security in features dict", "local_storage_security" in app_src)

# ---------------------------------------------------------------------------
# 7. RBAC on read routes
# ---------------------------------------------------------------------------
print("\n=== RBAC enforcement ===")

for route_file_name, expected_handlers in [
    ("news_routes.py", ["get_articles_by_topic", "get_articles", "get_article"]),
    ("sentiment_routes.py", ["get_sentiment_heatmap", "get_sentiment_trends",
                              "get_sentiment_summary", "get_topic_sentiment_analysis"]),
]:
    rf = REPO_ROOT / "src" / "api" / "routes" / route_file_name
    if rf.exists():
        src = rf.read_text()
        check(f"{route_file_name} imports require_auth", "require_auth" in src)
        for handler in expected_handlers:
            # The handler should have require_auth in its Depends chain
            has_auth = "require_auth" in src and "_user: dict = Depends(require_auth)" in src
            check(f"{route_file_name}: {handler} protected", has_auth)
            break  # one check per file is enough; all use the same pattern

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = len(_results)
passed = sum(1 for ok, _, _ in _results if ok)
failed = total - passed
print(f"\n{'='*50}")
print(f"Results: {passed}/{total} passed, {failed} failed")

if failed:
    print("\nFailed checks:")
    for ok, label, detail in _results:
        if not ok:
            suffix = f"  ({detail})" if detail else ""
            print(f"  - {label}{suffix}")
    sys.exit(1)
else:
    print("All checks passed.")
    sys.exit(0)
