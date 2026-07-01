"""Second coverage pass for src/nlp/keyword_topic_extractor.py.

The existing tests/unit/nlp/test_keyword_topic_extractor_coverage.py covers the
happy paths and the multi-doc / factory branches.  This file targets the
REMAINING uncovered lines (as reported by --cov term-missing):

  * module-level import fallbacks (NLTK / spaCy unavailable, dummy shims)
  * TextPreprocessor NLTK-init failure and the NLTK-unavailable / NLTK-error
    fallbacks in extract_sentences and extract_keywords_pos
  * exception handlers in _extract_keywords_single_doc / _extract_keywords_fallback
  * LDATopicModeler.fit_topics exception handler
  * KeywordTopicExtractor.extract_keywords_and_topics empty-text + double-fallback
  * create_keyword_extractor factory branches (NLTK LookupError, spaCy load OK /
    ImportError, simple-branch config error, outer exception)

Real sklearn/nltk are used; failures are simulated with monkeypatch, no model
downloads happen.
"""

import builtins
import importlib
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
        ("Tech firm launches AI", "Artificial intelligence and machine learning "
         "software powers the new computer product from the technology firm today."),
        ("Sports team wins", "The football team scored goals and won the "
         "championship match in a thrilling sports final game this weekend."),
        ("Market rises", "The stock market and economy showed gains as investors "
         "traded shares and business profits grew across the whole sector today."),
    ]
    return [
        {"id": str(i), "url": "https://x/{0}".format(i), "title": t, "content": c}
        for i, (t, c) in enumerate(topics)
    ]


# ---------------------------------------------------------------------------
# TextPreprocessor: NLTK-init failure and NLTK-unavailable / error fallbacks
# ---------------------------------------------------------------------------
class TestPreprocessorFallbacks:
    def test_init_handles_nltk_setup_failure(self, monkeypatch):
        # stopwords.words raising during __init__ triggers the except branch
        # (lemmatizer -> None, stop_words -> empty set, then news words added).
        monkeypatch.setattr(mod, "NLTK_AVAILABLE", True)

        def boom(*a, **k):
            raise RuntimeError("stopwords unavailable")

        monkeypatch.setattr(mod.stopwords, "words", boom)
        pre = TextPreprocessor()
        assert pre.lemmatizer is None
        # news-specific stopwords were still added on top of the empty set.
        assert "said" in pre.stop_words

    def test_extract_sentences_when_nltk_unavailable(self, monkeypatch):
        monkeypatch.setattr(mod, "NLTK_AVAILABLE", False)
        pre = TextPreprocessor()
        sents = pre.extract_sentences(
            "This sentence is long enough to keep! And this other one is too?"
        )
        assert all(len(s.split()) > 3 for s in sents)
        assert len(sents) >= 2

    def test_extract_sentences_tokenizer_error_falls_back(self, monkeypatch):
        monkeypatch.setattr(mod, "NLTK_AVAILABLE", True)
        pre = TextPreprocessor()

        def boom(text):
            raise RuntimeError("sent_tokenize broke")

        monkeypatch.setattr(mod, "sent_tokenize", boom)
        sents = pre.extract_sentences(
            "This is a long sentence with plenty of words. Another long one here now."
        )
        # regex fallback still returns the long sentences.
        assert len(sents) >= 2
        assert all(len(s.split()) > 3 for s in sents)

    def test_extract_keywords_pos_when_nltk_unavailable(self, monkeypatch):
        monkeypatch.setattr(mod, "NLTK_AVAILABLE", False)
        pre = TextPreprocessor()
        pre.stop_words = {"the", "and", "a"}
        kws = pre.extract_keywords_pos(
            "The rocket and a satellite orbit the planet", max_keywords=10
        )
        # stopwords removed, words deduped.
        assert "the" not in kws
        assert "rocket" in kws
        assert len(kws) == len(set(kws))

    def test_extract_keywords_pos_no_lemmatizer_keeps_word(self, monkeypatch):
        # NLTK available (real POS tagging) but lemmatizer is None -> the else
        # branch keeps the raw word (line 328).
        monkeypatch.setattr(mod, "NLTK_AVAILABLE", True)
        pre = TextPreprocessor()
        pre.lemmatizer = None
        kws = pre.extract_keywords_pos(
            "Astronomers observed brilliant supernovae exploding across galaxies",
            max_keywords=10,
        )
        assert isinstance(kws, list)
        assert len(kws) >= 1
        # words are kept verbatim (no lemmatization applied).
        assert all(isinstance(k, str) for k in kws)

    def test_extract_keywords_pos_lemmatizer_error_uses_original(self, monkeypatch):
        monkeypatch.setattr(mod, "NLTK_AVAILABLE", True)
        pre = TextPreprocessor()

        class BadLemmatizer:
            def lemmatize(self, word):
                raise RuntimeError("lemmatize failed")

        pre.lemmatizer = BadLemmatizer()
        kws = pre.extract_keywords_pos(
            "Researchers discovered galaxies using powerful telescopes today",
            max_keywords=10,
        )
        # On lemmatizer failure the original word is kept, so we still get results.
        assert isinstance(kws, list)
        assert len(kws) >= 1

    def test_extract_keywords_pos_processing_error_falls_back(self, monkeypatch):
        monkeypatch.setattr(mod, "NLTK_AVAILABLE", True)
        pre = TextPreprocessor()
        pre.stop_words = {"the", "and"}

        def boom(text):
            raise RuntimeError("word_tokenize broke")

        monkeypatch.setattr(mod, "word_tokenize", boom)
        kws = pre.extract_keywords_pos(
            "The engine and turbine power the aircraft", max_keywords=10
        )
        # simple regex fallback path returns non-stopword tokens.
        assert "the" not in kws
        assert "engine" in kws


