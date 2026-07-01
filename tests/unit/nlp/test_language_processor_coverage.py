"""Coverage tests for src/nlp/language_processor.py.

Targets the remaining uncovered branches in ``LanguageDetector``,
``LocalTranslationService`` and ``TranslationQualityChecker``:

* low-confidence detection result
* the non-Latin character-score combination path
* ``get_supported_languages`` on both detector and service
* translation text truncation and the ``langdetect`` code path
* the empty-text and length-ratio edge cases of the quality checker
* the several quality-score length-ratio penalty branches

No external dependencies are required (the module is pure-Python); the
optional ``langdetect`` path is exercised by patching the module-level hooks.
"""

import os
import sys

# Warm up torch before coverage's C tracer (nlp package import pulls torch in).
try:  # pragma: no cover - defensive
    import torch  # noqa: F401
except Exception:  # pragma: no cover
    pass

from unittest.mock import MagicMock, patch  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.language_processor as mod  # noqa: E402
from nlp.language_processor import (  # noqa: E402
    LanguageDetector,
    LocalTranslationService,
    TranslationQualityChecker,
)


class TestLanguageDetector:
    def test_short_text_returns_unknown(self):
        d = LanguageDetector()
        result = d.detect_language("hi", min_length=50)
        assert result["language"] == "unknown"
        assert result["reason"] == "text_too_short"

    def test_too_few_words_returns_unknown(self):
        d = LanguageDetector()
        # >= min_length chars but < 5 words after cleaning
        result = d.detect_language("wordone wordtwo " + "x" * 60, min_length=10)
        assert result["language"] == "unknown"
        assert result["reason"] == "insufficient_words"

    def test_low_confidence_returns_best_guess(self):
        d = LanguageDetector()
        # gibberish that matches no common words -> confidence < 0.1 branch
        text = "qwrtp zxcvb hjklm nbvcx plkju mnbvc"
        result = d.detect_language(text, min_length=5)
        assert result["language"] == "unknown"
        assert result["reason"] == "low_confidence"
        assert "best_guess" in result
        assert result["confidence"] < 0.1

    def test_english_detection_high_confidence(self):
        d = LanguageDetector()
        text = "the cat and the dog are in the house with the man for a day"
        result = d.detect_language(text, min_length=5)
        assert result["language"] == "en"
        assert result["method"] == "pattern_based"
        assert "all_scores" in result

    def test_chinese_char_score_path(self):
        d = LanguageDetector()
        # Chinese common words trigger the char-score (non-Latin) combine branch.
        text = "我 有 的 是 在 和 就 不 人 都 一 上 也 很 到"
        result = d.detect_language(text, min_length=5)
        assert result["language"] == "zh"

    def test_get_supported_languages(self):
        d = LanguageDetector()
        langs = d.get_supported_languages()
        assert "en" in langs and "zh" in langs
        assert set(langs) == set(LanguageDetector.LANGUAGE_PATTERNS.keys())


class TestLocalTranslationService:
    def test_empty_text_returns_error(self):
        svc = LocalTranslationService()
        result = svc.translate_text("", "es", "en")
        assert result["translation_performed"] is False
        assert result["error"] == "Empty text provided"

    def test_same_language_identity(self):
        svc = LocalTranslationService()
        result = svc.translate_text("hello", "en", "en")
        assert result["translated_text"] == "hello"
        assert result["confidence"] == 1.0

    def test_pass_through_and_cache(self):
        svc = LocalTranslationService()
        first = svc.translate_text("hola mundo", "es", "en")
        assert first["translation_performed"] is False
        assert first["translated_text"] == "hola mundo"
        # second identical call must hit the cache (same dict object)
        second = svc.translate_text("hola mundo", "es", "en")
        assert second is first

    def test_truncation_when_over_max_length(self):
        svc = LocalTranslationService()
        long_text = "x" * 20
        result = svc.translate_text(long_text, "es", "en", max_length=5)
        assert result["translated_text"] == "xxxxx"
        assert len(result["translated_text"]) == 5

    def test_get_supported_languages(self):
        svc = LocalTranslationService()
        assert svc.get_supported_languages() == LocalTranslationService.SUPPORTED_LANGUAGES

    def test_detect_language_empty_returns_default(self):
        svc = LocalTranslationService()
        result = svc.detect_language("   ")
        assert result["language_code"] == "en"
        assert result["error"] == "No language detected"

    def test_detect_language_uses_langdetect_when_available(self):
        svc = LocalTranslationService()
        candidate = MagicMock()
        candidate.lang = "fr-FR"
        candidate.prob = 0.88
        with patch.object(mod, "_HAS_LANGDETECT", True), patch.object(
            mod, "_langdetect_detect_langs", return_value=[candidate]
        ):
            result = svc.detect_language("bonjour le monde ceci est un texte")
        # code normalized ("fr-FR" -> "fr")
        assert result["language_code"] == "fr"
        assert result["confidence"] == 0.88
        assert result["error"] is None

    def test_detect_language_langdetect_empty_falls_back_to_heuristic(self):
        svc = LocalTranslationService()
        with patch.object(mod, "_HAS_LANGDETECT", True), patch.object(
            mod, "_langdetect_detect_langs", return_value=[]
        ):
            result = svc.detect_language(
                "the cat and the dog are in the house with the man"
            )
        # empty candidate list -> heuristic fallback path
        assert result["language_code"] == "en"
        assert result["error"] is None

    def test_detect_language_heuristic_unknown_maps_to_en(self):
        svc = LocalTranslationService()
        with patch.object(mod, "_HAS_LANGDETECT", False):
            # gibberish -> heuristic returns "unknown" -> mapped to "en"
            result = svc.detect_language("qwrtp zxcvb hjklm nbvcx plkju")
        assert result["language_code"] == "en"


