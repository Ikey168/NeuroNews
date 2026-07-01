"""
RAG Retriever Smoke Tests
Issue #238: CI: Smoke tests for indexing & /ask

Lightweight smoke tests for the embeddings layer of the RAG pipeline. They
verify that the CURRENT EmbeddingProvider API generates embeddings of the
expected shape and value type.

NOTE on scope (aligned to the current source API):
The original suite also exercised an async, DB-backed RAG *indexer* surface
(``indexer.ingest_documents``, ``indexer.search``, ``indexer._get_connection``).
That surface no longer exists in the source: ``jobs/rag/indexer.py`` exposes an
MLflow-coupled ``RAGIndexer.index_documents`` job with none of those methods,
and there is no ``ingest_documents``/``_get_connection`` anywhere in the tree.
Those tests targeted removed functionality and have been dropped; see the
hybrid retriever tests (services/rag/retriever.py) for the current search API.
"""

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

# The local embedding backend requires sentence-transformers. Skip collection
# cleanly if it is genuinely absent rather than crashing.
pytest.importorskip("sentence_transformers")

from services.embeddings.provider import EmbeddingProvider


_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "tiny_corpus.jsonl"


class _MockSentenceTransformer:
    """Stand-in for SentenceTransformer that avoids network model downloads.

    Generates deterministic-shaped real numpy embeddings so the *real*
    EmbeddingProvider.embed_texts code path (batching, vstack, retries) runs
    end-to-end without requiring the model weights to be downloaded.
    """

    EMBEDDING_DIM = 384

    def __init__(self, *args, **kwargs):
        self.device = "cpu"

    def encode(self, texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        return np.random.rand(len(texts), self.EMBEDDING_DIM).astype("float32")

    def get_sentence_embedding_dimension(self):
        return self.EMBEDDING_DIM


@pytest.fixture
def test_documents():
    """Load the tiny corpus fixture as a list of document dicts."""
    documents = []
    with open(_FIXTURE_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                documents.append(json.loads(line))
    assert documents, "tiny_corpus fixture should not be empty"
    return documents


@pytest.fixture
def embeddings_provider():
    """A real EmbeddingProvider backed by a mocked SentenceTransformer.

    Only the network-dependent model load is mocked; embed_texts itself is the
    real current-source implementation (synchronous, returns a numpy array).
    """
    with patch(
        "services.embeddings.backends.local_sentence_transformers.SentenceTransformer",
        _MockSentenceTransformer,
    ):
        yield EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            batch_size=2,
        )


class TestRAGRetrieverSmoke:
    """Smoke tests for the RAG embeddings pipeline."""

    def test_basic_functionality_without_vector_db(self, test_documents, embeddings_provider):
        """Test embedding generation without requiring a vector database."""
        texts = [doc["content"] for doc in test_documents[:2]]

        # embed_texts is synchronous in the current EmbeddingProvider API and
        # returns a numpy array of shape [N, dim].
        embeddings = embeddings_provider.embed_texts(texts)

        assert embeddings is not None
        assert len(embeddings) == len(texts)

        for embedding in embeddings:
            assert len(embedding) > 0, "Empty embedding generated"
            assert all(
                isinstance(float(x), float) for x in embedding
            ), "Invalid embedding values"

        # Provider reports a positive embedding dimension matching the output.
        assert embeddings_provider.dim() == len(embeddings[0])

    def test_embedding_generation(self, embeddings_provider, test_documents):
        """Test that embeddings are generated correctly across a batch."""
        texts = [doc["content"] for doc in test_documents[:3]]

        embeddings = embeddings_provider.embed_texts(texts)

        assert embeddings is not None
        assert len(embeddings) == len(texts)

        for embedding in embeddings:
            assert len(embedding) > 0, "Empty embedding generated"
            assert all(
                isinstance(float(x), float) for x in embedding
            ), "Invalid embedding values"

    def test_empty_input_returns_empty(self, embeddings_provider):
        """Embedding an empty list returns an empty array of the right width."""
        embeddings = embeddings_provider.embed_texts([])

        assert embeddings is not None
        assert len(embeddings) == 0
        # Shape should still expose the embedding dimension as the second axis.
        assert embeddings.shape[1] == embeddings_provider.dim()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
