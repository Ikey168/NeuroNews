"""
Coverage-focused tests for src/scraper/pipelines/multi_language_pipeline.py.

Exercises MultiLanguagePipeline (open/close/process/validate) and
LanguageFilterPipeline (from_crawler, filtering, stats). The heavy
MultiLanguageArticleProcessor is replaced with a lightweight stub, and
NewsItem is used for real item objects. scrapy is imported directly.
"""

import logging

import pytest

scrapy = pytest.importorskip("scrapy")

from scrapy.exceptions import DropItem

from src.scraper.items import NewsItem
from src.scraper.pipelines import multi_language_pipeline as mlp


# --------------------------------------------------------------------------- #
# Stub processor
# --------------------------------------------------------------------------- #

class _StubProcessor:
    def __init__(self, result=None, raise_on_process=False, **kwargs):
        self.kwargs = kwargs
        self._result = result or {}
        self._raise = raise_on_process

    def process_article(self, article_data):
        if self._raise:
            raise RuntimeError("processor boom")
        return self._result

    def get_translation_statistics(self):
        return {"total": 5}


class _Spider:
    name = "test-spider"


def _make_item(**overrides):
    item = NewsItem()
    item["title"] = overrides.get("title", "A reasonably long headline here")
    item["content"] = overrides.get("content", "x" * 200)
    item["url"] = overrides.get("url", "https://example.com/a")
    item["source"] = overrides.get("source", "src")
    return item


def _pipeline_with_processor(monkeypatch, **proc_kwargs):
    p = mlp.MultiLanguagePipeline(min_content_length=100)

    def _factory(**kwargs):
        return _StubProcessor(**{**proc_kwargs, **kwargs})

    monkeypatch.setattr(mlp, "MultiLanguageArticleProcessor", _factory)
    p.open_spider(_Spider())
    return p


# --------------------------------------------------------------------------- #
# open_spider
# --------------------------------------------------------------------------- #

def test_open_spider_initializes_processor(monkeypatch):
    p = _pipeline_with_processor(monkeypatch)
    assert isinstance(p.processor, _StubProcessor)
    # kwargs get forwarded from the pipeline config.
    assert p.processor.kwargs["target_language"] == "en"


def test_open_spider_reraises_on_failure(monkeypatch):
    p = mlp.MultiLanguagePipeline()

    def _boom(**kwargs):
        raise ValueError("cannot init")

    monkeypatch.setattr(mlp, "MultiLanguageArticleProcessor", _boom)
    with pytest.raises(ValueError):
        p.open_spider(_Spider())


# --------------------------------------------------------------------------- #
# close_spider
# --------------------------------------------------------------------------- #

def test_close_spider_logs_detailed_stats(monkeypatch, caplog):
    p = _pipeline_with_processor(monkeypatch)
    with caplog.at_level(logging.INFO):
        p.close_spider(_Spider())
    assert "Pipeline statistics" in caplog.text
    assert "Detailed translation statistics" in caplog.text


def test_close_spider_handles_stats_error(monkeypatch, caplog):
    p = _pipeline_with_processor(monkeypatch)

    def _boom():
        raise RuntimeError("no stats")

    p.processor.get_translation_statistics = _boom
    with caplog.at_level(logging.ERROR):
        p.close_spider(_Spider())
    assert "Error getting detailed statistics" in caplog.text


def test_close_spider_without_processor(monkeypatch):
    p = mlp.MultiLanguagePipeline()
    p.processor = None
    # Should not raise even with no processor.
    p.close_spider(_Spider())


# --------------------------------------------------------------------------- #
# process_item
# --------------------------------------------------------------------------- #

def test_process_item_disabled_returns_unchanged(monkeypatch):
    p = _pipeline_with_processor(monkeypatch)
    p.enabled = False
    item = _make_item()
    assert p.process_item(item, _Spider()) is item


def test_process_item_with_translation(monkeypatch):
    result = {
        "original_language": "es",
        "detection_confidence": 0.99,
        "translation_performed": True,
        "translation_quality": 0.85,
        "translated_title": "Translated T",
        "translated_content": "Translated C",
    }
    p = _pipeline_with_processor(monkeypatch, result=result)
    out = p.process_item(_make_item(), _Spider())
    assert out["original_language"] == "es"
    assert out["translation_performed"] is True
    assert out["translated_title"] == "Translated T"
    assert out["target_language"] == "en"
    assert p.stats["items_processed"] == 1
    assert p.stats["items_translated"] == 1
    assert p.stats["language_distribution"]["es"] == 1


def test_process_item_records_errors(monkeypatch, caplog):
    result = {
        "original_language": "fr",
        "translation_performed": False,
        "errors": ["some translation error"],
    }
    p = _pipeline_with_processor(monkeypatch, result=result)
    with caplog.at_level(logging.WARNING):
        p.process_item(_make_item(), _Spider())
    assert p.stats["translation_errors"] == 1
    assert "Translation errors" in caplog.text


