"""Storage tests for src/ingestion/scrapy_integration.py (warehouse writes)."""

import os
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("duckdb")

# scrapy_integration writes via the ``src.database`` connector singleton, so the
# test must reset that exact module instance.
import src.database.local_analytics_connector as connector  # noqa: E402
from ingestion.scrapy_integration import Article, store_articles  # noqa: E402


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    """Point the shared connection at a throwaway DuckDB file."""
    monkeypatch.setenv("NEURONEWS_DB_PATH", str(tmp_path / "test.duckdb"))
    connector._CONNECTION = None  # force re-open at the new path
    yield connector.get_shared_connection()
    try:
        connector._CONNECTION.close()
    except Exception:
        pass
    connector._CONNECTION = None


def make_article(n: int) -> Article:
    return Article(
        id="rss-{0:04d}".format(n),
        title="Headline number {0}".format(n),
        url="https://example.com/{0}".format(n),
        content="Some content {0}".format(n),
        publish_date=datetime(2025, 6, 18, 12, 0, 0),
        source="Test Feed",
        category="Technology",
        sentiment_score=0.2,
        sentiment_label="positive",
    )


def _count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]


class TestStoreArticles:
    def test_inserts_new_articles(self, warehouse):
        inserted = store_articles([make_article(1), make_article(2)])
        assert inserted == 2
        assert _count(warehouse) == 2

    def test_dedupes_by_id(self, warehouse):
        store_articles([make_article(1)])
        inserted = store_articles([make_article(1), make_article(2)])
        # article 1 already present -> only article 2 added
        assert inserted == 1
        assert _count(warehouse) == 2

    def test_replace_wipes_table(self, warehouse):
        store_articles([make_article(1), make_article(2)])
        inserted = store_articles([make_article(3)], replace=True)
        assert inserted == 1
        assert _count(warehouse) == 1
        row = warehouse.execute("SELECT id FROM news_articles").fetchone()
        assert row[0] == "rss-0003"

    def test_sample_seed_is_dropped_on_append(self, warehouse):
        # get_shared_connection seeds synthetic 'art-*' rows when empty
        assert warehouse.execute(
            "SELECT COUNT(*) FROM news_articles WHERE id LIKE 'art-%'"
        ).fetchone()[0] > 0
        store_articles([make_article(1)])
        # synthetic seed removed, only the real article remains
        assert warehouse.execute(
            "SELECT COUNT(*) FROM news_articles WHERE id LIKE 'art-%'"
        ).fetchone()[0] == 0
        assert _count(warehouse) == 1
