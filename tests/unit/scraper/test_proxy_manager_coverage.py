"""Coverage tests for src/scraper/proxy_manager.py.

Imports via ``src.scraper.proxy_manager`` so coverage attributes to the file.

Targets remaining uncovered branches:
  * _load_config success + error                       74, 78-104
  * rotation-strategy fallback branches                134, 140, 146, 154
  * check_proxy_health non-200 status + exception      239-246
  * start_health_monitor loop (one pass, cancel, error) 283-297
aiohttp is patched where it is looked up in the module.
"""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("aiohttp")

from src.scraper import proxy_manager as pm  # noqa: E402
from src.scraper.proxy_manager import (  # noqa: E402
    ProxyConfig,
    ProxyRotationManager,
    ProxyStats,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _proxy(host="1.1.1.1", port=8080, **kw):
    return ProxyConfig(host=host, port=port, **kw)


# ---------------------------------------------------------------------------
# _load_config
# ---------------------------------------------------------------------------

def test_load_config_reads_proxies_and_settings(tmp_path):
    """Lines 78-101: valid config file populates proxies + settings."""
    cfg = {
        "proxy_settings": {
            "rotation_strategy": "health_based",
            "health_check_interval": 120,
        },
        "proxies": [
            {"host": "10.0.0.1", "port": 3128, "proxy_type": "http"},
            {"host": "10.0.0.2", "port": 3129, "concurrent_limit": 2},
        ],
    }
    path = tmp_path / "proxies.json"
    path.write_text(json.dumps(cfg))

    mgr = ProxyRotationManager(config_path=str(path))

    assert mgr.rotation_strategy == "health_based"
    assert mgr.health_check_interval == 120
    assert len(mgr.proxies) == 2
    # Stats + connection tracking initialised for each proxy.
    assert mgr.proxy_stats["10.0.0.1:3128"].total_requests == 0
    assert mgr.active_connections["10.0.0.2:3129"] == 0


def test_load_config_missing_file_logged_not_raised(tmp_path):
    """Lines 103-104: a bad path is caught and logged, leaving no proxies."""
    missing = tmp_path / "does_not_exist.json"
    # Constructor calls _load_config; it must not raise.
    mgr = ProxyRotationManager(config_path=str(missing))
    assert mgr.proxies == []


def test_load_config_invalid_json_logged(tmp_path):
    """Lines 103-104: invalid JSON is caught and logged."""
    path = tmp_path / "bad.json"
    path.write_text("{not valid json")
    mgr = ProxyRotationManager(config_path=str(path))
    assert mgr.proxies == []


# ---------------------------------------------------------------------------
# Rotation strategy fallbacks (all healthy_proxies-empty branches)
# ---------------------------------------------------------------------------

def test_round_robin_falls_back_to_all_when_none_healthy():
    """Lines 131-134: no healthy proxy -> fall back to full list."""
    mgr = ProxyRotationManager(rotation_strategy="round_robin")
    p = _proxy()
    mgr.add_proxy(p)
    # Mark unhealthy so the healthy filter is empty -> fallback branch.
    mgr.proxy_stats["1.1.1.1:8080"].is_healthy = False

    chosen = _run(mgr.get_proxy())
    assert chosen is p


def test_random_strategy_falls_back_to_all(monkeypatch):
    """Lines 144-148: random strategy fallback + random.choice branch."""
    mgr = ProxyRotationManager(rotation_strategy="random")
    p = _proxy()
    mgr.add_proxy(p)
    mgr.proxy_stats["1.1.1.1:8080"].is_healthy = False
    monkeypatch.setattr(pm.random, "choice", lambda seq: seq[0])

    chosen = _run(mgr.get_proxy())
    assert chosen is p


def test_random_strategy_empty_returns_none():
    """Line 148: no proxies at all -> None."""
    mgr = ProxyRotationManager(rotation_strategy="random")
    assert _run(mgr.get_proxy()) is None


def test_health_based_returns_highest_score():
    """Lines 150-164: health_based sorts by health_score descending."""
    mgr = ProxyRotationManager(rotation_strategy="health_based")
    low = _proxy(host="2.2.2.2", port=1)
    high = _proxy(host="3.3.3.3", port=2)
    mgr.add_proxy(low)
    mgr.add_proxy(high)
    mgr.proxy_stats["2.2.2.2:1"].health_score = 30.0
    mgr.proxy_stats["3.3.3.3:2"].health_score = 95.0

    chosen = _run(mgr.get_proxy())
    assert chosen is high


def test_health_based_none_healthy_returns_none():
    """Lines 152-154: health_based with no healthy proxy -> None."""
    mgr = ProxyRotationManager(rotation_strategy="health_based")
    p = _proxy()
    mgr.add_proxy(p)
    mgr.proxy_stats["1.1.1.1:8080"].is_healthy = False
    assert _run(mgr.get_proxy()) is None


def test_unknown_strategy_defaults_to_round_robin():
    """Lines 126-127: an unrecognised strategy falls through to round robin."""
    mgr = ProxyRotationManager(rotation_strategy="mystery")
    p = _proxy()
    mgr.add_proxy(p)
    chosen = _run(mgr.get_proxy())
    assert chosen is p


def test_get_proxy_empty_pool_returns_none():
    """Line 117-118: no proxies -> None regardless of strategy."""
    mgr = ProxyRotationManager()
    assert _run(mgr.get_proxy()) is None


def test_round_robin_empty_pool_returns_none_directly():
    """Line 140: defensive None when the round-robin helper has no proxies."""
    mgr = ProxyRotationManager()
    # Call the helper directly (public get_proxy short-circuits on empty pool).
    assert mgr._get_round_robin_proxy() is None


# ---------------------------------------------------------------------------
# check_proxy_health -- non-200 and exception branches
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or {"origin": "9.9.9.9"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, *a, **k):
        if self._raise is not None:
            raise self._raise
        return self._response


def _install_fake_aiohttp(monkeypatch, session):
    """Patch aiohttp entry points used by check_proxy_health."""
    monkeypatch.setattr(pm.aiohttp, "TCPConnector", lambda *a, **k: object())
    monkeypatch.setattr(pm.aiohttp, "ClientTimeout", lambda *a, **k: object())
    monkeypatch.setattr(pm.aiohttp, "BasicAuth", lambda *a, **k: ("auth",))
    monkeypatch.setattr(
        pm.aiohttp, "ClientSession", lambda *a, **k: session
    )


def test_check_proxy_health_success(monkeypatch):
    """Lines 232-237: 200 response -> True."""
    session = _FakeSession(response=_FakeResponse(200))
    _install_fake_aiohttp(monkeypatch, session)
    mgr = ProxyRotationManager()
    p = _proxy(username="u", password="p")

    assert _run(mgr.check_proxy_health(p)) is True


def test_check_proxy_health_non_200(monkeypatch):
    """Lines 238-242: non-200 response -> False."""
    session = _FakeSession(response=_FakeResponse(503))
    _install_fake_aiohttp(monkeypatch, session)
    mgr = ProxyRotationManager()
    p = _proxy()

    assert _run(mgr.check_proxy_health(p)) is False


def test_check_proxy_health_exception(monkeypatch):
    """Lines 244-246: request raising -> caught -> False."""
    session = _FakeSession(raise_exc=RuntimeError("connection refused"))
    _install_fake_aiohttp(monkeypatch, session)
    mgr = ProxyRotationManager()
    p = _proxy()

    assert _run(mgr.check_proxy_health(p)) is False


# ---------------------------------------------------------------------------
# health_check_all -- healthy vs unhealthy result handling
# ---------------------------------------------------------------------------

def test_health_check_all_updates_scores(monkeypatch):
    """Lines 259-279: True result raises health; failure lowers it."""
    mgr = ProxyRotationManager()
    good = _proxy(host="4.4.4.4", port=1)
    bad = _proxy(host="5.5.5.5", port=2)
    mgr.add_proxy(good)
    mgr.add_proxy(bad)
    mgr.proxy_stats["4.4.4.4:1"].health_score = 50.0
    mgr.proxy_stats["5.5.5.5:2"].health_score = 50.0

    async def _health(proxy):
        return proxy is good  # good -> True, bad -> False

    monkeypatch.setattr(mgr, "check_proxy_health", _health)
    _run(mgr.health_check_all())

    assert mgr.proxy_stats["4.4.4.4:1"].is_healthy is True
    assert mgr.proxy_stats["4.4.4.4:1"].health_score == 55.0
    assert mgr.proxy_stats["5.5.5.5:2"].is_healthy is False
    assert mgr.proxy_stats["5.5.5.5:2"].health_score == 40.0


# ---------------------------------------------------------------------------
# start_health_monitor -- one loop pass, cancel, and error branch
# ---------------------------------------------------------------------------

def test_start_health_monitor_disabled_when_interval_zero(monkeypatch):
    """Lines 283-284: interval <= 0 -> monitor never loops (returns at once)."""
    mgr = ProxyRotationManager()
    mgr.health_check_interval = 0

    called = {"n": 0}

    async def _hc():
        called["n"] += 1

    monkeypatch.setattr(mgr, "health_check_all", _hc)
    _run(mgr.start_health_monitor())
    assert called["n"] == 0


def test_start_health_monitor_runs_then_cancelled(monkeypatch):
    """Lines 285-294: one health check, then CancelledError breaks the loop."""
    mgr = ProxyRotationManager()
    mgr.health_check_interval = 5

    calls = {"n": 0}

    async def _hc():
        calls["n"] += 1

    async def _sleep(_secs):
        raise asyncio.CancelledError

    monkeypatch.setattr(mgr, "health_check_all", _hc)
    monkeypatch.setattr(pm.asyncio, "sleep", _sleep)

    # Should return cleanly (CancelledError is caught with `break`).
    _run(mgr.start_health_monitor())
    assert calls["n"] == 1


def test_start_health_monitor_error_then_cancel(monkeypatch):
    """Lines 295-297: health_check_all raising -> error branch -> retry sleep.

    First iteration raises, hits the error handler and its 60s retry sleep;
    second iteration succeeds and the interval sleep is cancelled to break out.
    The 60s error-retry sleep must complete normally (it is NOT wrapped by the
    CancelledError handler), so only the *interval* sleep raises CancelledError.
    """
    mgr = ProxyRotationManager()
    mgr.health_check_interval = 5

    state = {"checks": 0, "error_sleeps": 0, "interval_sleeps": 0}

    async def _hc():
        state["checks"] += 1
        if state["checks"] == 1:
            raise RuntimeError("check exploded")

    async def _sleep(secs):
        if secs == 60:
            state["error_sleeps"] += 1
            return  # error-retry sleep completes normally
        state["interval_sleeps"] += 1
        raise asyncio.CancelledError  # interval sleep -> break loop

    monkeypatch.setattr(mgr, "health_check_all", _hc)
    monkeypatch.setattr(pm.asyncio, "sleep", _sleep)

    _run(mgr.start_health_monitor())
    assert state["checks"] == 2
    assert state["error_sleeps"] == 1
    assert state["interval_sleeps"] == 1