def test_process_item_validation_failure_drops(monkeypatch):
    p = _pipeline_with_processor(monkeypatch)
    bad = _make_item(content="short")  # below min_content_length
    with pytest.raises(DropItem):
        p.process_item(bad, _Spider())
    assert p.stats["items_dropped"] == 1


def test_process_item_processor_exception_drops(monkeypatch):
    p = _pipeline_with_processor(monkeypatch, raise_on_process=True)
    with pytest.raises(DropItem):
        p.process_item(_make_item(), _Spider())
    assert p.stats["items_dropped"] == 1


# --------------------------------------------------------------------------- #
# _validate_item
# --------------------------------------------------------------------------- #

def test_validate_item_missing_field():
    p = mlp.MultiLanguagePipeline(min_content_length=10)
    item = _make_item()
    del item["title"]
    assert p._validate_item(item) is False


def test_validate_item_content_too_short():
    p = mlp.MultiLanguagePipeline(min_content_length=100)
    assert p._validate_item(_make_item(content="tiny")) is False


def test_validate_item_invalid_url():
    p = mlp.MultiLanguagePipeline(min_content_length=10)
    assert p._validate_item(_make_item(url="ftp://bad")) is False


def test_validate_item_valid():
    p = mlp.MultiLanguagePipeline(min_content_length=10)
    assert p._validate_item(_make_item()) is True


# --------------------------------------------------------------------------- #
# LanguageFilterPipeline
# --------------------------------------------------------------------------- #

def test_get_original_language():
    fp = mlp.LanguageFilterPipeline()
    assert fp._get_original_language({"language_info": {"detected_language": "de"}}) == "de"
    assert fp._get_original_language({}) == "unknown"


class _FakeSettings:
    def __init__(self, values):
        self._v = values

    def get(self, key, default=None):
        return self._v.get(key, default)

    def getbool(self, key, default=False):
        return self._v.get(key, default)

    def getfloat(self, key, default=0.0):
        return self._v.get(key, default)

    def getint(self, key, default=0):
        return self._v.get(key, default)

    def getlist(self, key, default=None):
        return self._v.get(key, default or [])


class _FakeCrawler:
    def __init__(self, values):
        self.settings = _FakeSettings(values)


def test_from_crawler_builds_multilanguage_pipeline():
    crawler = _FakeCrawler(
        {
            "AWS_REGION": "eu-west-1",
            "TARGET_LANGUAGE": "en",
            "TRANSLATION_ENABLED": True,
            "TRANSLATION_QUALITY_THRESHOLD": 0.9,
            "MIN_CONTENT_LENGTH": 50,
        }
    )
    pipeline = mlp.LanguageFilterPipeline.from_crawler(crawler)
    # Note: from_crawler currently returns a MultiLanguagePipeline.
    assert isinstance(pipeline, mlp.MultiLanguagePipeline)
    assert pipeline.aws_region == "eu-west-1"
    assert pipeline.quality_threshold == 0.9
    assert pipeline.min_content_length == 50


def test_filter_blocked_language_drops():
    fp = mlp.LanguageFilterPipeline(blocked_languages=["ru"])
    item = _make_item()
    item["original_language"] = "ru"
    with pytest.raises(DropItem):
        fp.process_item(item, _Spider())
    assert fp.stats["filter_reasons"]["blocked_language"] == 1


def test_filter_language_not_allowed_drops():
    fp = mlp.LanguageFilterPipeline(allowed_languages=["en"])
    item = _make_item()
    item["original_language"] = "es"
    with pytest.raises(DropItem):
        fp.process_item(item, _Spider())
    assert fp.stats["filter_reasons"]["language_not_allowed"] == 1


def test_filter_translation_required_drops():
    fp = mlp.LanguageFilterPipeline(require_translation=True)
    item = _make_item()
    item["original_language"] = "en"
    item["translation_performed"] = False
    with pytest.raises(DropItem):
        fp.process_item(item, _Spider())
    assert fp.stats["filter_reasons"]["translation_required"] == 1


def test_filter_passes_valid_item():
    fp = mlp.LanguageFilterPipeline(allowed_languages=["en"])
    item = _make_item()
    item["original_language"] = "en"
    item["translation_performed"] = True
    out = fp.process_item(item, _Spider())
    assert out is item
    assert fp.stats["items_passed"] == 1


def test_filter_close_spider_logs(caplog):
    fp = mlp.LanguageFilterPipeline()
    with caplog.at_level(logging.INFO):
        fp.close_spider(_Spider())
    assert "Language filter pipeline statistics" in caplog.text
