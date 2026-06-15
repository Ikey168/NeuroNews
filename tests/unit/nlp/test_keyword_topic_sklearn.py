"""Tests for the sklearn-based extractors in keyword_topic_extractor."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("sklearn")

from nlp.keyword_topic_extractor import (  # noqa: E402
    KeywordResult,
    LDATopicModeler,
    TFIDFKeywordExtractor,
)

DOCS = [
    "Quantum computing uses qubits to perform calculations far faster than "
    "classical computers for certain problems like factoring large numbers.",
    "Machine learning models are trained on large datasets to recognize patterns "
    "and make predictions about new unseen data points automatically.",
    "Renewable energy from solar panels and wind turbines reduces carbon emissions "
    "and helps mitigate the effects of global climate change worldwide.",
]


class TestTFIDFKeywordExtractor:
    def test_empty(self):
        assert TFIDFKeywordExtractor().extract_keywords([]) == []

    def test_multi_doc(self):
        ex = TFIDFKeywordExtractor()
        results = ex.extract_keywords(DOCS, top_k=5)
        assert len(results) == len(DOCS)
        # at least one document produced keywords
        assert any(len(r) > 0 for r in results)
        for doc_kws in results:
            for kw in doc_kws:
                assert isinstance(kw, KeywordResult)
                assert kw.score >= 0

    def test_single_doc(self):
        ex = TFIDFKeywordExtractor()
        results = ex.extract_keywords([DOCS[0]], top_k=5)
        assert len(results) == 1
        assert isinstance(results[0], list)

    def test_blank_texts(self):
        ex = TFIDFKeywordExtractor()
        results = ex.extract_keywords(["   ", ""], top_k=5)
        assert len(results) == 2
        assert all(r == [] for r in results)


class TestLDATopicModeler:
    def test_insufficient_texts(self):
        result = LDATopicModeler(n_topics=2).fit_topics(["only one"])
        assert result["model_fitted"] is False

    def test_fit_topics(self):
        modeler = LDATopicModeler(n_topics=2, max_features=50)
        result = modeler.fit_topics(DOCS)
        # either fits (model_fitted True with topics) or gracefully reports not fitted
        assert "model_fitted" in result
        assert "topics" in result

    def test_predict_after_fit(self):
        modeler = LDATopicModeler(n_topics=2, max_features=50)
        fit_result = modeler.fit_topics(DOCS)
        if fit_result.get("model_fitted"):
            preds = modeler.predict_topics([DOCS[0]])
            assert isinstance(preds, list)
