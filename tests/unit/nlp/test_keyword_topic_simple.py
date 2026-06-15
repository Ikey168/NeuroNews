"""Tests for the dependency-free parts of keyword_topic_extractor."""

import os
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from nlp.keyword_topic_extractor import (  # noqa: E402
    ExtractionResult,
    KeywordResult,
    SimpleKeywordExtractor,
    TopicResult,
)


class TestDataclasses:
    def test_keyword_result(self):
        k = KeywordResult(keyword="ai", score=0.9, method="simple")
        assert k.keyword == "ai"
        assert k.method == "simple"

    def test_topic_result_defaults(self):
        t = TopicResult(topic_id=1, topic_name="tech", topic_words=["ai", "ml"], probability=0.5)
        assert t.coherence_score is None

    def test_extraction_result(self):
        r = ExtractionResult(
            article_id="a", url="u", title="t", keywords=[], topics=[],
            dominant_topic=None, extraction_method="simple",
            processed_at=datetime.now(), processing_time=0.1,
        )
        assert r.extraction_method == "simple"


@pytest.fixture
def extractor():
    return SimpleKeywordExtractor()


class TestSimpleKeywordExtractor:
    def test_default_config(self, extractor):
        assert extractor.config["keywords_per_article"] == 10
        assert extractor.topics_fitted is False

    def test_custom_config(self):
        ex = SimpleKeywordExtractor({"keywords_per_article": 3})
        assert ex.config["keywords_per_article"] == 3

    def test_clean_text(self, extractor):
        cleaned = extractor.preprocessor.clean_text(
            "<p>Hello</p> visit http://x.com now! 123"
        )
        assert "<p>" not in cleaned
        assert "http" not in cleaned
        assert "123" not in cleaned
        assert "Hello" in cleaned

    def test_extract_keywords_removes_stopwords(self, extractor):
        kws = extractor.preprocessor.extract_keywords_pos(
            "The quantum computer breaks the encryption", max_keywords=10
        )
        assert "the" not in kws
        assert "quantum" in kws
        assert "computer" in kws

    def test_extract_keywords_dedup_and_limit(self, extractor):
        kws = extractor.preprocessor.extract_keywords_pos(
            "alpha alpha beta gamma delta epsilon", max_keywords=2
        )
        assert len(kws) == 2

    def test_extract_keywords_and_topics(self, extractor):
        result = extractor.extract_keywords_and_topics(
            {"id": "1", "url": "u", "title": "Quantum Computing",
             "content": "Quantum computers solve encryption problems quickly."}
        )
        assert isinstance(result, ExtractionResult)
        assert result.extraction_method == "simple"
        assert len(result.keywords) > 0
        assert all(isinstance(k, KeywordResult) for k in result.keywords)
        assert all(k.method == "simple" for k in result.keywords)

    def test_empty_article(self, extractor):
        result = extractor.extract_keywords_and_topics({"id": "1"})
        assert result.keywords == []
        assert result.topics == []

    def test_process_batch(self, extractor):
        results = extractor.process_batch([
            {"id": "1", "title": "AI News", "content": "Artificial intelligence advances rapidly."},
            {"id": "2", "title": "Climate", "content": "Global warming accelerates worldwide."},
        ])
        assert len(results) == 2
        assert all(isinstance(r, ExtractionResult) for r in results)
