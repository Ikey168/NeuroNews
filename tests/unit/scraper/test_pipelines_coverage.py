"""Coverage-focused tests for src/scraper/pipelines.py.

Exercises ValidationPipeline scoring branches, DuplicateFilterPipeline URL /
content de-duplication, and the JSON writer pipelines (open/process/close)
using a temporary working directory. A lightweight spider stub captures logger
calls so we can assert rejection/duplicate logging.
"""

import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# NOTE: There is both a ``scraper/pipelines.py`` MODULE and a
# ``scraper/pipelines/`` PACKAGE. ``import scraper.pipelines`` resolves to the
# package, which does not expose the legacy ``JsonWriterPipeline`` from the
# flat module. Load the flat module directly by file path so this test targets
# ``src/scraper/pipelines.py`` (and coverage attributes to that file).
_PIPELINES_PATH = os.path.join(SRC, "scraper", "pipelines.py")
_spec = importlib.util.spec_from_file_location(
    "scraper_flat_pipelines", _PIPELINES_PATH
)
pipelines_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pipelines_mod)

DuplicateFilterPipeline = pipelines_mod.DuplicateFilterPipeline
EnhancedJsonWriterPipeline = pipelines_mod.EnhancedJsonWriterPipeline
JsonWriterPipeline = pipelines_mod.JsonWriterPipeline
ValidationPipeline = pipelines_mod.ValidationPipeline


class FakeSpider:
    """Minimal spider stub exposing a mock logger."""

    def __init__(self):
        self.logger = MagicMock()


def good_item(**over):
    item = {
        "title": "A clearly valid news headline here",
        "url": "https://example.com/news/story",
        "content": "Word " * 300,
        "source": "ExampleSource",
        "published_date": "2024-01-01T10:00:00Z",
    }
    item.update(over)
    return item


class TestValidationPipeline:
    def test_valid_item_passes_and_enriches(self):
        pipe = ValidationPipeline()
        spider = FakeSpider()
        result = pipe.process_item(good_item(), spider)

        assert result is not None
        assert result["validation_score"] >= 50
        assert result["content_quality"] in ("high", "medium", "low")
        assert result["word_count"] == 300
        assert result["reading_time"] == max(1, round(300 / 200))
        assert result["language"] == "en"
        assert "scraped_date" in result

    def test_high_quality_label(self):
        pipe = ValidationPipeline()
        result = pipe.process_item(good_item(), FakeSpider())
        # A full, valid item keeps a high score.
        assert result["content_quality"] == "high"
        assert result["validation_score"] >= 80

    def test_missing_required_fields_rejected(self):
        pipe = ValidationPipeline()
        spider = FakeSpider()
        item = {"title": "", "url": "", "content": "", "source": ""}
        result = pipe.process_item(item, spider)

        assert result is None
        # Below-threshold items are logged and dropped.
        spider.logger.warning.assert_called_once()

    def test_short_title_penalty(self):
        pipe = ValidationPipeline()
        # Title < 10 chars costs 10 points but item still passes.
        result = pipe.process_item(good_item(title="Short"), FakeSpider())
        assert result is not None
        assert result["validation_score"] < 100

    def test_long_title_penalty(self):
        pipe = ValidationPipeline()
        result = pipe.process_item(good_item(title="T" * 250), FakeSpider())
        assert result is not None
        assert result["validation_score"] < 100

    def test_short_content_penalty(self):
        pipe = ValidationPipeline()
        result = pipe.process_item(good_item(content="tiny"), FakeSpider())
        # Content < 100 chars costs 20; still enriched with content_length.
        assert result is not None
        assert result["content_length"] == 4
        assert result["validation_score"] <= 80

    def test_very_long_content_penalty(self):
        pipe = ValidationPipeline()
        long_content = "x" * 12000
        result = pipe.process_item(good_item(content=long_content), FakeSpider())
        assert result is not None
        assert result["content_length"] == 12000

    def test_missing_content_penalty(self):
        pipe = ValidationPipeline()
        item = good_item()
        del item["content"]
        result = pipe.process_item(item, FakeSpider())
        # Missing content: -25 (required) -30 (else branch) => borderline.
        assert result is None or result["validation_score"] < 80

    def test_invalid_url_penalty(self):
        pipe = ValidationPipeline()
        result = pipe.process_item(good_item(url="not-a-valid-url"), FakeSpider())
        # Scheme/netloc missing costs 15 points.
        assert result is not None
        assert result["validation_score"] < 100

    def test_invalid_date_penalty(self):
        pipe = ValidationPipeline()
        result = pipe.process_item(
            good_item(published_date="2024-13-99T99:99:99Z"), FakeSpider()
        )
        # Unparseable ISO date costs 10 points.
        assert result is not None
        assert result["validation_score"] < 100

    def test_non_iso_date_not_penalized(self):
        pipe = ValidationPipeline()
        result = pipe.process_item(
            good_item(published_date="January 1, 2024"), FakeSpider()
        )
        # No "T" -> parsing is skipped, so no date penalty.
        assert result is not None

    def test_medium_quality_label(self):
        pipe = ValidationPipeline()
        # Combine small penalties to land in the medium band (60-79):
        # short title (-10) + invalid url (-15) = 75.
        item = good_item(
            title="Short",  # -10
            url="not-a-valid-url",  # -15
        )
        result = pipe.process_item(item, FakeSpider())
        assert result is not None
        assert result["validation_score"] == 75
        assert result["content_quality"] == "medium"

    def test_explicit_language_preserved(self):
        pipe = ValidationPipeline()
        result = pipe.process_item(good_item(language="fr"), FakeSpider())
        assert result["language"] == "fr"


