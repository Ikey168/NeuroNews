#!/usr/bin/env python3
"""
Smoke test for Issue #334: Local resource monitoring.

Verifies psutil sampling, DuckDB persistence, query helpers, Prometheus
formatter, and the API routes (import only — no running server needed).

Run from the repo root:
    PYTHONPATH=. python3 .claude/skills/verify-resource-monitor/smoke.py

Exit 0 → all checks pass.  Exit 1 → at least one failure.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    _results.append((label, condition, detail))
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


# ---------------------------------------------------------------------------
# Mock psutil helpers
# ---------------------------------------------------------------------------

_CPU = 20.0
_MEM_PCT = 55.0
_MEM_RSS = 64 * 1024 * 1024  # 64 MB
_DISK_USED = 40 * (1024 ** 3)
_DISK_FREE = 300 * (1024 ** 3)
_DISK_PCT = 12.5


def _mock_psutil():
    import psutil

    vm = MagicMock()
    vm.percent = _MEM_PCT

    proc = MagicMock()
    proc.name.return_value = "smoke-test"
    proc.memory_info.return_value = MagicMock(rss=_MEM_RSS)

    disk = MagicMock()
    disk.used = _DISK_USED
    disk.free = _DISK_FREE
    disk.percent = _DISK_PCT

    return patch.multiple(
        "src.monitoring.resource_monitor",
        psutil=MagicMock(
            cpu_percent=MagicMock(return_value=_CPU),
            virtual_memory=MagicMock(return_value=vm),
            Process=MagicMock(return_value=proc),
            disk_usage=MagicMock(return_value=disk),
            NoSuchProcess=psutil.NoSuchProcess,
            AccessDenied=psutil.AccessDenied,
        ),
    )


# ---------------------------------------------------------------------------
# Run checks
# ---------------------------------------------------------------------------

import duckdb

section("1. Module imports")
try:
    from src.monitoring.resource_monitor import (
        COLLECT_INTERVAL_SECONDS,
        SCHEMA_SQL,
        collect_and_store,
        collect_sample,
        ensure_schema,
        get_metrics,
        get_summary,
        start_background_collector,
        store_sample,
    )
    check("resource_monitor imports", True)
except ImportError as e:
    check("resource_monitor imports", False, str(e))
    sys.exit(1)

try:
    from src.api.routes.metrics_routes import _to_prometheus, router
    check("metrics_routes imports", True)
except ImportError as e:
    check("metrics_routes imports", False, str(e))
    sys.exit(1)

check("COLLECT_INTERVAL_SECONDS is 60", COLLECT_INTERVAL_SECONDS == 60)
check("SCHEMA_SQL mentions resource_metrics", "resource_metrics" in SCHEMA_SQL)

# ---------------------------------------------------------------------------
section("2. collect_sample (mocked psutil)")

with _mock_psutil():
    rows = collect_sample()

check("returns 6 metric dicts", len(rows) == 6)
names = {r["metric_name"] for r in rows}
for expected in ["cpu_percent", "memory_percent", "memory_rss_mb",
                 "disk_used_gb", "disk_free_gb", "disk_percent"]:
    check(f"metric '{expected}' present", expected in names)

cpu = next(r for r in rows if r["metric_name"] == "cpu_percent")
check("cpu_percent value matches mock", abs(cpu["value"] - _CPU) < 0.01)
check("cpu_percent unit is '%'", cpu["unit"] == "%")

rss = next(r for r in rows if r["metric_name"] == "memory_rss_mb")
check("memory_rss_mb converted to MB", abs(rss["value"] - 64.0) < 0.1)
check("memory_rss_mb pid is set", rss["pid"] is not None)
check("memory_rss_mb process_name is set", rss["process_name"] == "smoke-test")

disk_used = next(r for r in rows if r["metric_name"] == "disk_used_gb")
check("disk_used_gb value correct", abs(disk_used["value"] - 40.0) < 0.01)
check("disk_used_gb unit is 'GB'", disk_used["unit"] == "GB")

for r in rows:
    check(f"sampled_at is datetime for {r['metric_name']}", isinstance(r["sampled_at"], datetime))

# ---------------------------------------------------------------------------
section("3. DuckDB schema + persistence")

db = duckdb.connect(":memory:")
ensure_schema(db)
tables = {t[0] for t in db.execute("SHOW TABLES").fetchall()}
check("resource_metrics table created", "resource_metrics" in tables)

with _mock_psutil():
    sample_rows = collect_sample()
store_sample(db, sample_rows)
count = db.execute("SELECT COUNT(*) FROM resource_metrics").fetchone()[0]
check("6 rows stored after one sample", count == 6)

all_ids = [r[0] for r in db.execute("SELECT id FROM resource_metrics").fetchall()]
check("all ids are unique UUIDs", len(set(all_ids)) == 6)

# Second sample
with _mock_psutil():
    sample_rows2 = collect_sample()
store_sample(db, sample_rows2)
count2 = db.execute("SELECT COUNT(*) FROM resource_metrics").fetchone()[0]
check("12 rows after two samples", count2 == 12)

# ---------------------------------------------------------------------------
section("4. get_metrics query helper")

all_m = get_metrics(db)
check("get_metrics returns 12 rows", len(all_m) == 12)

cpu_m = get_metrics(db, metric_name="cpu_percent")
check("filter by metric_name=cpu_percent → 2 rows", len(cpu_m) == 2)

limited = get_metrics(db, n=3)
check("n=3 limits result to 3", len(limited) == 3)

windowed = get_metrics(db, since_minutes=60)
check("since_minutes=60 includes recent rows", len(windowed) == 12)

empty_db = duckdb.connect(":memory:")
ensure_schema(empty_db)
check("empty table returns []", get_metrics(empty_db) == [])

row0 = all_m[0]
for key in ["sampled_at", "metric_name", "value", "unit"]:
    check(f"row has field '{key}'", key in row0)

# ---------------------------------------------------------------------------
section("5. get_summary")

summary = get_summary(db)
check("summary has '1h' key", "1h" in summary)
check("summary has '24h' key", "24h" in summary)
check("summary has 'sampled_at' key", "sampled_at" in summary)

cpu_1h = summary["1h"].get("cpu_percent")
check("cpu_percent in 1h window", cpu_1h is not None)
if cpu_1h:
    check("cpu_percent avg matches mock", abs(cpu_1h["avg"] - _CPU) < 0.1)
    check("cpu_percent unit is '%'", cpu_1h["unit"] == "%")
    check("cpu_percent has min/max keys", "min" in cpu_1h and "max" in cpu_1h)

# Average across two different values
db2 = duckdb.connect(":memory:")
ensure_schema(db2)
now = datetime.now(timezone.utc)
db2.executemany(
    "INSERT INTO resource_metrics VALUES (?, ?, ?, ?, ?, ?, ?)",
    [
        (str(uuid.uuid4()), now, "cpu_percent", 10.0, "%", None, None),
        (str(uuid.uuid4()), now, "cpu_percent", 30.0, "%", None, None),
    ],
)
s2 = get_summary(db2)
check("avg of 10+30 is 20", abs(s2["1h"]["cpu_percent"]["avg"] - 20.0) < 0.01)

empty_db2 = duckdb.connect(":memory:")
ensure_schema(empty_db2)
empty_s = get_summary(empty_db2)
check("empty DB summary 1h is {}", empty_s["1h"] == {})
check("empty DB summary 24h is {}", empty_s["24h"] == {})

# ---------------------------------------------------------------------------
section("6. collect_and_store (integration)")

db3 = duckdb.connect(":memory:")
ensure_schema(db3)
with _mock_psutil():
    returned = collect_and_store(db3)
check("collect_and_store returns 6 rows", len(returned) == 6)
check("rows persisted to DB", db3.execute("SELECT COUNT(*) FROM resource_metrics").fetchone()[0] == 6)

# ---------------------------------------------------------------------------
section("7. Prometheus text formatter")

prom_rows = [
    {"metric_name": "cpu_percent", "value": 15.0, "unit": "%",
     "sampled_at": "x", "process_name": None, "pid": None},
    {"metric_name": "memory_rss_mb", "value": 64.0, "unit": "MB",
     "sampled_at": "x", "process_name": "uvicorn", "pid": 9999},
]
prom_text = _to_prometheus(prom_rows)

check("Prometheus output ends with newline", prom_text.endswith("\n"))
check("HELP line for cpu_percent", "# HELP neuronews_cpu_percent" in prom_text)
check("TYPE line for cpu_percent", "# TYPE neuronews_cpu_percent gauge" in prom_text)
check("value line for cpu_percent", "neuronews_cpu_percent 15.0" in prom_text)
check("process label for memory_rss_mb", 'process="uvicorn"' in prom_text)
check("pid label for memory_rss_mb", 'pid="9999"' in prom_text)

# ---------------------------------------------------------------------------
section("8. FastAPI router")

routes = {getattr(r, "path", None) for r in router.routes}
check("/metrics route registered", "/metrics" in routes)
check("/metrics/summary route registered", "/metrics/summary" in routes)
check("/metrics/current route registered", "/metrics/current" in routes)

# ---------------------------------------------------------------------------
section("9. Background collector guard")

# Verify start_background_collector is idempotent (won't crash when called twice
# in a test context — though it won't actually start the thread here).
import src.monitoring.resource_monitor as _rm
original = _rm._collector_started
_rm._collector_started = True  # pretend already started
try:
    start_background_collector()  # should return without starting a second thread
    check("idempotent start guard works", True)
except Exception as exc:
    check("idempotent start guard works", False, str(exc))
finally:
    _rm._collector_started = original

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

passed = sum(1 for _, ok, _ in _results if ok)
total = len(_results)
print(f"\n{'='*50}")
print(f"Results: {passed}/{total} checks passed")
if passed < total:
    print("\nFailed checks:")
    for label, ok, detail in _results:
        if not ok:
            print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))
    sys.exit(1)
else:
    print("All checks passed.")
    sys.exit(0)
