"""Coverage-focused tests for src/nlp/keyword_topic_extractor.py.

Exercises the previously-uncovered branches: TF-IDF multi-document path,
frequency fallbacks, LDA fit/predict edge cases, error handling in the main
extractor, the SimpleKeywordExtractor, and the create_keyword_extractor factory
(including config loading). Uses real sklearn/numpy; no model downloads occur.
"""

import json
import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("sklearn")

import nlp.keyword_topic_extractor as mod  # noqa: E402
from nlp.keyword_topic_extractor import (  # noqa: E402
    ExtractionResult,
    KeywordResult,
    KeywordTopicExtractor,
    LDATopicModeler,
    SimpleKeywordExtractor,
    TextPreprocessor,
    TFIDFKeywordExtractor,
    create_keyword_extractor,
)


SMALL_CONFIG = {
    "tfidf_max_features": 50,
    "tfidf_ngram_range": [1, 2],
    "lda_n_topics": 2,
    "lda_max_features": 50,
    "keywords_per_article": 5,
    "min_topic_probability": 0.1,
}


def _corpus():
    topics = [
        ("Tech company launches AI", "Artificial intelligence and machine learning "
         "software powers the new computer product from the technology firm today."),
        ("Sports team wins title", "The football team scored goals and won the "
         "championship match in a thrilling sports final game this weekend."),
        ("Market rises today", "The stock market and economy showed gains as "
         "investors traded shares and business profits grew across the sector."),
        ("New AI research", "Researchers study machine learning algorithms and "
         "artificial intelligence models for computer vision technology systems."),
        ("Election results in", "Voters cast ballots as the government and political "
         "parties await the election outcome and policy decisions this month."),
    ]
    return [
        {"id": str(i), "url": "https://x/{0}".format(i), "title": t, "content": c}
        for i, (t, c) in enumerate(topics)
    ]


# ---------------------------------------------------------------------------
# TextPreprocessor uncovered paths
# ---------------------------------------------------------------------------
class TestTextPreprocessor:
    def test_clean_text_strips_html_urls_emails(self):
        pre = TextPreprocessor()
        cleaned = pre.clean_text(
            "<p>Contact bob@site.com about http://example.com/x now!</p>"
        )
        assert "<p>" not in cleaned
        assert "bob@site.com" not in cleaned
        assert "http://example.com" not in cleaned
        assert "Contact" in cleaned

    def test_extract_sentences_filters_short(self):
        pre = TextPreprocessor()
        sents = pre.extract_sentences(
            "This is a full sentence with content. Ok. Another proper sentence here."
        )
        # 2-word "Ok." must be dropped, only >3-word sentences retained
        assert all(len(s.split()) > 3 for s in sents)
        assert len(sents) >= 2

    def test_extract_keywords_pos_returns_lemmas(self):
        pre = TextPreprocessor()
        kws = pre.extract_keywords_pos(
            "Scientists discovered amazing new galaxies using powerful telescopes.",
            max_keywords=10,
        )
        assert isinstance(kws, list)
        assert len(kws) >= 1
        # dedup: no repeats
        assert len(kws) == len(set(kws))

    def test_extract_keywords_pos_respects_max(self):
        pre = TextPreprocessor()
        text = " ".join(
            "galaxy planet star comet nebula quasar pulsar meteor asteroid moon".split()
        )
        kws = pre.extract_keywords_pos(text, max_keywords=3)
        assert len(kws) <= 3


# ---------------------------------------------------------------------------
# TFIDFKeywordExtractor: multi-doc, single-doc, fallback
# ---------------------------------------------------------------------------
class TestTFIDF:
    def test_empty_input_returns_empty(self):
        ext = TFIDFKeywordExtractor(max_features=50)
        assert ext.extract_keywords([]) == []

    def test_all_blank_texts(self):
        ext = TFIDFKeywordExtractor(max_features=50)
        out = ext.extract_keywords(["   ", ""])
        assert out == [[], []]

    def test_single_document_uses_frequency(self):
        ext = TFIDFKeywordExtractor(max_features=50)
        out = ext.extract_keywords(
            ["Quantum computing research advances rapidly with new qubit hardware."],
            top_k=5,
        )
        assert len(out) == 1
        assert all(isinstance(k, KeywordResult) for k in out[0])
        # single-doc path uses "frequency" method
        assert all(k.method == "frequency" for k in out[0])

    def test_multi_document_tfidf(self):
        ext = TFIDFKeywordExtractor(max_features=100, ngram_range=(1, 2))
        texts = [a["content"] for a in _corpus()]
        out = ext.extract_keywords(texts, top_k=5)
        assert len(out) == len(texts)
        # at least one document produced tfidf keywords
        non_empty = [r for r in out if r]
        assert non_empty
        first = non_empty[0]
        assert all(k.method == "tfid" for k in first)
        # scores are positive floats and sorted descending
        scores = [k.score for k in first]
        assert all(s > 0 for s in scores)
        assert scores == sorted(scores, reverse=True)

    def test_fallback_extraction_direct(self):
        ext = TFIDFKeywordExtractor(max_features=50)
        out = ext._extract_keywords_fallback(
            ["breaking breaking economy economy economy market"], top_k=3
        )
        assert len(out) == 1
        kws = out[0]
        assert kws
        # 'economy' appears most frequently -> highest score first
        assert kws[0].keyword == "economy"
        assert kws[0].method == "frequency"

    def test_fallback_on_vectorizer_error(self, monkeypatch):
        ext = TFIDFKeywordExtractor(max_features=50)

        # Force the fit_transform path to blow up so the except branch runs.
        class Boom:
            def __init__(self, *a, **k):
                pass

            def fit_transform(self, *a, **k):
                raise ValueError("forced failure")

        monkeypatch.setattr(mod, "TfidfVectorizer", Boom)
        out = ext.extract_keywords(
            ["alpha beta gamma delta", "beta gamma delta epsilon"], top_k=3
        )
        # error branch -> fallback frequency extraction still returns results
        assert len(out) == 2
        assert any(r for r in out)


