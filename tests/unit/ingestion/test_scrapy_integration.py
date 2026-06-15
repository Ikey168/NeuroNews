"""Tests for src/ingestion/scrapy_integration.py."""

import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("scrapy")
from scrapy.exceptions import DropItem  # noqa: E402

from ingestion.scrapy_integration import (  # noqa: E402
    HighThroughputValidationPipeline,
    configure_optimized_settings,
)


def item(**over):
    base = {
        "title": "A reasonably long valid title here",
        "content": "word " * 50,  # > 100 chars
        "url": "https://example.com/1",
    }
    base.update(over)
    return base


@pytest.fixture
def pipeline():
    return HighThroughputValidationPipeline()


@pytest.fixture
def spider():
    s = MagicMock()
    s.logger = MagicMock()
    return s


class TestFastValidate:
    def test_valid_item(self, pipeline):
        result = pipeline._fast_validate_item(item())
        assert result["is_valid"] is True
        assert result["score"] == 100.0

    def test_missing_title(self, pipeline):
        result = pipeline._fast_validate_item(item(title=""))
        assert result["is_valid"] is False
        assert result["reason"] == "Missing title"

    def test_title_too_short(self, pipeline):
        result = pipeline._fast_validate_item(item(title="short"))
        assert result["is_valid"] is False
        assert "too short" in result["reason"]

    def test_title_too_long_penalized(self, pipeline):
        result = pipeline._fast_validate_item(item(title="x" * 301))
        assert result["is_valid"] is True
        assert result["score"] == 90.0

    def test_missing_content(self, pipeline):
        result = pipeline._fast_validate_item(item(content=""))
        assert result["is_valid"] is False
        assert result["reason"] == "Missing content"

    def test_content_too_short(self, pipeline):
        result = pipeline._fast_validate_item(item(content="tiny"))
        assert result["is_valid"] is False
        assert "Content too short" in result["reason"]

    def test_missing_url(self, pipeline):
        result = pipeline._fast_validate_item(item(url=""))
        assert result["is_valid"] is False
        assert result["reason"] == "Missing URL"


class TestProcessItem:
    def test_valid_passes(self, pipeline, spider):
        result = pipeline.process_item(item(), spider)
        assert result["validation_score"] == 100.0
        assert result["fast_validation"] is True
        assert pipeline.items_passed == 1

    def test_duplicate_url_dropped(self, pipeline, spider):
        pipeline.process_item(item(), spider)
        with pytest.raises(DropItem):
            pipeline.process_item(item(content="different content " * 20), spider)

    def test_invalid_dropped(self, pipeline, spider):
        with pytest.raises(DropItem):
            pipeline.process_item(item(title=""), spider)
        assert pipeline.items_failed >= 1


class TestConfigureSettings:
    def test_adds_pipelines(self):
        result = configure_optimized_settings({})
        assert "ITEM_PIPELINES" in result
        assert result["CONCURRENT_REQUESTS"] == 32
        assert result["AUTOTHROTTLE_ENABLED"] is True

    def test_preserves_existing(self):
        result = configure_optimized_settings({"CUSTOM_KEY": "value"})
        assert result["CUSTOM_KEY"] == "value"

    def test_does_not_mutate_input(self):
        original = {"a": 1}
        configure_optimized_settings(original)
        assert original == {"a": 1}
