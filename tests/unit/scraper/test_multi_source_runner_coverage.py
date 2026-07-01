"""Coverage-focused tests for src/scraper/multi_source_runner.py.

Scrapy's CrawlerProcess and get_project_settings are patched so no real
crawl runs. Covers run_spider (valid + invalid), run_all_spiders
(exclude / include_only / empty subset), generate_report (missing dir,
populated dir, malformed file), and the argparse-driven main() entrypoint.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("scrapy")

import src.scraper.multi_source_runner as msr  # noqa: E402


@pytest.fixture
def runner():
    """MultiSourceRunner with a stubbed Scrapy settings object."""
    with patch.object(msr, "get_project_settings", return_value=MagicMock()):
        return msr.MultiSourceRunner()


class TestRunSpider:
    def test_run_known_spider(self, runner):
        proc = MagicMock()
        with patch.object(msr, "CrawlerProcess", return_value=proc) as cp:
            runner.run_spider("cnn")
        cp.assert_called_once_with(runner.settings)
        proc.crawl.assert_called_once_with(runner.spiders["cnn"])
        proc.start.assert_called_once()

    def test_run_unknown_spider_raises(self, runner):
        with pytest.raises(ValueError) as exc:
            runner.run_spider("does_not_exist")
        assert "does_not_exist" in str(exc.value)
        assert "Available" in str(exc.value)


class TestRunAllSpiders:
    def test_run_all_default(self, runner, capsys):
        proc = MagicMock()
        with patch.object(msr, "CrawlerProcess", return_value=proc):
            runner.run_all_spiders()
        # Every registered spider is scheduled.
        assert proc.crawl.call_count == len(runner.spiders)
        proc.start.assert_called_once()
        assert "Running spiders" in capsys.readouterr().out

    def test_run_all_with_exclude(self, runner):
        proc = MagicMock()
        with patch.object(msr, "CrawlerProcess", return_value=proc):
            runner.run_all_spiders(exclude=["cnn", "bbc"])
        assert proc.crawl.call_count == len(runner.spiders) - 2

    def test_run_all_include_only(self, runner):
        proc = MagicMock()
        with patch.object(msr, "CrawlerProcess", return_value=proc):
            runner.run_all_spiders(include_only=["cnn", "npr"])
        assert proc.crawl.call_count == 2

    def test_run_all_empty_subset_prints_and_returns(self, runner, capsys):
        with patch.object(msr, "CrawlerProcess") as cp:
            runner.run_all_spiders(include_only=["nonexistent"])
        # No spiders match -> early return, no CrawlerProcess constructed.
        cp.assert_not_called()
        assert "No spiders to run" in capsys.readouterr().out


class TestGenerateReport:
    def test_no_sources_dir(self, runner, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        result = runner.generate_report()
        assert result is None
        assert "No data found" in capsys.readouterr().out

    def test_report_with_articles(self, runner, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        sources_dir = tmp_path / "data" / "sources"
        sources_dir.mkdir(parents=True)

        cnn_articles = [
            {
                "content": "abc",
                "validation_score": 90,
                "category": "Technology",
                "content_quality": "high",
            },
            {
                "content": "abcdef",
                "validation_score": 40,
                "category": "Politics",
                "content_quality": "low",
            },
        ]
        (sources_dir / "cnn_articles.json").write_text(json.dumps(cnn_articles))
        (sources_dir / "bbc_articles.json").write_text(
            json.dumps([{"content": "x" * 10, "content_quality": "medium"}])
        )
        # Non-matching file is ignored.
        (sources_dir / "notes.txt").write_text("ignore me")

        report = runner.generate_report()

        assert report["total_articles"] == 3
        assert report["quality_distribution"]["high"] == 1
        assert report["quality_distribution"]["medium"] == 1
        assert report["quality_distribution"]["low"] == 1
        assert "cnn" in report["sources"]
        assert report["sources"]["cnn"]["article_count"] == 2
        assert report["sources"]["cnn"]["avg_validation_score"] == 65.0
        assert set(report["sources"]["cnn"]["categories"]) == {"Technology", "Politics"}

        # Report is persisted to disk.
        saved = json.loads((tmp_path / "data" / "scraping_report.json").read_text())
        assert saved["total_articles"] == 3

        out = capsys.readouterr().out
        assert "Report generated" in out
        assert "Total articles scraped: 3" in out

    def test_report_handles_malformed_file(self, runner, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        sources_dir = tmp_path / "data" / "sources"
        sources_dir.mkdir(parents=True)
        (sources_dir / "broken_articles.json").write_text("{not json")
        (sources_dir / "good_articles.json").write_text(
            json.dumps([{"content": "ok", "content_quality": "high", "validation_score": 80}])
        )

        report = runner.generate_report()

        # Malformed file is caught and reported; the good file still counts.
        assert report["total_articles"] == 1
        assert "good" in report["sources"]
        assert "broken" not in report["sources"]
        assert "Error processing" in capsys.readouterr().out


class TestMain:
    def _patch_runner(self, monkeypatch, runner_mock):
        monkeypatch.setattr(msr, "MultiSourceRunner", MagicMock(return_value=runner_mock))

    def test_list(self, monkeypatch, capsys):
        runner_mock = MagicMock()
        runner_mock.spiders = {"cnn": object, "bbc": object}
        self._patch_runner(monkeypatch, runner_mock)
        monkeypatch.setattr(sys, "argv", ["multi_source_runner.py", "--list"])
        msr.main()
        out = capsys.readouterr().out
        assert "Available spiders" in out
        assert "cnn" in out

    def test_report(self, monkeypatch):
        runner_mock = MagicMock()
        self._patch_runner(monkeypatch, runner_mock)
        monkeypatch.setattr(sys, "argv", ["multi_source_runner.py", "--report"])
        msr.main()
        runner_mock.generate_report.assert_called_once()

    def test_single_spider(self, monkeypatch):
        runner_mock = MagicMock()
        self._patch_runner(monkeypatch, runner_mock)
        monkeypatch.setattr(sys, "argv", ["multi_source_runner.py", "--spider", "cnn"])
        msr.main()
        runner_mock.run_spider.assert_called_once_with("cnn")

    def test_all_with_exclude(self, monkeypatch):
        runner_mock = MagicMock()
        self._patch_runner(monkeypatch, runner_mock)
        monkeypatch.setattr(
            sys, "argv", ["multi_source_runner.py", "--all", "--exclude", "cnn", "bbc"]
        )
        msr.main()
        runner_mock.run_all_spiders.assert_called_once_with(
            exclude=["cnn", "bbc"], include_only=None
        )

    def test_all_with_include(self, monkeypatch):
        runner_mock = MagicMock()
        self._patch_runner(monkeypatch, runner_mock)
        monkeypatch.setattr(
            sys, "argv", ["multi_source_runner.py", "--all", "--include", "npr"]
        )
        msr.main()
        runner_mock.run_all_spiders.assert_called_once_with(
            exclude=None, include_only=["npr"]
        )

    def test_no_args_prints_help_hint(self, monkeypatch, capsys):
        runner_mock = MagicMock()
        self._patch_runner(monkeypatch, runner_mock)
        monkeypatch.setattr(sys, "argv", ["multi_source_runner.py"])
        msr.main()
        assert "Use --help" in capsys.readouterr().out
        runner_mock.run_spider.assert_not_called()
        runner_mock.run_all_spiders.assert_not_called()
