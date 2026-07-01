"""Comprehensive coverage tests for src/nlp/kubernetes/ai_processor.py.

All heavy / external clients (SentenceTransformer, psycopg2, DuckDB shared
connection, Redshift processor, torch.cuda) are mocked where they are looked
up so nothing touches the network or downloads a model. The real processing
logic (preprocessing, embedding wrappers, LDA/UMAP topic modeling, batching,
result formatting, stats, storage fallback, async orchestration) is exercised
with concrete assertions.
"""

import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# Guard genuinely optional heavy deps.
pytest.importorskip("torch")
pytest.importorskip("umap")
pytest.importorskip("sentence_transformers")
np = pytest.importorskip("numpy")

import asyncio  # noqa: E402

from nlp.kubernetes import ai_processor as ai_mod  # noqa: E402
from nlp.kubernetes.ai_processor import KubernetesAIProcessor  # noqa: E402


def make_proc(tmp_path, **over):
    kwargs = dict(
        batch_size=5,
        use_gpu=False,
        num_topics=2,
        topic_model_type="LDA",
        output_dir=str(tmp_path / "out"),
        model_cache_dir=str(tmp_path / "m"),
        gpu_cache_dir=str(tmp_path / "g"),
    )
    kwargs.update(over)
    return KubernetesAIProcessor(**kwargs)


@pytest.fixture
def proc(tmp_path):
    return make_proc(tmp_path)


def article(**over):
    base = dict(
        article_id="a1",
        title="AI breakthrough",
        content="Researchers unveiled a new machine learning model for vision.",
        url="https://example.com/1",
        source="bbc",
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        sentiment_label="POSITIVE",
        sentiment_score=0.9,
    )
    base.update(over)
    return base


# Enough distinct-vocabulary documents that TfidfVectorizer(min_df=2) keeps
# features and LDA can fit against num_topics=2.
CORPUS = [
    "economy market stocks finance trading investors economy market",
    "economy market inflation finance banking economy market trading",
    "football soccer players goals match football soccer league",
    "football soccer coach stadium football soccer players match",
    "economy finance market banks economy finance trading stocks",
    "football league match players football soccer goals stadium",
]


class TestInit:
    def test_directories_created_and_stats(self, proc):
        assert os.path.isdir(proc.output_dir)
        assert os.path.isdir(proc.model_cache_dir)
        assert os.path.isdir(proc.gpu_cache_dir)
        assert proc.use_gpu is False
        assert proc.stats["gpu_used"] is False
        assert proc.stats["num_topics"] == 2
        assert proc.stats["topic_model_type"] == "LDA"
        assert proc.stats["articles_processed"] == 0

    def test_gpu_branch_when_cuda_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ai_mod.torch.cuda, "is_available", lambda: True)
        empty = MagicMock()
        monkeypatch.setattr(ai_mod.torch.cuda, "empty_cache", empty)
        p = make_proc(tmp_path, use_gpu=True)
        assert p.use_gpu is True
        assert p.stats["gpu_used"] is True
        empty.assert_called()  # GPU init path executed
        assert os.environ.get("PYTORCH_CUDA_ALLOC_CONF") == "max_split_size_mb:512"


class TestPreprocess:
    def test_combines_title_and_content_collapses_whitespace(self, proc):
        out = proc.preprocess_texts([article(title="T", content="a   b\n\nc")])
        assert out == ["T. a b c"]

    def test_truncation_at_sentence_boundary(self, proc, monkeypatch):
        monkeypatch.setenv("ARTICLE_TEXT_MAX_LENGTH", "40")
        long = "First sentence here. " + "Second longer sentence padding. " * 10
        out = proc.preprocess_texts([article(title="Head", content=long)])
        assert len(out[0]) <= 60
        assert out[0].startswith("Head. First sentence here")

    def test_missing_keys_default_empty(self, proc):
        out = proc.preprocess_texts([{"article_id": "x"}])
        assert out == [". "] or out == [".  ".strip()]

    def test_empty_list(self, proc):
        assert proc.preprocess_texts([]) == []

    def test_per_article_exception_appends_empty(self, proc):
        # .get("title"/"content") raises inside the try; the except handler
        # still logs article_id safely -> "" appended to keep alignment.
        class Bad:
            def get(self, key, default=None):
                if key == "article_id":
                    return "bad-id"
                raise ValueError("bad article field")

        out = proc.preprocess_texts([Bad()])
        assert out == [""]