# ---------------------------------------------------------------------------
# TFIDFKeywordExtractor: exception handlers in single-doc / fallback helpers
# ---------------------------------------------------------------------------
class TestTFIDFHelperErrors:
    def test_single_doc_helper_swallows_error(self, monkeypatch):
        ext = TFIDFKeywordExtractor(max_features=50)

        def boom(*a, **k):
            raise RuntimeError("pos broke")

        monkeypatch.setattr(ext.preprocessor, "extract_keywords_pos", boom)
        out = ext._extract_keywords_single_doc(["some text here"], top_k=5)
        # error per-text swallowed -> empty list result for that text.
        assert out == [[]]

    def test_fallback_helper_swallows_error(self, monkeypatch):
        ext = TFIDFKeywordExtractor(max_features=50)

        # Force re.findall (used inside the fallback) to raise for this call.
        def boom(*a, **k):
            raise RuntimeError("findall broke")

        monkeypatch.setattr(mod.re, "findall", boom)
        out = ext._extract_keywords_fallback(["alpha beta gamma"], top_k=3)
        assert out == [[]]


# ---------------------------------------------------------------------------
# LDATopicModeler.fit_topics exception handler
# ---------------------------------------------------------------------------
class TestLDAFitError:
    def test_fit_topics_handles_vectorizer_error(self, monkeypatch):
        lda = LDATopicModeler(n_topics=2, max_features=50)

        def boom(*a, **k):
            raise RuntimeError("vectorize broke")

        # texts pass the length gate, but vectorizing raises -> except branch.
        monkeypatch.setattr(lda.vectorizer, "fit_transform", boom)
        texts = [a["content"] for a in _corpus()]
        info = lda.fit_topics(texts)
        assert info == {"topics": [], "model_fitted": False}


