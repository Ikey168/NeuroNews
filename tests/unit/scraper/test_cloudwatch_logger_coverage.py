"""Coverage-focused tests for src/scraper/cloudwatch_logger.py.

Targets the branches the existing ``test_cloudwatch_logger.py`` leaves uncovered:

* ``_ensure_log_group_exists`` when the log file already exists, and its OSError
  handling path.
* The batch-metrics flush triggered when the buffer reaches ``buffer_size``.
* ``_send_log_entry`` / ``_send_cloudwatch_metrics`` / ``_send_batch_metrics`` /
  ``create_alarm`` error branches (via injected failures).
* Optional metric emission (retry_count, captcha, ip_blocked) inside
  ``_send_cloudwatch_metrics``.
* ``_get_domain_from_url`` exception fallback.
* ``get_success_rate`` returning an average over datapoints and its error path;
  ``get_failure_count`` counting "failure"-status attempts.

Pure local-file implementation; no cloud mocking needed.
"""

import json
import os
import sys
import time

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.cloudwatch_logger import (  # noqa: E402
    LocalMetricsLogger,
    ScrapingMetrics,
    ScrapingStatus,
)


@pytest.fixture
def logger(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    return LocalMetricsLogger(namespace="Cov/NS", log_group="cov-group")


def metric(status=ScrapingStatus.SUCCESS, url="https://cov.example.com/a", **over):
    base = dict(url=url, status=status, timestamp=time.time(), duration_ms=100,
                articles_scraped=2)
    base.update(over)
    return ScrapingMetrics(**base)


class TestEnsureLogGroup:
    def test_existing_file_debug_branch(self, tmp_path, monkeypatch):
        # Pre-create the log file so the "already exists" branch runs.
        monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
        (tmp_path / "cov-group.log").write_text("")
        lg = LocalMetricsLogger(log_group="cov-group")
        assert os.path.exists(lg.log_file)
        # Re-invoke explicitly to be sure the existing-file branch is hit.
        lg._ensure_log_group_exists()
        assert os.path.exists(lg.log_file)

    def test_oserror_is_handled(self, logger, monkeypatch):
        def boom(*a, **k):
            raise OSError("no space left")

        monkeypatch.setattr("scraper.cloudwatch_logger.os.makedirs", boom)
        # Should log an error and not raise.
        logger._ensure_log_group_exists()


class TestGetDomain:
    def test_exception_fallback(self, logger, monkeypatch):
        import scraper.cloudwatch_logger as mod

        def boom(url):
            raise ValueError("bad")

        monkeypatch.setattr(mod, "urlparse", boom, raising=False)
        # urlparse is imported inside the function; patch the source module.
        monkeypatch.setattr(
            "urllib.parse.urlparse", lambda url: (_ for _ in ()).throw(RuntimeError())
        )
        assert logger._get_domain_from_url("https://x.com") == "unknown"


class TestOptionalMetrics:
    @pytest.mark.asyncio
    async def test_retry_captcha_ip_blocked_metrics(self, logger):
        m = metric(
            status=ScrapingStatus.IP_BLOCKED,
            retry_count=3,
            captcha_encountered=True,
            ip_blocked=True,
            articles_scraped=5,
        )
        await logger._send_cloudwatch_metrics(m)
        lines = [
            json.loads(x)
            for x in open(logger.metrics_file).read().splitlines()
            if x.strip()
        ]
        names = {rec["MetricName"] for rec in lines}
        assert "RetryCount" in names
        assert "CaptchaEncounters" in names
        assert "IPBlocks" in names
        assert "ArticlesScraped" in names

    @pytest.mark.asyncio
    async def test_metrics_error_branch(self, logger, monkeypatch):
        def boom(records):
            raise OSError("disk error")

        monkeypatch.setattr(logger, "_write_metric_records", boom)
        # Error is caught + logged, does not propagate.
        await logger._send_cloudwatch_metrics(metric())


class TestSendLogEntryError:
    @pytest.mark.asyncio
    async def test_log_entry_error_branch(self, logger, monkeypatch):
        # A NaN timestamp makes datetime.fromtimestamp raise a ValueError,
        # which is one of the exception types the method catches.
        bad = metric(timestamp=float("nan"))
        # Should be caught + logged, not raised.
        await logger._send_log_entry(bad)


class TestBatchFlush:
    @pytest.mark.asyncio
    async def test_buffer_full_triggers_batch(self, logger):
        logger.buffer_size = 3
        for _ in range(3):
            await logger.log_scraping_attempt(metric())
        # Buffer is cleared after the batch flush.
        assert logger.metrics_buffer == []
        # SuccessRate is only written by the batch aggregation.
        content = open(logger.metrics_file).read()
        assert "SuccessRate" in content

    @pytest.mark.asyncio
    async def test_batch_error_branch(self, logger, monkeypatch):
        logger.metrics_buffer.append(metric())

        def boom(records):
            raise ValueError("serialize fail")

        monkeypatch.setattr(logger, "_write_metric_records", boom)
        await logger._send_batch_metrics()  # caught, no raise


class TestSuccessRateAndFailureCount:
    @pytest.mark.asyncio
    async def test_success_rate_average(self, logger):
        logger._write_metric_records(
            [
                {"MetricName": "SuccessRate", "Value": 80,
                 "Timestamp": __import__("datetime").datetime.now(
                     tz=__import__("datetime").timezone.utc)},
                {"MetricName": "SuccessRate", "Value": 100,
                 "Timestamp": __import__("datetime").datetime.now(
                     tz=__import__("datetime").timezone.utc)},
            ]
        )
        rate = await logger.get_success_rate(hours=24)
        assert rate == pytest.approx(90.0)

    @pytest.mark.asyncio
    async def test_success_rate_error_branch(self, logger, monkeypatch):
        def boom(name, hours):
            raise OSError("read fail")

        monkeypatch.setattr(logger, "_read_metric_records", boom)
        assert await logger.get_success_rate(hours=1) == 0.0

    @pytest.mark.asyncio
    async def test_failure_count_counts_failures(self, logger):
        await logger._send_cloudwatch_metrics(metric(status=ScrapingStatus.FAILURE))
        await logger._send_cloudwatch_metrics(metric(status=ScrapingStatus.SUCCESS))
        count = await logger.get_failure_count(hours=24)
        assert count == 1

    @pytest.mark.asyncio
    async def test_failure_count_error_branch(self, logger, monkeypatch):
        def boom(name, hours):
            raise OSError("read fail")

        monkeypatch.setattr(logger, "_read_metric_records", boom)
        assert await logger.get_failure_count(hours=1) == 0


class TestCreateLogFileAndFlush:
    def test_created_log_file_info_branch(self, tmp_path, monkeypatch):
        # Fresh directory with no pre-existing log file -> the "Created local
        # log file" branch runs during __init__.
        target = tmp_path / "brandnew"
        monkeypatch.setenv("NEURONEWS_LOG_DIR", str(target))
        lg = LocalMetricsLogger(log_group="created-group")
        assert os.path.exists(lg.log_file)

    @pytest.mark.asyncio
    async def test_flush_writes_and_clears(self, logger):
        logger.metrics_buffer.append(metric())
        await logger.flush_metrics()
        assert logger.metrics_buffer == []
        assert "SuccessRate" in open(logger.metrics_file).read()

    @pytest.mark.asyncio
    async def test_create_alarm_success_writes_record(self, logger):
        await logger.create_alarm(
            alarm_name="cov-alarm", metric_name="Cov", threshold=5.0,
            comparison_operator="LessThanThreshold",
        )
        recs = [
            json.loads(x)
            for x in open(logger.alarms_file).read().splitlines()
            if x.strip()
        ]
        assert recs[-1]["AlarmName"] == "cov-alarm"
        assert recs[-1]["ComparisonOperator"] == "LessThanThreshold"


class TestReadMetricRecordsEdgeCases:
    def test_blank_bad_json_and_bad_timestamp_lines(self, logger):
        import datetime as _dt

        good_ts = _dt.datetime.now(tz=_dt.timezone.utc).isoformat()
        with open(logger.metrics_file, "w") as f:
            f.write("\n")  # blank line -> skipped (378)
            f.write("{not valid json\n")  # bad JSON -> ValueError skip (381-382)
            f.write(
                json.dumps({"MetricName": "SuccessRate", "Value": 50,
                            "Timestamp": "not-a-date"}) + "\n"
            )  # bad timestamp -> TypeError/ValueError skip (388-389)
            f.write(
                json.dumps({"MetricName": "Other", "Value": 1,
                            "Timestamp": good_ts}) + "\n"
            )  # wrong metric name -> filtered out
            f.write(
                json.dumps({"MetricName": "SuccessRate", "Value": 70,
                            "Timestamp": good_ts}) + "\n"
            )  # the only valid, matching record
        records = logger._read_metric_records("SuccessRate", 24)
        assert len(records) == 1
        assert records[0]["Value"] == 70

    @pytest.mark.asyncio
    async def test_failure_count_zero_when_no_failures(self, logger):
        await logger._send_cloudwatch_metrics(metric(status=ScrapingStatus.SUCCESS))
        assert await logger.get_failure_count(hours=24) == 0


class TestSendBatchEmptyGuard:
    @pytest.mark.asyncio
    async def test_empty_buffer_returns_early(self, logger, monkeypatch):
        called = {"n": 0}

        def spy(records):
            called["n"] += 1

        monkeypatch.setattr(logger, "_write_metric_records", spy)
        assert logger.metrics_buffer == []
        await logger._send_batch_metrics()
        # Early return -> no write attempted.
        assert called["n"] == 0


class TestCreateAlarmError:
    @pytest.mark.asyncio
    async def test_alarm_error_branch(self, logger, monkeypatch):
        import builtins

        real_open = builtins.open

        def boom(path, *a, **k):
            if str(path).endswith("scraper_alarms.jsonl"):
                raise OSError("cannot open alarms file")
            return real_open(path, *a, **k)

        monkeypatch.setattr(builtins, "open", boom)
        # Caught + logged, must not raise.
        await logger.create_alarm(
            alarm_name="a", metric_name="M", threshold=1.0
        )