class TestGenerateEmbeddings:
    def test_generates_and_counts(self, proc):
        model = MagicMock()
        model.encode.return_value = np.ones((2, 4), dtype=float)
        proc.embedding_model = model
        emb = proc.generate_embeddings(["hello world", "another doc"])
        assert emb.shape == (2, 4)
        assert proc.stats["embeddings_generated"] == 2
        # normalize/convert flags passed through to the model wrapper
        _, kwargs = model.encode.call_args
        assert kwargs["convert_to_numpy"] is True
        assert kwargs["normalize_embeddings"] is True
        assert kwargs["batch_size"] == proc.batch_size

    def test_all_empty_texts_returns_empty(self, proc):
        proc.embedding_model = MagicMock()
        emb = proc.generate_embeddings(["", "   "])
        assert emb.size == 0
        proc.embedding_model.encode.assert_not_called()

    def test_exception_returns_empty_array(self, proc):
        model = MagicMock()
        model.encode.side_effect = RuntimeError("cuda oom")
        proc.embedding_model = model
        emb = proc.generate_embeddings(["real text here"])
        assert emb.size == 0


class TestLDATopicModeling:
    def test_real_lda_assignments_and_descriptions(self, tmp_path):
        p = make_proc(tmp_path, topic_model_type="LDA", num_topics=2)
        # Build the real sklearn LDA model as initialize() would.
        from sklearn.decomposition import LatentDirichletAllocation

        p.topic_model = LatentDirichletAllocation(
            n_components=2, random_state=42, max_iter=20, learning_method="batch"
        )
        assignments, descriptions = p.perform_lda_topic_modeling(
            CORPUS, np.zeros((len(CORPUS), 3))
        )
        assert len(assignments) == len(CORPUS)
        assert all(0 <= a < 2 for a in assignments)
        assert len(descriptions) == 2
        d0 = descriptions[0]
        assert d0["model_type"] == "LDA"
        assert d0["topic_id"] == 0
        assert len(d0["topic_words"]) == 10
        assert d0["topic_label"].startswith("Topic_0_")
        assert p.stats["topics_extracted"] == 2

    def test_lda_failure_returns_empty(self, proc):
        # topic_model is None -> .fit raises -> caught -> ([], [])
        proc.topic_model = None
        assignments, descriptions = proc.perform_lda_topic_modeling(
            CORPUS, np.zeros((len(CORPUS), 3))
        )
        assert assignments == []
        assert descriptions == []


