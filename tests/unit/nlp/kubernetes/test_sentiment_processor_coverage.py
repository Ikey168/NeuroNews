"""Comprehensive coverage tests for src/nlp/kubernetes/sentiment_processor.py.

External clients (SentimentAnalyzer, psycopg2, DuckDB shared connection,
Redshift processor, torch.cuda) are mocked where they are looked up so nothing
downloads a model or hits the network. The real logic (batch text assembly,
truncation, analyze/analyze_batch wrappers, result formatting, stats, redshift
storage + backup fallback, ThreadPoolExecutor orchestration, main) is exercised
with concrete assertions.
"""

import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("torch")

import asyncio  # noqa: E402

from nlp.kubernetes import sentiment_processor as sent_mod  # noqa: E402
from nlp.kubernetes.sentiment_processor import (  # noqa: E402
    KubernetesSentimentProcessor,
)


def make_proc(tmp_path, **over):
    kwargs = dict(
        batch_size=2,
        max_workers=2,
        use_gpu=False,
        output_dir=str(tmp_path / "out"),
        model_cache_dir=str(tmp_path / "m"),
    )
    kwargs.update(over)
    return KubernetesSentimentProcessor(**kwargs)


@pytest.fixture
def proc(tmp_path):
    return make_proc(tmp_path)


def article(**over):
    base = dict(
        article_id="a1",
        title="Good news",
        content="great things happened today across the country",
        url="https://example.com/1",
        source="bbc",
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    base.update(over)
    return base


def sentiment(**over):
    base = dict(label="POSITIVE", score=0.9, confidence=0.88, all_scores={"POSITIVE": 0.9})
    base.update(over)
    return base


class TestInit:
    def test_defaults_and_dirs(self, proc):
        assert proc.batch_size == 2
        assert proc.use_gpu is False
        assert os.path.isdir(proc.output_dir)
        assert os.path.isdir(proc.model_cache_dir)
        assert proc.stats["gpu_used"] is False
        assert proc.stats["articles_processed"] == 0
        assert proc.stats["model_name"] == proc.model_name

    def test_gpu_flag_requires_cuda(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sent_mod.torch.cuda, "is_available", lambda: True)
        p = make_proc(tmp_path, use_gpu=True)
        assert p.use_gpu is True
        assert p.stats["gpu_used"] is True


class TestProcessBatch:
    def test_analyze_batch_path(self, proc):
        analyzer = MagicMock()
        analyzer.analyze_batch.return_value = [sentiment(), sentiment(label="NEGATIVE")]
        proc.sentiment_analyzer = analyzer
        results = proc.process_article_batch(
            [article(article_id="a1"), article(article_id="a2")]
        )
        assert len(results) == 2
        assert results[0]["sentiment_label"] == "POSITIVE"
        assert results[0]["sentiment_score"] == pytest.approx(0.9)
        assert results[0]["sentiment_confidence"] == pytest.approx(0.88)
        assert results[0]["sentiment_all_scores"] == {"POSITIVE": 0.9}
        assert results[0]["gpu_used"] is False
        assert results[1]["sentiment_label"] == "NEGATIVE"
        assert proc.stats["articles_processed"] == 2
        assert proc.stats["batches_processed"] == 1

    def test_fallback_individual_analyze(self, proc):
        analyzer = MagicMock(spec=["analyze"])  # no analyze_batch attribute
        analyzer.analyze.return_value = sentiment(label="NEUTRAL")
        proc.sentiment_analyzer = analyzer
        results = proc.process_article_batch([article(), article(article_id="a2")])
        assert len(results) == 2
        assert all(r["sentiment_label"] == "NEUTRAL" for r in results)
        assert analyzer.analyze.call_count == 2

    def test_confidence_defaults_to_score(self, proc):
        analyzer = MagicMock()
        # No "confidence" key -> falls back to score.
        analyzer.analyze_batch.return_value = [{"label": "POSITIVE", "score": 0.75}]
        proc.sentiment_analyzer = analyzer
        results = proc.process_article_batch([article()])
        assert results[0]["sentiment_confidence"] == pytest.approx(0.75)
        assert results[0]["sentiment_all_scores"] == {}

    def test_text_truncation(self, proc, monkeypatch):
        monkeypatch.setenv("ARTICLE_TEXT_MAX_LENGTH", "30")
        captured = {}
        analyzer = MagicMock()

        def cap(texts):
            captured["texts"] = texts
            return [sentiment() for _ in texts]

        analyzer.analyze_batch.side_effect = cap
        proc.sentiment_analyzer = analyzer
        proc.process_article_batch([article(content="x" * 500)])
        assert captured["texts"][0].endswith("...")
        assert len(captured["texts"][0]) <= 33

    def test_per_result_error_increments_failed(self, proc):
        analyzer = MagicMock()
        # Missing "label" -> KeyError in result build -> per-article failure.
        analyzer.analyze_batch.return_value = [{"score": 0.5}]
        proc.sentiment_analyzer = analyzer
        results = proc.process_article_batch([article()])
        assert results == []
        assert proc.stats["articles_failed"] == 1

    def test_batch_exception_returns_empty(self, proc):
        analyzer = MagicMock()
        analyzer.analyze_batch.side_effect = RuntimeError("model error")
        proc.sentiment_analyzer = analyzer
        results = proc.process_article_batch([article(), article(article_id="a2")])
        assert results == []
        assert proc.stats["articles_failed"] == 2


class TestFetchArticles:
    def test_fetch_maps_rows_with_limit(self, proc):
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("a1", "T", "Body", "https://u/1", "src", "2026-01-01", "2026-01-02")
        ]
        cur.__enter__ = lambda s: cur
        cur.__exit__ = lambda *a: False
        conn = MagicMock()
        conn.cursor.return_value = cur
        proc.postgres_conn = conn
        articles = asyncio.run(proc.fetch_articles_to_process(limit=5))
        assert len(articles) == 1
        assert articles[0]["article_id"] == "a1"
        assert articles[0]["scraped_at"] == "2026-01-02"
        sql, params = cur.execute.call_args[0]
        assert "LIMIT" in sql
        assert params[-1] == 5

    def test_fetch_no_limit_omits_clause(self, proc):
        cur = MagicMock()
        cur.fetchall.return_value = []
        cur.__enter__ = lambda s: cur
        cur.__exit__ = lambda *a: False
        conn = MagicMock()
        conn.cursor.return_value = cur
        proc.postgres_conn = conn
        articles = asyncio.run(proc.fetch_articles_to_process())
        assert articles == []
        sql, _ = cur.execute.call_args[0]
        assert "LIMIT" not in sql

    def test_fetch_error_returns_empty(self, proc):
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError("db down")
        proc.postgres_conn = conn
        assert asyncio.run(proc.fetch_articles_to_process()) == []


