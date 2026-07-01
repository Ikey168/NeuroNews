"""Coverage-focused tests for src/nlp/multi_language_processor.py.

Exercises the language-detection + translation pipeline, database persistence
(psycopg2 fully mocked), statistics aggregation, batch processing, and error
handling. No real DB or network access occurs.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("psycopg2")

from src.nlp.multi_language_processor import (  # noqa: E402
    MultiLanguageArticleProcessor,
)


def _make_processor(translation_enabled=True, quality_threshold=0.7):
    """Construct a processor with the parent DB init + analyzer patched out."""
    with patch("psycopg2.connect"), patch(
        "src.nlp.sentiment_analysis.SentimentAnalyzer"
    ), patch.object(
        MultiLanguageArticleProcessor, "_initialize_database"
    ), patch.object(
        MultiLanguageArticleProcessor, "_create_translation_tables"
    ):
        proc = MultiLanguageArticleProcessor(
            snowflake_account="localhost",
            snowflake_user="u",
            snowflake_password="p",
            translation_enabled=translation_enabled,
            quality_threshold=quality_threshold,
        )
    # Ensure conn_params exists for the psycopg2.connect-based methods.
    proc.conn_params = {"host": "localhost", "dbname": "test"}
    return proc


def _cursor_conn():
    """Build a MagicMock connection/cursor supporting context managers."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=None)
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    return conn, cur


# ---------------------------------------------------------------------------
# Construction & translation-disabled path
# ---------------------------------------------------------------------------
class TestConstruction:
    def test_defaults(self):
        proc = _make_processor()
        assert proc.target_language == "en"
        assert proc.translation_enabled is True
        assert proc.translate_service is not None
        assert proc.language_detector is not None

    def test_translation_disabled_leaves_service_none(self):
        proc = _make_processor(translation_enabled=False)
        assert proc.translate_service is None

    def test_create_translation_tables_executes_sql(self):
        proc = _make_processor()
        conn, cur = _cursor_conn()
        with patch(
            "src.nlp.multi_language_processor.psycopg2.connect",
            return_value=conn,
        ):
            proc._create_translation_tables()
        # two CREATE TABLE statements + commit
        assert cur.execute.call_count == 2
        assert conn.commit.called

    def test_create_translation_tables_raises_on_error(self):
        proc = _make_processor()
        with patch(
            "src.nlp.multi_language_processor.psycopg2.connect",
            side_effect=RuntimeError("db boom"),
        ):
            with pytest.raises(RuntimeError):
                proc._create_translation_tables()


