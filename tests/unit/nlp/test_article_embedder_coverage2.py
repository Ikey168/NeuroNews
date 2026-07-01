"""Coverage-focused tests for src/nlp/article_embedder.py.

Complements ``test_article_embedder_extra.py`` by exercising the database and
batch code paths it leaves untouched: cached-embedding reuse in
``generate_embedding``, the full ``generate_embeddings_batch`` flow (including
the all-cached short-circuit), ``_get_existing_embedding`` /
``_filter_existing_embeddings`` / ``store_embeddings`` /
``get_embeddings_for_clustering`` / ``create_embeddings_table`` against a
mocked psycopg2, the quality-score edge cases, and the error-handling
fallbacks.

SentenceTransformer and nltk.stopwords are replaced with lightweight stubs so
no model download or NLTK corpus is required; psycopg2 is mocked so no real
database is touched.
"""

# --- Warm up heavy C-extension imports BEFORE coverage traces them. ----------
import torch  # noqa: E402,F401

try:
    import torch._dynamo  # noqa: E402,F401
except Exception:
    pass
try:
    from transformers import pipeline as _warm_pipeline  # noqa: E402,F401
except Exception:
    pass
# -----------------------------------------------------------------------------

import os  # noqa: E402
import sys  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

np = pytest.importorskip("numpy")

import nlp.article_embedder as mod  # noqa: E402


@pytest.fixture
def embedder(monkeypatch):
    fake_model = MagicMock()
    fake_model.get_sentence_embedding_dimension.return_value = 4
    fake_model.encode.return_value = np.array([0.1, 0.2, 0.3, 0.4])
    monkeypatch.setattr(mod, "SentenceTransformer", lambda name: fake_model)
    fake_stop = MagicMock()
    fake_stop.words.return_value = ["the", "a", "an", "is"]
    monkeypatch.setattr(mod, "stopwords", fake_stop)
    # Give it connection params so DB code paths activate.
    return mod.ArticleEmbedder(conn_params={"host": "localhost", "dbname": "x"})


def dict_cursor(fetchone=None, fetchall=None, rowcount=0):
    """Return a psycopg2 connection cm whose cursor(...) yields canned data."""
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = fetchall or []
    cursor.rowcount = rowcount
    cur_cm = MagicMock()
    cur_cm.__enter__ = MagicMock(return_value=cursor)
    cur_cm.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cur_cm
    conn_cm = MagicMock()
    conn_cm.__enter__ = MagicMock(return_value=conn)
    conn_cm.__exit__ = MagicMock(return_value=False)
    return conn_cm, conn, cursor


# --------------------------------------------------------------------------- #
# preprocess_text fallback (lines 150-152)
# --------------------------------------------------------------------------- #
class TestPreprocessFallback:
    def test_exception_returns_truncated_original(self, embedder, monkeypatch):
        # Force re.sub to blow up so the except-branch fallback executes.
        monkeypatch.setattr(mod.re, "sub", MagicMock(side_effect=RuntimeError("re")))
        text = "x" * 2000
        out = embedder.preprocess_text(text)
        assert out == text[:1000]


# --------------------------------------------------------------------------- #
# _calculate_embedding_quality edge cases (lines 369-374, 391-394)
# --------------------------------------------------------------------------- #
class TestQualityEdgeCases:
    def test_short_text_low_score(self, embedder):
        score = embedder._calculate_embedding_quality(
            np.array([0.5, 0.5, 0.5, 0.5]), "one two"
        )
        assert 0.0 <= score <= 1.0

    def test_medium_short_text_branch(self, embedder):
        # 5-19 words -> text_score = 0.6 (line 370)
        text = " ".join(["word"] * 10)
        score = embedder._calculate_embedding_quality(np.array([0.5] * 8), text)
        assert 0.0 <= score <= 1.0

    def test_ideal_length_text_branch(self, embedder):
        # 20-99 words -> text_score = 1.0 (line 372)
        text = " ".join(["word"] * 50)
        score = embedder._calculate_embedding_quality(np.array([0.5] * 8), text)
        assert 0.0 <= score <= 1.0

    def test_long_text_branch(self, embedder):
        long_text = " ".join(["word"] * 150)
        score = embedder._calculate_embedding_quality(
            np.array([0.5] * 8), long_text
        )
        assert 0.0 <= score <= 1.0

    def test_quality_exception_returns_default(self, embedder, monkeypatch):
        monkeypatch.setattr(
            mod.np, "linalg", MagicMock(norm=MagicMock(side_effect=RuntimeError("x")))
        )
        assert embedder._calculate_embedding_quality(np.array([1.0]), "text") == 0.5


