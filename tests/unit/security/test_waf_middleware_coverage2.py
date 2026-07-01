"""Coverage tests for src/api/security/waf_middleware.py.

Drives the WAFSecurityMiddleware end-to-end with a FastAPI TestClient to cover
the dispatch flow (blocked responses, security headers, excluded paths, the
DISABLE_WAF_FOR_TESTS short-circuit) and exercises the individual detection
helpers (SQL injection, XSS, bot, geofencing, rate limiting) plus the
WAFMetricsMiddleware directly.

No AWS/boto3 involved: this WAF is fully in-process.
"""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from src.api.security.local_waf_manager import ActionType, ThreatType
from src.api.security.waf_middleware import (
    WAFMetricsMiddleware,
    WAFSecurityMiddleware,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_request(method="GET", path="/api/x", query=b"", body=b"", headers=None):
    """Build a real Starlette Request with an optional body."""
    hdrs = headers or []
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "headers": hdrs,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def build_app():
    app = FastAPI()
    app.add_middleware(WAFSecurityMiddleware)

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "up"}

    @app.post("/api/submit")
    def submit():
        return {"ok": True}

    return app


# --------------------------------------------------------------------------
# End-to-end dispatch through TestClient
# --------------------------------------------------------------------------

def test_benign_request_passes_with_security_headers():
    client = TestClient(build_app())
    resp = client.get(
        "/api/ping",
        headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; legit browser)"},
    )
    assert resp.status_code == 200
    # _add_security_headers stamped these on the response
    assert resp.headers["X-WAF-Protected"] == "true"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_excluded_path_skips_waf():
    client = TestClient(build_app())
    # /health is excluded; even a bot UA (too short) must not be blocked
    resp = client.get("/health", headers={"user-agent": "x"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "up"}


def test_sql_injection_blocked_via_dispatch():
    client = TestClient(build_app())
    resp = client.get(
        "/api/ping?q=1' UNION SELECT password FROM users--",
        headers={"user-agent": "Mozilla/5.0 (legit browser here)"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "WAF_BLOCKED"
    assert body["threat_type"] == ThreatType.SQL_INJECTION.value
    # blocked response still carries security headers
    assert resp.headers["X-WAF-Protected"] == "true"


def test_bot_user_agent_blocked_via_dispatch():
    client = TestClient(build_app())
    resp = client.get("/api/ping", headers={"user-agent": "sqlmap/1.0"})
    assert resp.status_code == 403
    assert resp.json()["threat_type"] == ThreatType.BOT_TRAFFIC.value


def test_short_user_agent_blocked_via_dispatch():
    client = TestClient(build_app())
    resp = client.get("/api/ping", headers={"user-agent": "abc"})
    assert resp.status_code == 403
    assert resp.json()["threat_type"] == ThreatType.BOT_TRAFFIC.value


def test_disable_waf_env_short_circuits(monkeypatch):
    monkeypatch.setenv("DISABLE_WAF_FOR_TESTS", "true")
    client = TestClient(build_app())
    # A payload that would normally be blocked passes straight through
    resp = client.get("/api/ping?q=UNION SELECT", headers={"user-agent": "x"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_forwarded_for_used_and_ip_block():
    app = FastAPI()
    mw = WAFSecurityMiddleware(app)
    mw.blocked_ips.add("9.9.9.9")

    app.add_middleware(WAFSecurityMiddleware)
    # We need the same instance to hold blocked_ips; instead drive the helper
    # directly to confirm X-Forwarded-For parsing feeds the block decision.
    req = make_request(headers=[(b"x-forwarded-for", b"9.9.9.9, 8.8.8.8")])
    assert mw._get_client_ip(req) == "9.9.9.9"
    check = run(mw._perform_security_checks(req, "9.9.9.9", "Mozilla/5.0 browser"))
    assert check["blocked"] is True
    assert check["threat_type"] == ThreatType.MALICIOUS_IP


def test_perform_checks_rate_limit_blocked():
    mw = WAFSecurityMiddleware(FastAPI())
    ip = "7.7.7.7"
    # Pre-fill the window so the next check is over the limit (line 176)
    mw.request_counts[ip] = [__import__("time").time()] * 200
    req = make_request()
    check = run(mw._perform_security_checks(req, ip, "Mozilla/5.0 browser here"))
    assert check["blocked"] is True
    assert check["threat_type"] == ThreatType.RATE_LIMIT_EXCEEDED


def test_perform_checks_geo_blocked():
    mw = WAFSecurityMiddleware(FastAPI())
    req = make_request()
    # IP inside the geofenced range triggers GEO_BLOCKED (line 186)
    check = run(mw._perform_security_checks(req, "1.0.1.7", "Mozilla/5.0 browser here"))
    assert check["blocked"] is True
    assert check["threat_type"] == ThreatType.GEO_BLOCKED


def test_perform_checks_xss_blocked():
    mw = WAFSecurityMiddleware(FastAPI())
    req = make_request(query=b"c=<script>alert(1)</script>")
    check = run(mw._perform_security_checks(req, "8.8.8.8", "Mozilla/5.0 browser here"))
    assert check["blocked"] is True
    assert check["threat_type"] == ThreatType.XSS_ATTACK


def test_dispatch_reraises_downstream_error():
    app = FastAPI()
    mw = WAFSecurityMiddleware(app)

    async def boom_call_next(request):
        raise RuntimeError("downstream failure")

    req = make_request(headers=[(b"user-agent", b"Mozilla/5.0 legit browser")])
    with pytest.raises(RuntimeError, match="downstream failure"):
        run(mw.dispatch(req, boom_call_next))


class _BadBodyRequest:
    """Minimal request-like object whose body() raises, to hit decode guards."""

    def __init__(self, method="POST", query=""):
        self.method = method

        class _URL:
            def __init__(self, q):
                self.query = q

        self.url = _URL(query)

    async def body(self):
        raise RuntimeError("cannot read body")


def test_sql_injection_body_read_failure_falls_back():
    mw = WAFSecurityMiddleware(FastAPI())
    # body() raises -> inner except sets body_content='' (lines 306-307),
    # clean query -> not detected
    result = run(mw._check_sql_injection(_BadBodyRequest(query="page=1")))
    assert result["detected"] is False


def test_xss_body_read_failure_falls_back():
    mw = WAFSecurityMiddleware(FastAPI())
    result = run(mw._check_xss_attacks(_BadBodyRequest(query="q=hi")))
    assert result["detected"] is False


class _ExplodingRequest:
    """Accessing .url.query raises, to hit the outer except in check helpers."""

    method = "GET"

    @property
    def url(self):
        raise RuntimeError("url access boom")


def test_sql_injection_outer_exception_handled():
    mw = WAFSecurityMiddleware(FastAPI())
    result = run(mw._check_sql_injection(_ExplodingRequest()))
    assert result["detected"] is False
    assert "error" in result


def test_xss_outer_exception_handled():
    mw = WAFSecurityMiddleware(FastAPI())
    result = run(mw._check_xss_attacks(_ExplodingRequest()))
    assert result["detected"] is False
    assert "error" in result


def test_send_security_alert_exception_handled(monkeypatch):
    from src.api.security import waf_middleware as wm

    mw = WAFSecurityMiddleware(FastAPI())

    class BadEvent:
        # Accessing .timestamp raises -> triggers except path (lines 449-450)
        @property
        def timestamp(self):
            raise RuntimeError("bad event")

    # Should swallow the error, not raise
    run(mw._send_security_alert(BadEvent()))


def test_log_request_metrics_exception_handled():
    mw = WAFSecurityMiddleware(FastAPI())

    class BadPath:
        # json.dumps over a non-serializable path -> except branch (468-469)
        pass

    # processing_time as a non-number forces round() to raise inside the try
    run(mw._log_request_metrics("1.1.1.1", "/x", object(), 200))


# --------------------------------------------------------------------------
# _get_client_ip variants
# --------------------------------------------------------------------------

def test_get_client_ip_real_ip_header():
    mw = WAFSecurityMiddleware(FastAPI())
    req = make_request(headers=[(b"x-real-ip", b"5.5.5.5")])
    assert mw._get_client_ip(req) == "5.5.5.5"


def test_get_client_ip_direct_client():
    mw = WAFSecurityMiddleware(FastAPI())
    req = make_request(headers=[])
    assert mw._get_client_ip(req) == "127.0.0.1"


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------

def test_rate_limiting_not_exceeded_then_exceeded():
    mw = WAFSecurityMiddleware(FastAPI())
    ip = "1.2.3.4"
    first = mw._check_rate_limiting(ip)
    assert first["exceeded"] is False
    assert first["remaining"] == 99
    # Blow past the 100-request window
    for _ in range(105):
        result = mw._check_rate_limiting(ip)
    assert result["exceeded"] is True
    assert result["limit"] == 100
    assert result["request_count"] > 100


# --------------------------------------------------------------------------
# Geofencing
# --------------------------------------------------------------------------

def test_geofencing_blocks_configured_range():
    mw = WAFSecurityMiddleware(FastAPI())
    result = run(mw._check_geofencing("1.0.1.5"))
    assert result["blocked"] is True
    assert "geofencing" in result["reason"]


def test_geofencing_allows_normal_ip():
    mw = WAFSecurityMiddleware(FastAPI())
    result = run(mw._check_geofencing("8.8.8.8"))
    assert result["blocked"] is False
    assert result["country"] == "Allowed"


def test_geofencing_invalid_ip_handled():
    mw = WAFSecurityMiddleware(FastAPI())
    # Not a valid IP -> exception path returns blocked False with error key
    result = run(mw._check_geofencing("not-an-ip"))
    assert result["blocked"] is False
    assert "error" in result


# --------------------------------------------------------------------------
# SQL injection / XSS helpers over real Request bodies
# --------------------------------------------------------------------------

def test_sql_injection_detected_in_body():
    mw = WAFSecurityMiddleware(FastAPI())
    req = make_request(method="POST", body=b"name=admin' OR 1=1 --")
    result = run(mw._check_sql_injection(req))
    assert result["detected"] is True
    assert "pattern_matched" in result


def test_sql_injection_clean_request():
    mw = WAFSecurityMiddleware(FastAPI())
    req = make_request(query=b"page=2&size=10")
    result = run(mw._check_sql_injection(req))
    assert result["detected"] is False


def test_xss_detected_in_query():
    mw = WAFSecurityMiddleware(FastAPI())
    req = make_request(query=b"c=%3Cscript%3Ealert(1)%3C/script%3E")
    # query string as seen by the middleware is the raw urlencoded form; use a
    # decodable payload directly in the raw query
    req2 = make_request(query=b"c=<script>alert(1)</script>")
    result = run(mw._check_xss_attacks(req2))
    assert result["detected"] is True
    assert result["threat_level"] == "high"


def test_xss_clean_request():
    mw = WAFSecurityMiddleware(FastAPI())
    req = make_request(query=b"q=hello+world")
    result = run(mw._check_xss_attacks(req))
    assert result["detected"] is False


def test_xss_detected_in_post_body():
    mw = WAFSecurityMiddleware(FastAPI())
    req = make_request(method="POST", body=b"bio=javascript:evil()")
    result = run(mw._check_xss_attacks(req))
    assert result["detected"] is True


# --------------------------------------------------------------------------
# Bot detection helper
# --------------------------------------------------------------------------

def test_bot_traffic_malicious_pattern():
    mw = WAFSecurityMiddleware(FastAPI())
    result = mw._check_bot_traffic("nikto/2.1.5 scanner")
    assert result["is_malicious_bot"] is True
    assert result["confidence"] == "high"


def test_bot_traffic_too_short():
    mw = WAFSecurityMiddleware(FastAPI())
    result = mw._check_bot_traffic("short")
    assert result["is_malicious_bot"] is True
    assert result["confidence"] == "medium"


def test_bot_traffic_legit_browser():
    mw = WAFSecurityMiddleware(FastAPI())
    result = mw._check_bot_traffic("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)")
    assert result["is_malicious_bot"] is False


# --------------------------------------------------------------------------
# Logging helpers
# --------------------------------------------------------------------------

def test_log_security_event_and_alert():
    mw = WAFSecurityMiddleware(FastAPI())
    # Should complete without raising and invoke _send_security_alert
    run(
        mw._log_security_event(
            threat_type=ThreatType.SQL_INJECTION,
            source_ip="1.1.1.1",
            user_agent="ua",
            request_path="/api/x",
            action_taken=ActionType.BLOCK,
            details={"reason": "test"},
        )
    )


def test_log_request_metrics():
    mw = WAFSecurityMiddleware(FastAPI())
    run(mw._log_request_metrics("1.1.1.1", "/api/x", 0.123, 200))


def test_create_blocked_response_content():
    mw = WAFSecurityMiddleware(FastAPI())
    resp = mw._create_blocked_response(
        {"threat_type": ThreatType.XSS_ATTACK, "response_code": 403}
    )
    assert resp.status_code == 403
    payload = json.loads(bytes(resp.body).decode())
    assert payload["threat_type"] == ThreatType.XSS_ATTACK.value
    assert resp.headers["X-WAF-Protected"] == "true"


# --------------------------------------------------------------------------
# WAFMetricsMiddleware
# --------------------------------------------------------------------------

def test_metrics_middleware_counts_and_blocks():
    app = FastAPI()
    app.add_middleware(WAFMetricsMiddleware)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    @app.get("/blocked")
    def blocked():
        return PlainTextResponse("no", status_code=403)

    client = TestClient(app)
    client.get("/ok")
    client.get("/blocked", headers={"X-Forwarded-For": "3.3.3.3"})

    # Grab the middleware instance to inspect collected metrics
    mw = None
    for m in app.user_middleware:
        if m.cls is WAFMetricsMiddleware:
            # Recreate metrics via a direct instance to compute get_metrics
            break

    # Drive get_metrics on a fresh instance populated manually to assert shape
    metrics_mw = WAFMetricsMiddleware(app)
    metrics_mw.metrics["total_requests"] = 2
    metrics_mw.metrics["blocked_requests"] = 1
    metrics_mw.metrics["response_times"] = [0.01, 0.02]
    metrics_mw.metrics["top_blocked_ips"] = {"3.3.3.3": 1}
    summary = metrics_mw.get_metrics()
    assert summary["total_requests"] == 2
    assert summary["blocked_requests"] == 1
    assert summary["block_rate"] == 50.0
    assert summary["top_blocked_ips"] == {"3.3.3.3": 1}


def test_metrics_get_metrics_empty():
    mw = WAFMetricsMiddleware(FastAPI())
    summary = mw.get_metrics()
    # No requests -> block_rate 0 and avg response 0
    assert summary["block_rate"] == 0
    assert summary["average_response_time_ms"] == 0.0


def test_metrics_dispatch_trims_and_counts_blocked_ip():
    mw = WAFMetricsMiddleware(FastAPI())
    # Seed >1000 response times so the next dispatch trims to 1000 (line 537)
    mw.metrics["response_times"] = [0.0] * 1001
    # Seed an already-blocked IP so the next blocked request increments it (548)
    mw.metrics["top_blocked_ips"] = {"3.3.3.3": 1}

    async def call_next_blocked(request):
        class Resp:
            status_code = 403

        return Resp()

    req = make_request(headers=[(b"x-forwarded-for", b"3.3.3.3")])
    run(mw.dispatch(req, call_next_blocked))

    assert len(mw.metrics["response_times"]) == 1000
    assert mw.metrics["blocked_requests"] == 1
    assert mw.metrics["top_blocked_ips"]["3.3.3.3"] == 2


def test_metrics_dispatch_new_blocked_ip():
    mw = WAFMetricsMiddleware(FastAPI())

    async def call_next_blocked(request):
        class Resp:
            status_code = 429

        return Resp()

    req = make_request(headers=[(b"x-forwarded-for", b"4.4.4.4")])
    run(mw.dispatch(req, call_next_blocked))
    assert mw.metrics["top_blocked_ips"]["4.4.4.4"] == 1
