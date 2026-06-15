"""Tests for src/nlp/article_embedder.py (model + nltk patched)."""

import os
import sys
from unittest.mock import MagicMock

import pytest

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
    return mod.ArticleEmbedder()


class TestPreprocess:
    def test_combines_title_and_content(self, embedder):
        out = embedder.preprocess_text("Body text here", title="Headline")
        assert out.startswith("Headline")
        assert "Body text here" in out

    def test_removes_urls_and_emails(self, embedder):
        out = embedder.preprocess_text("see https://x.com/a and mail me@x.com now")
        assert "https://" not in out
        assert "me@x.com" not in out

    def test_collapses_whitespace(self, embedder):
        assert "  " not in embedder.preprocess_text("a    b\n\nc")

    def test_truncates_long_text(self, embedder):
        long_text = "word " * 500
        out = embedder.preprocess_text(long_text)
        assert len(out.split()) <= 400


class TestHash:
    def test_deterministic(self, embedder):
        h1 = embedder.create_text_hash("hello")
        h2 = embedder.create_text_hash("hello")
        assert h1 == h2 and len(h1) == 64

    def test_different_text_different_hash(self, embedder):
        assert embedder.create_text_hash("a") != embedder.create_text_hash("b")


class TestQualityAndStats:
    def test_embedding_quality_returns_float(self, embedder):
        score = embedder._calculate_embedding_quality(
            np.array([0.1, 0.2, 0.3, 0.4]), "some preprocessed text content"
        )
        assert isinstance(score, float)

    def test_get_statistics(self, embedder):
        stats = embedder.get_statistics()
        assert "embeddings_generated" in stats


class TestGenerateEmbedding:
    @pytest.mark.asyncio
    async def test_generate(self, embedder):
        result = await embedder.generate_embedding("Body content", title="Title",
                                                   article_id="a1")
        assert result["article_id"] == "a1"
        assert result["embedding_dimension"] == 4
        assert len(result["embedding_vector"]) == 4
        assert result["embedding_model"] == embedder.model_name
        assert embedder.stats["embeddings_generated"] == 1

    @pytest.mark.asyncio
    async def test_generate_error_increments_stat(self, embedder):
        embedder.model.encode.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            await embedder.generate_embedding("x", article_id="a1")
        assert embedder.stats["errors"] == 1
