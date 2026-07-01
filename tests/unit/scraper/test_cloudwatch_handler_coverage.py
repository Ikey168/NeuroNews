"""Coverage-focused unit tests for src/scraper/log_utils/cloudwatch_handler.py.

This module is the local-file replacement for the old AWS CloudWatch Logs
handler; it does not import boto3/watchtower. Tests exercise the sanitizer,
the LocalFileLoggingHandler lifecycle (including the OSError -> LogStreamError
path via a patched RotatingFileHandler), and the configure_cloudwatch_logging
factory with a fake Scrapy settings object. Real files are written under a
tmp_path so no logs leak into the repo.
"""

import logging
import os
from unittest.mock import patch

import pytest

from src.scraper.log_utils import cloudwatch_handler as cw


# ---------------------------------------------------------------------------
# Fake Scrapy settings object
# ---------------------------------------------------------------------------
class FakeSettings:
    def __init__(self, bools=None, values=None):
        self._bools = bools or {}
        self._values = values or {}

    def getbool(self, key, default=False):
        return self._bools.get(key, default)

    def get(self, key, default=None):
        return self._values.get(key, default)


@pytest.fixture(autouse=True)
def _log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def test_get_log_dir_creates_directory(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "logs"
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(target))
    result = cw._get_log_dir()
    assert result == str(target)
    assert os.path.isdir(target)


def test_sanitize_name_replaces_invalid_chars():
    assert cw._sanitize_name("NeuroNews Scraper/v1") == "NeuroNews-Scraper-v1"


def test_sanitize_name_strips_dashes():
    assert cw._sanitize_name("--foo--") == "foo"


def test_sanitize_name_empty_becomes_default():
    assert cw._sanitize_name("///") == "default"


# ---------------------------------------------------------------------------
# LocalFileLoggingHandler
# ---------------------------------------------------------------------------
def test_handler_generates_stream_name_when_missing(_log_dir):
    handler = cw.LocalFileLoggingHandler(log_group_name="MyGroup")
    try:
        # Stream defaults to a scraper-<timestamp> name
        assert handler.log_stream_name.startswith("scraper-")
        # Log file lives under the configured log dir and merges sanitized names
        assert str(_log_dir) in handler.log_file
        assert handler.log_file.endswith(".log")
        assert "MyGroup" in os.path.basename(handler.log_file)
        assert handler._file_handler is not None
    finally:
        handler.close()


def test_handler_uses_explicit_stream_name(_log_dir):
    handler = cw.LocalFileLoggingHandler(
        log_group_name="Grp",
        log_stream_name="my stream/1",
    )
    try:
        assert handler.log_stream_name == "my stream/1"
        # Sanitized in filename
        assert "my-stream-1" in os.path.basename(handler.log_file)
    finally:
        handler.close()


def test_handler_ignores_deprecated_aws_kwargs(_log_dir):
    handler = cw.LocalFileLoggingHandler(
        log_group_name="Grp",
        aws_access_key_id="AKIA",
        aws_secret_access_key="secret",
        aws_region="us-east-1",
    )
    try:
        assert handler._file_handler is not None
    finally:
        handler.close()


def test_handler_emit_writes_record(_log_dir):
    handler = cw.LocalFileLoggingHandler(log_group_name="EmitGrp")
    handler.setFormatter(logging.Formatter("%(message)s"))
    try:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="hello world", args=(), exc_info=None,
        )
        handler.emit(record)
        handler._file_handler.flush()
        with open(handler.log_file) as fh:
            contents = fh.read()
        assert "hello world" in contents
    finally:
        handler.close()


def test_handler_set_formatter_propagates_to_file_handler(_log_dir):
    handler = cw.LocalFileLoggingHandler(log_group_name="FmtGrp")
    try:
        fmt = logging.Formatter("PREFIX %(message)s")
        handler.setFormatter(fmt)
        assert handler.formatter is fmt
        assert handler._file_handler.formatter is fmt
    finally:
        handler.close()


def test_handler_emit_calls_handle_error_on_failure(_log_dir):
    handler = cw.LocalFileLoggingHandler(log_group_name="ErrGrp")
    try:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="boom", args=(), exc_info=None,
        )
        with patch.object(handler._file_handler, "emit", side_effect=ValueError("nope")), \
             patch.object(handler, "handleError") as mock_handle:
            handler.emit(record)
        mock_handle.assert_called_once_with(record)
    finally:
        handler.close()


def test_handler_emit_noop_without_file_handler(_log_dir):
    handler = cw.LocalFileLoggingHandler(log_group_name="NoFH")
    handler._file_handler = None
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="x", args=(), exc_info=None,
    )
    # Should simply do nothing and not raise
    handler.emit(record)
    handler.close()


def test_handler_close_is_safe_without_file_handler(_log_dir):
    handler = cw.LocalFileLoggingHandler(log_group_name="CloseGrp")
    handler.close()
    handler._file_handler = None
    # Second close after clearing the handler must not raise
    handler.close()


def test_create_log_group_wraps_oserror_in_log_stream_error(_log_dir):
    with patch.object(cw, "RotatingFileHandler", side_effect=OSError("disk full")):
        with pytest.raises(cw.LogStreamError) as exc:
            cw.LocalFileLoggingHandler(log_group_name="FailGrp")
    assert "Failed to create local log file" in str(exc.value)


# ---------------------------------------------------------------------------
# configure_cloudwatch_logging
# ---------------------------------------------------------------------------
def test_configure_returns_none_when_disabled(_log_dir):
    settings = FakeSettings(bools={})
    assert cw.configure_cloudwatch_logging(settings, "spider1") is None


def test_configure_enabled_via_local_flag(_log_dir):
    settings = FakeSettings(
        bools={"LOCAL_FILE_LOGGING_ENABLED": True},
        values={"LOCAL_LOG_LEVEL": "DEBUG"},
    )
    handler = cw.configure_cloudwatch_logging(settings, "spiderA")
    try:
        assert isinstance(handler, cw.LocalFileLoggingHandler)
        # Default log group is applied when not set
        assert "NeuroNews-Scraper" in os.path.basename(handler.log_file)
        # Stream name embeds prefix + spider name
        assert "scraper-spiderA-" in handler.log_stream_name
        # Level applied from LOCAL_LOG_LEVEL
        assert handler.level == logging.DEBUG
        assert handler.formatter is not None
    finally:
        handler.close()


def test_configure_enabled_via_deprecated_cloudwatch_flag(_log_dir):
    settings = FakeSettings(
        bools={"CLOUDWATCH_LOGGING_ENABLED": True},
        values={
            "CLOUDWATCH_LOG_GROUP": "Legacy-Group",
            "CLOUDWATCH_LOG_STREAM_PREFIX": "legacy",
            "CLOUDWATCH_LOG_LEVEL": "WARNING",
        },
    )
    handler = cw.configure_cloudwatch_logging(settings, "spiderB")
    try:
        assert "Legacy-Group" in os.path.basename(handler.log_file)
        assert handler.log_stream_name.startswith("legacy-spiderB-")
        assert handler.level == logging.WARNING
    finally:
        handler.close()


def test_backward_compat_aliases_point_to_local_impls():
    assert cw.CloudWatchLoggingHandler is cw.LocalFileLoggingHandler
    assert cw.configure_local_file_logging is cw.configure_cloudwatch_logging


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