class TestDuplicateFilterPipeline:
    def test_unique_item_passes(self):
        pipe = DuplicateFilterPipeline()
        item = good_item()
        result = pipe.process_item(item, FakeSpider())
        assert result is not None
        assert result["duplicate_check"] == "unique"
        assert item["url"] in pipe.urls_seen

    def test_url_duplicate_rejected(self):
        pipe = DuplicateFilterPipeline()
        spider = FakeSpider()
        first = good_item()
        pipe.process_item(first, spider)
        # Same URL, different content -> URL duplicate.
        dup = good_item(content="Completely different text " * 40)
        result = pipe.process_item(dup, spider)
        assert result is None
        assert dup["duplicate_check"] == "url_duplicate"
        spider.logger.info.assert_called()

    def test_content_duplicate_rejected(self):
        pipe = DuplicateFilterPipeline()
        spider = FakeSpider()
        first = good_item(url="https://example.com/a")
        pipe.process_item(first, spider)
        # Different URL but identical content -> content duplicate.
        dup = good_item(url="https://example.com/b")
        result = pipe.process_item(dup, spider)
        assert result is None
        assert dup["duplicate_check"] == "content_duplicate"

    def test_item_without_content_still_tracked(self):
        pipe = DuplicateFilterPipeline()
        item = good_item()
        del item["content"]
        result = pipe.process_item(item, FakeSpider())
        # No content hash computed, but URL is recorded and item passes.
        assert result is not None
        assert result["duplicate_check"] == "unique"
        assert item["url"] in pipe.urls_seen


class TestEnhancedJsonWriterPipeline:
    def test_full_lifecycle_writes_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pipe = EnhancedJsonWriterPipeline()
        spider = FakeSpider()

        pipe.open_spider(spider)
        pipe.process_item(good_item(source="BBC News"), spider)
        pipe.process_item(good_item(source="BBC News", url="https://x/2"), spider)
        pipe.process_item(good_item(source="CNN"), spider)
        pipe.close_spider(spider)

        combined = json.loads((tmp_path / "data" / "all_articles.json").read_text())
        assert len(combined) == 3

        sources_dir = tmp_path / "data" / "sources"
        bbc = json.loads((sources_dir / "bbc_news_articles.json").read_text())
        assert len(bbc) == 2
        cnn = json.loads((sources_dir / "cnn_articles.json").read_text())
        assert len(cnn) == 1

    def test_missing_source_defaults_to_unknown(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pipe = EnhancedJsonWriterPipeline()
        spider = FakeSpider()
        pipe.open_spider(spider)
        item = good_item()
        del item["source"]
        pipe.process_item(item, spider)
        pipe.close_spider(spider)

        unknown = tmp_path / "data" / "sources" / "unknown_articles.json"
        assert unknown.exists()
        assert json.loads(unknown.read_text())


class TestJsonWriterPipeline:
    def test_legacy_lifecycle(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pipe = JsonWriterPipeline()
        spider = FakeSpider()

        pipe.open_spider(spider)
        pipe.process_item(good_item(url="https://x/1"), spider)
        pipe.process_item(good_item(url="https://x/2"), spider)
        pipe.close_spider(spider)

        data = json.loads((tmp_path / "data" / "news_articles.json").read_text())
        assert len(data) == 2
        assert data[0]["url"] == "https://x/1"