class TestStoreResults:
    def _result(self):
        return {
            "article_id": "a1",
            "sentiment_label": "POSITIVE",
            "sentiment_score": 0.9,
            "sentiment_confidence": 0.88,
            "sentiment_all_scores": {"POSITIVE": 0.9},
            "processing_timestamp": "2026-01-01T00:00:00Z",
            "processing_job_type": "sentiment-analysis",
            "model_name": "m",
            "gpu_used": False,
        }

    def test_empty_noop(self, proc):
        asyncio.run(proc.store_results_in_redshift([]))

    def test_success_path_builds_records(self, proc):
        processor = MagicMock()
        processor.__enter__.return_value = processor
        processor.__exit__.return_value = False
        processor.execute_sql = AsyncMock()
        processor.batch_insert_sentiment_results = AsyncMock(return_value=1)
        proc.redshift_processor = processor
        asyncio.run(proc.store_results_in_redshift([self._result()]))
        processor.execute_sql.assert_awaited()
        recs = processor.batch_insert_sentiment_results.await_args[0][0]
        assert recs[0]["article_id"] == "a1"
        # all_scores serialized to a JSON string for storage
        assert json.loads(recs[0]["sentiment_all_scores"]) == {"POSITIVE": 0.9}

    def test_failure_writes_backup(self, proc):
        # redshift_processor None -> `with None` raises -> backup file written.
        asyncio.run(proc.store_results_in_redshift([self._result()]))
        backups = [
            f
            for f in os.listdir(proc.output_dir)
            if f.startswith("sentiment_results_backup_")
        ]
        assert len(backups) == 1
        data = json.loads(open(os.path.join(proc.output_dir, backups[0])).read())
        assert data[0]["article_id"] == "a1"


class TestCreateTable:
    def test_create_table_sql(self, proc):
        processor = MagicMock()
        processor.execute_sql = AsyncMock()
        asyncio.run(proc.create_sentiment_results_table(processor))
        sql = processor.execute_sql.await_args[0][0]
        assert "nlp_results.sentiment_analysis" in sql

    def test_create_table_reraises(self, proc):
        processor = MagicMock()
        processor.execute_sql = AsyncMock(side_effect=RuntimeError("perm denied"))
        with pytest.raises(RuntimeError):
            asyncio.run(proc.create_sentiment_results_table(processor))


class TestUpdatePostgres:
    def test_update_commits(self, proc):
        cur = MagicMock()
        cur.__enter__ = lambda s: cur
        cur.__exit__ = lambda *a: False
        conn = MagicMock()
        conn.cursor.return_value = cur
        proc.postgres_conn = conn
        asyncio.run(proc.update_postgres_processing_status(["a1", "a2"]))
        conn.commit.assert_called_once()

    def test_update_error_rolls_back(self, proc):
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError("locked")
        proc.postgres_conn = conn
        asyncio.run(proc.update_postgres_processing_status(["a1"]))
        conn.rollback.assert_called_once()


