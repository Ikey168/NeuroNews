"""Coverage tests for src/api/monitoring/suspicious_activity_monitor.py.

Targets the remaining uncovered branches: profile-dependent detectors
(unusual hours, data scraping, unusual user agent), high error rate,
credential stuffing, DDoS, bot short-circuit, empty-input short-circuit,
detector exception handling, logging paths, risk score and recent-alerts.

Real boto3/AWS is not involved here; the detector is pure in-process logic.
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from src.api.monitoring.suspicious_activity_monitor import (
    AdvancedSuspiciousActivityDetector,
    AlertLevel,
    SuspiciousActivity,
    SuspiciousPatternType,
    UserBehaviorProfile,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_req(**kw):
    base = {
        "timestamp": datetime.now(),
        "endpoint": "/api/articles",
        "ip_address": "10.0.0.1",
        "user_agent": "Mozilla/5.0",
        "response_code": 200,
        "processing_time": 0.5,
    }
    base.update(kw)
    return base


def test_analyze_empty_requests_returns_empty():
    det = AdvancedSuspiciousActivityDetector()
    # line 127: early return on empty input
    assert run(det.analyze_user_activity("u1", [])) == []


def test_analyze_detects_and_stores_alert():
    det = AdvancedSuspiciousActivityDetector()
    now = datetime.now()
    # 60 rapid requests within last minute -> rapid_requests detector fires
    reqs = [make_req(timestamp=now - timedelta(seconds=1)) for _ in range(60)]
    activities = run(det.analyze_user_activity("rapid_user", reqs))
    kinds = {a.pattern_type for a in activities}
    assert SuspiciousPatternType.RAPID_REQUESTS in kinds
    # active_alerts populated (store loop lines 146-148)
    assert any(a.user_id == "rapid_user" for a in det.active_alerts)


def test_analyze_handles_detector_exception(monkeypatch):
    det = AdvancedSuspiciousActivityDetector()

    async def boom(user_id, requests):
        raise RuntimeError("detector failure")

    # Replace one matcher to raise -> exercises except block (lines 140-141)
    det.pattern_matchers[SuspiciousPatternType.RAPID_REQUESTS] = boom
    # Non-empty requests, but nothing else triggers; must not raise
    result = run(det.analyze_user_activity("u", [make_req()]))
    assert result == []


def test_rapid_requests_below_threshold_returns_none():
    det = AdvancedSuspiciousActivityDetector()
    # line 239: total requests below threshold -> None
    assert run(det._detect_rapid_requests("u", [make_req()])) is None


def test_rapid_requests_enough_total_but_none_recent():
    det = AdvancedSuspiciousActivityDetector()
    old = datetime.now() - timedelta(minutes=30)
    # >= threshold total, but all older than 60s -> recent < threshold -> None (line 239)
    reqs = [make_req(timestamp=old) for _ in range(60)]
    assert run(det._detect_rapid_requests("u", reqs)) is None


def test_unusual_hours_few_unusual_returns_none():
    det = AdvancedSuspiciousActivityDetector()
    profile = UserBehaviorProfile(user_id="u")
    profile.typical_hours = [9, 10, 11, 12, 13]
    det.user_profiles["u"] = profile
    base = datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
    # Only 3 unusual-hour requests (<= 5) -> fall through to None (line 285)
    reqs = [make_req(timestamp=base) for _ in range(3)]
    assert run(det._detect_unusual_hours("u", reqs)) is None


def test_bot_behavior_low_confidence_returns_none():
    det = AdvancedSuspiciousActivityDetector()
    base = datetime.now()
    # 25 requests, irregular timing (large gaps), varied IPs, varied endpoints,
    # benign UA -> confidence below 0.6 -> None (line 509)
    reqs = [
        make_req(
            timestamp=base + timedelta(seconds=i * i * 7),
            ip_address="10.0.0.{0}".format(i),
            endpoint="/api/e{0}".format(i),
            user_agent="Mozilla/5.0 (Windows NT 10.0)",
        )
        for i in range(25)
    ]
    assert run(det._detect_bot_behavior("u", reqs)) is None


def test_unusual_hours_requires_profile_history():
    det = AdvancedSuspiciousActivityDetector()
    # No profile -> None (line ~246/249 guard)
    assert run(det._detect_unusual_hours("nouser", [make_req()])) is None


def test_unusual_hours_detected():
    det = AdvancedSuspiciousActivityDetector()
    # Seed a profile with >=5 typical hours all in daytime (none in 2-6am)
    profile = UserBehaviorProfile(user_id="u")
    profile.typical_hours = [9, 10, 11, 12, 13]
    det.user_profiles["u"] = profile

    base = datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
    # 6 requests at 3am (unusual hour, not in typical, within 2-6 range)
    reqs = [make_req(timestamp=base) for _ in range(6)]
    activity = run(det._detect_unusual_hours("u", reqs))
    assert activity is not None
    assert activity.pattern_type == SuspiciousPatternType.UNUSUAL_HOURS
    assert activity.alert_level == AlertLevel.MEDIUM
    assert activity.details["unusual_requests"] == 6
    assert 3 in activity.details["hours_accessed"]


def test_multiple_ips_detected():
    det = AdvancedSuspiciousActivityDetector()
    now = datetime.now()
    reqs = [
        make_req(ip_address="10.0.0.{0}".format(i), timestamp=now)
        for i in range(6)
    ]
    activity = run(det._detect_multiple_ips("u", reqs))
    assert activity is not None
    assert activity.details["unique_ips"] >= 5


def test_high_error_rate_min_requests_guard():
    det = AdvancedSuspiciousActivityDetector()
    # line 334: fewer than 10 requests -> None
    assert run(det._detect_high_error_rate("u", [make_req() for _ in range(3)])) is None


def test_high_error_rate_no_recent_returns_none():
    det = AdvancedSuspiciousActivityDetector()
    old = datetime.now() - timedelta(hours=2)
    reqs = [make_req(timestamp=old, response_code=500) for _ in range(12)]
    # line 346: no requests in last 5 min -> None
    assert run(det._detect_high_error_rate("u", reqs)) is None


def test_high_error_rate_detected():
    det = AdvancedSuspiciousActivityDetector()
    now = datetime.now()
    # 12 recent requests, all errors -> error_rate 1.0 >= 0.5
    reqs = [make_req(timestamp=now, response_code=500) for _ in range(12)]
    activity = run(det._detect_high_error_rate("u", reqs))
    assert activity is not None
    assert activity.pattern_type == SuspiciousPatternType.HIGH_ERROR_RATE
    assert activity.details["error_rate"] == 1.0


def test_endpoint_abuse_detected():
    det = AdvancedSuspiciousActivityDetector()
    now = datetime.now()
    reqs = [make_req(endpoint="/api/scrape", timestamp=now) for _ in range(25)]
    activity = run(det._detect_endpoint_abuse("u", reqs))
    assert activity is not None
    assert "/api/scrape" in activity.details["abused_endpoints"]


def test_bot_behavior_below_min_requests():
    det = AdvancedSuspiciousActivityDetector()
    # line 433: fewer than 20 requests -> None
    assert run(det._detect_bot_behavior("u", [make_req() for _ in range(5)])) is None


def test_bot_behavior_detected_regular_timing_same_ip():
    det = AdvancedSuspiciousActivityDetector()
    base = datetime.now()
    # 25 requests exactly 1 second apart, same IP, same endpoint, bot UA
    reqs = [
        make_req(
            timestamp=base + timedelta(seconds=i),
            ip_address="10.0.0.1",
            endpoint="/api/articles",
            user_agent="python-requests/2.0 bot",
        )
        for i in range(25)
    ]
    activity = run(det._detect_bot_behavior("u", reqs))
    assert activity is not None
    assert activity.pattern_type == SuspiciousPatternType.BOT_BEHAVIOR
    assert activity.confidence_score >= 0.6


def test_credential_stuffing_detected():
    det = AdvancedSuspiciousActivityDetector()
    now = datetime.now()
    reqs = [
        make_req(endpoint="/auth/login", response_code=401, timestamp=now)
        for _ in range(12)
    ]
    activity = run(det._detect_credential_stuffing("u", reqs))
    assert activity is not None
    assert activity.alert_level == AlertLevel.CRITICAL
    assert activity.details["failed_attempts"] >= 5


def test_credential_stuffing_old_failures_not_recent():
    det = AdvancedSuspiciousActivityDetector()
    old = datetime.now() - timedelta(hours=1)
    reqs = [
        make_req(endpoint="/auth/login", response_code=401, timestamp=old)
        for _ in range(12)
    ]
    # 12 total failures but none in last 5 min -> None (line 532 branch)
    assert run(det._detect_credential_stuffing("u", reqs)) is None


def test_data_scraping_requires_profile():
    det = AdvancedSuspiciousActivityDetector()
    # line 561: no profile -> None
    assert run(det._detect_data_scraping("nouser", [make_req()])) is None


def test_data_scraping_detected():
    det = AdvancedSuspiciousActivityDetector()
    profile = UserBehaviorProfile(user_id="u")
    profile.typical_endpoints = {"/articles": 1}  # low normal rate
    det.user_profiles["u"] = profile
    now = datetime.now()
    reqs = [make_req(endpoint="/articles/{0}".format(i), timestamp=now) for i in range(40)]
    activity = run(det._detect_data_scraping("u", reqs))
    assert activity is not None
    assert activity.pattern_type == SuspiciousPatternType.DATA_SCRAPING
    assert activity.details["data_requests"] >= 30


def test_ddos_pattern_detected():
    det = AdvancedSuspiciousActivityDetector()
    now = datetime.now()
    reqs = [
        make_req(timestamp=now, processing_time=0.01)
        for _ in range(110)
    ]
    activity = run(det._detect_ddos_pattern("u", reqs))
    assert activity is not None
    assert activity.alert_level == AlertLevel.CRITICAL
    assert activity.details["fast_requests"] >= 100


def test_unusual_user_agent_requires_profile():
    det = AdvancedSuspiciousActivityDetector()
    # line 664: no profile -> None
    assert run(det._detect_unusual_user_agent("nouser", [make_req()])) is None


def test_unusual_user_agent_detected():
    det = AdvancedSuspiciousActivityDetector()
    profile = UserBehaviorProfile(user_id="u")
    profile.user_agent_patterns = ["Mozilla/5.0"]
    det.user_profiles["u"] = profile
    reqs = [make_req(user_agent="sqlmap-scraper")]
    activity = run(det._detect_unusual_user_agent("u", reqs))
    assert activity is not None
    assert "sqlmap-scraper" in activity.details["unusual_user_agents"]


def test_unusual_user_agent_known_agent_not_flagged():
    det = AdvancedSuspiciousActivityDetector()
    profile = UserBehaviorProfile(user_id="u")
    profile.user_agent_patterns = ["Mozilla/5.0"]
    det.user_profiles["u"] = profile
    # Known agent -> no unusual agents collected -> None
    assert run(det._detect_unusual_user_agent("u", [make_req(user_agent="Mozilla/5.0")])) is None


def test_log_suspicious_activity_info_branch():
    det = AdvancedSuspiciousActivityDetector()
    activity = SuspiciousActivity(
        user_id="u",
        pattern_type=SuspiciousPatternType.UNUSUAL_HOURS,
        alert_level=AlertLevel.LOW,  # -> info branch (line 726)
        timestamp=datetime.now(),
        details={},
        ip_addresses=["10.0.0.1"],
        endpoints_accessed=["/x"],
        request_count=1,
        confidence_score=0.3,
    )
    # Should not raise
    run(det._log_suspicious_activity(activity))


def test_get_user_risk_score_no_alerts():
    det = AdvancedSuspiciousActivityDetector()
    # line 743: no alerts -> 0.0
    assert det.get_user_risk_score("nobody") == 0.0


def test_get_user_risk_score_with_alerts():
    det = AdvancedSuspiciousActivityDetector()
    now = datetime.now()
    det.active_alerts.append(
        SuspiciousActivity(
            user_id="u",
            pattern_type=SuspiciousPatternType.RAPID_REQUESTS,
            alert_level=AlertLevel.CRITICAL,
            timestamp=now,
            details={},
            ip_addresses=[],
            endpoints_accessed=[],
            request_count=1,
            confidence_score=1.0,
        )
    )
    score = det.get_user_risk_score("u")
    assert 0.0 < score <= 1.0


def test_get_recent_alerts_filters_by_time_and_level():
    det = AdvancedSuspiciousActivityDetector()
    now = datetime.now()
    recent = SuspiciousActivity(
        user_id="u",
        pattern_type=SuspiciousPatternType.RAPID_REQUESTS,
        alert_level=AlertLevel.HIGH,
        timestamp=now,
        details={},
        ip_addresses=[],
        endpoints_accessed=[],
        request_count=1,
        confidence_score=0.9,
    )
    old = SuspiciousActivity(
        user_id="u",
        pattern_type=SuspiciousPatternType.RAPID_REQUESTS,
        alert_level=AlertLevel.HIGH,
        timestamp=now - timedelta(days=3),
        details={},
        ip_addresses=[],
        endpoints_accessed=[],
        request_count=1,
        confidence_score=0.9,
    )
    det.active_alerts.append(recent)
    det.active_alerts.append(old)
    # NOTE (genuine source behavior): get_recent_alerts compares
    # alert.alert_level.value >= min_alert_level.value, i.e. it string-compares
    # the enum *values* ("high", "low", ...) instead of severity rank. This is a
    # latent bug (lexical ordering != severity ordering). We pin min level to
    # HIGH so the level filter passes ("high" >= "high") and assert the time
    # window filter drops the 3-day-old alert while keeping the recent one.
    alerts = det.get_recent_alerts(hours=24, min_alert_level=AlertLevel.HIGH)
    assert recent in alerts
    assert old not in alerts