class TestUMAPTopicModeling:
    def test_real_umap_kmeans(self, tmp_path):
        p = make_proc(tmp_path, topic_model_type="UMAP", num_topics=2)
        rng = np.random.RandomState(0)
        # Two separated clusters in embedding space.
        emb = np.vstack(
            [rng.normal(0, 0.1, (6, 8)), rng.normal(5, 0.1, (6, 8))]
        ).astype(np.float32)
        texts = CORPUS + CORPUS
        assignments, descriptions = p.perform_umap_topic_modeling(texts, emb)
        assert len(assignments) == len(texts)
        assert all(0 <= a < 2 for a in assignments)
        assert len(descriptions) >= 1
        for d in descriptions:
            assert d["model_type"] == "UMAP+KMeans"
            assert "num_documents" in d
        assert p.stats["topics_extracted"] == len(descriptions)

    def test_umap_topic_description_tfidf_failure(self, tmp_path, monkeypatch):
        # Force the per-topic TF-IDF to raise so the except-branch produces an
        # empty-words topic description (lines building the fallback desc).
        p = make_proc(tmp_path, topic_model_type="UMAP", num_topics=2)
        import nlp.kubernetes.ai_processor as m

        real_umap = m.umap.UMAP

        # Make KMeans deterministic mapping: assign all docs to cluster 0.
        class FakeKMeans:
            def __init__(self, *a, **k):
                pass

            def fit_predict(self, X):
                return np.zeros(len(X), dtype=int)

        monkeypatch.setattr(m, "KMeans", FakeKMeans)

        class FakeUMAP:
            def __init__(self, *a, **k):
                pass

            def fit_transform(self, X):
                return np.asarray(X)[:, :2]

        monkeypatch.setattr(m.umap, "UMAP", FakeUMAP)

        # Vectorizer that raises for the topic-description step.
        class BoomVectorizer:
            def __init__(self, *a, **k):
                pass

            def fit_transform(self, texts):
                raise ValueError("empty vocabulary")

        monkeypatch.setattr(m, "TfidfVectorizer", BoomVectorizer)

        emb = np.random.RandomState(1).normal(0, 1, (4, 6)).astype(np.float32)
        texts = ["doc one text", "doc two text", "doc three text", "doc four text"]
        assignments, descriptions = p.perform_umap_topic_modeling(texts, emb)
        assert all(a == 0 for a in assignments)
        # Cluster 0 got a fallback description with empty words.
        cluster0 = [d for d in descriptions if d["topic_id"] == 0]
        assert len(cluster0) == 1
        assert cluster0[0]["topic_words"] == []
        assert cluster0[0]["topic_label"] == "Topic_0"
        assert cluster0[0]["num_documents"] == 4
        m.umap.UMAP = real_umap

    def test_umap_failure_returns_empty(self, tmp_path):
        p = make_proc(tmp_path, topic_model_type="UMAP", num_topics=2)
        # Empty embeddings -> umap raises -> caught -> ([], [])
        assignments, descriptions = p.perform_umap_topic_modeling([], np.array([]))
        assert assignments == []
        assert descriptions == []


class TestPerformTopicModelingDispatch:
    def test_dispatches_to_lda(self, proc, monkeypatch):
        lda = MagicMock(return_value=([0], [{"x": 1}]))
        monkeypatch.setattr(proc, "perform_lda_topic_modeling", lda)
        proc.topic_model_type = "LDA"
        out = proc.perform_topic_modeling(["t"], np.ones((1, 2)))
        lda.assert_called_once()
        assert out == ([0], [{"x": 1}])

    def test_dispatches_to_umap(self, proc, monkeypatch):
        umap_fn = MagicMock(return_value=([1], [{"y": 2}]))
        monkeypatch.setattr(proc, "perform_umap_topic_modeling", umap_fn)
        proc.topic_model_type = "UMAP"
        out = proc.perform_topic_modeling(["t"], np.ones((1, 2)))
        umap_fn.assert_called_once()
        assert out == ([1], [{"y": 2}])

    def test_dispatch_exception_returns_empty(self, proc, monkeypatch):
        monkeypatch.setattr(
            proc,
            "perform_lda_topic_modeling",
            MagicMock(side_effect=RuntimeError("boom")),
        )
        proc.topic_model_type = "LDA"
        assert proc.perform_topic_modeling(["t"], np.ones((1, 2))) == ([], [])