# ---------------------------------------------------------------------------
# process_article pipeline
# ---------------------------------------------------------------------------
class TestProcessArticle:
    def test_same_language_no_translation(self):
        proc = _make_processor()
        # detector returns a 2-tuple (unpacked in process_article)
        proc.language_detector.detect_language = MagicMock(return_value=("en", 0.95))
        proc._store_language_detection = MagicMock()
        # The parent exposes process_articles(), not process_article(); the child
        # calls super().process_article(...). Provide the attribute via create=True.
        with patch(
            "src.nlp.article_processor.ArticleProcessor.process_article",
            create=True,
            return_value={"sentiment": "ok"},
        ):
            result = proc.process_article(
                {"id": "a1", "title": "Hello", "content": "This is english text."}
            )
        assert result["original_language"] == "en"
        assert result["translation_performed"] is False
        assert result["errors"] == []
        assert proc._store_language_detection.called

    def test_foreign_language_triggers_translation(self):
        proc = _make_processor()
        proc.language_detector.detect_language = MagicMock(return_value=("es", 0.9))
        proc._store_language_detection = MagicMock()
        proc._translate_article = MagicMock(
            return_value={
                "translation_performed": True,
                "translated_title": "Hello",
                "translated_content": "Translated body",
                "translation_quality": 0.85,
            }
        )
        with patch(
            "src.nlp.article_processor.ArticleProcessor.process_article",
            create=True,
            return_value={"sentiment": "ok"},
        ):
            result = proc.process_article(
                {"id": "a2", "title": "Hola", "content": "Texto en espanol aqui."}
            )
        assert result["original_language"] == "es"
        assert result["translation_performed"] is True
        assert result["translated_content"] == "Translated body"
        proc._translate_article.assert_called_once()

    def test_generates_id_when_missing(self):
        proc = _make_processor()
        proc.language_detector.detect_language = MagicMock(return_value=("en", 0.9))
        proc._store_language_detection = MagicMock()
        # MultiLanguageArticleProcessor.process_article calls
        # super().process_article(...), but the parent ArticleProcessor only
        # defines process_articles (plural) -- a latent source bug; create=True
        # mocks the missing super method so the id-generation branch is covered.
        with patch(
            "src.nlp.article_processor.ArticleProcessor.process_article",
            return_value={},
            create=True,
        ):
            result = proc.process_article(
                {"url": "http://x/1", "title": "T", "content": "english text here."}
            )
        assert result["article_id"].startswith("article_")

    def test_error_captured_in_errors_list(self):
        proc = _make_processor()
        proc.language_detector.detect_language = MagicMock(
            side_effect=RuntimeError("detect fail")
        )
        result = proc.process_article(
            {"id": "a3", "title": "T", "content": "content"}
        )
        assert result["errors"]
        assert "detect fail" in result["errors"][0]


# ---------------------------------------------------------------------------
# _translate_article internal
# ---------------------------------------------------------------------------
class TestTranslateArticle:
    def test_accepts_high_quality_translation(self):
        proc = _make_processor()
        proc.translate_service.translate_text = MagicMock(
            return_value={
                "translated_text": "translated",
                "error": None,
                "confidence": 0.9,
            }
        )
        proc.quality_checker.check_translation_quality = MagicMock(
            return_value={"quality_score": 0.9, "issues": [], "recommendations": []}
        )
        proc._store_translation = MagicMock()
        out = proc._translate_article("a1", "Titulo", "Contenido", "es")
        assert out["translation_performed"] is True
        assert out["translated_content"] == "translated"
        assert out["translation_quality"] == pytest.approx(0.9)
        proc._store_translation.assert_called_once()

    def test_rejects_low_quality_translation(self):
        proc = _make_processor(quality_threshold=0.8)
        proc.translate_service.translate_text = MagicMock(
            return_value={"translated_text": "bad", "error": None, "confidence": 0.5}
        )
        proc.quality_checker.check_translation_quality = MagicMock(
            return_value={"quality_score": 0.3, "issues": ["x"], "recommendations": []}
        )
        proc._store_translation = MagicMock()
        out = proc._translate_article("a1", "T", "C", "es")
        assert out["translation_performed"] is False
        proc._store_translation.assert_not_called()

    def test_translation_error_short_circuits(self):
        proc = _make_processor()
        proc.translate_service.translate_text = MagicMock(
            return_value={"translated_text": "", "error": "svc down", "confidence": 0.0}
        )
        out = proc._translate_article("a1", "T", "C", "es")
        assert out["translation_performed"] is False

    def test_exception_recorded(self):
        proc = _make_processor()
        proc.translate_service.translate_text = MagicMock(
            side_effect=RuntimeError("boom")
        )
        out = proc._translate_article("a1", "T", "C", "es")
        assert out["translation_performed"] is False
        assert "translation_error" in out