# --------------------------------------------------------------------------- #
# generate_embedding cached-reuse path (lines 181-190)
# --------------------------------------------------------------------------- #
class TestGenerateEmbeddingCache:
    @pytest.mark.asyncio
    async def test_returns_cached_embedding(self, embedder, monkeypatch):
        cached = {"article_id": "a1", "embedding_vector": [0.0] * 4, "from_cache": True}

        async def fake_existing(article_id, text_hash):
            return cached

        monkeypatch.setattr(embedder, "_get_existing_embedding", fake_existing)
        result = await embedder.generate_embedding("body", title="t", article_id="a1")
        assert result is cached
        assert embedder.stats["cache_hits"] == 1
        # The model must NOT be invoked when a cache hit occurs.
        embedder.model.encode.assert_not_called()


# --------------------------------------------------------------------------- #
# generate_embeddings_batch (lines 250-339)
# --------------------------------------------------------------------------- #
class TestGenerateBatch:
    @pytest.mark.asyncio
    async def test_batch_generates_results(self, embedder, monkeypatch):
        embedder.model.encode.return_value = np.array(
            [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]
        )

        async def no_filter(data):
            return data

        monkeypatch.setattr(embedder, "_filter_existing_embeddings", no_filter)
        articles = [
            {"id": "1", "title": "T1", "content": "Content one here."},
            {"id": "2", "title": "T2", "content": "Content two here."},
        ]
        results = await embedder.generate_embeddings_batch(articles)
        assert len(results) == 2
        assert results[0]["article_id"] == "1"
        assert results[0]["embedding_dimension"] == 4
        assert all(r["processing_time"] >= 0 for r in results)
        assert embedder.stats["embeddings_generated"] == 2

    @pytest.mark.asyncio
    async def test_batch_all_cached_returns_empty(self, embedder, monkeypatch):
        async def filter_all(data):
            return []

        monkeypatch.setattr(embedder, "_filter_existing_embeddings", filter_all)
        results = await embedder.generate_embeddings_batch(
            [{"id": "1", "title": "T", "content": "C"}]
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_error_increments_stat(self, embedder, monkeypatch):
        async def no_filter(data):
            return data

        monkeypatch.setattr(embedder, "_filter_existing_embeddings", no_filter)
        embedder.model.encode.side_effect = RuntimeError("encode boom")
        with pytest.raises(RuntimeError, match="encode boom"):
            await embedder.generate_embeddings_batch(
                [{"id": "1", "title": "T", "content": "C"}]
            )
        assert embedder.stats["errors"] == 1


# --------------------------------------------------------------------------- #
# _get_existing_embedding (lines 400-462)
# --------------------------------------------------------------------------- #
class TestGetExistingEmbedding:
    @pytest.mark.asyncio
    async def test_found_row_parsed(self, embedder, monkeypatch):
        row = {
            "article_id": "a1",
            "embedding_vector_json": "[0.1, 0.2, 0.3, 0.4]",
            "embedding_dimension": 4,
            "text_preprocessed": "clean text",
            "text_hash": "hash",
            "tokens_count": 2,
            "embedding_quality_score": 0.8,
            "processing_time": 0.05,
            "embedding_model": embedder.model_name,
            "created_at": datetime(2026, 1, 1),
        }
        conn_cm, conn, cursor = dict_cursor(fetchone=row)
        monkeypatch.setattr(mod.psycopg2, "connect", lambda **kw: conn_cm)
        result = await embedder._get_existing_embedding("a1", "hash")
        assert result["from_cache"] is True
        assert result["embedding_vector"] == [0.1, 0.2, 0.3, 0.4]
        assert result["embedding_quality_score"] == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_no_row_returns_none(self, embedder, monkeypatch):
        conn_cm, conn, cursor = dict_cursor(fetchone=None)
        monkeypatch.setattr(mod.psycopg2, "connect", lambda **kw: conn_cm)
        assert await embedder._get_existing_embedding("a1", "hash") is None

    @pytest.mark.asyncio
    async def test_db_error_returns_none(self, embedder, monkeypatch):
        monkeypatch.setattr(
            mod.psycopg2, "connect", MagicMock(side_effect=RuntimeError("boom"))
        )
        assert await embedder._get_existing_embedding("a1", "hash") is None


# --------------------------------------------------------------------------- #
# _filter_existing_embeddings (lines 468-512)
# --------------------------------------------------------------------------- #
class TestFilterExisting:
    @pytest.mark.asyncio
    async def test_filters_existing(self, embedder, monkeypatch):
        data = [
            {"article_id": "1", "text_hash": "h1", "preprocessed_text": "a"},
            {"article_id": "2", "text_hash": "h2", "preprocessed_text": "b"},
        ]
        # Existing: article 1 / h1 -> should be filtered out.
        conn_cm, conn, cursor = dict_cursor(fetchall=[("1", "h1")])
        monkeypatch.setattr(mod.psycopg2, "connect", lambda **kw: conn_cm)
        result = await embedder._filter_existing_embeddings(data)
        assert len(result) == 1
        assert result[0]["article_id"] == "2"
        assert embedder.stats["cache_hits"] == 1

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self, embedder):
        assert await embedder._filter_existing_embeddings([]) == []

    @pytest.mark.asyncio
    async def test_error_returns_all(self, embedder, monkeypatch):
        data = [{"article_id": "1", "text_hash": "h1", "preprocessed_text": "a"}]
        monkeypatch.setattr(
            mod.psycopg2, "connect", MagicMock(side_effect=RuntimeError("boom"))
        )
        result = await embedder._filter_existing_embeddings(data)
        assert result == data