class TestProcessArticleBatch:
    def test_full_batch_result_formatting(self, proc, monkeypatch):
        articles = [article(article_id="a1"), article(article_id="a2")]
        monkeypatch.setattr(
            proc, "generate_embeddings", lambda texts: np.ones((len(texts), 3))
        )
        descs = [
            {
                "topic_id": 0,
                "topic_words": ["ai", "ml"],
                "topic_weights": [0.5, 0.3],
                "topic_label": "Topic_0_ai_ml",
                "model_type": "LDA",
            },
            {
                "topic_id": 1,
                "topic_words": ["sport"],
                "topic_weights": [0.9],
                "topic_label": "Topic_1_sport",
                "model_type": "LDA",
            },
        ]
        monkeypatch.setattr(
            proc, "perform_topic_modeling", lambda t, e: ([0, 1], descs)
        )
        results = proc.process_article_batch(articles)
        assert len(results) == 2
        r0 = results[0]
        assert r0["article_id"] == "a1"
        assert r0["topic_id"] == 0
        assert r0["topic_label"] == "Topic_0_ai_ml"
        # topic_words/weights serialized to JSON strings
        assert json.loads(r0["topic_words"]) == ["ai", "ml"]
        assert json.loads(r0["topic_weights"]) == [0.5, 0.3]
        assert r0["topic_model_type"] == "LDA"
        assert r0["gpu_used"] is False
        assert proc.stats["articles_processed"] == 2
        assert proc.stats["batches_processed"] == 1

    def test_missing_topic_description_skips_article(self, proc, monkeypatch):
        monkeypatch.setattr(
            proc, "generate_embeddings", lambda texts: np.ones((1, 3))
        )
        # assignment points at topic 5 but no description with topic_id 5
        monkeypatch.setattr(
            proc,
            "perform_topic_modeling",
            lambda t, e: ([5], [{"topic_id": 0, "topic_label": "x"}]),
        )
        results = proc.process_article_batch([article()])
        assert results == []

    def test_per_article_result_exception_increments_failed(self, proc, monkeypatch):
        # Article missing the required "title" key -> KeyError inside result
        # dict build -> caught per-article -> articles_failed incremented.
        bad = {"article_id": "a1", "url": "u", "source": "s"}
        monkeypatch.setattr(
            proc, "generate_embeddings", lambda texts: np.ones((1, 3))
        )
        monkeypatch.setattr(
            proc,
            "perform_topic_modeling",
            lambda t, e: (
                [0],
                [
                    {
                        "topic_id": 0,
                        "topic_words": [],
                        "topic_weights": [],
                        "topic_label": "L",
                        "model_type": "LDA",
                    }
                ],
            ),
        )
        results = proc.process_article_batch([bad])
        assert results == []
        assert proc.stats["articles_failed"] == 1

    def test_empty_embeddings_returns_empty(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "generate_embeddings", lambda texts: np.array([]))
        assert proc.process_article_batch([article()]) == []

    def test_no_topic_assignments_returns_empty(self, proc, monkeypatch):
        monkeypatch.setattr(
            proc, "generate_embeddings", lambda texts: np.ones((1, 3))
        )
        monkeypatch.setattr(proc, "perform_topic_modeling", lambda t, e: ([], []))
        assert proc.process_article_batch([article()]) == []

    def test_outer_exception_increments_failed(self, proc, monkeypatch):
        monkeypatch.setattr(
            proc,
            "generate_embeddings",
            MagicMock(side_effect=RuntimeError("explode")),
        )
        arts = [article(), article(article_id="a2")]
        assert proc.process_article_batch(arts) == []
        assert proc.stats["articles_failed"] == len(arts)


class TestFetchArticles:
    def test_fetch_maps_rows(self, proc):
        cur = MagicMock()
        cur.fetchall.return_value = [
            (
                "a1",
                "Title",
                "Content body",
                "https://u/1",
                "src",
                "2026-01-01",
                "2026-01-02",
                "POSITIVE",
                0.8,
            )
        ]
        cur.__enter__ = lambda s: cur
        cur.__exit__ = lambda *a: False
        conn = MagicMock()
        conn.cursor.return_value = cur
        proc.postgres_conn = conn
        articles = asyncio.run(proc.fetch_articles_to_process(limit=10))
        assert len(articles) == 1
        assert articles[0]["article_id"] == "a1"
        assert articles[0]["sentiment_label"] == "POSITIVE"
        # LIMIT clause added when limit is provided
        sql, params = cur.execute.call_args[0]
        assert "LIMIT" in sql
        assert params[-1] == 10

    def test_fetch_error_returns_empty(self, proc):
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError("db down")
        proc.postgres_conn = conn
        assert asyncio.run(proc.fetch_articles_to_process()) == []