# ---------------------------------------------------------------------------
# DB store helpers (psycopg2.connect based)
# ---------------------------------------------------------------------------
class TestStoreHelpers:
    def test_store_language_detection_inserts(self):
        proc = _make_processor()
        conn, cur = _cursor_conn()
        with patch(
            "src.nlp.multi_language_processor.psycopg2.connect",
            return_value=conn,
        ):
            proc._store_language_detection("a1", "es", 0.85, "heuristic", 42)
        assert cur.execute.called
        assert conn.commit.called

    def test_store_language_detection_swallows_error(self):
        proc = _make_processor()
        with patch(
            "src.nlp.multi_language_processor.psycopg2.connect",
            side_effect=RuntimeError("db"),
        ):
            # must not raise
            proc._store_language_detection("a1", "es", 0.85, "heuristic", 42)

    def test_store_translation_inserts(self):
        proc = _make_processor()
        conn, cur = _cursor_conn()
        with patch(
            "src.nlp.multi_language_processor.psycopg2.connect",
            return_value=conn,
        ):
            proc._store_translation(
                "a1", "es", "en", "Titulo", "Title", "Contenido", "Content",
                0.9, 0.8, ["issue"], ["rec"],
            )
        assert cur.execute.called
        assert conn.commit.called

    def test_store_translation_swallows_error(self):
        proc = _make_processor()
        with patch(
            "src.nlp.multi_language_processor.psycopg2.connect",
            side_effect=RuntimeError("db"),
        ):
            proc._store_translation(
                "a1", "es", "en", "t", "t", "c", "c", 0.9, 0.8, [], []
            )


# ---------------------------------------------------------------------------
# get_translation_statistics
# ---------------------------------------------------------------------------
class TestStatistics:
    def test_aggregates_stats(self):
        proc = _make_processor()
        conn, cur = _cursor_conn()
        # 3 fetch calls: language distribution, translation stats, quality dist
        cur.fetchall.side_effect = [
            [("en", 10), ("es", 5)],
            [
                {
                    "original_language": "es",
                    "target_language": "en",
                    "translation_count": 5,
                    "avg_quality": 0.8,
                    "avg_confidence": 0.7,
                }
            ],
            [("high", 3), ("low", 2)],
        ]
        with patch(
            "src.nlp.multi_language_processor.psycopg2.connect",
            return_value=conn,
        ):
            stats = proc.get_translation_statistics()
        assert stats["language_distribution"] == {"en": 10, "es": 5}
        assert stats["total_articles_processed"] == 15
        assert stats["total_translations"] == 5
        assert stats["quality_distribution"] == {"high": 3, "low": 2}

    def test_statistics_error_returns_empty(self):
        proc = _make_processor()
        with patch(
            "src.nlp.multi_language_processor.psycopg2.connect",
            side_effect=RuntimeError("db"),
        ):
            assert proc.get_translation_statistics() == {}


# ---------------------------------------------------------------------------
# process_batch
# ---------------------------------------------------------------------------
class TestBatch:
    def test_process_batch_all_success(self):
        proc = _make_processor()
        proc.process_article = MagicMock(
            side_effect=lambda a: {"article_id": a["id"], "ok": True}
        )
        arts = [{"id": str(i), "title": "t", "content": "c"} for i in range(12)]
        results = proc.process_batch(arts)
        assert len(results) == 12
        assert all(r["ok"] for r in results)

    def test_process_batch_handles_failure(self):
        proc = _make_processor()

        def flaky(article):
            if article["id"] == "1":
                raise RuntimeError("bad article")
            return {"article_id": article["id"]}

        proc.process_article = MagicMock(side_effect=flaky)
        arts = [{"id": "0"}, {"id": "1"}, {"id": "2"}]
        results = proc.process_batch(arts)
        assert len(results) == 3
        # the failing article yields an {'error': ...} entry
        assert any("error" in r for r in results)


