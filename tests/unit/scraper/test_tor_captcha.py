"""Tests for src/scraper/tor_manager.py and src/scraper/captcha_solver.py."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiohttp")

from scraper.captcha_solver import CaptchaSolver  # noqa: E402
from scraper.tor_manager import TorManager  # noqa: E402


class TestTorManager:
    def test_proxy_urls(self):
        mgr = TorManager()
        assert mgr.get_proxy_url() == "socks5://127.0.0.1:9050"
        assert mgr.get_proxy() == mgr.tor_proxy_url

    def test_custom_proxy(self):
        mgr = TorManager(tor_proxy_url="socks5://10.0.0.1:9999")
        assert mgr.get_proxy() == "socks5://10.0.0.1:9999"

    @pytest.mark.asyncio
    async def test_rotate_identity_control_port(self):
        mgr = TorManager()
        sock = MagicMock()
        sock.connect_ex.return_value = 0
        sock.recv.return_value = b"250 OK"
        with patch("socket.socket", return_value=sock):
            assert await mgr.rotate_identity() is True
        sock.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_rotate_identity_falls_back(self):
        mgr = TorManager()
        sock = MagicMock()
        sock.connect_ex.return_value = 1  # control port closed
        with patch("socket.socket", return_value=sock), \
                patch.object(mgr, "_rotate_via_subprocess",
                             AsyncMock(return_value=True)) as fb:
            assert await mgr.rotate_identity() is True
            fb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rotate_via_subprocess_success(self):
        mgr = TorManager()
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"out", b""))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            assert await mgr._rotate_via_subprocess() is True

    @pytest.mark.asyncio
    async def test_rotate_via_subprocess_failure(self):
        mgr = TorManager()
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"", b"err"))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            assert await mgr._rotate_via_subprocess() is False

    @pytest.mark.asyncio
    async def test_rotate_via_subprocess_exception(self):
        mgr = TorManager()
        with patch("asyncio.create_subprocess_exec",
                   AsyncMock(side_effect=OSError("no torify"))):
            assert await mgr._rotate_via_subprocess() is False


class TestCaptchaDetect:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("html,expected", [
        ('<div class="g-recaptcha"></div>', True),
        ('<div class="h-captcha"></div>', True),
        ('<div data-sitekey="abc"></div>', True),
        ('<div class="cf-turnstile"></div>', True),
        ("<p>just a normal page</p>", False),
        ("", False),
    ])
    async def test_detect(self, html, expected):
        solver = CaptchaSolver(api_key="k")
        assert await solver.detect_captcha(html) is expected

    def test_get_captcha_result_stub(self):
        assert CaptchaSolver(api_key="k").get_captcha_result() is None


def _session_cm(post_json=None, get_jsons=None):
    """Build a mock aiohttp ClientSession context manager."""
    session = MagicMock()

    def make_resp(payload):
        resp = MagicMock()
        resp.json = AsyncMock(return_value=payload)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    if post_json is not None:
        session.post.return_value = make_resp(post_json)
    if get_jsons is not None:
        session.get.side_effect = [make_resp(j) for j in get_jsons]

    outer = MagicMock()
    outer.__aenter__ = AsyncMock(return_value=session)
    outer.__aexit__ = AsyncMock(return_value=False)
    return outer


class TestCaptchaSolve:
    @pytest.mark.asyncio
    async def test_recaptcha_submit_error(self):
        solver = CaptchaSolver(api_key="k")
        with patch("aiohttp.ClientSession",
                   return_value=_session_cm(post_json={"status": 0})):
            assert await solver.solve_recaptcha_v2("site", "url") is None

    @pytest.mark.asyncio
    async def test_recaptcha_success_via_polling(self):
        solver = CaptchaSolver(api_key="k")
        sess = _session_cm(post_json={"status": 1, "request": "cid"},
                           get_jsons=[{"status": 1, "request": "TOKEN"}])
        with patch("aiohttp.ClientSession", return_value=sess), \
                patch("asyncio.sleep", AsyncMock()):
            assert await solver.solve_recaptcha_v2("site", "url") == "TOKEN"

    @pytest.mark.asyncio
    async def test_recaptcha_via_get_captcha_result_hook(self):
        solver = CaptchaSolver(api_key="k")
        sess = _session_cm(post_json={"status": 1, "request": "cid"})
        with patch("aiohttp.ClientSession", return_value=sess), \
                patch("asyncio.sleep", AsyncMock()), \
                patch.object(solver, "get_captcha_result", return_value="HOOKTOK"):
            assert await solver.solve_recaptcha_v2("site", "url") == "HOOKTOK"

    @pytest.mark.asyncio
    async def test_hcaptcha_submit_error(self):
        solver = CaptchaSolver(api_key="k")
        with patch("aiohttp.ClientSession",
                   return_value=_session_cm(post_json={"status": 0})):
            assert await solver.solve_hcaptcha("site", "url") is None

    @pytest.mark.asyncio
    async def test_hcaptcha_success(self):
        solver = CaptchaSolver(api_key="k")
        sess = _session_cm(post_json={"status": 1, "request": "cid"},
                           get_jsons=[{"status": 1, "request": "HTOK"}])
        with patch("aiohttp.ClientSession", return_value=sess), \
                patch("asyncio.sleep", AsyncMock()):
            assert await solver.solve_hcaptcha("site", "url") == "HTOK"
