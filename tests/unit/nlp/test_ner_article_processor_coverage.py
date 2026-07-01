"""Coverage tests for src/nlp/ner_article_processor.py.

Targets error-handling and edge branches the happy-path tests in test_ner.py do
not reach: NER-processor init failure fallback, NER-schema DDL failure (swallowed),
the ``process_articles`` exception + sentiment-only fallback, empty-input early
returns in the store/update helpers, and the exception paths in
``get_entity_statistics`` / ``search_entities``.

The NER processor factory, sentiment analyzer and psycopg2 are all mocked so no
model is loaded and no database is contacted.
"""

import os
import sys

# Warm up torch before coverage's C tracer (avoids the sys_modules_saved
# delete/re-import segfault under --cov). The nlp package pulls torch in.
try:  # pragma: no cover - defensive
    import torch  # noqa: F401
except Exception:  # pragma: no cover
    pass

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.ner_article_processor as mod  # noqa: E402
from nlp.ner_article_processor import (  # noqa: E402
    NERArticleProcessor,
    create_ner_article_processor,
)


def _cm(value):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=value)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _fake_psycopg2():
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=_cm(cursor))
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    fake = MagicMock()
    fake.connect = MagicMock(return_value=conn)
    return fake, conn, cursor


def _make_processor(ner_enabled=True, ner_processor=None, create_ner_side=None):
    """Build a NERArticleProcessor with analyzer, NER factory and DB mocked."""
    fake_pg, conn, cursor = _fake_psycopg2()
    ner_proc = ner_processor if ner_processor is not None else MagicMock()

    ner_factory = MagicMock(return_value=ner_proc)
    if create_ner_side is not None:
        ner_factory = MagicMock(side_effect=create_ner_side)

    with patch.object(mod, "psycopg2", fake_pg), patch(
        "nlp.article_processor.psycopg2", fake_pg
    ), patch(
        "nlp.article_processor.create_analyzer", return_value=MagicMock()
    ), patch.object(
        mod, "create_ner_processor", ner_factory
    ):
        proc = NERArticleProcessor(
            snowflake_account="acct",
            snowflake_user="u",
            snowflake_password="p",
            ner_enabled=ner_enabled,
            batch_size=3,
        )
    return proc, fake_pg, conn, cursor, ner_proc


class TestInit:
    def test_ner_init_failure_disables_ner(self):
        proc, *_ = _make_processor(create_ner_side=RuntimeError("model load fail"))
        # __init__ caught the failure and continued without NER
        assert proc.ner_enabled is False
        assert proc.ner_processor is None

    def test_ner_disabled_explicitly(self):
        proc, *_ = _make_processor(ner_enabled=False)
        assert proc.ner_enabled is False
        assert proc.ner_processor is None

    def test_ner_schema_ddl_failure_is_swallowed(self):
        """A failure creating NER tables must NOT raise (it is logged)."""
        fake_pg, conn, cursor = _fake_psycopg2()

        # Base schema init (parent) succeeds; the NER DDL execute raises.
        call_state = {"n": 0}

        def execute_side(sql, *a, **k):
            call_state["n"] += 1
            if "article_entities" in sql:
                raise Exception("ner ddl fail")

        cursor.execute.side_effect = execute_side

        with patch.object(mod, "psycopg2", fake_pg), patch(
            "nlp.article_processor.psycopg2", fake_pg
        ), patch(
            "nlp.article_processor.create_analyzer", return_value=MagicMock()
        ), patch.object(
            mod, "create_ner_processor", MagicMock(return_value=MagicMock())
        ):
            # Should construct without raising despite the NER DDL failure.
            proc = NERArticleProcessor(
                snowflake_account="a",
                snowflake_user="u",
                snowflake_password="p",
            )
        assert proc.ner_enabled is True