class TestSaveStats:
    def test_writes_and_derives(self, proc):
        proc.stats["articles_processed"] = 5
        proc.stats["total_processing_time"] = 2.5
        proc.save_processing_stats()
        files = [
            f for f in os.listdir(proc.output_dir) if f.startswith("sentiment_job_stats")
        ]
        assert len(files) == 1
        data = json.loads(open(os.path.join(proc.output_dir, files[0])).read())
        assert data["articles_processed"] == 5
        assert "average_processing_time" in data
        assert "throughput_articles_per_second" in data

    def test_zero_processed(self, proc):
        proc.save_processing_stats()
        files = [
            f for f in os.listdir(proc.output_dir) if f.startswith("sentiment_job_stats")
        ]
        data = json.loads(open(os.path.join(proc.output_dir, files[0])).read())
        assert "average_processing_time" not in data


class TestInitialize:
    def test_initialize_wires_components(self, proc, monkeypatch):
        analyzer = MagicMock()
        monkeypatch.setattr(
            sent_mod, "SentimentAnalyzer", MagicMock(return_value=analyzer)
        )
        fake_conn = MagicMock()
        monkeypatch.setattr(sent_mod.psycopg2, "connect", lambda **kw: fake_conn)
        import src.database.local_analytics_connector as lac

        monkeypatch.setattr(lac, "get_shared_connection", lambda: MagicMock())
        asyncio.run(proc.initialize())
        assert proc.sentiment_analyzer is analyzer
        assert proc.postgres_conn is fake_conn

    def test_initialize_reraises(self, proc, monkeypatch):
        monkeypatch.setattr(
            sent_mod,
            "SentimentAnalyzer",
            MagicMock(side_effect=RuntimeError("model load failed")),
        )
        with pytest.raises(RuntimeError):
            asyncio.run(proc.initialize())


class TestRunProcessingJob:
    def test_no_articles_short_circuit(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "initialize", AsyncMock())
        monkeypatch.setattr(
            proc, "fetch_articles_to_process", AsyncMock(return_value=[])
        )
        store = AsyncMock()
        monkeypatch.setattr(proc, "store_results_in_redshift", store)
        asyncio.run(proc.run_processing_job())
        store.assert_not_awaited()

    def test_full_job_batches_and_stores(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "initialize", AsyncMock())
        # 3 articles, batch_size=2 -> 2 batches.
        arts = [article(article_id=f"a{i}") for i in range(3)]
        monkeypatch.setattr(
            proc, "fetch_articles_to_process", AsyncMock(return_value=arts)
        )

        def fake_batch(batch):
            return [{"article_id": a["article_id"]} for a in batch]

        monkeypatch.setattr(proc, "process_article_batch", fake_batch)
        store = AsyncMock()
        update = AsyncMock()
        monkeypatch.setattr(proc, "store_results_in_redshift", store)
        monkeypatch.setattr(proc, "update_postgres_processing_status", update)
        proc.postgres_conn = MagicMock()
        asyncio.run(proc.run_processing_job(max_articles=3))
        # store/update called once per non-empty batch (2 batches)
        assert store.await_count == 2
        assert update.await_count == 2
        proc.postgres_conn.close.assert_called_once()

    def test_batch_future_exception_logged(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "initialize", AsyncMock())
        arts = [article()]
        monkeypatch.setattr(
            proc, "fetch_articles_to_process", AsyncMock(return_value=arts)
        )
        monkeypatch.setattr(
            proc,
            "process_article_batch",
            MagicMock(side_effect=RuntimeError("worker boom")),
        )
        store = AsyncMock()
        monkeypatch.setattr(proc, "store_results_in_redshift", store)
        proc.postgres_conn = MagicMock()
        # Should not raise; the future exception is caught and logged.
        asyncio.run(proc.run_processing_job())
        store.assert_not_awaited()

    def test_job_reraises_on_init_failure(self, proc, monkeypatch):
        monkeypatch.setattr(
            proc, "initialize", AsyncMock(side_effect=RuntimeError("init fail"))
        )
        proc.postgres_conn = MagicMock()
        redshift = MagicMock()
        redshift.close = AsyncMock()
        proc.redshift_processor = redshift
        with pytest.raises(RuntimeError):
            asyncio.run(proc.run_processing_job())
        proc.postgres_conn.close.assert_called_once()
        redshift.close.assert_awaited_once()


class TestMain:
    def test_main_success_exits_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "--batch-size", "7"])
        inst = MagicMock()
        inst.run_processing_job = AsyncMock()
        monkeypatch.setattr(
            sent_mod, "KubernetesSentimentProcessor", MagicMock(return_value=inst)
        )
        with pytest.raises(SystemExit) as ei:
            asyncio.run(sent_mod.main())
        assert ei.value.code == 0
        inst.run_processing_job.assert_awaited_once()

    def test_main_failure_exits_one(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog"])
        inst = MagicMock()
        inst.run_processing_job = AsyncMock(side_effect=RuntimeError("job fail"))
        monkeypatch.setattr(
            sent_mod, "KubernetesSentimentProcessor", MagicMock(return_value=inst)
        )
        with pytest.raises(SystemExit) as ei:
            asyncio.run(sent_mod.main())
        assert ei.value.code == 1