# --------------------------------------------------------------------------- #
# store_embeddings (lines 514-571)
# --------------------------------------------------------------------------- #
class TestStoreEmbeddings:
    @pytest.mark.asyncio
    async def test_no_conn_params_returns_zero(self, monkeypatch):
        fake_model = MagicMock()
        fake_model.get_sentence_embedding_dimension.return_value = 4
        monkeypatch.setattr(mod, "SentenceTransformer", lambda name: fake_model)
        monkeypatch.setattr(mod, "stopwords", MagicMock(words=lambda x: []))
        emb = mod.ArticleEmbedder(conn_params={})
        assert await emb.store_embeddings([{"article_id": "1"}]) == 0

    @pytest.mark.asyncio
    async def test_stores_rows(self, embedder, monkeypatch):
        conn_cm, conn, cursor = dict_cursor(rowcount=2)
        monkeypatch.setattr(mod.psycopg2, "connect", lambda **kw: conn_cm)
        embeddings = [
            {
                "article_id": "1",
                "embedding_dimension": 4,
                "embedding_vector": [0.1, 0.2, 0.3, 0.4],
                "text_preprocessed": "t",
                "text_hash": "h",
                "tokens_count": 1,
                "embedding_quality_score": 0.9,
                "processing_time": 0.1,
            }
        ]
        stored = await embedder.store_embeddings(embeddings)
        assert stored == 2
        conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_error_returns_zero(self, embedder, monkeypatch):
        monkeypatch.setattr(
            mod.psycopg2, "connect", MagicMock(side_effect=RuntimeError("boom"))
        )
        assert await embedder.store_embeddings([{"article_id": "1"}]) == 0


