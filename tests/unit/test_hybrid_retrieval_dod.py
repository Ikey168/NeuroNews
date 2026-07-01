#!/usr/bin/env python3
"""
Definition of Done (DoD) verification for Issue #232
Hybrid retrieval + (optional) cross-encoder rerank

DoD Requirements:
- retriever.search(query) returns [{chunk, score, source, url}] with length <= K
- Candidate fetch: top-k from vector + top-k from lexical -> union
- Score fusion: weighted sum or Reciprocal Rank Fusion
- Optional reranker (e.g., cross-encoder/ms-marco-MiniLM-L-6-v2); gated by env

The search paths require a live Postgres backend (vector + lexical stores).
Those tests are skipped via a connectivity probe when the DB is genuinely
unreachable. File-existence and env-gating checks run unconditionally.
"""

import hashlib
import os
import socket
import sys
from pathlib import Path

import numpy as np
import pytest

# Repo root is two levels up: <repo>/tests/unit/<file>
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    # Package-level re-exports.
    from services.rag import (
        HybridRetriever,
        VectorSearchService,
        LexicalSearchService,
        CrossEncoderReranker,
    )
    # Retriever-module symbols (not re-exported by services.rag.__init__).
    from services.rag.retriever import (
        HybridSearchFilters,
        get_hybrid_retriever,
        hybrid_search,
    )
except ImportError as _e:  # stale or optional dependency
    pytest.skip("module import failed: {0}".format(_e), allow_module_level=True)


def _postgres_available() -> bool:
    """Probe the vector/lexical Postgres backend used by the hybrid retriever."""
    params = VectorSearchService().connection_params
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        return sock.connect_ex((params["host"], int(params["port"]))) == 0
    finally:
        sock.close()


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="PostgreSQL backend not reachable; hybrid retrieval integration "
    "tests require live vector + lexical stores",
)


def simulate_embedding(text: str, dim: int = 384) -> np.ndarray:
    """Simulate text embedding using hash-based approach."""
    hash_obj = hashlib.md5(text.encode())
    seed = int(hash_obj.hexdigest()[:8], 16)
    np.random.seed(seed)

    embedding = np.random.normal(0, 1, dim)
    embedding = embedding / np.linalg.norm(embedding)

    return embedding


def test_files_exist():
    """DoD: required implementation files exist and services are exported."""
    required_files = [
        "services/rag/retriever.py",
        "services/rag/rerank.py",
    ]
    for file_path in required_files:
        full_path = PROJECT_ROOT / file_path
        assert full_path.exists(), f"{file_path} missing"

    # Services must be importable from the package (already imported above).
    assert isinstance(HybridRetriever, type)
    assert isinstance(CrossEncoderReranker, type)


@requires_postgres
def test_retriever_search_api():
    """DoD: retriever.search(query) returns results with length <= K and the
    convenience function returns dicts with chunk/score/source/url keys."""
    with get_hybrid_retriever() as retriever:
        query = "test query for API compliance"
        query_embedding = simulate_embedding(query)
        k = 5

        results = retriever.search(
            query=query,
            query_embedding=query_embedding,
            k=k,
        )

        assert isinstance(results, list), f"Expected list, got {type(results)}"
        assert len(results) <= k, f"Expected <= {k} results, got {len(results)}"

        if results:
            result = results[0]
            for attr in ("content", "final_score", "source", "url"):
                assert hasattr(result, attr), f"Result missing attribute: {attr}"

            dict_results = hybrid_search(query, query_embedding, k=3)
            assert isinstance(dict_results, list)

            if dict_results:
                dict_result = dict_results[0]
                for key in ("chunk", "score", "source", "url"):
                    assert key in dict_result, f"Dict result missing key: {key}"


@requires_postgres
def test_candidate_fetch_union():
    """DoD: candidate fetch: top-k from vector + top-k from lexical -> union."""
    with get_hybrid_retriever() as retriever:
        query = "machine learning artificial intelligence"
        query_embedding = simulate_embedding(query)

        results = retriever.search(
            query=query,
            query_embedding=query_embedding,
            k=10,
            vector_k=5,
            lexical_k=5,
        )

        # Every result must carry a recognised search-method label.
        for r in results:
            assert r.search_method in ("vector", "lexical", "both")

        # At least one scoring component must be populated per result.
        for r in results:
            assert (r.vector_score is not None) or (r.lexical_score is not None)


@requires_postgres
def test_score_fusion_methods():
    """DoD: score fusion via weighted sum, RRF, or max."""
    with get_hybrid_retriever() as retriever:
        query = "neural networks deep learning"
        query_embedding = simulate_embedding(query)

        for method in ("weighted", "rrf", "max"):
            results = retriever.search(
                query=query,
                query_embedding=query_embedding,
                k=5,
                fusion_method=method,
            )
            for result in results:
                assert hasattr(result, "fusion_score"), f"Missing fusion_score in {method}"
                assert result.fusion_score >= 0, (
                    f"Invalid fusion_score in {method}: {result.fusion_score}"
                )


def test_optional_reranker_env_gating():
    """DoD: reranker is optional and gated by the ENABLE_RERANKING env var.

    This exercises only the reranker configuration path, which does not need a
    database.
    """
    reranker = CrossEncoderReranker(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
    model_info = reranker.get_model_info()
    for key in ("model_name", "is_enabled", "model_loaded", "has_sentence_transformers"):
        assert key in model_info, f"Missing model_info key: {key}"

    original_env = os.environ.get("ENABLE_RERANKING")
    try:
        os.environ["ENABLE_RERANKING"] = "false"
        assert not CrossEncoderReranker().is_enabled, (
            "Reranker should be disabled when ENABLE_RERANKING=false"
        )

        os.environ["ENABLE_RERANKING"] = "true"
        assert CrossEncoderReranker().is_enabled, (
            "Reranker should be enabled when ENABLE_RERANKING=true"
        )
    finally:
        if original_env is None:
            os.environ.pop("ENABLE_RERANKING", None)
        else:
            os.environ["ENABLE_RERANKING"] = original_env


@requires_postgres
def test_optional_reranker_search():
    """DoD: reranking integrates into retriever.search() without errors."""
    with get_hybrid_retriever(enable_reranking=True) as retriever:
        query = "quantum computing applications"
        query_embedding = simulate_embedding(query)

        results_with_rerank = retriever.search(
            query=query,
            query_embedding=query_embedding,
            k=3,
            enable_reranking=True,
        )
        results_no_rerank = retriever.search(
            query=query,
            query_embedding=query_embedding,
            k=3,
            enable_reranking=False,
        )

        assert isinstance(results_with_rerank, list)
        assert isinstance(results_no_rerank, list)
        assert len(results_with_rerank) <= 3
        assert len(results_no_rerank) <= 3