class TestTranslationQualityChecker:
    def test_empty_text_returns_zero_quality(self):
        qc = TranslationQualityChecker()
        result = qc.check_translation_quality("", "algo", "es", "en")
        assert result["quality_score"] == 0.0
        assert "Empty text provided" in result["issues"]

    def test_untranslated_flagged(self):
        qc = TranslationQualityChecker()
        result = qc.check_translation_quality("same text", "same text", "es", "en")
        assert "No translation occurred" in result["issues"]

    def test_translation_too_short_issue(self):
        qc = TranslationQualityChecker()
        # en->de expected ratio (0.7, 1.2); ratio well below 0.7
        result = qc.check_translation_quality(
            "a" * 100, "b" * 10, "en", "de"
        )
        assert any("too short" in i for i in result["issues"])

    def test_translation_too_long_issue(self):
        qc = TranslationQualityChecker()
        # en->de expected max 1.2; ratio ~3.0 triggers "too long"
        result = qc.check_translation_quality(
            "a" * 30, "b" * 90, "en", "de"
        )
        assert any("too long" in i for i in result["issues"])

    def test_encoding_issue_flagged(self):
        qc = TranslationQualityChecker()
        result = qc.check_translation_quality("hello world", "h�llo w�rld", "es", "en")
        assert any("encoding" in i for i in result["issues"])

    def test_assess_quality_known_pair_length_ok(self):
        qc = TranslationQualityChecker()
        # ratio ~1.0 within en->es bounds (0.8, 1.3)
        result = qc.assess_translation_quality(
            "hello world foo", "hola mundo fooo", "en", "es"
        )
        assert result["length_ratio_ok"] is True
        assert result["overall_score"] == result["quality_score"]

    def test_assess_quality_unknown_pair_lenient(self):
        qc = TranslationQualityChecker()
        # unknown pair uses the lenient 0.3..3.0 check
        result = qc.assess_translation_quality(
            "hello world", "bonjour le", "en", "xx"
        )
        assert "length_ratio_ok" in result

    def test_quality_score_very_short_penalty(self):
        qc = TranslationQualityChecker()
        # length_ratio < 0.2 -> base_score *= 0.2 branch
        score = qc._calculate_quality_score(0.1, [], ("en", "de"))
        assert 0.0 <= score <= 0.3

    def test_quality_score_short_penalty(self):
        qc = TranslationQualityChecker()
        # 0.2 <= ratio < 0.3 -> base_score *= 0.4 branch
        score = qc._calculate_quality_score(0.25, [], ("en", "de"))
        assert 0.0 <= score <= 0.5

    def test_quality_score_very_long_penalty(self):
        qc = TranslationQualityChecker()
        # ratio > 5.0 -> base_score *= 0.3 branch
        score = qc._calculate_quality_score(6.0, [], ("en", "de"))
        assert 0.0 <= score <= 0.35

    def test_quality_score_long_penalty(self):
        qc = TranslationQualityChecker()
        # 3.0 < ratio <= 5.0 -> base_score *= 0.5 branch
        score = qc._calculate_quality_score(4.0, [], ("en", "de"))
        assert 0.0 <= score <= 0.55

    def test_quality_score_moderate_lenient_pair(self):
        qc = TranslationQualityChecker()
        # normal ratio + writing-system pair -> lenient length_penalty branch
        score = qc._calculate_quality_score(1.0, [], ("en", "zh"))
        assert score == 1.0

    def test_quality_score_moderate_default_pair(self):
        qc = TranslationQualityChecker()
        score = qc._calculate_quality_score(1.0, [], ("en", "es"))
        assert score == 1.0
