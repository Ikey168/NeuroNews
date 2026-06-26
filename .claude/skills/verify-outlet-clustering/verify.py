#!/usr/bin/env python3
"""
Smoke-test for the outlet editorial-framing cluster pipeline (#115).

Runs against synthetic frame vectors (no warehouse required) and prints
the cluster assignments + silhouette score.  Pass --live to query the real
local_warehouse.duckdb instead.

Exit 0 = PASS, 1 = FAIL.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np

LINE = "─" * 72


def run_synthetic():
    from src.argument_mining.outlet_clustering import OutletVector, run_clustering, FRAME_LABELS  # type: ignore[import]

    sources = [
        ("Bloomberg",             "news",       {"economic":0.72,"security":0.24,"humanitarian":0.12,"legal":0.15,"political":0.35,"scientific":0.20,"other":0.04}, 69),
        ("Reuters",               "news",       {"economic":0.61,"security":0.30,"humanitarian":0.18,"legal":0.19,"political":0.42,"scientific":0.16,"other":0.05}, 64),
        ("Financial Times",       "news",       {"economic":0.58,"security":0.26,"humanitarian":0.21,"legal":0.23,"political":0.47,"scientific":0.18,"other":0.06}, 68),
        ("The Guardian",          "news",       {"economic":0.34,"security":0.28,"humanitarian":0.46,"legal":0.24,"political":0.52,"scientific":0.22,"other":0.08}, 70),
        ("STAT News",             "news",       {"economic":0.22,"security":0.12,"humanitarian":0.38,"legal":0.14,"political":0.18,"scientific":0.44,"other":0.06}, 35),
        ("Wired",                 "news",       {"economic":0.30,"security":0.18,"humanitarian":0.14,"legal":0.12,"political":0.22,"scientific":0.55,"other":0.10}, 32),
        ("energy-transition.blog","blog",       {"economic":0.28,"security":0.14,"humanitarian":0.30,"legal":0.10,"political":0.36,"scientific":0.42,"other":0.18}, 32),
        ("Nature Climate Change", "paper",      {"economic":0.14,"security":0.08,"humanitarian":0.22,"legal":0.11,"political":0.10,"scientific":0.78,"other":0.04}, 58),
        ("IMF Working Papers",    "paper",      {"economic":0.82,"security":0.10,"humanitarian":0.16,"legal":0.20,"political":0.28,"scientific":0.34,"other":0.03}, 24),
        ("Energy Policy Podcast", "transcript", {"economic":0.44,"security":0.22,"humanitarian":0.18,"legal":0.24,"political":0.58,"scientific":0.28,"other":0.09}, 18),
    ]

    outlets = []
    for src, stype, frames, dc in sources:
        vec = np.array([frames.get(f, 0.0) for f in FRAME_LABELS], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        outlets.append(OutletVector(source=src, source_type=stype, doc_count=dc, vector=vec))

    matrix = np.stack([o.vector for o in outlets])
    return run_clustering(outlets, matrix, k_min=2, k_max=5)


def run_live():
    import os, duckdb
    from src.argument_mining.outlet_clustering import build_outlet_vectors, run_clustering  # type: ignore[import]

    db = os.environ.get("NEURONEWS_DB_PATH", str(REPO / "data" / "local_warehouse.duckdb"))
    conn = duckdb.connect(db, read_only=True)
    outlets, matrix = build_outlet_vectors(conn, date_range="90d")
    conn.close()
    if len(outlets) < 2:
        raise RuntimeError(f"only {len(outlets)} outlet(s) with frame data — run frame extraction first")
    return run_clustering(outlets, matrix, k_min=2, k_max=8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="Query real warehouse instead of synthetic data")
    args = ap.parse_args()

    print(LINE)
    print("  Outlet Clustering — smoke-test")
    print(LINE)

    mode = "live warehouse" if args.live else "synthetic vectors"
    print(f"  Mode: {mode}\n")

    try:
        result = run_live() if args.live else run_synthetic()
    except Exception as e:
        print(f"\n  FAIL: {e}")
        sys.exit(1)

    print(f"  k={result.k}  method={result.method}  silhouette={result.silhouette:.4f}"
          f"  outlets={result.n_outlets}")
    print()

    by_cluster: dict = {}
    for o in result.outlets:
        by_cluster.setdefault(o.cluster_id, []).append(o)

    for cid in sorted(by_cluster):
        members = by_cluster[cid]
        label = members[0].cluster_label
        dominant = members[0].dominant_frame
        print(f"  Cluster {cid} — {label}  (dominant: {dominant})")
        for m in members:
            print(f"    [{m.source_type:<12}] {m.source}  ({m.doc_count} docs)")
        print()

    # Validation checks
    errors = []
    if result.k < 2:
        errors.append(f"k={result.k} < 2 (too few clusters)")
    if result.silhouette < 0:
        errors.append(f"silhouette={result.silhouette:.4f} < 0 (clusters worse than random)")
    if result.n_outlets < 2:
        errors.append(f"n_outlets={result.n_outlets} < 2 (need more data)")

    # Each cluster should have at least one member
    for cid in range(result.k):
        if cid not in by_cluster:
            errors.append(f"cluster {cid} is empty")

    # PCA coords should not all be zero
    all_zero = all(abs(o.pca_x) < 1e-6 and abs(o.pca_y) < 1e-6 for o in result.outlets)
    if all_zero:
        errors.append("all PCA coordinates are zero — PCA failed")

    print(LINE)
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        sys.exit(1)
    else:
        print("  RESULT: PASS — clustering produced valid k-cluster assignment with PCA coords")
    print(LINE)


if __name__ == "__main__":
    main()
