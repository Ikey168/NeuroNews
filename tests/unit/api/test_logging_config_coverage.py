"""Coverage-focused unit tests for src/api/logging_config.py.

Exercises the LocalRequestLogger middleware end to end through Starlette's
TestClient (real file logging into a tmp_path), the __init__ handler-dedup
branch, the error path in dispatch, and the configure_logging helper. Logging
side effects are contained to a tmp_path and asserted against the written file.
"""

import asyncio
import json
import logging
import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.api import logging_config as lc


@pytest.fixture(autouse=True)
def _log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_loggers():
    """Remove handlers created by tests so files can be re-created cleanly."""
    yield
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("neuronews.api."):
            lg = logging.getLogger(name)
            for h in list(lg.handlers):
                h.close()
                lg.removeHandler(h)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def test_get_log_dir_creates(tmp_path, monkeypatch):
    target = tmp_path / "a" / "b"
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(target))
    assert lc._get_log_dir() == str(target)
    assert os.path.isdir(target)


def test_sanitize_name():
    assert lc._sanitize_name("API Requests/v2") == "API-Requests-v2"
    assert lc._sanitize_name("###") == "default"


# ---------------------------------------------------------------------------
# LocalRequestLogger.__init__
# ---------------------------------------------------------------------------
def test_init_sets_up_file_logger(_log_dir):
    app = FastAPI()
    mw = lc.LocalRequestLogger(app, log_group="init group", aws_region="us-west-2")
    assert mw.log_group == "init group"
    # aws_region is stored but deprecated/unused
    assert mw.aws_region == "us-west-2"
    assert mw.log_stream.startswith("api-")
    # File path built from sanitized group name
    assert os.path.basename(mw.log_file) == "init-group.log"
    # Dedicated logger created, non-propagating, with a rotating file handler
    assert mw._file_logger.name == "neuronews.api.init-group"
    assert mw._file_logger.propagate is False
    assert any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        for h in mw._file_logger.handlers
    )


def test_init_does_not_duplicate_handler(_log_dir):
    app = FastAPI()
    mw1 = lc.LocalRequestLogger(app, log_group="dedup")
    count_after_first = len(mw1._file_logger.handlers)
    # Second middleware for the same log group must reuse the existing handler
    mw2 = lc.LocalRequestLogger(app, log_group="dedup")
    assert len(mw2._file_logger.handlers) == count_after_first
    assert mw1._file_logger is mw2._file_logger


# ---------------------------------------------------------------------------
# dispatch — success path via TestClient
# ---------------------------------------------------------------------------
def _build_app(log_group):
    app = FastAPI()
    app.add_middleware(lc.LocalRequestLogger, log_group=log_group)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    return app


def test_dispatch_logs_successful_request(_log_dir):
    app = _build_app("success case")
    client = TestClient(app)
    resp = client.get("/ping", headers={"X-Request-ID": "req-42"})
    assert resp.status_code == 200

    log_file = _log_dir / "success-case.log"
    assert log_file.exists()
    lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
    assert lines, "expected at least one log entry"
    entry = json.loads(lines[-1])
    assert entry["method"] == "GET"
    assert entry["path"] == "/ping"
    assert entry["status_code"] == 200
    assert entry["request_id"] == "req-42"
    assert entry["duration"].endswith("s")
    assert "error" not in entry


def test_dispatch_logs_error_and_reraises(_log_dir):
    app = _build_app("err case")
    # raise_server_exceptions=False lets the middleware finally-block run and
    # the exception propagate through Starlette's error handling.
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500

    log_file = _log_dir / "err-case.log"
    assert log_file.exists()
    lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
    entry = json.loads(lines[-1])
    assert entry["status_code"] == 500
    assert entry["path"] == "/boom"
    # Error message captured from the raised exception
    assert entry["error"] == "kaboom"


def test_dispatch_handles_file_write_error(_log_dir):
    """If the file logger raises OSError/ValueError, it is caught and logged."""
    app = FastAPI()
    mw = lc.LocalRequestLogger(app, log_group="write-fail")

    async def call_next(request):
        from starlette.responses import JSONResponse
        return JSONResponse({"ok": True})

    class FakeReq:
        headers = {}
        method = "GET"

        class url:
            path = "/x"

    with patch.object(mw._file_logger, "info", side_effect=OSError("disk gone")), \
         patch.object(lc.logging, "error") as mock_log_error:
        result = asyncio.run(mw.dispatch(FakeReq(), call_next))

    # Response is still returned despite the write failure
    assert result.status_code == 200
    mock_log_error.assert_called_once()
    assert "Failed to write logs" in mock_log_error.call_args[0][0]


# ---------------------------------------------------------------------------
# configure_logging + alias
# ---------------------------------------------------------------------------
def test_configure_logging_adds_middleware(_log_dir):
    app = FastAPI()
    with patch.object(app, "add_middleware") as mock_add:
        lc.configure_logging(app, log_group="cfg", aws_region="eu-1")
    mock_add.assert_called_once()
    args, kwargs = mock_add.call_args
    assert args[0] is lc.LocalRequestLogger
    assert kwargs["log_group"] == "cfg"
    assert kwargs["aws_region"] == "eu-1"


def test_configure_logging_real_app_registers_middleware(_log_dir):
    app = FastAPI()
    lc.configure_logging(app, log_group="realcfg")

    @app.get("/z")
    async def z():
        return {"v": 1}

    client = TestClient(app)
    assert client.get("/z").status_code == 200
    assert (_log_dir / "realcfg.log").exists()


def test_cloudwatch_logger_alias_is_local_request_logger():
    assert lc.CloudWatchLogger is lc.LocalRequestLogger


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