class TestStoreResults:
    def test_empty_results_noop(self, proc):
        # Should return immediately without touching redshift_processor (None).
        asyncio.run(proc.store_results_in_redshift([]))

    def test_success_path(self, proc):
        processor = MagicMock()
        processor.__enter__.return_value = processor
        processor.__exit__.return_value = False
        processor.execute_sql = AsyncMock()
        processor.batch_insert_topic_results = AsyncMock(return_value=3)
        proc.redshift_processor = processor
        results = [{"article_id": "a1", "topic_id": 0}]
        asyncio.run(proc.store_results_in_redshift(results))
        processor.batch_insert_topic_results.assert_awaited_once_with(results)
        processor.execute_sql.assert_awaited()  # table creation ran

    def test_failure_writes_backup_file(self, proc):
        # redshift_processor is None -> `with None as ...` raises -> backup file.
        results = [{"article_id": "a1", "topic_id": 0, "processing_timestamp": "x"}]
        asyncio.run(proc.store_results_in_redshift(results))
        backups = [
            f
            for f in os.listdir(proc.output_dir)
            if f.startswith("topic_results_backup_")
        ]
        assert len(backups) == 1
        data = json.loads(open(os.path.join(proc.output_dir, backups[0])).read())
        assert data[0]["article_id"] == "a1"


class TestCreateTable:
    def test_create_table_executes_sql(self, proc):
        processor = MagicMock()
        processor.execute_sql = AsyncMock()
        asyncio.run(proc.create_topic_results_table(processor))
        sql = processor.execute_sql.await_args[0][0]
        assert "nlp_results.topic_modeling" in sql

    def test_create_table_reraises(self, proc):
        processor = MagicMock()
        processor.execute_sql = AsyncMock(side_effect=RuntimeError("no perms"))
        with pytest.raises(RuntimeError):
            asyncio.run(proc.create_topic_results_table(processor))


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
        assert cur.execute.called

    def test_update_error_rolls_back(self, proc):
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError("locked")
        proc.postgres_conn = conn
        asyncio.run(proc.update_postgres_processing_status(["a1"]))
        conn.rollback.assert_called_once()


class TestSaveStats:
    def test_writes_stats_and_derives_throughput(self, proc):
        proc.stats["articles_processed"] = 4
        proc.stats["topics_extracted"] = 2
        proc.stats["total_processing_time"] = 2.0
        proc.save_processing_stats()
        files = [f for f in os.listdir(proc.output_dir) if f.startswith("topic_job_stats")]
        assert len(files) == 1
        data = json.loads(open(os.path.join(proc.output_dir, files[0])).read())
        assert data["articles_processed"] == 4
        assert "average_processing_time" in data
        assert "throughput_articles_per_second" in data

    def test_save_stats_zero_processed(self, proc):
        proc.save_processing_stats()
        files = [f for f in os.listdir(proc.output_dir) if f.startswith("topic_job_stats")]
        data = json.loads(open(os.path.join(proc.output_dir, files[0])).read())
        assert data["articles_processed"] == 0
        assert "average_processing_time" not in data


class TestInitialize:
    def test_initialize_wires_components(self, proc, monkeypatch):
        st = MagicMock()
        monkeypatch.setattr(ai_mod, "SentenceTransformer", MagicMock(return_value=st))
        fake_conn = MagicMock()
        monkeypatch.setattr(ai_mod.psycopg2, "connect", lambda **kw: fake_conn)
        shared = MagicMock()
        import src.database.local_analytics_connector as lac

        monkeypatch.setattr(lac, "get_shared_connection", lambda: shared)
        asyncio.run(proc.initialize())
        assert proc.embedding_model is st
        assert proc.postgres_conn is fake_conn
        # LDA topic model instantiated for LDA type
        assert proc.topic_model is not None

    def test_initialize_umap_leaves_topic_model_none(self, tmp_path, monkeypatch):
        p = make_proc(tmp_path, topic_model_type="UMAP")
        monkeypatch.setattr(
            ai_mod, "SentenceTransformer", MagicMock(return_value=MagicMock())
        )
        monkeypatch.setattr(ai_mod.psycopg2, "connect", lambda **kw: MagicMock())
        import src.database.local_analytics_connector as lac

        monkeypatch.setattr(lac, "get_shared_connection", lambda: MagicMock())
        asyncio.run(p.initialize())
        assert p.topic_model is None

    def test_initialize_reraises_on_failure(self, proc, monkeypatch):
        monkeypatch.setattr(
            ai_mod,
            "SentenceTransformer",
            MagicMock(side_effect=RuntimeError("model dl failed")),
        )
        with pytest.raises(RuntimeError):
            asyncio.run(proc.initialize())