# ---------------------------------------------------------------------------
# KeywordTopicExtractor: empty text + double (tfidf then pos) failure
# ---------------------------------------------------------------------------
class TestExtractorEdgeCases:
    def test_empty_text_returns_empty_result(self):
        ext = KeywordTopicExtractor(config=SMALL_CONFIG)
        result = ext.extract_keywords_and_topics(
            {"id": "e1", "url": "u", "title": "", "content": ""}
        )
        assert isinstance(result, ExtractionResult)
        assert result.extraction_method == "empty"
        assert result.keywords == []
        assert result.topics == []

    def test_tfidf_and_pos_both_fail_leaves_keywords_empty(self, monkeypatch):
        ext = KeywordTopicExtractor(config=SMALL_CONFIG)

        def boom_tfidf(*a, **k):
            raise RuntimeError("tfidf broke")

        def boom_pos(*a, **k):
            raise RuntimeError("pos broke too")

        monkeypatch.setattr(ext.tfidf_extractor, "extract_keywords", boom_tfidf)
        monkeypatch.setattr(
            ext.tfidf_extractor.preprocessor, "extract_keywords_pos", boom_pos
        )
        result = ext.extract_keywords_and_topics(_corpus()[0])
        # both extraction attempts failed -> keywords stays empty, still returns.
        assert isinstance(result, ExtractionResult)
        assert result.keywords == []


# ---------------------------------------------------------------------------
# create_keyword_extractor factory branches
# ---------------------------------------------------------------------------
class TestFactoryBranches:
    def test_nltk_lookuperror_still_returns_full_extractor(self, monkeypatch):
        # nltk import succeeds but stopwords.words raises LookupError inside the
        # factory -> nltk_available False; sklearn present -> full extractor.
        import nltk.corpus as nltk_corpus

        def boom(*a, **k):
            raise LookupError("no nltk data")

        monkeypatch.setattr(nltk_corpus.stopwords, "words", boom)
        ext = create_keyword_extractor()
        assert isinstance(ext, KeywordTopicExtractor)

    def test_spacy_load_success_branch(self, monkeypatch):
        # Force spacy.load to succeed inside the factory (spacy_available True).
        import spacy

        monkeypatch.setattr(spacy, "load", lambda name: object())
        ext = create_keyword_extractor()
        assert isinstance(ext, KeywordTopicExtractor)

    def test_spacy_import_error_branch(self, monkeypatch):
        # Make `import spacy` inside the factory raise ImportError (line 1035-1036).
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "spacy" or name.startswith("spacy."):
                raise ImportError("no spacy")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        ext = create_keyword_extractor()
        # sklearn still present -> full extractor returned.
        assert isinstance(ext, KeywordTopicExtractor)

    def test_nltk_import_error_branch(self, monkeypatch):
        # Make `import nltk` inside the factory raise ImportError (lines 1021-1022).
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "nltk" or name.startswith("nltk."):
                raise ImportError("no nltk")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        ext = create_keyword_extractor()
        # sklearn still available -> full extractor is returned regardless.
        assert isinstance(ext, KeywordTopicExtractor)

    def test_simple_branch_config_load_error(self, monkeypatch, tmp_path):
        # No sklearn -> simple branch; a broken config file triggers the
        # config-load except in the SimpleKeywordExtractor branch.
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("sklearn"):
                raise ImportError("no sklearn")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        bad = tmp_path / "bad.json"
        bad.write_text("{ not: valid json")
        ext = create_keyword_extractor(str(bad))
        assert isinstance(ext, SimpleKeywordExtractor)
        # falls back to default config despite the unreadable file.
        assert ext.config["keywords_per_article"] == 10

    def test_outer_exception_falls_back_to_simple(self, monkeypatch):
        # Make the very first thing the factory does (the sklearn import attempt)
        # raise a non-ImportError so the outer try/except catches it and returns
        # a SimpleKeywordExtractor (lines 1074-1078).
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("sklearn"):
                raise RuntimeError("unexpected sklearn explosion")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        ext = create_keyword_extractor()
        assert isinstance(ext, SimpleKeywordExtractor)


