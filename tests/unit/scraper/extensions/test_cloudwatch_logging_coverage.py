"""Coverage-focused tests for src/scraper/extensions/cloudwatch_logging.py.

Exercises ``LocalFileLoggingExtension`` (aliased ``CloudWatchLoggingExtension``):

* ``from_crawler`` raising ``NotConfigured`` when disabled, and wiring signals
  when enabled (via either the ``LOCAL_FILE_LOGGING_ENABLED`` or deprecated
  ``CLOUDWATCH_LOGGING_ENABLED`` setting).
* ``spider_opened`` attaching the returned handler to root/scrapy/spider loggers
  and logging the configuration line, plus the no-handler branch.
* ``spider_closed`` detaching + closing the handler, and the no-op branch when
  no handler was ever attached.

scrapy is guarded with ``importorskip``.
"""

import logging
import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("scrapy")
from scrapy import signals  # noqa: E402
from scrapy.exceptions import NotConfigured  # noqa: E402

from scraper.extensions.cloudwatch_logging import (  # noqa: E402
    CloudWatchLoggingExtension,
    LocalFileLoggingExtension,
)


class FakeSettings:
    def __init__(self, values):
        self._values = values

    def getbool(self, key, default=False):
        return bool(self._values.get(key, default))


class FakeSignals:
    def __init__(self):
        self.connected = []

    def connect(self, receiver, signal):
        self.connected.append((receiver, signal))


class FakeCrawler:
    def __init__(self, values):
        self.settings = FakeSettings(values)
        self.signals = FakeSignals()


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, msg):
        self.messages.append(msg)


class FakeSpider:
    def __init__(self, name="myspider"):
        self.name = name
        self.logger = FakeLogger()


class DummyHandler(logging.Handler):
    """A handler exposing the attributes the extension reads for logging."""

    def __init__(self):
        super().__init__()
        self.log_group_name = "grp"
        self.log_stream_name = "strm"
        self.closed = False

    def emit(self, record):  # pragma: no cover - not exercised
        pass

    def close(self):
        self.closed = True
        super().close()


class TestFromCrawler:
    def test_alias_points_to_local_extension(self):
        assert CloudWatchLoggingExtension is LocalFileLoggingExtension

    def test_not_configured_when_disabled(self):
        crawler = FakeCrawler({})
        with pytest.raises(NotConfigured):
            LocalFileLoggingExtension.from_crawler(crawler)

    def test_enabled_via_local_setting_connects_signals(self):
        crawler = FakeCrawler({"LOCAL_FILE_LOGGING_ENABLED": True})
        ext = LocalFileLoggingExtension.from_crawler(crawler)
        signals_connected = {sig for _, sig in crawler.signals.connected}
        assert signals.spider_opened in signals_connected
        assert signals.spider_closed in signals_connected
        assert ext.crawler is crawler

    def test_enabled_via_deprecated_cloudwatch_alias(self):
        crawler = FakeCrawler({"CLOUDWATCH_LOGGING_ENABLED": True})
        ext = LocalFileLoggingExtension.from_crawler(crawler)
        assert len(crawler.signals.connected) == 2
        assert ext.crawler is crawler


class TestSpiderOpened:
    def test_attaches_handler_to_all_loggers(self, monkeypatch):
        crawler = FakeCrawler({"LOCAL_FILE_LOGGING_ENABLED": True})
        ext = LocalFileLoggingExtension.from_crawler(crawler)
        handler = DummyHandler()
        monkeypatch.setattr(
            "scraper.extensions.cloudwatch_logging.configure_cloudwatch_logging",
            lambda settings, name: handler,
        )
        spider = FakeSpider(name="uniquespider1")
        try:
            ext.spider_opened(spider)
            assert ext.handler is handler
            assert handler in logging.getLogger().handlers
            assert handler in logging.getLogger("scrapy").handlers
            assert handler in logging.getLogger("uniquespider1").handlers
            assert any("Local file logging configured" in m for m in spider.logger.messages)
            assert any("grp" in m and "strm" in m for m in spider.logger.messages)
        finally:
            logging.getLogger().removeHandler(handler)
            logging.getLogger("scrapy").removeHandler(handler)
            logging.getLogger("uniquespider1").removeHandler(handler)

    def test_no_handler_returned_does_nothing(self, monkeypatch):
        crawler = FakeCrawler({"LOCAL_FILE_LOGGING_ENABLED": True})
        ext = LocalFileLoggingExtension.from_crawler(crawler)
        monkeypatch.setattr(
            "scraper.extensions.cloudwatch_logging.configure_cloudwatch_logging",
            lambda settings, name: None,
        )
        spider = FakeSpider(name="uniquespider2")
        ext.spider_opened(spider)
        assert not hasattr(ext, "handler")
        assert spider.logger.messages == []


class TestSpiderClosed:
    def test_removes_and_closes_handler(self, monkeypatch):
        crawler = FakeCrawler({"LOCAL_FILE_LOGGING_ENABLED": True})
        ext = LocalFileLoggingExtension.from_crawler(crawler)
        handler = DummyHandler()
        monkeypatch.setattr(
            "scraper.extensions.cloudwatch_logging.configure_cloudwatch_logging",
            lambda settings, name: handler,
        )
        spider = FakeSpider(name="uniquespider3")
        ext.spider_opened(spider)
        assert handler in logging.getLogger("uniquespider3").handlers

        ext.spider_closed(spider)
        assert handler not in logging.getLogger().handlers
        assert handler not in logging.getLogger("scrapy").handlers
        assert handler not in logging.getLogger("uniquespider3").handlers
        assert handler.closed is True
        assert any("shutting down local file logging" in m for m in spider.logger.messages)

    def test_close_without_handler_is_noop(self):
        crawler = FakeCrawler({"LOCAL_FILE_LOGGING_ENABLED": True})
        ext = LocalFileLoggingExtension.from_crawler(crawler)
        spider = FakeSpider(name="uniquespider4")
        # No handler attribute -> the guarded branch is skipped, no error.
        ext.spider_closed(spider)
        assert spider.logger.messages == []
