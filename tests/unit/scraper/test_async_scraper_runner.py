"""Tests for src/scraper/async_scraper_runner.py."""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiohttp")

from scraper.async_scraper_runner import AsyncScraperRunner  # noqa: E402


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # setup_logging writes async_scraper.log to cwd
    return AsyncScraperRunner()


class TestLoadConfig:
    def test_defaults(self, runner):
        assert runner.config["max_concurrent"] == 20
        assert runner.config["headless"] is True
        assert runner.config["timeout"] == 30

    def test_from_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"max_concurrent": 5, "custom": "x"}))
        r = AsyncScraperRunner(config_path=str(cfg))
        assert r.config["max_concurrent"] == 5  # overridden
        assert r.config["custom"] == "x"  # merged
        assert r.config["headless"] is True  # default kept

    def test_missing_file_uses_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        r = AsyncScraperRunner(config_path=str(tmp_path / "nope.json"))
        assert r.config["max_concurrent"] == 20


class TestGetSources:
    def test_default_sources(self, runner):
        sources = runner.get_sources_to_scrape()
        assert isinstance(sources, list)
        assert len(sources) > 0

    def test_configured_sources(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "sources": [
                {"name": "TestSrc", "base_url": "https://test.com",
                 "article_selectors": {}, "link_patterns": ["/article/"]},
            ]
        }))
        r = AsyncScraperRunner(config_path=str(cfg))
        sources = r.get_sources_to_scrape()
        assert any(s.name == "TestSrc" for s in sources)

    def test_filter(self, runner):
        all_sources = runner.get_sources_to_scrape()
        if len(all_sources) >= 1:
            target = all_sources[0].name
            filtered = runner.get_sources_to_scrape(source_filter=target)
            assert all(s.name == target for s in filtered)


class TestSaveResults:
    @pytest.mark.asyncio
    async def test_save_results(self, runner, tmp_path):
        runner.config["output_dir"] = str(tmp_path / "out")
        scraper = MagicMock()
        scraper.save_articles = AsyncMock()
        scraper.get_performance_stats = MagicMock(return_value={
            "elapsed_time": 1.0, "articles_per_second": 2.0, "success_rate": 100.0,
            "successful_requests": 5, "failed_requests": 0, "avg_response_time": 0.3,
            "avg_memory_mb": 100.0, "avg_cpu_percent": 10.0, "source_stats": {},
        })
        await runner.save_results(scraper, [])
        scraper.save_articles.assert_awaited_once()
        # stats file written
        out = tmp_path / "out"
        assert any(p.name.startswith("performance_stats_") for p in out.iterdir())


class TestPrintSummary:
    def test_print_summary(self, runner, capsys):
        stats = {
            "elapsed_time": 2.5, "articles_per_second": 4.0, "success_rate": 95.0,
            "successful_requests": 19, "failed_requests": 1, "avg_response_time": 0.5,
            "avg_memory_mb": 150.0, "avg_cpu_percent": 20.0,
            "source_stats": {"BBC": {"articles": 10, "errors": 1}},
        }
        articles = [MagicMock(content_quality="high"), MagicMock(content_quality="low")]
        runner.print_summary(articles, stats)
        out = capsys.readouterr().out
        assert "PERFORMANCE SUMMARY" in out
        assert "BBC" in out

    def test_print_summary_empty(self, runner, capsys):
        stats = {
            "elapsed_time": 0.0, "articles_per_second": 0.0, "success_rate": 0.0,
            "successful_requests": 0, "failed_requests": 0, "avg_response_time": 0.0,
            "avg_memory_mb": 0.0, "avg_cpu_percent": 0.0, "source_stats": {},
        }
        runner.print_summary([], stats)
        assert "Total Articles: 0" in capsys.readouterr().out
