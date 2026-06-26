# verify-source-comparison

Smoke-tests the multi-source news comparison engine (Issue #46) without
needing a running API server.

## What it tests

| Stage | What |
|-------|------|
| Coverage query | Articles correctly grouped and counted by source |
| Sentiment | avg_sentiment and dominant_sentiment match expected values |
| Trust scores | `frame_diversity`, `composite_score` populated from outlet_scores |
| Cluster | `cluster_label` joined from outlet_clusters |
| Stance | Per-topic stance joined from source_stances |
| Summary | most_positive/negative/trusted/coverage_source correct |
| Edge cases | Empty topic, no-match topic, limit parameter |
| Profile | `get_source_profile()` returns article count, trust scores, stances |
| Trustworthiness list | `list_source_trustworthiness()` filters by source_type |

## Usage

```bash
# From repo root:
PYTHONPATH=. python3 .claude/skills/verify-source-comparison/smoke.py
```

Expected: all checks pass, exit 0.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `ModuleNotFoundError: duckdb` | `pip install duckdb` |
| `BinderException: Cannot compare VARCHAR and TIMESTAMP` | `computed_at` column is not a valid timestamp string in the test fixture |
| Wrong sentiment sign | Check `avg_sentiment` computation — negative scores for negative articles |
| 0 sources found | ILIKE pattern not matching — check topic keyword vs. article title/content |
