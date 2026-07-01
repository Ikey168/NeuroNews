"""
Coverage-focused unit tests for src/argument_mining/evidence.py.

Targets branches the scenario suite does not reach:
  - _cosine_similarities: sklearn ImportError fallback, empty corpus,
    TF-IDF runtime exception fallback, and the normal happy path
  - _default_corpus: sentence splitting, exclusion of the source document,
    None/short-content skipping, and the missing-table error handler
"""
from __future__ import annotations

import builtins
from unittest import mock

import pytest

from src.argument_mining.evidence import (
    _cosine_similarities,
    _default_corpus,
    _evidence_id,
)

duckdb = pytest.importorskip("duckdb")


# ---------------------------------------------------------------------------
# _cosine_similarities
# ---------------------------------------------------------------------------

class TestCosineSimilarities:
    def test_happy_path_ranks_similar_higher(self):
        pytest.importorskip("sklearn")
        scores = _cosine_similarities(
            "the interest rate fell sharply",
            ["the interest rate fell sharply last month", "cooking pasta recipes"],
        )
        assert len(scores) == 2
        assert scores[0] > scores[1]
        assert scores[0] > 0.0

    def test_empty_corpus_returns_empty_list(self):
        pytest.importorskip("sklearn")
        assert _cosine_similarities("some claim text", []) == []

    def test_sklearn_import_error_disables_search(self):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("sklearn"):
                raise ImportError("sklearn missing")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            scores = _cosine_similarities("claim", ["s1 here", "s2 here"])
        # one 0.0 per corpus text
        assert scores == [0.0, 0.0]

    def test_tfidf_runtime_exception_falls_back_to_zeros(self):
        pytest.importorskip("sklearn")

        class BoomVectorizer:
            def __init__(self, *args, **kwargs):
                pass

            def fit_transform(self, texts):
                raise ValueError("tfidf boom")

        with mock.patch(
            "sklearn.feature_extraction.text.TfidfVectorizer", BoomVectorizer
        ):
            scores = _cosine_similarities("claim", ["a b c", "d e f", "g h i"])
        assert scores == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# _default_corpus
# ---------------------------------------------------------------------------

def _make_news_conn():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE news_articles (id VARCHAR, content VARCHAR)")
    return conn


class TestDefaultCorpus:
    def test_splits_sentences_and_tags_source(self):
        conn = _make_news_conn()
        conn.execute(
            "INSERT INTO news_articles VALUES (?, ?)",
            ["a1", "The unemployment rate fell to 3.8 percent. Markets rose sharply today."],
        )
        corpus = _default_corpus(conn, exclude_document_id="other")
        assert ("The unemployment rate fell to 3.8 percent.", "a1", "news") in corpus
        assert ("Markets rose sharply today.", "a1", "news") in corpus
        assert all(entry[2] == "news" for entry in corpus)

    def test_excludes_source_document(self):
        conn = _make_news_conn()
        conn.execute(
            "INSERT INTO news_articles VALUES (?, ?)",
            ["keep", "This is a long enough sentence to be kept in the corpus."],
        )
        conn.execute(
            "INSERT INTO news_articles VALUES (?, ?)",
            ["drop-me", "This document should be excluded from the corpus entirely."],
        )
        corpus = _default_corpus(conn, exclude_document_id="drop-me")
        doc_ids = {entry[1] for entry in corpus}
        assert "drop-me" not in doc_ids
        assert "keep" in doc_ids

    def test_null_content_row_is_skipped(self):
        conn = _make_news_conn()
        conn.execute("INSERT INTO news_articles VALUES (?, ?)", ["a1", None])
        conn.execute(
            "INSERT INTO news_articles VALUES (?, ?)",
            ["a2", "A genuine sentence long enough to survive the length filter."],
        )
        corpus = _default_corpus(conn, exclude_document_id="none")
        assert all(entry[1] == "a2" for entry in corpus)
        assert len(corpus) == 1

    def test_short_sentences_filtered_out(self):
        conn = _make_news_conn()
        conn.execute(
            "INSERT INTO news_articles VALUES (?, ?)",
            ["a1", "Short. This one is definitely long enough to be included here."],
        )
        corpus = _default_corpus(conn, exclude_document_id="none")
        texts = [entry[0] for entry in corpus]
        assert "Short." not in texts
        assert any("long enough" in t for t in texts)

    def test_missing_table_returns_empty(self):
        # fresh connection without news_articles table -> error handler -> []
        conn = duckdb.connect(":memory:")
        assert _default_corpus(conn, exclude_document_id="x") == []


# ---------------------------------------------------------------------------
# _evidence_id determinism (id helper)
# ---------------------------------------------------------------------------

class TestEvidenceId:
    def test_deterministic_and_prefixed(self):
        a = _evidence_id("cl-1", "doc-2", "some evidence text")
        b = _evidence_id("cl-1", "doc-2", "some evidence text")
        assert a == b
        assert a.startswith("ev-")

    def test_differs_by_document(self):
        a = _evidence_id("cl-1", "doc-2", "text")
        b = _evidence_id("cl-1", "doc-3", "text")
        assert a != b
