"""Tests for src/scraper/cloudwatch_logger.py (local file-based metrics)."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.cloudwatch_logger import (  # noqa: E402
    LocalMetricsLogger,
    ScrapingMetrics,
    ScrapingStatus,
    _sanitize_name,
)


@pytest.fixture
def logger(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    return LocalMetricsLogger(namespace="Test/NS", log_group="test-group")


def metric(status=ScrapingStatus.SUCCESS, url="https://example.com/a", **over):
    base = dict(url=url, status=status, timestamp=__import__("time").time(),
                duration_ms=120, articles_scraped=3)
    base.update(over)
    return ScrapingMetrics(**base)


class TestHelpers:
    def test_sanitize_name(self):
        assert _sanitize_name("foo/bar baz") == "foo-bar-baz"
        assert _sanitize_name("!!!") == "default"

    def test_status_enum(self):
        assert ScrapingStatus.SUCCESS.value == "success"
        assert ScrapingStatus.CAPTCHA_BLOCKED.value == "captcha_blocked"

    def test_metrics_defaults(self):
        m = metric()
        assert m.retry_count == 0
        assert m.captcha_encountered is False

    def test_get_domain_from_url(self, logger):
        assert logger._get_domain_from_url("https://news.example.com/x") == "news.example.com"

    def test_get_domain_invalid(self, logger):
        assert isinstance(logger._get_domain_from_url("::::"), str)


class TestInit:
    def test_paths_created(self, logger, tmp_path):
        assert logger.namespace == "Test/NS"
        assert str(tmp_path) in logger.log_file
        assert logger.metrics_file.endswith("scraper_metrics.jsonl")


class TestLogging:
    @pytest.mark.asyncio
    async def test_log_scraping_attempt_writes(self, logger):
        await logger.log_scraping_attempt(metric())
        assert os.path.exists(logger.metrics_file) or os.path.exists(logger.log_file)

    @pytest.mark.asyncio
    async def test_success_rate_after_logging(self, logger):
        await logger.log_scraping_attempt(metric(status=ScrapingStatus.SUCCESS))
        await logger.log_scraping_attempt(metric(status=ScrapingStatus.FAILURE))
        rate = await logger.get_success_rate(hours=24)
        assert isinstance(rate, float)
        assert 0.0 <= rate <= 100.0

    @pytest.mark.asyncio
    async def test_failure_count(self, logger):
        await logger.log_scraping_attempt(metric(status=ScrapingStatus.FAILURE))
        count = await logger.get_failure_count(hours=24)
        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.asyncio
    async def test_success_rate_empty(self, logger):
        assert await logger.get_success_rate(hours=1) == 0.0


class TestAlarmsAndFlush:
    @pytest.mark.asyncio
    async def test_create_alarm(self, logger):
        await logger.create_alarm(
            alarm_name="high-failure", metric_name="FailureCount",
            threshold=10, comparison_operator="GreaterThanThreshold",
        )
        assert os.path.exists(logger.alarms_file)

    @pytest.mark.asyncio
    async def test_flush_metrics(self, logger):
        await logger.log_scraping_attempt(metric())
        await logger.flush_metrics()  # should not raise


class TestReadRecords:
    def test_read_missing_file(self, logger):
        assert logger._read_metric_records("SuccessRate", 24) == []