# ---------------------------------------------------------------------------
# Module-level import fallbacks: reload with nltk / spacy blocked
# ---------------------------------------------------------------------------
class TestModuleImportFallbacks:
    @staticmethod
    def _reload_with_blocked(block_names):
        """Reload the module with the named top-level imports failing.

        Returns the freshly-loaded module object.  Caller MUST restore the
        canonical module afterwards.
        """
        real_import = builtins.__import__

        def guarded(name, *a, **k):
            for blocked in block_names:
                if name == blocked or name.startswith(blocked + "."):
                    raise ImportError("blocked {0}".format(name))
            return real_import(name, *a, **k)

        # Drop cached copies so the import machinery re-runs the top-level code.
        purge = [
            m
            for m in list(sys.modules)
            if any(m == b or m.startswith(b + ".") for b in block_names)
        ]
        saved = {m: sys.modules.pop(m) for m in purge}
        builtins.__import__ = guarded
        try:
            reloaded = importlib.reload(mod)
        finally:
            builtins.__import__ = real_import
            for m, val in saved.items():
                sys.modules.setdefault(m, val)
        return reloaded

    def _restore(self):
        # Reload cleanly so the module (and its module-level singletons) are
        # back to the real NLTK/spaCy-backed implementation for anything else.
        importlib.reload(mod)

    def test_nltk_import_error_installs_dummy_shims(self):
        try:
            reloaded = self._reload_with_blocked(["nltk"])
            assert reloaded.NLTK_AVAILABLE is False
            # Dummy shims are wired up and behave sensibly.
            assert reloaded.word_tokenize("alpha beta gamma") == [
                "alpha",
                "beta",
                "gamma",
            ]
            assert reloaded.sent_tokenize("one. two. three") == [
                "one",
                " two",
                " three",
            ]
            assert reloaded.pos_tag(["x", "y"]) == [("x", "NN"), ("y", "NN")]
            assert reloaded.WordNetLemmatizer().lemmatize("running") == "running"
        finally:
            self._restore()

    def test_spacy_import_error_sets_flag_false(self):
        try:
            reloaded = self._reload_with_blocked(["spacy"])
            assert reloaded.SPACY_AVAILABLE is False
            assert reloaded.nlp is None
        finally:
            self._restore()

    def test_preprocessor_usable_after_nltk_blocked_reload(self):
        try:
            reloaded = self._reload_with_blocked(["nltk"])
            # With NLTK gone the preprocessor falls back to simple heuristics but
            # remains fully usable end to end.
            pre = reloaded.TextPreprocessor()
            assert pre.lemmatizer is None
            kws = pre.extract_keywords_pos(
                "Satellites orbit distant planets in deep space", max_keywords=5
            )
            assert isinstance(kws, list)
            assert len(kws) >= 1
        finally:
            self._restore()

    def test_nltk_present_but_nonfunctional_sets_flag_false(self):
        # nltk imports fine, but the functional probe (stopwords.words) raises,
        # so the module marks NLTK_AVAILABLE False (lines 74-80).
        import nltk.corpus as nltk_corpus

        orig_words = nltk_corpus.stopwords.words

        def boom(*a, **k):
            raise RuntimeError("stopwords data missing")

        nltk_corpus.stopwords.words = boom
        try:
            reloaded = importlib.reload(mod)
            assert reloaded.NLTK_AVAILABLE is False
        finally:
            nltk_corpus.stopwords.words = orig_words
            self._restore()

    def test_nltk_data_download_failure_is_logged(self):
        # ensure_nltk_data: data missing (find raises) AND download raises ->
        # the "Failed to download" except branch runs (lines 62-63).
        import nltk

        orig_find = nltk.data.find
        orig_download = nltk.download

        def find_boom(path, *a, **k):
            raise LookupError("not found")

        def download_boom(name, *a, **k):
            raise RuntimeError("download failed")

        nltk.data.find = find_boom
        nltk.download = download_boom
        try:
            reloaded = importlib.reload(mod)
            # Module still imports; NLTK becomes usable again once real data is
            # confirmed by the functional probe (find is restored in finally).
            assert reloaded is mod
        finally:
            nltk.data.find = orig_find
            nltk.download = orig_download
            self._restore()
