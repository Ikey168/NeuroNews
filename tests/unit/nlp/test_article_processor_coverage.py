"""Coverage tests for src/nlp/article_processor.py.

Targets the uncovered lines of ``ArticleProcessor``: analyzer-init failure,
database initialisation (success + failure), result storage (success + failure)
and the full ``process_articles`` orchestration path.

All external I/O is mocked:
* ``create_analyzer`` (so no sentiment model / AWS client is built)
* ``psycopg2.connect`` (so no real database is contacted)

These complement the multi-language tests, which only touch the base
``ArticleProcessor`` incidentally.
"""

import os
import sys

# Warm up torch BEFORE coverage's C tracer touches its C extension. Importing the
# nlp package pulls in torch (via ner_processor); doing it first here avoids the
# coverage "sys_modules_saved" delete/re-import segfault when running under --cov.
try:  # pragma: no cover - defensive: torch may be absent in some environments
    import torch  # noqa: F401
except Exception:  # pragma: no cover
    pass

from unittest.mock import MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.article_processor as mod  # noqa: E402
from nlp.article_processor import ArticleProcessor  # noqa: E402


def _cm(value):
    """Wrap ``value`` as a context manager returning itself."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=value)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _fake_psycopg2():
    """Return (fake_psycopg2_module, conn, cursor) with context-manager wiring."""
    cursor = MagicMock()
    cursor_cm = _cm(cursor)
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor_cm)
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    fake = MagicMock()
    fake.connect = MagicMock(return_value=conn)
    return fake, conn, cursor


def _make_processor(analyzer=None):
    """Build an ArticleProcessor with analyzer + DB fully mocked."""
    analyzer = analyzer or MagicMock()
    fake_pg, conn, cursor = _fake_psycopg2()
    with patch.object(mod, "create_analyzer", return_value=analyzer) as ca, patch.object(
        mod, "psycopg2", fake_pg
    ):
        proc = ArticleProcessor(
            snowflake_account="acct",
            snowflake_user="user",
            snowflake_password="pw",
            sentiment_provider="aws",
            batch_size=5,
        )
    return proc, analyzer, fake_pg, conn, cursor, ca


class TestInit:
    def test_conn_params_and_analyzer_created(self):
        proc, analyzer, fake_pg, conn, cursor, ca = _make_processor()
        assert proc.batch_size == 5
        assert proc.conn_params["account"] == "acct"
        assert proc.conn_params["warehouse"] == "ANALYTICS_WH"
        assert proc.conn_params["schema"] == "PUBLIC"
        # analyzer built via create_analyzer with the provider
        assert ca.call_args.kwargs["provider"] == "aws"
        # __init__ ran _initialize_database -> executed the CREATE TABLE DDL
        cursor.execute.assert_called_once()
        ddl = cursor.execute.call_args.args[0]
        assert "CREATE TABLE IF NOT EXISTS article_sentiment" in ddl
        assert conn.commit.called

    def test_analyzer_init_failure_raises(self):
        fake_pg, _, _ = _fake_psycopg2()
        with patch.object(
            mod, "create_analyzer", side_effect=RuntimeError("no analyzer")
        ), patch.object(mod, "psycopg2", fake_pg):
            with pytest.raises(RuntimeError, match="no analyzer"):
                ArticleProcessor(
                    snowflake_account="a",
                    snowflake_user="u",
                    snowflake_password="p",
                )

    def test_database_init_failure_raises(self):
        fake_pg = MagicMock()
        fake_pg.connect.side_effect = Exception("db unreachable")
        with patch.object(mod, "create_analyzer", return_value=MagicMock()), patch.object(
            mod, "psycopg2", fake_pg
        ):
            with pytest.raises(Exception, match="db unreachable"):
                ArticleProcessor(
                    snowflake_account="a",
                    snowflake_user="u",
                    snowflake_password="p",
                )


class TestStoreResults:
    def test_store_results_calls_execute_batch(self):
        proc, _, fake_pg, conn, cursor, _ = _make_processor()
        rows = [{"article_id": "1"}, {"article_id": "2"}]
        with patch.object(mod, "psycopg2", fake_pg), patch.object(
            mod, "execute_batch"
        ) as eb:
            proc._store_results(rows)
        assert eb.called
        # page_size passed through from batch_size
        assert eb.call_args.kwargs["page_size"] == 5
        # the data list forwarded unchanged
        assert eb.call_args.args[2] == rows
        assert conn.commit.called

    def test_store_results_raises_on_error(self):
        proc, _, fake_pg, _, _, _ = _make_processor()
        with patch.object(mod, "psycopg2", fake_pg), patch.object(
            mod, "execute_batch", side_effect=Exception("insert failed")
        ):
            with pytest.raises(Exception, match="insert failed"):
                proc._store_results([{"article_id": "1"}])


class TestProcessArticles:
    def test_process_articles_full_path(self):
        analyzer = MagicMock()
        analyzer.batch_analyze.return_value = [
            {
                "sentiment": "positive",
                "confidence": 0.91,
                "all_scores": {"positive": 0.91},
                "provider": "aws",
            }
        ]
        proc, _, fake_pg, _, _, _ = _make_processor(analyzer=analyzer)
        articles = [
            {
                "article_id": "42",
                "url": "https://ex.com/a",
                "title": "Title",
                "content": "Body",
                "source_domain": "ex.com",
                "publish_date": "2026-07-01",
            }
        ]
        with patch.object(mod, "psycopg2", fake_pg), patch.object(mod, "execute_batch"):
            results = proc.process_articles(articles)

        # analyzer received "title. content" combined text
        text_arg = analyzer.batch_analyze.call_args.args[0]
        assert text_arg == ["Title. Body"]
        assert analyzer.batch_analyze.call_args.kwargs["batch_size"] == 5

        assert len(results) == 1
        r = results[0]
        assert r["article_id"] == "42"
        assert r["url"] == "https://ex.com/a"
        assert r["sentiment"] == "positive"
        assert r["confidence"] == 0.91
        assert r["sentiment_scores"] == {"positive": 0.91}
        assert r["provider"] == "aws"
        assert r["source_domain"] == "ex.com"
        assert r["publish_date"] == "2026-07-01"

    def test_process_articles_missing_all_scores_defaults_empty(self):
        analyzer = MagicMock()
        analyzer.batch_analyze.return_value = [
            {"sentiment": "neutral", "confidence": 0.5, "provider": "aws"}
        ]
        proc, _, fake_pg, _, _, _ = _make_processor(analyzer=analyzer)
        articles = [{"article_id": "1", "url": "u"}]
        with patch.object(mod, "psycopg2", fake_pg), patch.object(mod, "execute_batch"):
            results = proc.process_articles(articles)
        assert results[0]["sentiment_scores"] == {}
        assert results[0]["title"] is None

    def test_process_articles_reraises_on_analyzer_error(self):
        analyzer = MagicMock()
        analyzer.batch_analyze.side_effect = RuntimeError("model boom")
        proc, _, fake_pg, _, _, _ = _make_processor(analyzer=analyzer)
        with patch.object(mod, "psycopg2", fake_pg):
            with pytest.raises(RuntimeError, match="model boom"):
                proc.process_articles([{"article_id": "1", "url": "u"}])