# ---------------------------------------------------------------------------
# LDATopicModeler edge cases
# ---------------------------------------------------------------------------
class TestLDA:
    def test_fit_insufficient_texts(self):
        lda = LDATopicModeler(n_topics=2, max_features=50)
        info = lda.fit_topics(["only one"])
        assert info == {"topics": [], "model_fitted": False}

    def test_fit_texts_too_short_after_cleaning(self):
        lda = LDATopicModeler(n_topics=2, max_features=50)
        # both short -> cleaned list < 2 after the >10-word filter
        info = lda.fit_topics(["short one", "short two"])
        assert info["model_fitted"] is False

    def test_fit_and_topic_structure(self):
        lda = LDATopicModeler(n_topics=2, max_features=100)
        texts = [a["content"] for a in _corpus()]
        info = lda.fit_topics(texts)
        assert info["model_fitted"] is True
        assert info["n_texts"] >= 2
        assert isinstance(info["perplexity"], float)
        assert len(info["topics"]) == 2
        for t in info["topics"]:
            assert "topic_name" in t and t["topic_words"]

    def test_predict_before_fit_returns_empty(self):
        lda = LDATopicModeler(n_topics=2, max_features=50)
        out = lda.predict_topics(["some text", "other text"])
        assert out == [[], []]

    def test_predict_after_fit(self):
        lda = LDATopicModeler(n_topics=2, max_features=100)
        texts = [a["content"] for a in _corpus()]
        lda.fit_topics(texts)
        out = lda.predict_topics([texts[0]])
        assert len(out) == 1
        # results are TopicResult sorted by probability descending
        probs = [t.probability for t in out[0]]
        assert probs == sorted(probs, reverse=True)

    def test_predict_handles_transform_error(self, monkeypatch):
        lda = LDATopicModeler(n_topics=2, max_features=100)
        lda.fit_topics([a["content"] for a in _corpus()])

        def boom(*a, **k):
            raise RuntimeError("transform boom")

        monkeypatch.setattr(lda.vectorizer, "transform", boom)
        out = lda.predict_topics(["text a", "text b"])
        assert out == [[], []]


# ---------------------------------------------------------------------------
# KeywordTopicExtractor main flows
# ---------------------------------------------------------------------------
class TestKeywordTopicExtractor:
    def test_extract_falls_back_to_pos_on_tfidf_error(self, monkeypatch):
        ext = KeywordTopicExtractor(config=SMALL_CONFIG)

        def boom(*a, **k):
            raise RuntimeError("tfidf explode")

        monkeypatch.setattr(ext.tfidf_extractor, "extract_keywords", boom)
        result = ext.extract_keywords_and_topics(_corpus()[0])
        assert isinstance(result, ExtractionResult)
        # POS fallback path assigns method 'pos'
        assert result.keywords
        assert all(k.method == "pos" for k in result.keywords)

    def test_topics_extracted_when_fitted(self):
        ext = KeywordTopicExtractor(config=SMALL_CONFIG)
        ext.fit_corpus(_corpus())
        assert ext.topics_fitted is True
        result = ext.extract_keywords_and_topics(_corpus()[0])
        assert isinstance(result.topics, list)
        # dominant_topic is either None or the top topic
        if result.topics:
            assert result.dominant_topic is result.topics[0]

    def test_extract_topics_error_is_swallowed(self, monkeypatch):
        ext = KeywordTopicExtractor(config=SMALL_CONFIG)
        ext.fit_corpus(_corpus())

        def boom(*a, **k):
            raise RuntimeError("predict boom")

        monkeypatch.setattr(ext.lda_modeler, "predict_topics", boom)
        result = ext.extract_keywords_and_topics(_corpus()[0])
        # error swallowed -> topics stays empty, still returns a result
        assert result.topics == []
        assert result.dominant_topic is None

    def test_fit_corpus_skips_articles_without_content(self):
        ext = KeywordTopicExtractor(config=SMALL_CONFIG)
        arts = _corpus() + [{"id": "no", "title": "T", "content": ""}]
        info = ext.fit_corpus(arts)
        assert info["model_fitted"] is True

    def test_process_batch_fits_then_processes(self):
        ext = KeywordTopicExtractor(config=SMALL_CONFIG)
        results = ext.process_batch(_corpus())
        assert len(results) == len(_corpus())
        assert all(isinstance(r, ExtractionResult) for r in results)
        # topic model gets fitted as a side-effect
        assert ext.topics_fitted is True

    def test_process_batch_empty(self):
        ext = KeywordTopicExtractor(config=SMALL_CONFIG)
        assert ext.process_batch([]) == []

    def test_process_batch_handles_article_error(self, monkeypatch):
        ext = KeywordTopicExtractor(config=SMALL_CONFIG)
        ext.topics_fitted = True  # skip fitting

        calls = {"n": 0}
        real = ext.extract_keywords_and_topics

        def flaky(article):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom on first")
            return real(article)

        monkeypatch.setattr(ext, "extract_keywords_and_topics", flaky)
        results = ext.process_batch(_corpus()[:2])
        assert len(results) == 2
        # first article produced an empty-result fallback
        assert results[0].extraction_method == "empty"


