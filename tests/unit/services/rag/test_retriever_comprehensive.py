"""Comprehensive tests for services/rag/retriever.py."""

import os
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.rag.retriever import (  # noqa: E402
    HybridRetriever,
    HybridSearchFilters,
    HybridSearchResult,
    get_hybrid_retriever,
)


def hsr(doc_id, vec=None, lex=None, chunk="c1"):
    return HybridSearchResult(
        id=f"{doc_id}:{chunk}", doc_id=doc_id, chunk_id=chunk, title="t", content="body",
        source="s", url="u", published_at=None, vector_score=vec, lexical_score=lex,
        fusion_score=0.0, final_score=0.0, word_count=10, char_count=50,
        search_method="vector" if vec else "lexical",
    )


def vec_result(doc_id, score, chunk="c1"):
    return SimpleNamespace(
        id=f"{doc_id}:{chunk}", doc_id=doc_id, chunk_id=chunk, title="t", content="body",
        source="s", url="u", published_at=None, similarity_score=score,
        word_count=10, char_count=50,
    )


def lex_result(doc_id, rank, chunk="c1"):
    return SimpleNamespace(
        id=f"{doc_id}:{chunk}", doc_id=doc_id, chunk_id=chunk, title="t", content="body",
        source="s", url="u", published_at=None, rank=rank, word_count=10, char_count=50,
    )


@pytest.fixture
def retriever():
    return HybridRetriever()


class TestFilters:
    def test_defaults(self):
        f = HybridSearchFilters()
        assert f.min_vector_similarity == 0.0
        assert f.source is None


class TestInit:
    def test_default_weights(self, retriever):
        assert retriever.vector_weight == 0.6
        assert retriever.lexical_weight == 0.4
        assert retriever.rrf_k == 60


class TestMergeCandidates:
    def test_merge_overlapping(self, retriever):
        vector = [vec_result("d1", 0.9), vec_result("d2", 0.8)]
        lexical = [lex_result("d1", 5.0), lex_result("d3", 3.0)]
        merged = retriever._merge_candidates(vector, lexical)
        by_doc = {c.doc_id: c for c in merged}
        assert by_doc["d1"].search_method == "both"
        assert by_doc["d1"].vector_score == 0.9
        assert by_doc["d1"].lexical_score == 5.0
        assert by_doc["d2"].search_method == "vector"
        assert by_doc["d3"].search_method == "lexical"

    def test_merge_only_vector(self, retriever):
        merged = retriever._merge_candidates([vec_result("d1", 0.5)], [])
        assert len(merged) == 1
        assert merged[0].search_method == "vector"


class TestWeightedFusion:
    def test_combines_scores(self, retriever):
        cands = [hsr("d1", vec=1.0, lex=10.0)]
        retriever._weighted_fusion(cands)
        # 0.6*1.0 + 0.4*(10/10 capped at 1.0) = 1.0
        assert cands[0].fusion_score == pytest.approx(1.0)
        assert cands[0].final_score == cands[0].fusion_score

    def test_vector_only(self, retriever):
        cands = [hsr("d1", vec=0.5)]
        retriever._weighted_fusion(cands)
        assert cands[0].fusion_score == pytest.approx(0.3)  # 0.6*0.5


class TestRRF:
    def test_rrf_scores(self, retriever):
        cands = [hsr("d1", vec=0.9, lex=5.0), hsr("d2", vec=0.5, lex=2.0)]
        retriever._reciprocal_rank_fusion(cands)
        # d1 ranks first in both -> higher fusion score
        assert cands[0].fusion_score > cands[1].fusion_score


class TestMaxFusion:
    def test_max(self, retriever):
        cands = [hsr("d1", vec=0.3, lex=9.0)]  # lexical normalized 0.9 > 0.3
        retriever._max_fusion(cands)
        assert cands[0].fusion_score == pytest.approx(0.9)


class TestFuseScores:
    def test_dispatch_weighted(self, retriever):
        cands = [hsr("d1", vec=1.0)]
        out = retriever._fuse_scores(cands, "weighted")
        assert out[0].fusion_score == pytest.approx(0.6)

    def test_dispatch_unknown_falls_back(self, retriever):
        cands = [hsr("d1", vec=1.0)]
        out = retriever._fuse_scores(cands, "bogus")
        assert out[0].fusion_score == pytest.approx(0.6)


class TestSearchAndStats:
    def test_search_with_mocked_services(self):
        vsvc = SimpleNamespace(
            search=lambda *a, **k: [vec_result("d1", 0.9)],
            connect=lambda: None, disconnect=lambda: None,
        )
        lsvc = SimpleNamespace(
            search=lambda *a, **k: [lex_result("d2", 4.0)],
            connect=lambda: None, disconnect=lambda: None,
        )
        r = HybridRetriever(vector_service=vsvc, lexical_service=lsvc)
        results = r.search("query", query_embedding=[0.1, 0.2], k=5,
                           fusion_method="weighted", enable_reranking=False)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_get_search_stats(self, retriever):
        stats = retriever.get_search_stats()
        assert isinstance(stats, dict)


class TestFactory:
    def test_get_hybrid_retriever(self):
        import services.rag.retriever as mod
        from unittest.mock import patch, MagicMock
        with patch.object(mod, "VectorSearchService", MagicMock()), \
             patch.object(mod, "LexicalSearchService", MagicMock()), \
             patch.object(mod, "CrossEncoderReranker", MagicMock()):
            r = get_hybrid_retriever(enable_reranking=False)
        assert isinstance(r, HybridRetriever)
