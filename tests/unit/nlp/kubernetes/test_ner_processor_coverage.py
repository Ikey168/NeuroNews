"""Comprehensive coverage tests for src/nlp/kubernetes/ner_processor.py.

External clients (NERProcessor, psycopg2, DuckDB shared connection, Redshift
processor, torch.cuda) are mocked where they are looked up so nothing downloads
a model or touches the network. The real logic (batch text assembly,
truncation, entity result formatting, per-article error handling, stats,
redshift storage + backup fallback, ThreadPoolExecutor orchestration, main) is
exercised with concrete assertions.
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

from nlp.kubernetes import ner_processor as ner_mod  # noqa: E402
from nlp.kubernetes.ner_processor import KubernetesNERProcessor  # noqa: E402


def make_proc(tmp_path, **over):
    kwargs = dict(
        batch_size=2,
        max_workers=2,
        use_gpu=False,
        confidence_threshold=0.7,
        output_dir=str(tmp_path / "out"),
        model_cache_dir=str(tmp_path / "m"),
    )
    kwargs.update(over)
    return KubernetesNERProcessor(**kwargs)


@pytest.fixture
def proc(tmp_path):
    return make_proc(tmp_path)


def article(**over):
    base = dict(
        article_id="a1",
        title="Google announcement",
        content="Google and Meta announced a partnership in California today.",
        url="https://example.com/1",
        source="bbc",
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    base.update(over)
    return base


def entity(**over):
    base = dict(
        text="Google", type="ORG", confidence=0.95, start_position=0, end_position=6
    )
    base.update(over)
    return base


class TestInit:
    def test_defaults_and_dirs(self, proc):
        assert proc.confidence_threshold == 0.7
        assert proc.batch_size == 2
        assert proc.use_gpu is False
        assert os.path.isdir(proc.output_dir)
        assert os.path.isdir(proc.model_cache_dir)
        assert proc.stats["entities_extracted"] == 0
        assert proc.stats["confidence_threshold"] == 0.7
        assert proc.stats["gpu_used"] is False

    def test_gpu_flag_requires_cuda(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ner_mod.torch.cuda, "is_available", lambda: True)
        p = make_proc(tmp_path, use_gpu=True)
        assert p.use_gpu is True
        assert p.stats["gpu_used"] is True


class TestProcessBatch:
    def test_extracts_and_formats_entities(self, proc):
        ner = MagicMock()
        ner.extract_entities.return_value = [
            entity(),
            entity(text="Meta", type="ORG", confidence=0.9, start_position=11, end_position=15),
        ]
        proc.ner_processor = ner
        results = proc.process_article_batch([article()])
        assert len(results) == 2
        r0 = results[0]
        assert r0["entity_text"] == "Google"
        assert r0["entity_type"] == "ORG"
        assert r0["entity_confidence"] == pytest.approx(0.95)
        assert r0["entity_start_position"] == 0
        assert r0["entity_end_position"] == 6
        assert r0["article_id"] == "a1"
        assert r0["confidence_threshold"] == 0.7
        assert r0["gpu_used"] is False
        assert proc.stats["entities_extracted"] == 2
        assert proc.stats["articles_processed"] == 1
        assert proc.stats["batches_processed"] == 1

    def test_entity_missing_optional_positions(self, proc):
        ner = MagicMock()
        # Entity without start/end positions -> .get returns None.
        ner.extract_entities.return_value = [
            {"text": "California", "type": "LOC", "confidence": 0.8}
        ]
        proc.ner_processor = ner
        results = proc.process_article_batch([article()])
        assert results[0]["entity_start_position"] is None
        assert results[0]["entity_end_position"] is None

    def test_text_truncation(self, proc, monkeypatch):
        monkeypatch.setenv("ARTICLE_TEXT_MAX_LENGTH", "40")
        captured = {}
        ner = MagicMock()

        def cap(text, article_id):
            captured["text"] = text
            return []

        ner.extract_entities.side_effect = cap
        proc.ner_processor = ner
        proc.process_article_batch([article(content="y" * 500)])
        assert captured["text"].endswith("...")
        assert len(captured["text"]) <= 43

    def test_empty_entities_still_counts_article(self, proc):
        ner = MagicMock()
        ner.extract_entities.return_value = []
        proc.ner_processor = ner
        results = proc.process_article_batch([article()])
        assert results == []
        assert proc.stats["articles_processed"] == 1
        assert proc.stats["entities_extracted"] == 0

    def test_per_article_error_increments_failed(self, proc):
        ner = MagicMock()
        ner.extract_entities.side_effect = RuntimeError("ner failed")
        proc.ner_processor = ner
        results = proc.process_article_batch([article(), article(article_id="a2")])
        assert results == []
        assert proc.stats["articles_failed"] == 2

    def test_outer_exception_returns_empty(self, proc):
        # A sequence whose len() works (so the outer handler's len(articles)
        # succeeds) but whose iteration raises -> hits the OUTER try/except and
        # increments articles_failed by len(articles).
        class BadArticles:
            def __len__(self):
                return 2

            def __iter__(self):
                raise RuntimeError("iteration failed")

        proc.ner_processor = MagicMock()
        assert proc.process_article_batch(BadArticles()) == []
        assert proc.stats["articles_failed"] == 2


class TestFetchArticles:
    def test_fetch_maps_rows(self, proc):
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("a1", "T", "Body content", "https://u/1", "src", "2026-01-01", "2026-01-02")
        ]
        cur.__enter__ = lambda s: cur
        cur.__exit__ = lambda *a: False
        conn = MagicMock()
        conn.cursor.return_value = cur
        proc.postgres_conn = conn
        articles = asyncio.run(proc.fetch_articles_to_process(limit=3))
        assert len(articles) == 1
        assert articles[0]["article_id"] == "a1"
        sql, params = cur.execute.call_args[0]
        assert "LIMIT" in sql
        assert params[-1] == 3

    def test_fetch_error_returns_empty(self, proc):
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError("db down")
        proc.postgres_conn = conn
        assert asyncio.run(proc.fetch_articles_to_process()) == []


class TestStoreResults:
    def _result(self):
        return {
            "article_id": "a1",
            "entity_text": "Google",
            "entity_type": "ORG",
            "entity_confidence": 0.95,
            "processing_timestamp": "2026-01-01T00:00:00Z",
        }

    def test_empty_noop(self, proc):
        asyncio.run(proc.store_results_in_redshift([]))

    def test_success_path(self, proc):
        processor = MagicMock()
        processor.__enter__.return_value = processor
        processor.__exit__.return_value = False
        processor.execute_sql = AsyncMock()
        processor.batch_insert_entity_results = AsyncMock(return_value=1)
        proc.redshift_processor = processor
        results = [self._result()]
        asyncio.run(proc.store_results_in_redshift(results))
        processor.execute_sql.assert_awaited()
        processor.batch_insert_entity_results.assert_awaited_once_with(results)

    def test_failure_writes_backup(self, proc):
        asyncio.run(proc.store_results_in_redshift([self._result()]))
        backups = [
            f
            for f in os.listdir(proc.output_dir)
            if f.startswith("entity_results_backup_")
        ]
        assert len(backups) == 1
        data = json.loads(open(os.path.join(proc.output_dir, backups[0])).read())
        assert data[0]["entity_text"] == "Google"


class TestCreateTable:
    def test_create_table_sql(self, proc):
        processor = MagicMock()
        processor.execute_sql = AsyncMock()
        asyncio.run(proc.create_entity_results_table(processor))
        sql = processor.execute_sql.await_args[0][0]
        assert "nlp_results.entity_extraction" in sql

    def test_create_table_reraises(self, proc):
        processor = MagicMock()
        processor.execute_sql = AsyncMock(side_effect=RuntimeError("perm denied"))
        with pytest.raises(RuntimeError):
            asyncio.run(proc.create_entity_results_table(processor))


class TestUpdatePostgres:
    def test_update_commits(self, proc):
        cur = MagicMock()
        cur.__enter__ = lambda s: cur
        cur.__exit__ = lambda *a: False
        conn = MagicMock()
        conn.cursor.return_value = cur
        proc.postgres_conn = conn
        asyncio.run(proc.update_postgres_processing_status(["a1"]))
        conn.commit.assert_called_once()

    def test_update_error_rolls_back(self, proc):
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError("locked")
        proc.postgres_conn = conn
        asyncio.run(proc.update_postgres_processing_status(["a1"]))
        conn.rollback.assert_called_once()


class TestSaveStats:
    def test_writes_and_derives_entity_metrics(self, proc):
        proc.stats["articles_processed"] = 3
        proc.stats["entities_extracted"] = 9
        proc.stats["total_processing_time"] = 1.5
        proc.save_processing_stats()
        files = [
            f for f in os.listdir(proc.output_dir) if f.startswith("ner_job_stats")
        ]
        assert len(files) == 1
        data = json.loads(open(os.path.join(proc.output_dir, files[0])).read())
        assert data["entities_extracted"] == 9
        assert "average_processing_time" in data
        assert "average_entities_per_article" in data
        assert data["average_entities_per_article"] == pytest.approx(3.0)

    def test_zero_processed(self, proc):
        proc.save_processing_stats()
        files = [
            f for f in os.listdir(proc.output_dir) if f.startswith("ner_job_stats")
        ]
        data = json.loads(open(os.path.join(proc.output_dir, files[0])).read())
        assert "average_entities_per_article" not in data


class TestInitialize:
    def test_initialize_wires_components(self, proc, monkeypatch):
        ner = MagicMock()
        monkeypatch.setattr(ner_mod, "NERProcessor", MagicMock(return_value=ner))
        fake_conn = MagicMock()
        monkeypatch.setattr(ner_mod.psycopg2, "connect", lambda **kw: fake_conn)
        import src.database.local_analytics_connector as lac

        monkeypatch.setattr(lac, "get_shared_connection", lambda: MagicMock())
        asyncio.run(proc.initialize())
        assert proc.ner_processor is ner
        assert proc.postgres_conn is fake_conn

    def test_initialize_reraises(self, proc, monkeypatch):
        monkeypatch.setattr(
            ner_mod,
            "NERProcessor",
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

    def test_full_job_batches_and_dedupes_ids(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "initialize", AsyncMock())
        arts = [article(article_id=f"a{i}") for i in range(3)]  # batch_size=2 -> 2 batches
        monkeypatch.setattr(
            proc, "fetch_articles_to_process", AsyncMock(return_value=arts)
        )

        def fake_batch(batch):
            # Emit two entity rows per article to exercise id de-duplication.
            out = []
            for a in batch:
                out.append({"article_id": a["article_id"], "entity_text": "X"})
                out.append({"article_id": a["article_id"], "entity_text": "Y"})
            return out

        monkeypatch.setattr(proc, "process_article_batch", fake_batch)
        store = AsyncMock()
        update = AsyncMock()
        monkeypatch.setattr(proc, "store_results_in_redshift", store)
        monkeypatch.setattr(proc, "update_postgres_processing_status", update)
        proc.postgres_conn = MagicMock()
        asyncio.run(proc.run_processing_job(max_articles=3))
        assert store.await_count == 2
        assert update.await_count == 2
        # Each update call received de-duplicated article ids.
        for call in update.await_args_list:
            ids = call[0][0]
            assert len(ids) == len(set(ids))
        proc.postgres_conn.close.assert_called_once()

    def test_batch_future_exception_logged(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "initialize", AsyncMock())
        monkeypatch.setattr(
            proc, "fetch_articles_to_process", AsyncMock(return_value=[article()])
        )
        monkeypatch.setattr(
            proc,
            "process_article_batch",
            MagicMock(side_effect=RuntimeError("worker boom")),
        )
        store = AsyncMock()
        monkeypatch.setattr(proc, "store_results_in_redshift", store)
        proc.postgres_conn = MagicMock()
        asyncio.run(proc.run_processing_job())
        store.assert_not_awaited()

    def test_job_reraises_and_cleans_up(self, proc, monkeypatch):
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
        monkeypatch.setattr(
            sys, "argv", ["prog", "--confidence-threshold", "0.5"]
        )
        inst = MagicMock()
        inst.run_processing_job = AsyncMock()
        monkeypatch.setattr(
            ner_mod, "KubernetesNERProcessor", MagicMock(return_value=inst)
        )
        with pytest.raises(SystemExit) as ei:
            asyncio.run(ner_mod.main())
        assert ei.value.code == 0
        inst.run_processing_job.assert_awaited_once()

    def test_main_failure_exits_one(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog"])
        inst = MagicMock()
        inst.run_processing_job = AsyncMock(side_effect=RuntimeError("job fail"))
        monkeypatch.setattr(
            ner_mod, "KubernetesNERProcessor", MagicMock(return_value=inst)
        )
        with pytest.raises(SystemExit) as ei:
            asyncio.run(ner_mod.main())
        assert ei.value.code == 1