# ---------------------------------------------------------------------------
# SimpleKeywordExtractor
# ---------------------------------------------------------------------------
class TestSimpleKeywordExtractor:
    def test_default_config(self):
        s = SimpleKeywordExtractor()
        assert s.config["keywords_per_article"] == 10
        assert s.topics_fitted is False

    def test_extract_keywords(self):
        s = SimpleKeywordExtractor()
        result = s.extract_keywords_and_topics(_corpus()[0])
        assert isinstance(result, ExtractionResult)
        assert result.extraction_method == "simple"
        assert result.keywords
        assert all(k.method == "simple" for k in result.keywords)
        # stopwords like 'the' filtered out
        assert "the" not in [k.keyword for k in result.keywords]

    def test_empty_article(self):
        s = SimpleKeywordExtractor()
        result = s.extract_keywords_and_topics({"id": "e", "title": "", "content": ""})
        assert result.extraction_method == "simple"
        assert result.keywords == []

    def test_preprocessor_clean_text_removes_nonalpha(self):
        s = SimpleKeywordExtractor()
        cleaned = s.preprocessor.clean_text("Hello, World123! http://x.com <b>hi</b>")
        # digits and punctuation and urls stripped
        assert "123" not in cleaned
        assert "http" not in cleaned
        assert "Hello" in cleaned

    def test_process_batch(self):
        s = SimpleKeywordExtractor()
        results = s.process_batch(_corpus()[:3])
        assert len(results) == 3
        assert all(r.extraction_method == "simple" for r in results)


# ---------------------------------------------------------------------------
# create_keyword_extractor factory
# ---------------------------------------------------------------------------
class TestFactory:
    def test_returns_full_extractor_when_sklearn_present(self):
        ext = create_keyword_extractor()
        assert isinstance(ext, KeywordTopicExtractor)

    def test_loads_config_from_file(self, tmp_path):
        cfg = {"lda_n_topics": 3, "keywords_per_article": 7}
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(cfg))
        ext = create_keyword_extractor(str(p))
        assert isinstance(ext, KeywordTopicExtractor)
        assert ext.config["lda_n_topics"] == 3
        assert ext.config["keywords_per_article"] == 7

    def test_bad_config_file_is_ignored(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ not valid json ]")
        ext = create_keyword_extractor(str(p))
        # falls back to default config (None) but still returns extractor
        assert isinstance(ext, KeywordTopicExtractor)
        assert ext.config["lda_n_topics"] == 10

    def test_nonexistent_config_path(self):
        ext = create_keyword_extractor("/nonexistent/path/to/config.json")
        assert isinstance(ext, KeywordTopicExtractor)

    def test_falls_back_to_simple_without_sklearn(self, monkeypatch):
        # Make the sklearn import inside the factory fail so the simple
        # extractor branch is taken.
        real_import = __builtins__["__import__"] if isinstance(
            __builtins__, dict) else __builtins__.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("sklearn"):
                raise ImportError("no sklearn for you")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)
        ext = create_keyword_extractor()
        assert isinstance(ext, SimpleKeywordExtractor)

    def test_simple_branch_loads_config(self, monkeypatch, tmp_path):
        real_import = __builtins__["__import__"] if isinstance(
            __builtins__, dict) else __builtins__.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("sklearn"):
                raise ImportError("no sklearn")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)
        cfg = {"keywords_per_article": 4}
        p = tmp_path / "c.json"
        p.write_text(json.dumps(cfg))
        ext = create_keyword_extractor(str(p))
        assert isinstance(ext, SimpleKeywordExtractor)
        assert ext.config["keywords_per_article"] == 4