class TestProcessArticles:
    def test_process_articles_ner_disabled_returns_sentiment_only(self):
        proc, fake_pg, *_ = _make_processor(ner_enabled=False)
        sentiment = [{"article_id": "1", "sentiment": "positive"}]
        with patch(
            "nlp.article_processor.ArticleProcessor.process_articles",
            return_value=sentiment,
        ):
            out = proc.process_articles([{"article_id": "1", "url": "u"}])
        assert out == sentiment

    def test_process_articles_enhances_with_entities(self):
        ner_proc = MagicMock()
        ner_proc.extract_entities.return_value = [
            {
                "text": "OpenAI",
                "type": "ORG",
                "confidence": 0.95,
                "start_position": 0,
                "end_position": 6,
            }
        ]
        proc, fake_pg, _, _, _ = _make_processor(ner_processor=ner_proc)
        sentiment = [{"article_id": "1", "sentiment": "neutral"}]
        with patch(
            "nlp.article_processor.ArticleProcessor.process_articles",
            return_value=sentiment,
        ), patch.object(mod, "execute_batch"):
            out = proc.process_articles(
                [{"article_id": "1", "url": "u", "title": "T", "content": "OpenAI"}]
            )
        assert out[0]["entity_count"] == 1
        assert out[0]["entity_types"] == ["ORG"]
        assert out[0]["entities"][0]["text"] == "OpenAI"

    def test_process_articles_error_falls_back_to_sentiment(self):
        """If NER processing raises, fall back to parent sentiment-only path."""
        ner_proc = MagicMock()
        ner_proc.extract_entities.side_effect = RuntimeError("extract boom")
        proc, fake_pg, _, _, _ = _make_processor(ner_processor=ner_proc)
        sentiment = [{"article_id": "1", "sentiment": "positive"}]

        with patch(
            "nlp.article_processor.ArticleProcessor.process_articles",
            return_value=sentiment,
        ) as parent:
            out = proc.process_articles([{"article_id": "1", "url": "u"}])
        # parent.process_articles called twice: once in the try, once in fallback
        assert parent.call_count == 2
        assert out == sentiment


class TestStoreEntities:
    def test_store_entities_empty_noop(self):
        proc, fake_pg, *_ = _make_processor()
        fake_pg.connect.reset_mock()
        with patch.object(mod, "psycopg2", fake_pg):
            proc._store_entities([])
        assert not fake_pg.connect.called

    def test_store_entities_error_is_swallowed(self):
        proc, fake_pg, *_ = _make_processor()
        with patch.object(mod, "psycopg2", fake_pg), patch.object(
            mod, "execute_batch", side_effect=Exception("write fail")
        ):
            # Must not raise (error is logged, processing continues).
            proc._store_entities([{"article_id": "1", "entity_text": "X"}])

    def test_store_entities_success(self):
        proc, fake_pg, conn, _, _ = _make_processor()
        with patch.object(mod, "psycopg2", fake_pg), patch.object(
            mod, "execute_batch"
        ) as eb:
            proc._store_entities([{"article_id": "1", "entity_text": "X"}])
        assert eb.called
        assert conn.commit.called


class TestUpdateArticles:
    def test_update_empty_results_noop(self):
        proc, fake_pg, *_ = _make_processor()
        fake_pg.connect.reset_mock()
        with patch.object(mod, "psycopg2", fake_pg):
            proc._update_articles_with_entities([])
        assert not fake_pg.connect.called

    def test_update_no_entities_key_noop(self):
        """Results without an 'entities' key produce no updates -> early return."""
        proc, fake_pg, *_ = _make_processor()
        fake_pg.connect.reset_mock()
        with patch.object(mod, "psycopg2", fake_pg), patch.object(
            mod, "execute_batch"
        ) as eb:
            proc._update_articles_with_entities([{"article_id": "1"}])
        assert not eb.called
        assert not fake_pg.connect.called

    def test_update_error_is_swallowed(self):
        proc, fake_pg, *_ = _make_processor()
        results = [
            {
                "article_id": "1",
                "entities": [{"text": "X", "type": "ORG", "confidence": 0.9}],
            }
        ]
        with patch.object(mod, "psycopg2", fake_pg), patch.object(
            mod, "execute_batch", side_effect=Exception("update fail")
        ):
            proc._update_articles_with_entities(results)  # no raise

    def test_update_success_serializes_entities(self):
        proc, fake_pg, conn, _, _ = _make_processor()
        results = [
            {
                "article_id": "1",
                "entities": [{"text": "X", "type": "ORG", "confidence": 0.9}],
            }
        ]
        with patch.object(mod, "psycopg2", fake_pg), patch.object(
            mod, "execute_batch"
        ) as eb:
            proc._update_articles_with_entities(results)
        assert eb.called
        update_data = eb.call_args.args[2]
        assert update_data[0]["article_id"] == "1"
        assert '"text": "X"' in update_data[0]["entities"]
        assert conn.commit.called


