"""Comprehensive tests for services/rag/rerank.py."""

import os
import sys
from unittest.mock import MagicMock

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.rag.rerank import (  # noqa: E402
    CrossEncoderReranker,
    RerankResult,
    get_reranker,
    rerank_candidates,
)


def candidates(n=3):
    return [
        {"title": f"Doc {i}", "content": f"content about topic {i}",
         "score": 1.0 - i * 0.2, "source": "s", "url": f"u{i}"}
        for i in range(n)
    ]


@pytest.fixture
def disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_RERANKING", "false")
    return CrossEncoderReranker()


class TestCheckEnabled:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_RERANKING", raising=False)
        assert CrossEncoderReranker().is_enabled is False

    @pytest.mark.parametrize("val", ["true", "1", "yes", "on", "TRUE"])
    def test_enabled_values(self, monkeypatch, val):
        monkeypatch.setenv("ENABLE_RERANKING", val)
        r = CrossEncoderReranker()
        assert r.is_enabled is True


class TestFallbackRerank:
    def test_disabled_preserves_order(self, disabled):
        results = disabled.rerank("query", candidates(3))
        assert len(results) == 3
        assert all(isinstance(r, RerankResult) for r in results)
        assert [r.original_index for r in results] == [0, 1, 2]
        # rerank score equals original when disabled
        assert results[0].rerank_score == results[0].original_score

    def test_top_k(self, disabled):
        results = disabled.rerank("query", candidates(5), top_k=2)
        assert len(results) == 2

    def test_empty_candidates(self, disabled):
        assert disabled.rerank("query", []) == []


class TestFallbackScore:
    def test_jaccard_overlap(self, disabled):
        cands = [
            {"title": "quantum computing", "content": "qubits"},
            {"title": "cooking recipes", "content": "food"},
        ]
        scores = disabled._fallback_score("quantum computing", cands)
        assert scores[0] > scores[1]

    def test_no_overlap_zero(self, disabled):
        scores = disabled._fallback_score("xyz", [{"title": "abc", "content": "def"}])
        assert scores[0] == 0.0


class TestFuseScores:
    def test_weighted(self, disabled):
        assert disabled._fuse_scores(1.0, 0.0, "weighted", 0.7) == pytest.approx(0.7)

    def test_max(self, disabled):
        assert disabled._fuse_scores(0.3, 0.8, "max", 0.7) == 0.8

    def test_product(self, disabled):
        assert disabled._fuse_scores(0.5, 0.5, "product", 0.7) == pytest.approx(0.25)

    def test_rerank_only(self, disabled):
        assert disabled._fuse_scores(0.1, 0.9, "rerank_only", 0.7) == 0.9

    def test_unknown_falls_back_to_weighted(self, disabled):
        assert disabled._fuse_scores(1.0, 0.0, "bogus", 0.7) == pytest.approx(0.7)


class TestWithMockedModel:
    def test_rerank_with_model_reorders(self, monkeypatch):
        monkeypatch.setenv("ENABLE_RERANKING", "true")
        r = CrossEncoderReranker()
        r.is_enabled = True
        # mock cross-encoder scores: second doc scores highest
        r._cross_encoder_score = MagicMock(return_value=[0.1, 0.9, 0.5])
        r.model = MagicMock()
        results = r.rerank("q", candidates(3), score_fusion="rerank_only")
        # highest final score should be the second candidate
        top = max(results, key=lambda x: x.final_score)
        assert top.original_index == 1


class TestModelInfo:
    def test_get_model_info(self, disabled):
        info = disabled.get_model_info()
        assert info["is_enabled"] is False
        assert info["model_loaded"] is False
        assert "model_name" in info


class TestFactories:
    def test_get_reranker(self):
        assert isinstance(get_reranker(), CrossEncoderReranker)

    def test_rerank_candidates_function(self, monkeypatch):
        monkeypatch.setenv("ENABLE_RERANKING", "false")
        results = rerank_candidates("q", candidates(3), top_k=2)
        assert len(results) == 2
