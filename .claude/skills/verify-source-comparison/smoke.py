"""
Smoke test for the multi-source news comparison engine — Issue #46.
Run: PYTHONPATH=. python3 .claude/skills/verify-source-comparison/smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import duckdb

# ── Helpers ──────────────────────────────────────────────────────────────────

_passed = 0
_failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    status = "\033[32mPASS\033[0m" if condition else "\033[31mFAIL\033[0m"
    suffix = f"  — {detail}" if detail and not condition else ""
    print(f"  {status}  {label}{suffix}")
    if condition:
        _passed += 1
    else:
        _failed += 1


# ── In-memory fixture DB ──────────────────────────────────────────────────────

def _build_db() -> duckdb.DuckDBPyConnection:
    db = duckdb.connect(":memory:")
    db.execute("""
        CREATE TABLE news_articles (
            id VARCHAR, title VARCHAR, url VARCHAR, content VARCHAR,
            publish_date TIMESTAMP, source VARCHAR, category VARCHAR,
            sentiment_score DOUBLE, sentiment_label VARCHAR
        );
        CREATE TABLE outlet_scores (
            source VARCHAR, source_type VARCHAR, score_date VARCHAR,
            frame_diversity DOUBLE, attribution_rate DOUBLE,
            stance_neutrality DOUBLE, composite_score DOUBLE,
            doc_count INTEGER, claim_count INTEGER, computed_at VARCHAR
        );
        CREATE TABLE outlet_clusters (
            source VARCHAR, source_type VARCHAR, cluster_id INTEGER,
            cluster_label VARCHAR, pca_x DOUBLE, pca_y DOUBLE,
            dominant_frame VARCHAR, doc_count INTEGER, computed_at VARCHAR
        );
        CREATE TABLE source_stances (
            source VARCHAR, source_type VARCHAR, topic VARCHAR,
            stance VARCHAR, confidence DOUBLE, document_count INTEGER,
            window_start VARCHAR, window_end VARCHAR, computed_at VARCHAR
        );
    """)
    db.executemany("INSERT INTO news_articles VALUES (?,?,?,?,?,?,?,?,?)", [
        ("a1", "Climate Change summit held", "u1", "Climate Change talks in Paris.", "2026-06-01 10:00:00", "BBC World", "Environment", 0.1, "neutral"),
        ("a2", "Climate Change: new pledges", "u2", "More Climate Change commitments.", "2026-06-02 10:00:00", "BBC World", "Environment", 0.4, "positive"),
        ("a3", "Climate Change threatens economy", "u3", "Critics warn of Climate Change costs.", "2026-06-03 10:00:00", "Fox News", "Environment", -0.5, "negative"),
        ("a4", "Climate Change: market panic", "u4", "Investors fear Climate Change rules.", "2026-06-04 10:00:00", "Fox News", "Environment", -0.3, "negative"),
        ("a5", "Climate Change action welcomed", "u5", "Scientists praise Climate Change steps.", "2026-06-05 10:00:00", "Guardian", "Environment", 0.7, "positive"),
        ("a6", "Climate Change bill passed", "u6", "Climate Change legislation passes.", "2026-06-06 10:00:00", "Guardian", "Environment", 0.5, "positive"),
        ("a7", "Climate Change youth march", "u7", "Young people protest Climate Change.", "2026-06-07 10:00:00", "Guardian", "Environment", 0.3, "positive"),
        ("a8", "Football results weekend",  "u8", "Weekend football roundup.",          "2026-06-01 10:00:00", "BBC Sport",  "Sports",      0.5, "positive"),
    ])
    db.executemany("INSERT INTO outlet_scores VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("BBC World", "news", "2026-06-01", 0.85, 0.90, 0.80, 0.85, 20, 5, "2026-06-01 00:00:00"),
        ("Fox News",  "news", "2026-06-01", 0.55, 0.60, 0.50, 0.55, 10, 2, "2026-06-01 00:00:00"),
        ("Guardian",  "news", "2026-06-01", 0.78, 0.82, 0.74, 0.78, 18, 4, "2026-06-01 00:00:00"),
    ])
    db.executemany("INSERT INTO outlet_clusters VALUES (?,?,?,?,?,?,?,?,?)", [
        ("BBC World", "news", 1, "centrist",      0.1, 0.2, "policy",   20, "2026-06-01"),
        ("Fox News",  "news", 2, "market-focused",-0.4, 0.1, "economic",10, "2026-06-01"),
        ("Guardian",  "news", 1, "centrist",      0.2, 0.3, "policy",   18, "2026-06-01"),
    ])
    db.executemany("INSERT INTO source_stances VALUES (?,?,?,?,?,?,?,?,?)", [
        ("BBC World", "news", "Climate Change", "neutral",    0.72, 2, "2026-05-01", "2026-06-01", "2026-06-01"),
        ("Fox News",  "news", "Climate Change", "skeptical",  0.68, 2, "2026-05-01", "2026-06-01", "2026-06-01"),
        ("Guardian",  "news", "Climate Change", "supportive", 0.81, 3, "2026-05-01", "2026-06-01", "2026-06-01"),
    ])
    return db


# ── Test run ──────────────────────────────────────────────────────────────────

def run() -> None:
    from src.nlp.source_comparator import (
        compare_sources,
        get_source_profile,
        list_source_trustworthiness,
    )

    db = _build_db()

    print("\nverify-source-comparison smoke test")
    print("=" * 50)

    # ── compare_sources ──────────────────────────────────────────────────────
    print("\n── compare_sources ─────────────────────────────────────────────────")
    result = compare_sources("Climate Change", db)

    sources = {c["source"] for c in result["comparison"]}
    check("BBC World found", "BBC World" in sources)
    check("Fox News found", "Fox News" in sources)
    check("Guardian found", "Guardian" in sources)
    check("BBC Sport excluded (no match)", "BBC Sport" not in sources)

    check("total_articles == 7", result["total_articles"] == 7, str(result["total_articles"]))
    check("sources_found == 3", result["sources_found"] == 3, str(result["sources_found"]))

    by_src = {c["source"]: c for c in result["comparison"]}

    check("BBC article_count == 2", by_src["BBC World"]["article_count"] == 2)
    check("Fox article_count == 2", by_src["Fox News"]["article_count"] == 2)
    check("Guardian article_count == 3", by_src["Guardian"]["article_count"] == 3)

    total_share = sum(c["coverage_share_pct"] for c in result["comparison"])
    check("coverage shares sum to ~100", abs(total_share - 100.0) < 0.5, f"{total_share:.1f}")

    check("BBC avg_sentiment > 0", (by_src["BBC World"]["avg_sentiment"] or 0) > 0,
          str(by_src["BBC World"]["avg_sentiment"]))
    check("Fox avg_sentiment < 0", (by_src["Fox News"]["avg_sentiment"] or 0) < 0,
          str(by_src["Fox News"]["avg_sentiment"]))
    check("Guardian avg_sentiment > 0", (by_src["Guardian"]["avg_sentiment"] or 0) > 0,
          str(by_src["Guardian"]["avg_sentiment"]))

    check("Fox dominant_sentiment == negative", by_src["Fox News"]["dominant_sentiment"] == "negative",
          by_src["Fox News"]["dominant_sentiment"])
    check("Guardian dominant_sentiment == positive", by_src["Guardian"]["dominant_sentiment"] == "positive",
          by_src["Guardian"]["dominant_sentiment"])

    check("BBC trust_scores populated", by_src["BBC World"]["trust_scores"] is not None)
    check("BBC composite_score ~0.85",
          abs((by_src["BBC World"]["trust_scores"] or {}).get("composite_score", 0) - 0.85) < 0.01,
          str(by_src["BBC World"]["trust_scores"]))

    check("BBC cluster label == centrist",
          (by_src["BBC World"]["cluster"] or {}).get("cluster_label") == "centrist",
          str(by_src["BBC World"]["cluster"]))

    check("Fox stance == skeptical", by_src["Fox News"]["stance"] == "skeptical",
          str(by_src["Fox News"]["stance"]))
    check("Guardian stance == supportive", by_src["Guardian"]["stance"] == "supportive",
          str(by_src["Guardian"]["stance"]))

    summary = result["summary"]
    check("most_positive_source == Guardian", summary.get("most_positive_source") == "Guardian",
          str(summary.get("most_positive_source")))
    check("most_negative_source == Fox News", summary.get("most_negative_source") == "Fox News",
          str(summary.get("most_negative_source")))
    check("most_trusted_source == BBC World", summary.get("most_trusted_source") == "BBC World",
          str(summary.get("most_trusted_source")))
    check("highest_coverage_source == Guardian", summary.get("highest_coverage_source") == "Guardian",
          str(summary.get("highest_coverage_source")))
    check("stance_spread contains supportive", "supportive" in summary.get("stance_spread", []),
          str(summary.get("stance_spread")))

    # Edge cases
    empty = compare_sources("", db)
    check("empty topic returns 0 articles", empty["total_articles"] == 0)

    nomatch = compare_sources("ZZZnonexistentZZZ", db)
    check("no-match topic returns empty comparison", nomatch["comparison"] == [])

    limited = compare_sources("Climate Change", db, limit=2)
    check("limit=2 respected", limited["sources_found"] <= 2)

    print("\n── get_source_profile ──────────────────────────────────────────────")
    profile = get_source_profile("BBC World", db)
    check("profile total_articles == 2", profile["total_articles"] == 2,
          str(profile["total_articles"]))
    check("profile trust_scores present", profile["trust_scores"] is not None)
    check("profile cluster present", profile["cluster"] is not None)
    check("profile stances present", len(profile["stances"]) >= 1,
          str(len(profile["stances"])))
    check("profile cluster_label == centrist",
          (profile["cluster"] or {}).get("cluster_label") == "centrist")

    unknown = get_source_profile("Unknown XYZ", db)
    check("unknown source returns 0 articles", unknown["total_articles"] == 0)
    check("unknown source trust_scores is None", unknown["trust_scores"] is None)

    print("\n── list_source_trustworthiness ─────────────────────────────────────")
    trust_rows = list_source_trustworthiness(db)
    check("returns 3 scored sources", len(trust_rows) == 3, str(len(trust_rows)))
    check("each row has composite_score", all("composite_score" in r for r in trust_rows))

    news_only = list_source_trustworthiness(db, source_type="news")
    check("news filter returns 3 rows", len(news_only) == 3, str(len(news_only)))

    blog_only = list_source_trustworthiness(db, source_type="blog")
    check("blog filter returns 0 rows", len(blog_only) == 0, str(len(blog_only)))

    no_scores = duckdb.connect(":memory:")
    no_scores.execute("""
        CREATE TABLE outlet_scores (source VARCHAR, source_type VARCHAR,
            score_date VARCHAR, frame_diversity DOUBLE, attribution_rate DOUBLE,
            stance_neutrality DOUBLE, composite_score DOUBLE,
            doc_count INTEGER, claim_count INTEGER, computed_at VARCHAR)
    """)
    empty_trust = list_source_trustworthiness(no_scores)
    check("empty scores table returns []", empty_trust == [])

    print(f"\n{'=' * 50}")
    print(f"Results: {_passed} passed, {_failed} failed")
    if _failed == 0:
        print("All checks passed.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    run()
