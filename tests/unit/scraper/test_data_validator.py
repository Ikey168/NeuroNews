"""Tests for src/scraper/data_validator.py (pure logic)."""

import json
import os
import sys
from datetime import datetime, timedelta

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.data_validator import ScrapedDataValidator  # noqa: E402


def make_article(**over):
    base = dict(
        title="A decent title for the article",
        url="https://bbc.com/news/article-1",
        content="word " * 100,
        source="bbc",
        published_date=datetime.now().strftime("%Y-%m-%d"),
        author="Alice",
        category="Technology",
        scraped_date="2026-01-01",
        validation_score=90,
        content_quality="high",
    )
    base.update(over)
    return base


@pytest.fixture
def validator():
    return ScrapedDataValidator(data_dir="data")


class TestFieldCompleteness:
    def test_all_filled(self, validator):
        out = validator._check_field_completeness([make_article()])
        assert out["title"]["filled"] == 1
        assert out["title"]["percentage"] == 100.0
        assert out["title"]["required"] is True
        assert out["author"]["required"] is False

    def test_missing_fields(self, validator):
        out = validator._check_field_completeness([make_article(title="", author="")])
        assert out["title"]["filled"] == 0
        assert out["title"]["percentage"] == 0.0


class TestUrlValidity:
    def test_valid_and_domain_match(self, validator):
        out = validator._check_url_validity([make_article()], "bbc")
        assert out["valid_urls"] == 1
        assert out["url_validity_percentage"] == 100.0
        assert out["domain_matches"] == 1

    def test_invalid_url(self, validator):
        out = validator._check_url_validity([make_article(url="not-a-url")], "bbc")
        assert out["valid_urls"] == 0

    def test_empty_url(self, validator):
        out = validator._check_url_validity([make_article(url="")], "bbc")
        assert out["valid_urls"] == 0


class TestDateValidity:
    def test_recent_date(self, validator):
        out = validator._check_date_validity([make_article()])
        assert out["valid_dates"] == 1
        assert out["recent_articles"] == 1
        assert out["future_dates"] == 0

    def test_iso_date(self, validator):
        out = validator._check_date_validity(
            [make_article(published_date="2026-06-01T12:00:00Z")]
        )
        assert out["valid_dates"] == 1

    def test_future_date(self, validator):
        future = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        out = validator._check_date_validity([make_article(published_date=future)])
        assert out["future_dates"] == 1

    def test_invalid_date(self, validator):
        out = validator._check_date_validity([make_article(published_date="garbage")])
        assert out["valid_dates"] == 0


class TestContentQuality:
    def test_normal_content(self, validator):
        out = validator._check_content_quality([make_article()])
        assert out["empty_content_count"] == 0
        assert out["average_word_count"] == 100
        assert out["max_content_length"] > 0

    def test_empty_content(self, validator):
        out = validator._check_content_quality([make_article(content="   ")])
        assert out["empty_content_count"] == 1
        assert out["average_content_length"] == 0


class TestDuplicates:
    def test_no_duplicates(self, validator):
        arts = [make_article(url="https://x.com/1", title="One"),
                make_article(url="https://x.com/2", title="Two")]
        out = validator._check_duplicates(arts)
        assert out["url_duplicates"] == 0
        assert out["title_duplicates"] == 0
        assert out["uniqueness_percentage"] == 100.0

    def test_url_duplicate(self, validator):
        arts = [make_article(url="https://x.com/1", title="One"),
                make_article(url="https://x.com/1", title="Two")]
        out = validator._check_duplicates(arts)
        assert out["url_duplicates"] == 1


class TestCategoriesAndAuthors:
    def test_categories(self, validator):
        arts = [make_article(category="Tech"), make_article(category="Tech"),
                make_article(category="Sports")]
        out = validator._analyze_categories(arts)
        assert out["Tech"] == 2
        assert out["Sports"] == 1

    def test_authors(self, validator):
        arts = [make_article(author="Alice"), make_article(author=""),
                make_article(author="unknown")]
        out = validator._analyze_authors(arts)
        assert out["unknown_author_count"] == 2
        assert "Alice" in out["top_authors"]


class TestValidationScores:
    def test_scores(self, validator):
        arts = [make_article(validation_score=80, content_quality="high"),
                make_article(validation_score=40, content_quality="low")]
        out = validator._analyze_validation_scores(arts)
        assert out["average_validation_score"] == 60
        assert out["min_validation_score"] == 40
        assert out["max_validation_score"] == 80
        assert out["quality_distribution"]["high"] == 1


class TestSourceValidation:
    def test_validate_source_data(self, validator):
        out = validator.validate_source_data([make_article()], "bbc")
        assert out["total_articles"] == 1
        assert 0 <= out["accuracy_score"] <= 100

    def test_empty_source(self, validator):
        out = validator.validate_source_data([], "bbc")
        assert "error" in out

    def test_high_quality_high_score(self, validator):
        arts = [make_article() for _ in range(3)]
        out = validator.validate_source_data(arts, "bbc")
        assert out["accuracy_score"] > 70


class TestAllSourcesAndReport:
    def test_no_sources_dir(self, tmp_path):
        v = ScrapedDataValidator(data_dir=str(tmp_path))
        assert "error" in v.validate_all_sources()

    def test_validate_and_save(self, tmp_path):
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "bbc_articles.json").write_text(json.dumps([make_article()]))
        v = ScrapedDataValidator(data_dir=str(tmp_path))
        results = v.validate_all_sources()
        assert "bbc" in results
        assert "summary" in results
        assert results["summary"]["total_sources_analyzed"] == 1

        out_path = tmp_path / "report.json"
        v.save_validation_report(str(out_path))
        assert out_path.exists()

    def test_bad_json_file(self, tmp_path):
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "bad_articles.json").write_text("{not valid json")
        v = ScrapedDataValidator(data_dir=str(tmp_path))
        results = v.validate_all_sources()
        assert "error" in results["bad"]
