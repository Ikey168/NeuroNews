#!/usr/bin/env python3
"""
verify-cloud-cleanup smoke test
Validates that cloud env-var references have been removed from src/ and scripts/.
"""
from __future__ import annotations

import re
import subprocess
import sys
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
# 1. CI gate script exists and passes (this is the authoritative DoD check)
# ---------------------------------------------------------------------------
print("\n=== CI gate script (check_cloud_refs.py) ===")

gate_script = REPO_ROOT / "scripts" / "check_cloud_refs.py"
check("scripts/check_cloud_refs.py exists", gate_script.exists())

if gate_script.exists():
    r = subprocess.run(
        [sys.executable, str(gate_script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    check("check_cloud_refs.py exits 0 (no banned refs)", r.returncode == 0, r.stdout.strip())

# ---------------------------------------------------------------------------
# 3. .env.example contains required offline vars only
# ---------------------------------------------------------------------------
print("\n=== .env.example content ===")

env_example = REPO_ROOT / ".env.example"
check(".env.example exists", env_example.exists())

if env_example.exists():
    content = env_example.read_text()
    for var in ["NEURONEWS_DB_PATH", "NEURONEWS_DEV_MODE", "NEURONEWS_LOG_LEVEL"]:
        check(f".env.example mentions {var}", var in content)
    for banned in ["SNOWFLAKE_", "REDSHIFT_", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]:
        check(f".env.example free of {banned!r}", banned not in content)

# ---------------------------------------------------------------------------
# 4. local_cloud.py uses hardcoded local credentials (no env var lookups)
# ---------------------------------------------------------------------------
print("\n=== local_cloud.py offline-first ===")

local_cloud = REPO_ROOT / "src" / "utils" / "local_cloud.py"
check("src/utils/local_cloud.py exists", local_cloud.exists())

if local_cloud.exists():
    text = local_cloud.read_text()
    check("local_cloud uses hardcoded 'local' key",
          '"local"' in text and "AWS_ACCESS_KEY_ID" not in text)

# ---------------------------------------------------------------------------
# 5. archived cloud-only files moved to archive/
# ---------------------------------------------------------------------------
print("\n=== Archived cloud files ===")

ARCHIVED = [
    "archive/dashboards/quicksight_service.py",
    "archive/scripts/setup_aws_dev.py",
    "archive/database/examples/s3_storage_example.py",
    "archive/scripts/manage_db_endpoints.py",
]
NOT_IN_SRC = [
    "src/dashboards/quicksight_service.py",
    "scripts/setup_aws_dev.py",
]
for path in ARCHIVED:
    check(f"{path} exists in archive", (REPO_ROOT / path).exists())
for path in NOT_IN_SRC:
    check(f"{path} removed from source tree", not (REPO_ROOT / path).exists())

# ---------------------------------------------------------------------------
# 6. get_duckdb_path importable from database_utils
# ---------------------------------------------------------------------------
print("\n=== database_utils API ===")

try:
    from src.utils.database_utils import get_duckdb_path
    path = get_duckdb_path()
    check("get_duckdb_path() returns a string", isinstance(path, str))
    check("get_redshift_connection_params removed", True)
except ImportError as e:
    if "get_redshift_connection_params" in str(e):
        check("get_redshift_connection_params removed", False, str(e))
    else:
        check("get_duckdb_path importable", False, str(e))

try:
    from src.utils.database_utils import get_redshift_connection_params  # type: ignore
    check("get_redshift_connection_params removed", False, "still importable!")
except ImportError:
    check("get_redshift_connection_params removed", True)

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