class TestFactory:
    def test_create_ner_article_processor_returns_instance(self):
        fake_pg, _, _ = _fake_psycopg2()
        with patch.object(mod, "psycopg2", fake_pg), patch(
            "nlp.article_processor.psycopg2", fake_pg
        ), patch(
            "nlp.article_processor.create_analyzer", return_value=MagicMock()
        ), patch.object(
            mod, "create_ner_processor", MagicMock(return_value=MagicMock())
        ):
            proc = create_ner_article_processor(
                snowflake_account="a",
                snowflake_user="u",
                snowflake_password="p",
            )
        assert isinstance(proc, NERArticleProcessor)


class TestStatisticsAndSearch:
    def test_get_entity_statistics_error_returns_empty(self):
        proc, *_ = _make_processor()
        fake_pg = MagicMock()
        fake_pg.connect.side_effect = Exception("db down")
        with patch.object(mod, "psycopg2", fake_pg):
            assert proc.get_entity_statistics() == {}

    def test_get_entity_statistics_parses_rows(self):
        ner_proc = MagicMock()
        ner_proc.get_statistics.return_value = {"processed": 5}
        proc, fake_pg, _, cursor, _ = _make_processor(ner_processor=ner_proc)
        cursor.fetchall.side_effect = [
            [("ORG", 10, 4, 0.9, 0.7, 0.99)],  # entity_statistics
            [("OpenAI", "ORG", 3, 0.95, 2)],  # common_entities
        ]
        with patch.object(mod, "psycopg2", fake_pg):
            stats = proc.get_entity_statistics()
        assert stats["ner_processor_stats"] == {"processed": 5}
        assert stats["entity_type_statistics"][0]["type"] == "ORG"
        assert stats["entity_type_statistics"][0]["avg_confidence"] == 0.9
        assert stats["most_common_entities"][0]["text"] == "OpenAI"

    def test_search_entities_error_returns_empty(self):
        proc, *_ = _make_processor()
        fake_pg = MagicMock()
        fake_pg.connect.side_effect = Exception("db down")
        with patch.object(mod, "psycopg2", fake_pg):
            assert proc.search_entities(entity_text="X") == []

    def test_search_entities_with_filters_parses_rows(self):
        from datetime import datetime

        proc, fake_pg, _, cursor, _ = _make_processor()
        extracted = datetime(2026, 1, 5, 12, 0, 0)
        cursor.fetchall.return_value = [
            ("OpenAI", "ORG", 0.95, "1", "Title", "http://x", extracted),
        ]
        with patch.object(mod, "psycopg2", fake_pg):
            results = proc.search_entities(
                entity_text="Open", entity_type="ORG", min_confidence=0.5, limit=10
            )
        assert len(results) == 1
        assert results[0]["entity_text"] == "OpenAI"
        assert results[0]["confidence"] == 0.95
        assert results[0]["extracted_at"] == extracted.isoformat()
        # Both filters populated the params dict (note: the source SQL template
        # leaves the literal "{where_clause}" placeholder unformatted -- a genuine
        # source bug -- but the filter params are still assembled here).
        sql, params = cursor.execute.call_args.args
        assert params["entity_text"] == "%Open%"
        assert params["entity_type"] == "ORG"
        assert params["min_confidence"] == 0.5
        assert params["limit"] == 10

    def test_search_entities_null_extracted_at(self):
        proc, fake_pg, _, cursor, _ = _make_processor()
        cursor.fetchall.return_value = [
            ("Foo", "MISC", 0.6, "2", "T", "u", None),
        ]
        with patch.object(mod, "psycopg2", fake_pg):
            results = proc.search_entities()
        assert results[0]["extracted_at"] is None