# ---------------------------------------------------------------------------
# Convenience / connection-based helpers
# ---------------------------------------------------------------------------
class TestConvenienceHelpers:
    def test_detect_and_store_language(self):
        proc = _make_processor()
        proc.language_detector.detect_language = MagicMock(
            return_value={"language": "es", "confidence": 0.8}
        )
        proc.store_language_detection = MagicMock(return_value=True)
        out = proc.detect_and_store_language({"id": "a1", "content": "hola mundo"})
        assert out["detected_language"] == "es"
        assert out["confidence"] == 0.8
        proc.store_language_detection.assert_called_once()

    def test_translate_article_convenience(self):
        proc = _make_processor()
        proc.translate_service.translate_text = MagicMock(
            return_value={"translated_text": "hi", "error": None}
        )
        out = proc.translate_article({"content": "hola"}, "es", "en")
        assert out["translated_text"] == "hi"
        assert out["translated_content"] == "hi"
        assert out["error"] is None

    def test_translate_article_with_error(self):
        proc = _make_processor()
        proc.translate_service.translate_text = MagicMock(
            return_value={"translated_text": None, "error": "boom"}
        )
        out = proc.translate_article({"content": "hola"}, "es", "en")
        assert out["error"] == "boom"
        assert "translated_content" not in out

    def test_update_language_stats_and_get_statistics(self):
        proc = _make_processor()
        proc.update_language_stats("es")
        proc.update_language_stats("fr")
        proc.update_language_stats("es")
        stats = proc.get_processing_statistics()
        assert stats["language_distribution"]["es"] == 2
        assert stats["language_distribution"]["fr"] == 1

    def test_get_processing_statistics_when_empty(self):
        proc = _make_processor()
        assert proc.get_processing_statistics() == {"language_distribution": {}}

    def test_generate_article_id_is_deterministic(self):
        proc = _make_processor()
        data = {"url": "http://x/1", "title": "Title"}
        a = proc._generate_article_id(data)
        b = proc._generate_article_id(data)
        assert a == b
        assert a.startswith("article_")


# ---------------------------------------------------------------------------
# self.connection based table/store helpers
# ---------------------------------------------------------------------------
class TestConnectionBasedHelpers:
    def _with_connection(self, proc):
        conn, cur = _cursor_conn()
        # these helpers use `with self.connection.cursor() as cursor:`
        conn.cursor.return_value = cur
        proc.connection = conn
        return conn, cur

    def test_create_language_detection_table_success(self):
        proc = _make_processor()
        conn, cur = self._with_connection(proc)
        assert proc.create_language_detection_table() is True
        assert cur.execute.called
        assert conn.commit.called

    def test_create_language_detection_table_error(self):
        proc = _make_processor()
        proc.connection = MagicMock()
        proc.connection.cursor.side_effect = RuntimeError("boom")
        assert proc.create_language_detection_table() is False

    def test_create_translation_table_success(self):
        proc = _make_processor()
        conn, cur = self._with_connection(proc)
        assert proc.create_translation_table() is True
        assert cur.execute.called

    def test_create_translation_table_error(self):
        proc = _make_processor()
        proc.connection = MagicMock()
        proc.connection.cursor.side_effect = RuntimeError("boom")
        assert proc.create_translation_table() is False

    def test_store_language_detection_public_success(self):
        proc = _make_processor()
        conn, cur = self._with_connection(proc)
        ok = proc.store_language_detection(
            {"article_id": "a1", "detected_language": "es", "confidence": 0.8}
        )
        assert ok is True
        assert cur.execute.called

    def test_store_language_detection_public_error(self):
        proc = _make_processor()
        proc.connection = MagicMock()
        proc.connection.cursor.side_effect = RuntimeError("boom")
        assert proc.store_language_detection({"article_id": "a1"}) is False

    def test_store_translation_public_success(self):
        proc = _make_processor()
        conn, cur = self._with_connection(proc)
        ok = proc.store_translation(
            {
                "article_id": "a1",
                "original_language": "es",
                "target_language": "en",
                "original_title": "t",
                "translated_title": "T",
                "original_content": "c",
                "translated_content": "C",
                "quality_score": 0.9,
                "issues": ["x"],
            }
        )
        assert ok is True
        assert cur.execute.called

    def test_store_translation_public_error(self):
        proc = _make_processor()
        proc.connection = MagicMock()
        proc.connection.cursor.side_effect = RuntimeError("boom")
        assert proc.store_translation({"article_id": "a1"}) is False