class TestRunProcessingJob:
    def test_no_articles_short_circuits(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "initialize", AsyncMock())
        monkeypatch.setattr(proc, "fetch_articles_to_process", AsyncMock(return_value=[]))
        store = AsyncMock()
        monkeypatch.setattr(proc, "store_results_in_redshift", store)
        asyncio.run(proc.run_processing_job())
        store.assert_not_awaited()

    def test_full_job_orchestration(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "initialize", AsyncMock())
        arts = [article(article_id="a1")]
        monkeypatch.setattr(
            proc, "fetch_articles_to_process", AsyncMock(return_value=arts)
        )
        batch_results = [{"article_id": "a1", "topic_id": 0}]
        monkeypatch.setattr(
            proc, "process_article_batch", lambda a: batch_results
        )
        store = AsyncMock()
        update = AsyncMock()
        monkeypatch.setattr(proc, "store_results_in_redshift", store)
        monkeypatch.setattr(proc, "update_postgres_processing_status", update)
        proc.postgres_conn = MagicMock()
        asyncio.run(proc.run_processing_job(max_articles=1))
        store.assert_awaited_once_with(batch_results)
        update.assert_awaited_once_with(["a1"])
        proc.postgres_conn.close.assert_called_once()

    def test_cleanup_closes_redshift_and_gpu(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "initialize", AsyncMock())
        monkeypatch.setattr(
            proc, "fetch_articles_to_process", AsyncMock(return_value=[])
        )
        proc.postgres_conn = MagicMock()
        redshift = MagicMock()
        redshift.close = AsyncMock()
        proc.redshift_processor = redshift
        # Force the GPU cleanup branch in finally.
        proc.use_gpu = True
        empty = MagicMock()
        monkeypatch.setattr(ai_mod.torch.cuda, "empty_cache", empty)
        asyncio.run(proc.run_processing_job())
        redshift.close.assert_awaited_once()
        empty.assert_called()

    def test_job_reraises_and_cleans_up(self, proc, monkeypatch):
        monkeypatch.setattr(
            proc, "initialize", AsyncMock(side_effect=RuntimeError("init fail"))
        )
        proc.postgres_conn = MagicMock()
        with pytest.raises(RuntimeError):
            asyncio.run(proc.run_processing_job())
        # finally block still closed the connection
        proc.postgres_conn.close.assert_called_once()


class TestMain:
    def test_main_success_exits_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "--num-topics", "3"])
        inst = MagicMock()
        inst.run_processing_job = AsyncMock()
        monkeypatch.setattr(ai_mod, "KubernetesAIProcessor", MagicMock(return_value=inst))
        with pytest.raises(SystemExit) as ei:
            asyncio.run(ai_mod.main())
        assert ei.value.code == 0
        inst.run_processing_job.assert_awaited_once()

    def test_main_failure_exits_one(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog"])
        inst = MagicMock()
        inst.run_processing_job = AsyncMock(side_effect=RuntimeError("job fail"))
        monkeypatch.setattr(ai_mod, "KubernetesAIProcessor", MagicMock(return_value=inst))
        with pytest.raises(SystemExit) as ei:
            asyncio.run(ai_mod.main())
        assert ei.value.code == 1
