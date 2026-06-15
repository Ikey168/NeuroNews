"""Tests for src/nlp/keyword_topic_extractor.py (real sklearn, small config)."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("sklearn")

from nlp.keyword_topic_extractor import (  # noqa: E402
    ExtractionResult,
    KeywordTopicExtractor,
    TextPreprocessor,
)


CONFIG = {
    "tfidf_max_features": 50,
    "tfidf_ngram_range": [1, 2],
    "lda_n_topics": 2,
    "lda_max_features": 50,
    "keywords_per_article": 5,
    "min_topic_probability": 0.1,
}


def corpus():
    topics = [
        ("Tech company launches AI", "Artificial intelligence and machine learning "
         "software powers the new computer product from the technology firm."),
        ("Sports team wins title", "The football team scored goals and won the "
         "championship match in a thrilling sports final game."),
        ("Market rises today", "The stock market and economy showed gains as "
         "investors traded shares and business profits grew."),
        ("New AI research", "Researchers study machine learning algorithms and "
         "artificial intelligence models for computer vision technology."),
        ("Election results in", "Voters cast ballots as the government and political "
         "parties await the election outcome and policy decisions."),
    ]
    return [
        {"id": str(i), "url": f"https://x/{i}", "title": t, "content": c}
        for i, (t, c) in enumerate(topics)
    ]


@pytest.fixture
def extractor():
    return KeywordTopicExtractor(config=CONFIG)


class TestPreprocessor:
    def test_clean_text(self):
        pre = TextPreprocessor()
        cleaned = pre.clean_text("Hello   WORLD!!! visit http://x.com now")
        assert isinstance(cleaned, str)
        assert "http://x.com" not in cleaned

    def test_extract_sentences(self):
        pre = TextPreprocessor()
        sents = pre.extract_sentences("First sentence here. Second sentence here.")
        assert isinstance(sents, list)


class TestExtractor:
    def test_default_config(self):
        ext = KeywordTopicExtractor()
        assert ext.config["lda_n_topics"] == 10
        assert ext.topics_fitted is False

    def test_extract_keywords_single_article(self, extractor):
        result = extractor.extract_keywords_and_topics(corpus()[0])
        assert isinstance(result, ExtractionResult)
        assert result.article_id == "0"
        assert len(result.keywords) >= 1
        assert result.extraction_method == "tfidf_lda"

    def test_empty_article(self, extractor):
        result = extractor.extract_keywords_and_topics({"id": "x", "title": "", "content": ""})
        assert result.extraction_method == "empty"
        assert result.keywords == []

    def test_fit_corpus_and_topics(self, extractor):
        info = extractor.fit_corpus(corpus())
        assert extractor.topics_fitted is True
        assert info["model_fitted"] is True
        # After fitting, extraction should attempt topic assignment
        result = extractor.extract_keywords_and_topics(corpus()[0])
        assert isinstance(result.topics, list)

    def test_process_batch(self, extractor):
        results = extractor.process_batch(corpus()[:3])
        assert len(results) == 3
        assert all(isinstance(r, ExtractionResult) for r in results)
