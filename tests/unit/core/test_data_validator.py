"""Tests for src/scraper/data_validator.py."""

import json
import os
import sys
from datetime import datetime, timedelta

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.data_validator import ScrapedDataValidator  # noqa: E402


def make_articles(n=3, source="example_com"):
    now = datetime.now()
    return [
        {
            "title": f"Article number {i} with a headline",
            "url": f"https://example.com/news/{i}",
            "content": "word " * 100,
            "source": source,
            "published_date": (now - timedelta(days=i)).isoformat(),
            "author": f"Author {i}",
            "category": "tech" if i % 2 == 0 else "news",
            "validation_score": 80 + i,
            "content_quality": "high",
        }
        for i in range(n)
    ]


@pytest.fixture
def data_dir(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "example_com_articles.json").write_text(
        json.dumps(make_articles(4))
    )
    (sources / "other_site_articles.json").write_text(
        json.dumps(make_articles(2, source="other_site"))
    )
    return str(tmp_path)


class TestValidateAllSources:
    def test_no_sources_dir(self, tmp_path):
        validator = ScrapedDataValidator(data_dir=str(tmp_path / "nope"))
        assert validator.validate_all_sources() == {"error": "No sources data found"}

    def test_validates_each_source(self, data_dir):
        validator = ScrapedDataValidator(data_dir=data_dir)
        results = validator.validate_all_sources()
        assert "example_com" in results
        assert "other_site" in results
        assert results["example_com"]["total_articles"] == 4
        summary = results["summary"]
        assert summary["total_sources_analyzed"] == 2
        assert summary["total_articles_across_sources"] == 6
        assert summary["best_performing_source"] in ("example_com", "other_site")

    def test_invalid_json_reports_error(self, tmp_path):
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "broken_articles.json").write_text("{not json")
        validator = ScrapedDataValidator(data_dir=str(tmp_path))
        results = validator.validate_all_sources()
        assert "error" in results["broken"]


class TestValidateSourceData:
    def test_empty_articles(self):
        validator = ScrapedDataValidator()
        assert validator.validate_source_data([], "x") == {
            "error": "No articles found"
        }

    def test_full_validation(self):
        validator = ScrapedDataValidator()
        result = validator.validate_source_data(make_articles(5), "example.com")
        assert result["total_articles"] == 5
        assert result["field_completeness"]["title"]["percentage"] == 100.0
        assert result["field_completeness"]["title"]["required"] is True
        assert result["url_validity"]["url_validity_percentage"] == 100.0
        assert result["url_validity"]["domain_consistency_percentage"] == 100.0
        assert result["date_validity"]["date_validity_percentage"] == 100.0
        assert result["duplicate_detection"]["url_duplicates"] == 0
        assert result["accuracy_score"] > 80

    def test_duplicates_detected(self):
        articles = make_articles(2) + make_articles(2)
        validator = ScrapedDataValidator()
        result = validator.validate_source_data(articles, "example.com")
        assert result["duplicate_detection"]["url_duplicates"] == 2
        assert result["duplicate_detection"]["title_duplicates"] == 2

    def test_empty_content_counted(self):
        articles = make_articles(2)
        articles[0]["content"] = "   "
        validator = ScrapedDataValidator()
        result = validator.validate_source_data(articles, "example.com")
        assert result["content_quality"]["empty_content_count"] == 1
        assert result["content_quality"]["empty_content_percentage"] == 50.0

    def test_future_and_invalid_dates(self):
        articles = make_articles(3)
        articles[0]["published_date"] = (
            datetime.now() + timedelta(days=10)
        ).isoformat()
        articles[1]["published_date"] = "not-a-date"
        articles[2]["published_date"] = "2024-01-15"  # plain date format
        validator = ScrapedDataValidator()
        result = validator.validate_source_data(articles, "example.com")
        assert result["date_validity"]["future_dates"] == 1
        assert result["date_validity"]["valid_dates"] == 2

    def test_unknown_authors(self):
        articles = make_articles(3)
        articles[0]["author"] = ""
        articles[1]["author"] = "Unknown"
        validator = ScrapedDataValidator()
        result = validator.validate_source_data(articles, "example.com")
        assert result["author_analysis"]["unknown_author_count"] == 2

    def test_category_distribution(self):
        validator = ScrapedDataValidator()
        result = validator.validate_source_data(make_articles(4), "example.com")
        assert result["category_distribution"]["tech"] == 2
        assert result["category_distribution"]["news"] == 2

    def test_validation_scores(self):
        validator = ScrapedDataValidator()
        result = validator.validate_source_data(make_articles(3), "example.com")
        scores = result["validation_scores"]
        assert scores["min_validation_score"] == 80
        assert scores["max_validation_score"] == 82
        assert scores["quality_distribution"]["high"] == 3


class TestSaveValidationReport:
    def test_save_report(self, data_dir, capsys):
        validator = ScrapedDataValidator(data_dir=data_dir)
        results = validator.save_validation_report()
        report_path = os.path.join(data_dir, "validation_report.json")
        assert os.path.exists(report_path)
        saved = json.loads(open(report_path).read())
        assert saved["summary"]["total_sources_analyzed"] == 2
        assert "summary" in results

    def test_save_report_custom_path(self, data_dir, tmp_path):
        out = str(tmp_path / "custom_report.json")
        validator = ScrapedDataValidator(data_dir=data_dir)
        validator.save_validation_report(output_path=out)
        assert os.path.exists(out)
