"""Orchestration tests for src/scraper/async_scraper_runner.py."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiohttp")

import scraper.async_scraper_runner as runner_mod  # noqa: E402
from scraper.async_scraper_runner import AsyncScraperRunner  # noqa: E402


STATS = {
    "elapsed_time": 1.0, "articles_per_second": 2.0, "success_rate": 100.0,
    "successful_requests": 2, "failed_requests": 0, "avg_response_time": 0.1,
    "avg_memory_mb": 10.0, "avg_cpu_percent": 5.0, "total_articles": 2,
    "source_stats": {"bbc": {"articles": 2, "errors": 0}},
}


def _fake_engine_cls():
    scraper = MagicMock()
    scraper.scrape_sources_async = AsyncMock(return_value=[])
    scraper.save_articles = AsyncMock()
    scraper.get_performance_stats = MagicMock(return_value=STATS)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=scraper)
    ctx.__aexit__ = AsyncMock(return_value=False)

    cls = MagicMock(return_value=ctx)
    cls._scraper = scraper
    return cls


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return AsyncScraperRunner()


class TestRunScraper:
    @pytest.mark.asyncio
    async def test_run_scraper_no_monitoring(self, runner, tmp_path):
        runner.config["performance_monitoring"] = False
        runner.config["output_dir"] = str(tmp_path / "out")
        fake = _fake_engine_cls()
        with patch.object(runner_mod, "AsyncNewsScraperEngine", fake):
            articles = await runner.run_scraper([MagicMock(name="src")])
        assert articles == []
        fake._scraper.scrape_sources_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_scraper_test_mode_limits_sources(self, runner, tmp_path):
        runner.config["performance_monitoring"] = False
        runner.config["output_dir"] = str(tmp_path / "out")
        sources = [MagicMock() for _ in range(5)]
        fake = _fake_engine_cls()
        with patch.object(runner_mod, "AsyncNewsScraperEngine", fake):
            await runner.run_scraper(sources, test_mode=True)
        passed = fake._scraper.scrape_sources_async.call_args[0][0]
        assert len(passed) == 2


class TestMonitorPerformance:
    @pytest.mark.asyncio
    async def test_monitor_cancels_cleanly(self, runner):
        scraper = MagicMock()
        scraper.get_performance_stats = MagicMock(return_value=STATS)
        with patch("asyncio.sleep", AsyncMock(side_effect=__import__("asyncio").CancelledError)):
            # CancelledError is caught internally -> returns without raising
            await runner.monitor_performance(scraper)


class TestMain:
    def test_main_no_sources(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "--sources", "DoesNotExist"])
        assert runner_mod.main() == 1

    def test_main_success(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["prog", "--test", "--output", str(tmp_path)])
        with patch.object(AsyncScraperRunner, "run_scraper", AsyncMock(return_value=[1, 2])):
            assert runner_mod.main() == 0

    def test_main_handles_exception(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["prog"])
        with patch.object(AsyncScraperRunner, "run_scraper",
                          AsyncMock(side_effect=RuntimeError("boom"))):
            assert runner_mod.main() == 1
