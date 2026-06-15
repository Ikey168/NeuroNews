"""Tests for validation/rate-limit pipelines in src/ingestion/scrapy_integration.py."""

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
    AdaptiveRateLimitPipeline,
    HighThroughputValidationPipeline,
)


@pytest.fixture
def spider():
    s = MagicMock()
    s.logger = MagicMock()
    return s


def item(**over):
    base = dict(
        title="A sufficiently long article title",
        url="https://bbc.com/news/1",
        content="word " * 50,  # 250 chars, > min 100
    )
    base.update(over)
    return base


class TestFastValidate:
    def test_valid(self):
        pipe = HighThroughputValidationPipeline()
        result = pipe._fast_validate_item(item())
        assert result["is_valid"] is True
        assert result["score"] <= 100

    def test_missing_title(self):
        pipe = HighThroughputValidationPipeline()
        assert pipe._fast_validate_item(item(title=""))["reason"] == "Missing title"

    def test_short_title(self):
        pipe = HighThroughputValidationPipeline()
        assert pipe._fast_validate_item(item(title="short"))["is_valid"] is False

    def test_long_title_penalty(self):
        pipe = HighThroughputValidationPipeline()
        result = pipe._fast_validate_item(item(title="x" * 350))
        assert result["is_valid"] is True
        assert result["score"] == 90

    def test_missing_content(self):
        pipe = HighThroughputValidationPipeline()
        assert pipe._fast_validate_item(item(content=""))["reason"] == "Missing content"

    def test_short_content(self):
        pipe = HighThroughputValidationPipeline()
        assert pipe._fast_validate_item(item(content="tiny"))["is_valid"] is False

    def test_missing_url(self):
        pipe = HighThroughputValidationPipeline()
        assert pipe._fast_validate_item(item(url=""))["reason"] == "Missing URL"


class TestValidationProcessItem:
    def test_valid_item_passes(self, spider):
        pipe = HighThroughputValidationPipeline()
        result = pipe.process_item(item(), spider)
        assert result["validation_score"] > 0
        assert result["fast_validation"] is True
        assert pipe.items_passed == 1

    def test_duplicate_url_dropped(self, spider):
        pipe = HighThroughputValidationPipeline()
        pipe.process_item(item(url="https://x/1"), spider)
        with pytest.raises(DropItem):
            pipe.process_item(item(url="https://x/1"), spider)

    def test_invalid_dropped(self, spider):
        pipe = HighThroughputValidationPipeline()
        with pytest.raises(DropItem):
            pipe.process_item(item(title=""), spider)
        assert pipe.items_failed >= 1


class TestAdaptiveRateLimit:
    def test_init(self):
        pipe = AdaptiveRateLimitPipeline()
        assert pipe.current_delay == 1.0
        assert pipe.min_delay == 0.1

    def test_process_item_adds_metadata(self, spider):
        pipe = AdaptiveRateLimitPipeline()
        result = pipe.process_item(item(), spider)
        assert result["adaptive_rate_limit"] is True
        assert result["current_delay"] == pipe.current_delay
        assert pipe.items_processed == 1
