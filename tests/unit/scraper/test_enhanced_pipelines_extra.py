"""Extra focused tests for src/scraper/enhanced_pipelines.py targeting coverage gaps.

These exercise the Scrapy item pipelines with real assertions on processed item
fields, dedupe logic, quality/credibility filtering, report file output, and the
from_crawler / close_spider hooks.
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("scrapy")
from scrapy.exceptions import DropItem  # noqa: E402

from scraper.enhanced_pipelines import (  # noqa: E402
    DuplicateFilterPipeline,
    EnhancedValidationPipeline,
    QualityFilterPipeline,
    SourceCredibilityPipeline,
    ValidationReportPipeline,
)


@pytest.fixture
def spider():
    s = MagicMock()
    s.logger = MagicMock()
    s.name = "test_spider"
    s.crawler.stats = MagicMock()
    return s


def make_crawler(settings_dict):
    """Build a fake crawler whose .settings behaves like Scrapy Settings getters."""

    class FakeSettings:
        def __init__(self, d):
            self._d = d

        def get(self, key, default=None):
            return self._d.get(key, default)

        def getfloat(self, key, default=0.0):
            return float(self._d.get(key, default))

        def getint(self, key, default=0):
            return int(self._d.get(key, default))

        def getbool(self, key, default=False):
            return bool(self._d.get(key, default))

    return SimpleNamespace(settings=FakeSettings(settings_dict))


# --------------------------------------------------------------------------- #
# EnhancedValidationPipeline
# --------------------------------------------------------------------------- #
class TestEnhancedValidationPipeline:
    def test_from_crawler_with_domain_config(self):
        crawler = make_crawler(
            {
                "TRUSTED_DOMAINS": ["trusted.com"],
                "QUESTIONABLE_DOMAINS": ["maybe.com"],
                "BANNED_DOMAINS": ["bad.com"],
            }
        )
        pipeline = EnhancedValidationPipeline.from_crawler(crawler)
        assert pipeline.validation_pipeline is not None
        assert pipeline.stats_logged is False

    def test_from_crawler_no_domains(self):
        crawler = make_crawler({})
        pipeline = EnhancedValidationPipeline.from_crawler(crawler)
        assert pipeline.validation_pipeline is not None

    def test_process_item_valid(self, spider):
        pipeline = EnhancedValidationPipeline()
        result = SimpleNamespace(
            score=82.5,
            is_valid=True,
            issues=[],
            warnings=["minor_warning"],
            cleaned_data={"content_quality": "good", "title": "Cleaned Title"},
        )
        pipeline.validation_pipeline = MagicMock()
        pipeline.validation_pipeline.process_article.return_value = result

        item = {"url": "https://example.com/a", "title": "Raw Title"}
        out = pipeline.process_item(item, spider)

        # cleaned_data merged into item
        assert out["title"] == "Cleaned Title"
        assert out["content_quality"] == "good"
        # validation metadata attached
        assert out["validation_result"]["score"] == 82.5
        assert out["validation_result"]["is_valid"] is True
        assert out["validation_result"]["warnings"] == ["minor_warning"]
        # warning was logged
        spider.logger.warning.assert_called_once()

    def test_process_item_dropped_when_none(self, spider):
        pipeline = EnhancedValidationPipeline()
        pipeline.validation_pipeline = MagicMock()
        pipeline.validation_pipeline.process_article.return_value = None

        with pytest.raises(DropItem):
            pipeline.process_item({"url": "https://example.com/x"}, spider)
        spider.logger.info.assert_called_once()

    def test_close_spider_records_stats(self, spider):
        pipeline = EnhancedValidationPipeline()
        pipeline.validation_pipeline = MagicMock()
        pipeline.validation_pipeline.get_statistics.return_value = {
            "processed_count": 10,
            "accepted_count": 8,
            "rejected_count": 2,
            "warnings_count": 1,
            "acceptance_rate": 80.0,
            "rejection_rate": 20.0,
        }
        pipeline.close_spider(spider)
        spider.crawler.stats.set_value.assert_any_call(
            "validation_processed_count", 10
        )
        spider.crawler.stats.set_value.assert_any_call(
            "validation_accepted_count", 8
        )
        spider.crawler.stats.set_value.assert_any_call(
            "validation_acceptance_rate", 80.0
        )


# --------------------------------------------------------------------------- #
# QualityFilterPipeline
# --------------------------------------------------------------------------- #
class TestQualityFilterPipeline:
    def test_from_crawler(self):
        crawler = make_crawler(
            {"QUALITY_MIN_SCORE": 75.0, "QUALITY_MIN_CONTENT_LENGTH": 500}
        )
        pipeline = QualityFilterPipeline.from_crawler(crawler)
        assert pipeline.min_score == 75.0
        assert pipeline.min_content_length == 500

    def test_passes_quality(self, spider):
        pipeline = QualityFilterPipeline(min_score=60.0, min_content_length=200)
        item = {
            "validation_score": 90,
            "content_length": 500,
            "validation_result": {"issues": []},
            "url": "https://example.com/ok",
        }
        out = pipeline.process_item(item, spider)
        assert out is item
        assert pipeline.filtered_count == 0

    def test_drop_low_score(self, spider):
        pipeline = QualityFilterPipeline(min_score=60.0)
        with pytest.raises(DropItem):
            pipeline.process_item(
                {"validation_score": 10, "url": "https://example.com/low"}, spider
            )
        assert pipeline.filtered_count == 1

    def test_drop_short_content(self, spider):
        pipeline = QualityFilterPipeline(min_score=0.0, min_content_length=200)
        with pytest.raises(DropItem):
            pipeline.process_item(
                {
                    "validation_score": 99,
                    "content_length": 50,
                    "url": "https://example.com/short",
                },
                spider,
            )
        assert pipeline.filtered_count == 1

    def test_drop_critical_issue(self, spider):
        pipeline = QualityFilterPipeline(min_score=0.0, min_content_length=0)
        item = {
            "validation_score": 99,
            "content_length": 999,
            "validation_result": {"issues": ["banned_domain"]},
            "url": "https://example.com/banned",
        }
        with pytest.raises(DropItem):
            pipeline.process_item(item, spider)
        assert pipeline.filtered_count == 1

    def test_close_spider_sets_stats(self, spider):
        pipeline = QualityFilterPipeline()
        pipeline.filtered_count = 7
        pipeline.close_spider(spider)
        spider.crawler.stats.set_value.assert_called_once_with(
            "quality_filtered_count", 7
        )


# --------------------------------------------------------------------------- #
# SourceCredibilityPipeline
# --------------------------------------------------------------------------- #
class TestSourceCredibilityPipeline:
    def test_from_crawler(self):
        crawler = make_crawler({"BLOCK_UNRELIABLE_SOURCES": True})
        pipeline = SourceCredibilityPipeline.from_crawler(crawler)
        assert pipeline.block_unreliable is True

    def test_trusted_priority_boost(self, spider):
        pipeline = SourceCredibilityPipeline()
        item = {"source_credibility": "trusted", "url": "https://t.com"}
        out = pipeline.process_item(item, spider)
        assert out["priority"] == 10
        assert pipeline.credibility_stats["trusted"] == 1

    def test_reliable_priority_boost(self, spider):
        pipeline = SourceCredibilityPipeline()
        out = pipeline.process_item(
            {"source_credibility": "reliable", "priority": 2}, spider
        )
        assert out["priority"] == 7

    def test_questionable_warning_and_penalty(self, spider):
        pipeline = SourceCredibilityPipeline()
        item = {
            "source_credibility": "questionable",
            "validation_result": {"warnings": []},
        }
        out = pipeline.process_item(item, spider)
        assert out["priority"] == -5
        assert "source_credibility_questionable" in out["validation_result"]["warnings"]

    def test_unreliable_blocked(self, spider):
        pipeline = SourceCredibilityPipeline(block_unreliable=True)
        with pytest.raises(DropItem):
            pipeline.process_item(
                {"source_credibility": "unreliable", "url": "https://u.com"}, spider
            )
        assert pipeline.blocked_count == 1

    def test_unreliable_not_blocked_penalty(self, spider):
        pipeline = SourceCredibilityPipeline(block_unreliable=False)
        item = {
            "source_credibility": "unreliable",
            "validation_result": {"warnings": []},
        }
        out = pipeline.process_item(item, spider)
        assert out["priority"] == -10
        assert pipeline.blocked_count == 0

    def test_close_spider_records_per_level(self, spider):
        pipeline = SourceCredibilityPipeline()
        pipeline.process_item({"source_credibility": "trusted"}, spider)
        pipeline.close_spider(spider)
        spider.crawler.stats.set_value.assert_any_call("credibility_trusted_count", 1)
        spider.crawler.stats.set_value.assert_any_call("credibility_blocked_count", 0)


# --------------------------------------------------------------------------- #
# DuplicateFilterPipeline
# --------------------------------------------------------------------------- #
class TestDuplicateFilterPipeline:
    def test_unique_item_marked(self, spider):
        pipeline = DuplicateFilterPipeline()
        out = pipeline.process_item(
            {"url": "https://example.com/1", "title": "First", "content": "alpha"},
            spider,
        )
        assert out["duplicate_check"] == "unique"
        assert pipeline.duplicate_count == 0

    def test_duplicate_url_dropped(self, spider):
        pipeline = DuplicateFilterPipeline()
        pipeline.process_item(
            {"url": "https://example.com/dup", "title": "A", "content": "x"}, spider
        )
        with pytest.raises(DropItem):
            pipeline.process_item(
                {"url": "https://example.com/dup", "title": "B", "content": "y"},
                spider,
            )
        assert pipeline.duplicate_count == 1
        assert pipeline.duplicate_reasons["duplicate_url"] == 1

    def test_duplicate_content_dropped(self, spider):
        pipeline = DuplicateFilterPipeline()
        pipeline.process_item(
            {"url": "https://a.com/1", "title": "T1", "content": "same body text"},
            spider,
        )
        with pytest.raises(DropItem):
            pipeline.process_item(
                {"url": "https://b.com/2", "title": "T2", "content": "same body text"},
                spider,
            )
        assert pipeline.duplicate_reasons["duplicate_content"] == 1

    def test_close_spider_records_stats(self, spider):
        pipeline = DuplicateFilterPipeline()
        pipeline.duplicate_count = 3
        pipeline.duplicate_reasons["duplicate_url"] = 3
        pipeline.close_spider(spider)
        spider.crawler.stats.set_value.assert_any_call("duplicates_total_count", 3)
        spider.crawler.stats.set_value.assert_any_call("duplicates_duplicate_url_count", 3)


# --------------------------------------------------------------------------- #
# ValidationReportPipeline
# --------------------------------------------------------------------------- #
class TestValidationReportPipeline:
    def test_from_crawler(self):
        crawler = make_crawler({"VALIDATION_REPORT_FILE": "custom/report.json"})
        pipeline = ValidationReportPipeline.from_crawler(crawler)
        assert pipeline.report_file == "custom/report.json"

    def test_process_item_collects(self, spider):
        pipeline = ValidationReportPipeline()
        item = {
            "url": "https://example.com/a",
            "source": "SrcA",
            "validation_score": 80,
            "content_quality": "good",
            "source_credibility": "trusted",
        }
        out = pipeline.process_item(item, spider)
        assert out is item
        assert len(pipeline.articles) == 1
        assert pipeline.articles[0]["source"] == "SrcA"

    def test_close_spider_empty_warns(self, spider):
        pipeline = ValidationReportPipeline()
        pipeline.close_spider(spider)
        spider.logger.warning.assert_called_once()

    def test_close_spider_writes_report(self, spider, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pipeline = ValidationReportPipeline(report_file="data/validation_report.json")
        pipeline.process_item(
            {
                "url": "https://example.com/a",
                "source": "SrcA",
                "validation_score": 90,
                "content_quality": "good",
                "source_credibility": "trusted",
            },
            spider,
        )
        pipeline.process_item(
            {
                "url": "https://example.com/b",
                "source": "SrcB",
                "validation_score": 50,
                "content_quality": "fair",
                "source_credibility": "questionable",
            },
            spider,
        )
        pipeline.close_spider(spider)

        report_path = tmp_path / "data" / "validation_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text())
        assert report["report_metadata"]["total_articles_processed"] == 2
        stats = report["summary_statistics"]
        assert stats["average_validation_score"] == 70.0
        assert stats["min_validation_score"] == 50
        assert stats["max_validation_score"] == 90
        # SrcA scored higher -> best performing
        assert report["source_performance"]["best_performing_source"]["name"] == "SrcA"
        assert report["source_performance"]["worst_performing_source"]["name"] == "SrcB"

    def test_generate_report_empty(self, spider):
        pipeline = ValidationReportPipeline()
        report = pipeline._generate_report(spider)
        assert report == {"error": "No articles processed"}
