"""Tests for services/embeddings/provider.py logic (with a fake backend)."""

import os
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

np = pytest.importorskip("numpy")

from services.embeddings.provider import EmbeddingProvider  # noqa: E402


class FakeBackend:
    def __init__(self, dim=4):
        self._dim = dim
        self.calls = 0

    def embed_texts(self, texts):
        self.calls += 1
        return np.ones((len(texts), self._dim))

    def dim(self):
        return self._dim

    def name(self):
        return "fake-backend"


def make_provider(backend=None, **kw):
    backend = backend or FakeBackend()
    with patch.object(EmbeddingProvider, "_create_backend", return_value=backend):
        return EmbeddingProvider(**kw)


class TestInit:
    def test_defaults(self):
        p = make_provider()
        assert p.provider_name == "local"
        assert p.batch_size == 32
        assert p.max_retries == 3

    def test_unknown_provider_raises(self):
        # real _create_backend raises ValueError for unknown providers
        with pytest.raises(ValueError):
            EmbeddingProvider(provider="bogus")


class TestEmbedTexts:
    def test_basic(self):
        p = make_provider()
        out = p.embed_texts(["a", "b", "c"])
        assert out.shape == (3, 4)

    def test_empty(self):
        p = make_provider()
        out = p.embed_texts([])
        assert out.shape == (0, 4)

    def test_batching(self):
        backend = FakeBackend()
        p = make_provider(backend=backend, batch_size=2)
        out = p.embed_texts(["a", "b", "c", "d", "e"])
        assert out.shape == (5, 4)
        assert backend.calls == 3  # ceil(5/2)

    def test_retry_then_success(self):
        class FlakyBackend(FakeBackend):
            def __init__(self):
                super().__init__()
                self.attempts = 0

            def embed_texts(self, texts):
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError("transient")
                return np.ones((len(texts), self._dim))

        backend = FlakyBackend()
        p = make_provider(backend=backend, max_retries=3)
        out = p.embed_texts(["a"])
        assert out.shape == (1, 4)
        assert backend.attempts == 2

    def test_retry_exhausted_raises(self):
        class DeadBackend(FakeBackend):
            def embed_texts(self, texts):
                raise RuntimeError("always fails")

        p = make_provider(backend=DeadBackend(), max_retries=2)
        with pytest.raises(RuntimeError):
            p.embed_texts(["a"])


class TestDimAndName:
    def test_dim(self):
        assert make_provider(backend=FakeBackend(dim=8)).dim() == 8

    def test_name(self):
        assert make_provider().name() == "local:fake-backend"


class TestDeterministicSeed:
    def test_seed_set(self):
        p = make_provider(deterministic_seed=42)
        assert p.deterministic_seed == 42
