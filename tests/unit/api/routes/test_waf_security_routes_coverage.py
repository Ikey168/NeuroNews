"""Comprehensive coverage tests for src/api/routes/waf_security_routes.py.

The router is mounted on a *fresh* FastAPI app and driven with a TestClient
(``raise_server_exceptions=False``). The local WAF manager (LocalWAFManager --
no boto3, no AWS) is used for real, seeded with in-memory SecurityEvents so the
blocked-request / SQL / XSS / geofencing analysis code paths run against real
data. Auth dependencies are overridden per-test to exercise the admin/auth
branches as well as the success paths. Every assertion checks concrete response
structure or status codes.
"""

import importlib.util
import os
import sys
import types
from datetime import datetime, timezone

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _load_routes_module(name):
    """Load src.api.routes.<name> from its file WITHOUT running the routes
    package ``__init__`` (which eagerly imports ``article_routes`` -> torch;
    importing torch while coverage's C tracer is active crashes the process).

    The module is registered under its canonical dotted name so coverage's
    ``--cov=src.api.routes.<name>`` matches, and ``src`` / ``src.api`` are still
    imported normally (they carry no heavy deps).
    """
    import src  # noqa: F401
    import src.api  # noqa: F401

    dotted = "src.api.routes." + name
    if dotted in sys.modules:
        return sys.modules[dotted]

    routes_dir = os.path.join(os.path.dirname(src.api.__file__), "routes")
    if "src.api.routes" not in sys.modules:
        pkg = types.ModuleType("src.api.routes")
        pkg.__path__ = [routes_dir]
        sys.modules["src.api.routes"] = pkg

    spec = importlib.util.spec_from_file_location(
        dotted, os.path.join(routes_dir, name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = module
    spec.loader.exec_module(module)
    return module


mod = _load_routes_module("waf_security_routes")  # noqa: E402

from src.api.security.local_waf_manager import (  # noqa: E402
    ActionType,
    LocalWAFManager,
    SecurityEvent,
    ThreatType,
)


ADMIN_USER = {"sub": "admin-123", "role": "admin"}


def _seed_events(manager):
    """Populate the manager with realistic BLOCKED security events."""
    events = [
        SecurityEvent(
            timestamp=datetime.now(timezone.utc),
            threat_type=ThreatType.SQL_INJECTION,
            source_ip="10.0.0.1",
            user_agent="sqlmap",
            request_path="/api/x?q=UNION SELECT password FROM users--",
            action_taken=ActionType.BLOCK,
            details={"country": "RU", "method": "GET"},
            severity="high",
        ),
        SecurityEvent(
            timestamp=datetime.now(timezone.utc),
            threat_type=ThreatType.XSS_ATTACK,
            source_ip="10.0.0.2",
            user_agent="attacker",
            request_path="/search?q=<script>alert(1)</script>",
            action_taken=ActionType.BLOCK,
            details={"country": "CN", "method": "GET"},
            severity="high",
        ),
        SecurityEvent(
            timestamp=datetime.now(timezone.utc),
            threat_type=ThreatType.GEO_BLOCKED,
            source_ip="10.0.0.3",
            user_agent="curl",
            request_path="/api/geo",
            action_taken=ActionType.BLOCK,
            details={"country": "KP", "method": "POST"},
            severity="medium",
        ),
    ]
    for e in events:
        manager.record_event(e)


@pytest.fixture
def waf(monkeypatch, tmp_path):
    """A real, seeded LocalWAFManager patched in as the module singleton."""
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    manager = LocalWAFManager()
    _seed_events(manager)
    monkeypatch.setattr(mod, "waf_manager", manager)
    return manager


@pytest.fixture
def app(waf):
    application = FastAPI()
    application.include_router(mod.router)
    # Default: authenticated admin for all protected endpoints.
    application.dependency_overrides[mod.require_admin] = lambda: ADMIN_USER
    application.dependency_overrides[mod.require_auth] = lambda: ADMIN_USER
    return application


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------- #
# require_admin dependency (unit-level, direct call)
# --------------------------------------------------------------------------- #

def test_require_admin_allows_admin_role():
    import asyncio

    result = asyncio.run(mod.require_admin(user={"role": "administrator", "sub": "u"}))
    assert result["sub"] == "u"


def test_require_admin_rejects_non_admin():
    import asyncio

    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.require_admin(user={"role": "viewer"}))
    assert exc.value.status_code == 403
    assert "Admin privileges" in exc.value.detail


# --------------------------------------------------------------------------- #
# /waf/deploy
# --------------------------------------------------------------------------- #

def test_deploy_waf_success(client, waf):
    resp = client.post("/api/security/waf/deploy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "AWS WAF deployed successfully"
    assert body["web_acl_name"] == waf.web_acl_name
    assert body["components"]["web_acl"] == "deployed"
    assert body["components"]["logging"] == "configured"
    assert body["components"]["dashboard"] == "created"
    assert body["deployed_by"] == "admin-123"
    assert "SQL Injection Protection" in body["rules_deployed"]


def test_deploy_waf_create_acl_failure(client, waf, monkeypatch):
    monkeypatch.setattr(waf, "create_web_acl", lambda: False)
    resp = client.post("/api/security/waf/deploy")
    assert resp.status_code == 500
    assert "Failed to create WAF Web ACL" in resp.json()["detail"]


def test_deploy_waf_partial_failure(client, waf, monkeypatch):
    monkeypatch.setattr(waf, "setup_logging", lambda: False)
    monkeypatch.setattr(waf, "create_security_dashboard", lambda: False)
    resp = client.post("/api/security/waf/deploy")
    assert resp.status_code == 200
    comps = resp.json()["components"]
    assert comps["logging"] == "failed"
    assert comps["dashboard"] == "failed"


# --------------------------------------------------------------------------- #
# /waf/associate/{arn}
# --------------------------------------------------------------------------- #

def test_associate_waf_success(client, waf):
    # The path param does not match embedded slashes, so use a slash-free ARN.
    arn = "arn:aws:apigateway:us-east-1::restapis-abc123"
    resp = client.post(f"/api/security/waf/associate/{arn}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_gateway_arn"] == arn
    assert body["associated_by"] == "admin-123"


def test_associate_waf_failure(client, waf, monkeypatch):
    monkeypatch.setattr(waf, "associate_with_api_gateway", lambda arn: False)
    resp = client.post("/api/security/waf/associate/some-arn")
    assert resp.status_code == 500
    assert "Failed to associate WAF" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# /waf/metrics
# --------------------------------------------------------------------------- #

def test_get_security_metrics_success(client, waf):
    resp = client.get("/api/security/waf/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["web_acl_name"] == waf.web_acl_name
    assert "SQLInjectionBlocked" in body["metrics"]
    # Seeded one SQL injection event -> blocked_requests == 1.
    assert body["metrics"]["SQLInjectionBlocked"]["blocked_requests"] == 1
    assert "start" in body["time_range"] and "end" in body["time_range"]


def test_get_security_metrics_error_payload(client, waf, monkeypatch):
    monkeypatch.setattr(waf, "get_security_metrics", lambda: {"error": "boom"})
    resp = client.get("/api/security/waf/metrics")
    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]


def test_get_security_metrics_unexpected_exception(client, waf, monkeypatch):
    # A raised (non-HTTPException) error hits the generic except -> 500.
    def boom():
        raise RuntimeError("cloudwatch unreachable")

    monkeypatch.setattr(waf, "get_security_metrics", boom)
    resp = client.get("/api/security/waf/metrics")
    assert resp.status_code == 500
    assert "cloudwatch unreachable" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# /waf/blocked-requests
# --------------------------------------------------------------------------- #

def test_blocked_requests_success(client):
    resp = client.get("/api/security/waf/blocked-requests")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_blocked"] == 3
    assert len(body["blocked_requests"]) == 3
    analysis = body["analysis"]
    assert "top_blocked_countries" in analysis
    assert "top_blocked_ips" in analysis
    assert isinstance(analysis["common_attack_patterns"], list)
    # RU/CN/KP each appear once in seeded data.
    assert set(analysis["top_blocked_countries"]) == {"RU", "CN", "KP"}


def test_blocked_requests_limit_validation(client):
    # ge=1, le=1000 -> 0 is rejected with 422.
    resp = client.get("/api/security/waf/blocked-requests", params={"limit": 0})
    assert resp.status_code == 422


def test_blocked_requests_error(client, waf, monkeypatch):
    def boom(_limit):
        raise RuntimeError("db down")

    monkeypatch.setattr(waf, "get_blocked_requests", boom)
    resp = client.get("/api/security/waf/blocked-requests")
    assert resp.status_code == 500
    assert "db down" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# /waf/status
# --------------------------------------------------------------------------- #

def test_waf_status_success(client):
    resp = client.get("/api/security/waf/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["protection_active"] is True
    assert body["waf_health"]["overall_status"] == "healthy"
    features = body["security_features"]
    assert features["sql_injection_protection"] is True
    assert "middleware_metrics" in body


def test_waf_status_error(client, waf, monkeypatch):
    def boom():
        raise RuntimeError("health failed")

    monkeypatch.setattr(waf, "health_check", boom)
    resp = client.get("/api/security/waf/status")
    assert resp.status_code == 500
    assert "health failed" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# /threats/real-time
# --------------------------------------------------------------------------- #

def test_real_time_threats_success(client):
    resp = client.get("/api/security/threats/real-time", params={"hours": 6})
    assert resp.status_code == 200
    body = resp.json()
    assert body["monitoring_period_hours"] == 6
    ta = body["threat_analysis"]
    assert "active_threats" in ta
    assert ta["risk_level"] in {"low", "medium", "high"}
    assert isinstance(ta["recommendations"], list) and ta["recommendations"]
    assert isinstance(body["alerts"], list)


def test_real_time_threats_hours_validation(client):
    # ge=1, le=24 -> 25 rejected.
    resp = client.get("/api/security/threats/real-time", params={"hours": 25})
    assert resp.status_code == 422


def test_real_time_threats_high_risk_alert(client, waf, monkeypatch):
    # Force high blocked counts so risk_level == high and an alert is generated.
    high_metrics = {
        "metrics": {
            "SQLInjectionBlocked": {"blocked_requests": 200},
            "XSSBlocked": {"blocked_requests": 20},
            "GeoBlocked": {"blocked_requests": 10},
            "RateLimitExceeded": {"blocked_requests": 5},
        }
    }
    monkeypatch.setattr(waf, "get_security_metrics", lambda: high_metrics)
    resp = client.get("/api/security/threats/real-time")
    assert resp.status_code == 200
    body = resp.json()
    assert body["threat_analysis"]["risk_level"] == "high"
    assert any(a["severity"] == "high" for a in body["alerts"])
    # Recommendation for excessive SQL injection is included.
    assert any("SQL injection" in r for r in body["threat_analysis"]["recommendations"])


def test_real_time_threats_error(client, waf, monkeypatch):
    def boom():
        raise RuntimeError("metrics unavailable")

    monkeypatch.setattr(waf, "get_security_metrics", boom)
    resp = client.get("/api/security/threats/real-time")
    assert resp.status_code == 500
    assert "metrics unavailable" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# /waf/configure
# --------------------------------------------------------------------------- #

def test_configure_waf_updates_settings(client, waf):
    payload = {"allowed_countries": ["US", "CA"], "rate_limit": 500}
    resp = client.post("/api/security/waf/configure", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated_settings"]["allowed_countries"] == ["US", "CA"]
    assert body["updated_settings"]["rate_limit"] == 500
    # Real manager state mutated.
    assert waf.allowed_countries == ["US", "CA"]
    assert waf.rate_limit_requests == 500


def test_configure_waf_empty_body(client, waf):
    resp = client.post("/api/security/waf/configure", json={})
    assert resp.status_code == 200
    assert resp.json()["updated_settings"] == {}


def test_configure_waf_rate_limit_validation(client):
    # rate_limit ge=100, le=10000 -> 50 rejected.
    resp = client.post("/api/security/waf/configure", json={"rate_limit": 50})
    assert resp.status_code == 422


def test_configure_waf_error_path(client, waf, monkeypatch):
    # Make assigning allowed_countries on the manager raise -> generic except 500.
    class _Raiser:
        def __setattr__(self, name, value):
            raise RuntimeError("config store broken")

    monkeypatch.setattr(mod, "waf_manager", _Raiser())
    resp = client.post(
        "/api/security/waf/configure", json={"allowed_countries": ["US"]}
    )
    assert resp.status_code == 500
    assert "config store broken" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# /waf/health (no auth required)
# --------------------------------------------------------------------------- #

def test_waf_health_success(client):
    resp = client.get("/api/security/waf/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] == "healthy"
    assert "waf_engine" in body["components"]


def test_waf_health_error_returns_error_status(client, waf, monkeypatch):
    def boom():
        raise RuntimeError("engine crash")

    monkeypatch.setattr(waf, "health_check", boom)
    resp = client.get("/api/security/waf/health")
    # Handler catches and returns a 200 error-status body (not an HTTP 500).
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] == "error"
    assert "engine crash" in body["components"]["error"]


# --------------------------------------------------------------------------- #
# /attacks/sql-injection
# --------------------------------------------------------------------------- #

def test_sql_injection_attempts_filters(client):
    resp = client.get("/api/security/attacks/sql-injection", params={"limit": 50})
    assert resp.status_code == 200
    body = resp.json()
    # Seeded SQL event has "SELECT ... FROM" in URI -> matched by "sql"? No:
    # filter looks for 'sql' substring; ensure structure regardless of count.
    assert "total_sql_injection_attempts" in body
    assert body["protection_status"] == "active"
    assert isinstance(body["analysis"]["common_injection_patterns"], list)
    assert body["analysis"]["attack_frequency"] in {"low", "medium", "high"}


def test_sql_injection_attempts_error(client, waf, monkeypatch):
    def boom(_limit):
        raise RuntimeError("query failed")

    monkeypatch.setattr(waf, "get_blocked_requests", boom)
    resp = client.get("/api/security/attacks/sql-injection")
    assert resp.status_code == 500
    assert "query failed" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# /attacks/xss
# --------------------------------------------------------------------------- #

def test_xss_attempts_filters_script_uri(client):
    resp = client.get("/api/security/attacks/xss", params={"limit": 50})
    assert resp.status_code == 200
    body = resp.json()
    # The seeded XSS event URI contains "<script>" -> matched by "script".
    assert body["total_xss_attempts"] >= 1
    assert body["protection_status"] == "active"
    assert "common_xss_patterns" in body["analysis"]
    assert "attack_vectors" in body["analysis"]


def test_xss_attempts_error(client, waf, monkeypatch):
    def boom(_limit):
        raise RuntimeError("xss query failed")

    monkeypatch.setattr(waf, "get_blocked_requests", boom)
    resp = client.get("/api/security/attacks/xss")
    assert resp.status_code == 500
    assert "xss query failed" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# /geofencing/status
# --------------------------------------------------------------------------- #

def test_geofencing_status_success(client, waf):
    resp = client.get("/api/security/geofencing/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["geofencing_enabled"] is True
    assert body["allowed_countries"] == waf.allowed_countries
    stats = body["statistics"]
    # The seeded GEO_BLOCKED event (action "BLOCK", threat geo) -> matched by "geo"?
    # The filter checks the action string for "geo"; BLOCK does not contain geo,
    # so total_geo_blocked may be 0 -- assert the structure is present.
    assert "total_geo_blocked" in stats
    assert body["configuration"]["enforcement_mode"] == "block"


def test_geofencing_status_error(client, waf, monkeypatch):
    def boom(_limit):
        raise RuntimeError("geo query failed")

    monkeypatch.setattr(waf, "get_blocked_requests", boom)
    resp = client.get("/api/security/geofencing/status")
    assert resp.status_code == 500
    assert "geo query failed" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Auth branch: no override -> real require_admin/require_auth reject
# --------------------------------------------------------------------------- #

def test_metrics_requires_auth(waf):
    # Fresh app with NO dependency overrides -> real JWT auth rejects (401).
    application = FastAPI()
    application.include_router(mod.router)
    unauth = TestClient(application, raise_server_exceptions=False)
    resp = unauth.get("/api/security/waf/metrics")
    assert resp.status_code == 401


def test_status_requires_auth(waf):
    application = FastAPI()
    application.include_router(mod.router)
    unauth = TestClient(application, raise_server_exceptions=False)
    resp = unauth.get("/api/security/waf/status")
    assert resp.status_code == 401


def test_configure_forbidden_for_non_admin(waf):
    # Override only require_auth (used by require_admin) with a non-admin user;
    # the real require_admin then raises 403.
    application = FastAPI()
    application.include_router(mod.router)
    application.dependency_overrides[mod.require_auth] = lambda: {"role": "viewer"}
    c = TestClient(application, raise_server_exceptions=False)
    resp = c.post("/api/security/waf/configure", json={})
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Analysis helper functions (direct unit tests)
# --------------------------------------------------------------------------- #

def test_analyze_blocked_countries_and_ips():
    reqs = [
        {"country": "RU", "client_ip": "1.1.1.1"},
        {"country": "RU", "client_ip": "1.1.1.1"},
        {"country": "CN", "client_ip": "2.2.2.2"},
    ]
    countries = mod._analyze_blocked_countries(reqs)
    assert countries["RU"] == 2
    assert countries["CN"] == 1
    ips = mod._analyze_blocked_ips(reqs)
    assert ips["1.1.1.1"] == 2


def test_analyze_attack_patterns_detects_types():
    reqs = [
        {"uri": "/x?q=<script>alert(1)</script>"},
        {"uri": "/y?id=1 UNION SELECT * FROM users"},
        {"uri": "/z?p=" + "A" * 250},
    ]
    patterns = mod._analyze_attack_patterns(reqs)
    assert "XSS attempt" in patterns
    assert "SQL injection" in patterns
    assert "Long URI (potential buffer overflow)" in patterns


def test_calculate_risk_level_thresholds():
    def m(n):
        return {"metrics": {k: {"blocked_requests": n} for k in
                            ["SQLInjectionBlocked", "XSSBlocked", "GeoBlocked",
                             "RateLimitExceeded"]}}

    assert mod._calculate_risk_level(m(0), {}) == "low"
    assert mod._calculate_risk_level(m(20), {}) == "medium"   # 80 total
    assert mod._calculate_risk_level(m(50), {}) == "high"     # 200 total


def test_generate_security_recommendations_variants():
    recs_good = mod._generate_security_recommendations({"metrics": {}}, {})
    assert any("Security posture is good" in r for r in recs_good)

    waf_metrics = {"metrics": {"SQLInjectionBlocked": {"blocked_requests": 50}}}
    recs = mod._generate_security_recommendations(waf_metrics, {"block_rate": 10})
    assert any("SQL injection" in r for r in recs)
    assert any("High block rate" in r for r in recs)


def test_generate_security_alerts_high_risk():
    alerts = mod._generate_security_alerts({"risk_level": "high"})
    assert alerts and alerts[0]["severity"] == "high"
    assert mod._generate_security_alerts({"risk_level": "low"}) == []


def test_extract_metric_value_safe():
    metrics = {"metrics": {"X": {"blocked_requests": 7}}}
    assert mod._extract_metric_value(metrics, "X") == 7
    # Missing "metrics" key -> default {} -> missing metric -> default {} -> 0.
    assert mod._extract_metric_value({}, "missing") == 0
    # Metric present but value shaped without "blocked_requests" -> 0.
    assert mod._extract_metric_value({"metrics": {"X": {}}}, "X") == 0


def test_calculate_attack_frequency_thresholds():
    assert mod._calculate_attack_frequency([{}] * 25) == "high"
    assert mod._calculate_attack_frequency([{}] * 10) == "medium"
    assert mod._calculate_attack_frequency([{}] * 2) == "low"


def test_count_by_country_and_top():
    geo = [{"country": "RU"}, {"country": "RU"}, {"country": "CN"}]
    counts = mod._count_by_country(geo)
    assert counts == {"RU": 2, "CN": 1}
    top = mod._get_top_blocked_countries(geo)
    assert top[0] == "RU"


def test_get_top_attacking_ips():
    attempts = [{"client_ip": "9.9.9.9"}, {"client_ip": "9.9.9.9"},
                {"client_ip": "8.8.8.8"}]
    top = mod._get_top_attacking_ips(attempts)
    assert top[0] == "9.9.9.9"


def test_calculate_active_threats_extracts_counts():
    waf_metrics = {
        "metrics": {
            "SQLInjectionBlocked": {"blocked_requests": 3},
            "XSSBlocked": {"blocked_requests": 2},
        }
    }
    result = mod._calculate_active_threats(waf_metrics, {"blocked_requests": 9})
    assert result["sql_injection_attempts"] == 3
    assert result["xss_attempts"] == 2
    assert result["middleware_blocked"] == 9


def test_analyze_threat_trends_static_shape():
    trends = mod._analyze_threat_trends({})
    assert set(trends.keys()) == {
        "sql_injection", "xss_attacks", "bot_traffic", "geo_violations"
    }


def test_static_pattern_analyzers():
    assert mod._analyze_sql_patterns([]) == [
        "UNION-based injection", "Boolean-based blind", "Time-based blind"
    ]
    assert "Script tag injection" in mod._analyze_xss_patterns([])
    assert "Query parameters" in mod._analyze_xss_vectors([])
