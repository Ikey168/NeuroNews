"""Coverage-focused tests for src/scraper/data_validator.py.

Targets branches the existing ``test_data_validator.py`` leaves uncovered:

* ``_check_url_validity`` swallowing a urlparse exception.
* ``_analyze_validation_scores`` with an empty article list (zeroed stats).
* ``_calculate_accuracy_score`` mid-tier scoring bands for empty-content
  percentage and average word count.
* ``_generate_summary`` returning an error dict when there are no sources.
* ``save_validation_report`` writing to its default path.
* ``main`` printing the summary + per-source results.

Pure logic; no cloud mocking required.
"""

import json
import os
import sys
from unittest.mock import patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper import data_validator as dv_mod  # noqa: E402
from scraper.data_validator import ScrapedDataValidator  # noqa: E402


def make_article(**over):
    base = dict(
        title="A reasonable article title here",
        url="https://bbc.com/news/article-1",
        content="word " * 100,
        source="bbc",
        published_date="2026-06-01",
        author="Alice",
        category="Technology",
        validation_score=90,
        content_quality="high",
    )
    base.update(over)
    return base


@pytest.fixture
def validator():
    return ScrapedDataValidator(data_dir="data")


class TestUrlValidityException:
    def test_urlparse_exception_swallowed(self, validator, monkeypatch):
        # Force urlparse to raise so the ``except BaseException: pass`` runs.
        monkeypatch.setattr(
            dv_mod,
            "urlparse",
            lambda url: (_ for _ in ()).throw(RuntimeError("bad")),
        )
        out = validator._check_url_validity([make_article()], "bbc")
        # No URL counted as valid because parsing raised.
        assert out["valid_urls"] == 0
        assert out["domain_matches"] == 0


class TestValidationScoresEmpty:
    def test_empty_articles_zeroed(self, validator):
        out = validator._analyze_validation_scores([])
        assert out["average_validation_score"] == 0
        assert out["min_validation_score"] == 0
        assert out["max_validation_score"] == 0
        assert out["quality_distribution"] == {}


class TestAccuracyScoreBands:
    def _score(self, validator, articles):
        validations = validator.validate_source_data(articles, "bbc")
        return validations["accuracy_score"]

    def test_mid_empty_content_band(self, validator):
        # ~33% empty content -> hits the "< 50" band (5 points), and short
        # word counts fall between the 20/50 thresholds.
        articles = [
            make_article(content="   "),  # empty
            make_article(content="word " * 30),  # 30 words -> ">20" band (5 pts)
            make_article(content="word " * 30),
        ]
        score = self._score(validator, articles)
        assert 0 < score < 100

    def test_moderate_empty_between_10_and_25(self, validator):
        # 5 articles, 1 empty -> 20% empty -> "< 25" band (10 points).
        articles = [make_article(content="word " * 60) for _ in range(4)]
        articles.append(make_article(content=""))
        cq = validator._check_content_quality(articles)
        assert 10 <= cq["empty_content_percentage"] < 25
        score = self._score(validator, articles)
        assert score > 0


class TestSummaryNoSources:
    def test_generate_summary_no_sources(self, validator):
        # Only a "summary" key -> no real sources -> error dict.
        out = validator._generate_summary({"summary": {}})
        assert out == {"error": "No valid sources found"}


class TestSaveDefaultPath:
    def test_save_uses_default_path(self, tmp_path):
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "bbc_articles.json").write_text(json.dumps([make_article()]))
        v = ScrapedDataValidator(data_dir=str(tmp_path))
        # No output_path -> defaults to <data_dir>/validation_report.json.
        results = v.save_validation_report()
        default_path = tmp_path / "validation_report.json"
        assert default_path.exists()
        saved = json.loads(default_path.read_text())
        assert "bbc" in saved
        assert results["summary"]["total_sources_analyzed"] == 1


class TestMain:
    def test_main_prints_summary_and_sources(self, tmp_path, monkeypatch, capsys):
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "bbc_articles.json").write_text(json.dumps([make_article()]))
        (sources / "cnn_articles.json").write_text(
            json.dumps([make_article(url="https://cnn.com/x", source="cnn")])
        )
        monkeypatch.chdir(tmp_path)

        # main() constructs ScrapedDataValidator() with default data_dir="data";
        # patch so it points at our populated tmp directory.
        monkeypatch.setattr(
            dv_mod,
            "ScrapedDataValidator",
            lambda *a, **k: ScrapedDataValidator(data_dir=str(tmp_path)),
        )
        dv_mod.main()
        out = capsys.readouterr().out
        assert "VALIDATION SUMMARY" in out
        assert "Sources analyzed: 2" in out
        assert "PER-SOURCE RESULTS" in out
        assert "BBC" in out or "CNN" in out
