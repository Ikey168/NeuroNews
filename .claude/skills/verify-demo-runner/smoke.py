#!/usr/bin/env python3
"""
verify-demo-runner smoke test — Issue #298.

Checks (25 total):
  - data/demo/articles.json exists and is valid
  - Article diversity: 3+ distinct sources, 3+ distinct categories
  - scripts/demo.py exists and has correct structure
  - Makefile demo + demo-api targets present
  - Full pipeline run completes in < 120s (--no-kg for speed)
  - Pipeline output contains expected sections
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
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
# 1. Demo dataset
# ---------------------------------------------------------------------------
print("\n=== Demo dataset (data/demo/articles.json) ===")

demo_file = REPO_ROOT / "data" / "demo" / "articles.json"
check("data/demo/articles.json exists", demo_file.exists())

articles = []
if demo_file.exists():
    try:
        articles = json.loads(demo_file.read_text())
        check("articles.json is valid JSON", True)
    except Exception as e:
        check("articles.json is valid JSON", False, str(e))

check("at least 10 articles bundled", len(articles) >= 10, f"got {len(articles)}")
check("at most 20 articles bundled", len(articles) <= 20, f"got {len(articles)}")

if articles:
    sources = {a.get("source") for a in articles}
    cats = {a.get("category") for a in articles}
    check("3+ distinct sources", len(sources) >= 3, f"sources={sources}")
    check("3+ distinct categories", len(cats) >= 3, f"cats={cats}")

    required_cats = {"Technology", "Politics", "Science"}
    has_required = required_cats.issubset(cats)
    check("Technology, Politics, Science categories present", has_required,
          f"missing={required_cats - cats}")

    for field in ("id", "title", "content", "source", "category", "url"):
        all_have = all(field in a for a in articles)
        check(f"all articles have '{field}' field", all_have)

    ids = [a.get("id", "") for a in articles]
    check("all article ids start with 'demo-'", all(i.startswith("demo-") for i in ids))

# ---------------------------------------------------------------------------
# 2. scripts/demo.py structure
# ---------------------------------------------------------------------------
print("\n=== scripts/demo.py structure ===")

demo_script = REPO_ROOT / "scripts" / "demo.py"
check("scripts/demo.py exists", demo_script.exists())

if demo_script.exists():
    src = demo_script.read_text()
    check("ingest_articles() defined", "def ingest_articles(" in src)
    check("run_sentiment() defined", "def run_sentiment(" in src)
    check("run_claim_extraction() defined", "def run_claim_extraction(" in src)
    check("run_outlet_scoring() defined", "def run_outlet_scoring(" in src)
    check("run_kg_update() defined", "def run_kg_update(" in src)
    check("print_summary() defined", "def print_summary(" in src)
    check("--open-api flag defined", "--open-api" in src)
    check("--reset flag defined", "--reset" in src)
    check("--no-kg flag defined", "--no-kg" in src)
    check("uses get_shared_connection", "get_shared_connection" in src)
    check("loads from data/demo/", "data/demo" in src or "DEMO_ARTICLES_FILE" in src)

# ---------------------------------------------------------------------------
# 3. Makefile targets
# ---------------------------------------------------------------------------
print("\n=== Makefile ===")

makefile = REPO_ROOT / "Makefile"
check("Makefile exists", makefile.exists())

if makefile.exists():
    mk = makefile.read_text()
    check("'make demo' target defined", "\ndemo:" in mk)
    check("'make demo-api' target defined", "\ndemo-api:" in mk)
    check("demo target runs scripts/demo.py", "scripts/demo.py" in mk)
    check("demo listed in .PHONY", "demo" in mk.split(".PHONY")[1].split("\n")[0])

# ---------------------------------------------------------------------------
# 4. End-to-end pipeline run
# ---------------------------------------------------------------------------
print("\n=== End-to-end pipeline run ===")

t0 = time.time()
result = subprocess.run(
    [sys.executable, str(demo_script), "--no-kg", "--reset"],
    capture_output=True,
    text=True,
    cwd=str(REPO_ROOT),
    timeout=180,
)
elapsed = time.time() - t0

check("demo.py exits with code 0", result.returncode == 0,
      f"rc={result.returncode}\n{result.stderr[-400:] if result.stderr else ''}")
check("completes in < 120 seconds", elapsed < 120, f"{elapsed:.1f}s")

out = result.stdout + result.stderr
check("'Articles ingested' in output", "Articles ingested" in out)
check("'Sentiment breakdown' in output", "Sentiment breakdown" in out)
check("'Claims extracted' in output", "Claims extracted" in out)
check("'Outlet scores' in output", "Outlet scores" in out or "outlet" in out.lower())
check("'Pipeline time' in output", "Pipeline time" in out)

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