# --------------------------------------------------------------------------- #
# get_embeddings_for_clustering (lines 573-672)
# --------------------------------------------------------------------------- #
class TestClustering:
    @pytest.mark.asyncio
    async def test_no_conn_params_returns_empty(self, monkeypatch):
        fake_model = MagicMock()
        fake_model.get_sentence_embedding_dimension.return_value = 4
        monkeypatch.setattr(mod, "SentenceTransformer", lambda name: fake_model)
        monkeypatch.setattr(mod, "stopwords", MagicMock(words=lambda x: []))
        emb = mod.ArticleEmbedder(conn_params=None)
        assert await emb.get_embeddings_for_clustering() == []

    @pytest.mark.asyncio
    async def test_returns_rows_with_filters(self, embedder, monkeypatch):
        row = {
            "article_id": "a1",
            "embedding_vector_json": "[0.1, 0.2, 0.3, 0.4]",
            "embedding_dimension": 4,
            "embedding_quality_score": 0.7,
            "title": "Title",
            "content": "Content",
            "source": "src",
            "published_date": datetime(2026, 1, 1),
            "category": "tech",
            "sentiment_score": 0.5,
            "source_credibility": "trusted",
        }
        conn_cm, conn, cursor = dict_cursor(fetchall=[row])
        monkeypatch.setattr(mod.psycopg2, "connect", lambda **kw: conn_cm)
        results = await embedder.get_embeddings_for_clustering(
            limit=10, category_filter="tech", days_back=14
        )
        assert len(results) == 1
        assert results[0]["article_id"] == "a1"
        assert isinstance(results[0]["embedding_vector"], np.ndarray)
        assert results[0]["sentiment_score"] == pytest.approx(0.5)
        # limit + category both appended to params -> query executed once.
        assert cursor.execute.called

    @pytest.mark.asyncio
    async def test_clustering_error_returns_empty(self, embedder, monkeypatch):
        monkeypatch.setattr(
            mod.psycopg2, "connect", MagicMock(side_effect=RuntimeError("boom"))
        )
        assert await embedder.get_embeddings_for_clustering() == []


# --------------------------------------------------------------------------- #
# create_embeddings_table (lines 686-719)
# --------------------------------------------------------------------------- #
class TestCreateTable:
    @pytest.mark.asyncio
    async def test_no_conn_params_noop(self, monkeypatch):
        fake_model = MagicMock()
        fake_model.get_sentence_embedding_dimension.return_value = 4
        monkeypatch.setattr(mod, "SentenceTransformer", lambda name: fake_model)
        monkeypatch.setattr(mod, "stopwords", MagicMock(words=lambda x: []))
        emb = mod.ArticleEmbedder(conn_params={})
        # Should return without touching psycopg2.
        assert await emb.create_embeddings_table() is None

    @pytest.mark.asyncio
    async def test_creates_table(self, embedder, monkeypatch):
        conn_cm, conn, cursor = dict_cursor()
        monkeypatch.setattr(mod.psycopg2, "connect", lambda **kw: conn_cm)
        await embedder.create_embeddings_table()
        assert cursor.execute.called
        conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_table_error_swallowed(self, embedder, monkeypatch):
        # Errors are logged but not re-raised in create_embeddings_table.
        monkeypatch.setattr(
            mod.psycopg2, "connect", MagicMock(side_effect=RuntimeError("boom"))
        )
        assert await embedder.create_embeddings_table() is None


# --------------------------------------------------------------------------- #
# get_statistics avg calculation with data (line 679-683)
# --------------------------------------------------------------------------- #
class TestStatistics:
    def test_avg_processing_time_computed(self, embedder):
        embedder.stats["embeddings_generated"] = 2
        embedder.stats["total_processing_time"] = 1.0
        stats = embedder.get_statistics()
        assert stats["avg_processing_time"] == pytest.approx(0.5)
        assert stats["model_name"] == embedder.model_name
        assert stats["embedding_dimension"] == 4
