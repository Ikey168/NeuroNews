# Test Suite Stabilization Plan

The `Test & Quality Checks` CI gate runs the full `tests/` suite, which carries
a large backlog of pre-existing failures left over from the repository
reorganization: the tests were written against earlier versions of the code
whose APIs have since changed. This is a dedicated, incremental effort to bring
the suite back to green, tracked on the `claude/test-suite-repair` branch.

This file is the working plan: baseline, methodology, and the prioritized
cluster list. Update the progress log as clusters are fixed.

## Baseline (full local run)

```
5749 tests | 4257 passed | 1014 failed | 278 collection errors | 200 skipped
```

Failure exception mix (root-cause signal — overwhelmingly test/source API drift):

| Exception | Count | Typical cause |
|---|---:|---|
| AttributeError | 196 | test calls a method/attribute the source no longer has, or a wrong `patch()` target |
| TypeError | 164 | changed function/constructor signature (renamed/removed kwargs) |
| AssertionError | 111 | expected value no longer matches current behavior |
| ModuleNotFoundError | 38 | import of a moved/renamed module |
| NameError | 32 | symbol used but never imported (missing import) |
| KeyError / ValueError / other | ~30 | assorted drift |

`133` distinct test files fail; the top ~30 account for ~60% of failures.

## Running the suite locally

The repo's Debian system Python conflicts with `pip` (RECORD-less packages),
so use a clean virtualenv:

```bash
python3 -m venv /tmp/venv
/tmp/venv/bin/pip install -U pip wheel setuptools
/tmp/venv/bin/pip install -r requirements.txt
/tmp/venv/bin/pip install pytest pytest-cov pytest-asyncio pytest-timeout httpx
# torchcodec needs FFmpeg libs that may be unavailable; drop it so its import is a no-op
/tmp/venv/bin/pip uninstall -y torchcodec
```

Run a single file (fast iteration):

```bash
/tmp/venv/bin/python -m pytest <path> -q -p no:cacheprovider \
  --timeout=60 --timeout-method=signal --tb=short
```

The CI gate also `--ignore`s a set of modules that need optional feature
dependencies (snowflake / qdrant / AWS-quicksight / scraper connectors); see
`.github/workflows/ci-cd-pipeline.yml`.

## Methodology (rules)

1. **Align tests with the *current* source API** — the source is the source of
   truth unless it is genuinely buggy.
2. **Never weaken a test to make it pass** — no blanket `try/except`, no
   trivially-true assertions, no deleting assertions. If behavior changed, find
   the *correct* new expectation from the source.
3. **Fix the source only when it is genuinely wrong** (a real bug), and keep
   such changes minimal and isolated.
4. **A genuinely obsolete test** (the feature it covers was intentionally
   removed) may be deleted — with a one-line reason in the commit.
5. **Optional-dependency imports** (e.g. `openai`) must be guarded so they never
   crash module import/collection.
6. Verify each file passes in the venv before moving on.

## Common fix patterns observed

- Missing imports → add `from <module> import <Symbol>` for symbols the file uses.
- Wrong `patch()` target → patch where a symbol is *looked up*, not where it is
  defined (e.g. a lazily-imported `services.rag.vector.VectorSearchService`, not
  `services.vector_service.VectorSearchService`).
- Renamed kwargs → e.g. `QueryFilter(property=...)` → `property_name=...`.
- Removed helper methods / changed return types → rewrite the test against the
  current API (may be a substantial per-file rewrite).

## Prioritized clusters (top failing files)

| Failures | File | Status |
|---:|---|---|
| 22→ | tests/unit/services/test_vector_services_comprehensive.py | in progress (43→21) |
| 70 | tests/unit/api/graph/test_queries.py | todo — needs rewrite vs current GraphQueries |
| 43 | tests/unit/api/graph/test_traversal.py | todo |
| 43 | tests/api/test_comprehensive_routes.py | todo |
| 40 | tests/api/graph/test_export.py | todo |
| 37 | tests/api/routes/test_enhanced_coverage.py | todo |
| 26 | tests/security/test_audit_log.py | todo |
| 22 | tests/unit/database/test_database_integration_comprehensive.py | todo |
| 22 | tests/unit/database/integration/test_database_integration_comprehensive.py | todo |
| 21 | tests/unit/scraper/test_async_scraper_engine.py | todo |
| 19 | tests/unit/api/test_knowledge_graph_api.py | todo |
| 19 | tests/api/routes/test_error_validation.py | todo |
| 18 | tests/security/test_waf_middleware.py | todo |
| 17 | tests/ingestion/test_blog_connector.py | todo |
| 17 | tests/api/graph/test_optimized_api_100.py | todo |

…plus ~118 more files with smaller counts. Work top-down; subsystem clusters
(graph API, database, security, api/routes) tend to share root causes within a
subsystem.

## Known source bugs surfaced while repairing (fix separately)

- `src/scraper/async_scraper_engine.py`: `get_article_links_http` calls
  `self.extract_links_from_html(...)`, which is never defined anywhere — any
  real HTTP scrape reaching link extraction raises `AttributeError`.
- `src/api/graph/queries.py:298` (`execute_relationship_query`): references the
  gremlin anonymous-traversal alias `__`, which is never imported at module
  scope, so the default `include_properties=True` path raises
  `NameError: name '__' is not defined`. Fix: `from gremlin_python.process.graph_traversal import __`.

## Progress log

- **vector_services_comprehensive**: added missing source imports, made the
  optional `OpenAIBackend` import non-fatal, and corrected `patch()` targets
  (`services.vector_service.VectorSearchService` →
  `services.rag.vector.VectorSearchService`). 43 → 21 failures (remaining 21 are
  more lazy-import patch-target fixes; routed to a later batch).
- **ingestion/test_blog_connector**: guarded the optional `feedparser` import
  (not a declared dependency) with skipif. 17 → 0 (38 pass, 17 skip).
- **security/test_audit_log**: realigned to the rewritten local-file logger
  (AWS CloudWatch integration was removed); replaced removed-method tests with
  the current convenience methods. 26 → 0 (25 pass).
- **unit/scraper/test_async_scraper_engine**: realigned renamed methods /
  signatures (PerformanceMonitor, parse_article_html, validate_article); removed
  9 tests for genuinely-removed helpers. 21 → 0 (14 pass).
</content>
