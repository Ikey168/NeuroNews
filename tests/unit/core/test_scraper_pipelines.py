"""Tests for the scraper pipelines package and the legacy pipelines module."""

import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.pipelines import (  # noqa: E402
    DuplicateFilterPipeline,
    EnhancedJsonWriterPipeline,
    ValidationPipeline,
)


def _load_legacy_pipelines():
    """Load src/scraper/pipelines.py, which is shadowed by the package."""
    path = os.path.join(SRC, "scraper", "pipelines.py")
    spec = importlib.util.spec_from_file_location("legacy_scraper_pipelines", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


JsonWriterPipeline = _load_legacy_pipelines().JsonWriterPipeline


def make_item(**overrides):
    item = {
        "title": "A reasonably long valid headline here",
        "url": "https://example.com/news/1",
        "content": "word " * 150,
        "source": "Example News",
        "published_date": "2025-01-15T10:00:00",
    }
    item.update(overrides)
    return item


@pytest.fixture
def spider():
    s = MagicMock()
    s.name = "test_spider"
    return s


class TestValidationPipeline:
    def test_valid_item_passes(self, spider):
        pipeline = ValidationPipeline()
        item = pipeline.process_item(make_item(), spider)
        assert item is not None
        assert item["validation_score"] >= 80
        assert item["content_quality"] == "high"
        assert item["word_count"] == 150
        assert item["reading_time"] == 1
        assert item["language"] == "en"
        assert "scraped_date" in item

    def test_missing_fields_rejected(self, spider):
        pipeline = ValidationPipeline()
        result = pipeline.process_item({"title": ""}, spider)
        assert result is None
        spider.logger.warning.assert_called_once()

    def test_short_title_penalized(self, spider):
        pipeline = ValidationPipeline()
        item = pipeline.process_item(make_item(title="short"), spider)
        assert item["validation_score"] == 90

    def test_long_title_penalized(self, spider):
        pipeline = ValidationPipeline()
        item = pipeline.process_item(make_item(title="x" * 250), spider)
        assert item["validation_score"] == 90

    def test_short_content_penalized(self, spider):
        pipeline = ValidationPipeline()
        item = pipeline.process_item(make_item(content="tiny"), spider)
        assert item["validation_score"] == 80

    def test_very_long_content_small_penalty(self, spider):
        pipeline = ValidationPipeline()
        item = pipeline.process_item(make_item(content="w" * 10001), spider)
        assert item["validation_score"] == 95

    def test_invalid_url_penalized(self, spider):
        pipeline = ValidationPipeline()
        item = pipeline.process_item(make_item(url="not-a-url"), spider)
        assert item["validation_score"] == 85

    def test_invalid_date_penalized(self, spider):
        pipeline = ValidationPipeline()
        item = pipeline.process_item(
            make_item(published_date="2025-13-99T99:99:99"), spider
        )
        assert item["validation_score"] == 90

    def test_medium_quality_band(self, spider):
        pipeline = ValidationPipeline()
        item = pipeline.process_item(
            make_item(title="short", content="tiny"), spider
        )
        # -10 title, -20 short content => 70 => medium
        assert item["content_quality"] == "medium"

    def test_low_quality_band(self, spider):
        pipeline = ValidationPipeline()
        item = pipeline.process_item(
            make_item(title="short", content="tiny", url="bad"), spider
        )
        # 100 -10 -20 -15 = 55 => low but >= 50 passes
        assert item["content_quality"] == "low"
        assert item["validation_score"] == 55


class TestDuplicateFilterPipeline:
    def test_unique_item_passes(self, spider):
        pipeline = DuplicateFilterPipeline()
        item = pipeline.process_item(make_item(), spider)
        assert item["duplicate_check"] == "unique"

    def test_duplicate_url_dropped(self, spider):
        pipeline = DuplicateFilterPipeline()
        pipeline.process_item(make_item(), spider)
        result = pipeline.process_item(make_item(content="different"), spider)
        assert result is None

    def test_duplicate_content_dropped(self, spider):
        pipeline = DuplicateFilterPipeline()
        pipeline.process_item(make_item(), spider)
        result = pipeline.process_item(
            make_item(url="https://example.com/news/2"), spider
        )
        assert result is None

    def test_item_without_content(self, spider):
        pipeline = DuplicateFilterPipeline()
        item = make_item()
        del item["content"]
        assert pipeline.process_item(item, spider)["duplicate_check"] == "unique"


class TestJsonWriterPipeline:
    def test_writes_valid_json(self, tmp_path, monkeypatch, spider):
        monkeypatch.chdir(tmp_path)
        pipeline = JsonWriterPipeline()
        pipeline.open_spider(spider)
        pipeline.process_item(make_item(), spider)
        pipeline.process_item(make_item(url="https://example.com/2"), spider)
        pipeline.close_spider(spider)

        data = json.loads((tmp_path / "data" / "news_articles.json").read_text())
        assert len(data) == 2
        assert data[0]["source"] == "Example News"


class TestEnhancedJsonWriterPipeline:
    def test_writes_combined_and_source_files(self, tmp_path, monkeypatch, spider):
        monkeypatch.chdir(tmp_path)
        pipeline = EnhancedJsonWriterPipeline()
        pipeline.open_spider(spider)
        pipeline.process_item(make_item(), spider)
        pipeline.process_item(
            make_item(url="https://other.com/1", source="Other Site"), spider
        )
        pipeline.process_item(
            make_item(url="https://example.com/2"), spider
        )
        pipeline.close_spider(spider)

        combined = json.loads((tmp_path / "data" / "all_articles.json").read_text())
        assert len(combined) == 3

        example = json.loads(
            (tmp_path / "data" / "sources" / "example_news_articles.json").read_text()
        )
        assert len(example) == 2

        other = json.loads(
            (tmp_path / "data" / "sources" / "other_site_articles.json").read_text()
        )
        assert len(other) == 1
