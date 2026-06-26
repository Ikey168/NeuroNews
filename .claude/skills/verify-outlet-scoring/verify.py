#!/usr/bin/env python3
"""
Smoke-test for the outlet transparency scoring pipeline (#116).

Validates scoring formulas and (optionally) runs against the live warehouse.

Exit 0 = PASS, 1 = FAIL.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

LINE = "─" * 72


def run_unit_tests():
    from src.argument_mining.outlet_scorer import _shannon_entropy, FRAME_LABELS  # type: ignore[import]

    results = []

    # 1. Balanced 7-frame distribution => diversity = 1.0
    balanced = {f: 1.0 for f in FRAME_LABELS}
    d = _shannon_entropy(balanced, 7)
    ok = abs(d - 1.0) < 1e-5
    results.append(("balanced 7-frame entropy = 1.0", ok, f"{d:.4f}"))

    # 2. Fully concentrated => entropy = 0.0
    conc = {f: (1.0 if f == "economic" else 0.0) for f in FRAME_LABELS}
    d2 = _shannon_entropy(conc, 7)
    ok2 = abs(d2 - 0.0) < 1e-5
    results.append(("concentrated entropy = 0.0", ok2, f"{d2:.4f}"))

    # 3. Equal 4-stance distribution => neutrality = 1.0
    equal_s = {"supportive": 1.0, "critical": 1.0, "neutral": 1.0, "ambiguous": 1.0}
    s = _shannon_entropy(equal_s, 4)
    ok3 = abs(s - 1.0) < 1e-5
    results.append(("equal stance entropy = 1.0", ok3, f"{s:.4f}"))

    # 4. Partial distribution stays in (0, 1)
    partial = {"economic": 0.7, "political": 0.4, "security": 0.3, "humanitarian": 0.1,
               "legal": 0.0, "scientific": 0.0, "other": 0.0}
    p = _shannon_entropy(partial, 7)
    ok4 = 0 < p < 1
    results.append((f"partial 4-frame entropy ∈ (0,1) = {p:.4f}", ok4, ""))

    # 5. Empty dict => 0.0
    e = _shannon_entropy({}, 7)
    ok5 = abs(e - 0.0) < 1e-5
    results.append(("empty dict entropy = 0.0", ok5, f"{e:.4f}"))

    return results


def run_live():
    import os, duckdb
    from src.argument_mining.outlet_scorer import compute_outlet_scores  # type: ignore[import]

    db = os.environ.get("NEURONEWS_DB_PATH", str(REPO / "data" / "local_warehouse.duckdb"))
    conn = duckdb.connect(db, read_only=True)
    rows = compute_outlet_scores(conn, date_range="90d")
    conn.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="Also run against live warehouse")
    args = ap.parse_args()

    print(LINE)
    print("  Outlet Transparency Scoring — smoke-test")
    print(LINE)

    # Unit tests
    print("\n  Unit tests:")
    unit = run_unit_tests()
    all_ok = True
    for desc, ok, val in unit:
        status = "PASS" if ok else "FAIL"
        suffix = f"  ({val})" if val else ""
        print(f"    [{status}] {desc}{suffix}")
        if not ok:
            all_ok = False

    if args.live:
        print("\n  Live warehouse scores:")
        try:
            rows = run_live()
        except Exception as e:
            print(f"    [FAIL] {e}")
            all_ok = False
            rows = []

        if rows:
            header = f"  {'Rank':>4}  {'Source':<30} {'Score':>6}  {'Div':>5}  {'Attr':>5}  {'Neut':>5}"
            print(f"\n{header}")
            print("  " + "─" * (len(header) - 2))
            for i, r in enumerate(rows[:15], 1):
                print(
                    f"  {i:>4}  {r.source:<30} "
                    f"{r.composite_score:>6.3f}  "
                    f"{r.frame_diversity:>5.3f}  "
                    f"{r.attribution_rate:>5.3f}  "
                    f"{r.stance_neutrality:>5.3f}"
                )
        else:
            print("    (no outlets with sufficient data — run frame extraction first)")

    print()
    print(LINE)
    if all_ok:
        print("  RESULT: PASS")
    else:
        print("  RESULT: FAIL")
    print(LINE)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
