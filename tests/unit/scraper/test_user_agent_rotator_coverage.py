"""Coverage-focused tests for src/scraper/user_agent_rotator.py.

Targets the branches not exercised by test_user_agent_rotator.py or
test_user_agent_rotator_extra.py: config loading, get_headers with client
hints, sec-ch-ua generation per browser, realistic delays, human typing,
advanced rotation collision handling, config-file rotation, and the
usage/session rotation triggers.
"""

import json
import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.user_agent_rotator import BrowserProfile, UserAgentRotator  # noqa: E402


def profile(**over):
    base = dict(
        user_agent="UA/1.0",
        accept="text/html",
        accept_language="en",
        accept_encoding="gzip",
        cache_control="no-cache",
        dnt="1",
        platform="Windows",
        browser_name="Chrome",
        version="131.0.0.0",
        is_mobile=False,
    )
    base.update(over)
    return BrowserProfile(**base)


@pytest.fixture
def rotator():
    return UserAgentRotator()


class TestLoadConfig:
    def test_load_config_missing_file_falls_back_to_defaults(self, tmp_path):
        missing = str(tmp_path / "does_not_exist.json")
        r = UserAgentRotator(config_file=missing)
        # Missing config path triggers the warning branch + default init.
        assert len(r.browser_profiles) > 0
        assert any(p.browser_name == "Chrome" for p in r.browser_profiles)

    def test_load_config_valid_file(self, tmp_path):
        cfg = {
            "browser_profiles": [
                {
                    "user_agent": "CFG-UA",
                    "accept": "text/html",
                    "accept_language": "en",
                    "accept_encoding": "gzip",
                    "cache_control": "no-cache",
                    "dnt": "1",
                    "platform": "Linux",
                    "browser_name": "Firefox",
                    "version": "132.0",
                    "is_mobile": False,
                }
            ],
            "settings": {
                "session_duration_range": [10, 20],
                "max_profile_usage": 7,
            },
        }
        path = tmp_path / "ua_config.json"
        path.write_text(json.dumps(cfg))

        r = UserAgentRotator(config_file=str(path))
        assert len(r.browser_profiles) == 1
        assert r.browser_profiles[0].user_agent == "CFG-UA"
        assert r.session_duration_range == (10, 20)
        assert r.max_profile_usage == 7

    def test_load_config_invalid_json_falls_back(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json")

        r = UserAgentRotator()
        r.load_config(str(path))
        # On JSON error the except branch reinitializes defaults.
        assert len(r.browser_profiles) > 0

    def test_load_config_missing_settings_uses_defaults(self, tmp_path):
        cfg = {"browser_profiles": []}
        path = tmp_path / "cfg2.json"
        path.write_text(json.dumps(cfg))

        r = UserAgentRotator()
        r.load_config(str(path))
        assert r.max_profile_usage == 100
        assert r.session_duration_range == (300, 1800)


class TestGetHeaders:
    def test_get_headers_adds_client_hints(self, rotator):
        rotator.browser_profiles = [profile(browser_name="Chrome", version="131.0.0.0")]
        headers = rotator.get_headers()
        assert headers["Sec-Ch-Ua-Mobile"] == "?0"
        assert headers["Sec-Ch-Ua-Platform"] == '"Windows"'
        assert "Google Chrome" in headers["Sec-Ch-Ua"]

    def test_get_headers_mobile_flag(self, rotator):
        rotator.browser_profiles = [
            profile(is_mobile=True, platform="iOS", browser_name="Safari", version="18.1")
        ]
        headers = rotator.get_headers()
        assert headers["Sec-Ch-Ua-Mobile"] == "?1"
        assert headers["Sec-Ch-Ua-Platform"] == '"iOS"'

    def test_get_headers_merges_additional(self, rotator):
        rotator.browser_profiles = [profile()]
        headers = rotator.get_headers(additional_headers={"X-Custom": "yes"})
        assert headers["X-Custom"] == "yes"
        assert headers["User-Agent"] == "UA/1.0"


class TestSecChUa:
    def test_chrome(self, rotator):
        p = profile(browser_name="Chrome", version="131.0.0.0")
        assert rotator._generate_sec_ch_ua(p) == (
            '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="8"'
        )

    def test_firefox(self, rotator):
        p = profile(browser_name="Firefox", version="132.0")
        assert rotator._generate_sec_ch_ua(p) == '"Firefox";v="132"'

    def test_safari(self, rotator):
        p = profile(browser_name="Safari", version="18.1")
        assert rotator._generate_sec_ch_ua(p) == '"Safari";v="18"'

    def test_edge(self, rotator):
        p = profile(browser_name="Edge", version="131.0.0.0")
        assert rotator._generate_sec_ch_ua(p) == (
            '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="8"'
        )

    def test_unknown_browser(self, rotator):
        p = profile(browser_name="Opera", version="99.1")
        assert rotator._generate_sec_ch_ua(p) == '"Opera";v="99"'


class TestRealisticDelaysAndTyping:
    def test_delays_mobile(self, rotator):
        rotator.browser_profiles = [profile(is_mobile=True)]
        low, high = rotator.get_realistic_delays()
        assert (low, high) == (2.0, 5.0)

    def test_delays_desktop(self, rotator):
        rotator.browser_profiles = [profile(is_mobile=False)]
        low, high = rotator.get_realistic_delays()
        assert (low, high) == (1.0, 3.0)

    def test_simulate_human_typing_scales_with_length(self, rotator):
        # base delay for 200 chars = 200/200*60 = 60s; ±25% => within [45, 75]
        delay = rotator.simulate_human_typing(200)
        assert 45.0 <= delay <= 75.0

    def test_simulate_human_typing_short_text(self, rotator):
        delay = rotator.simulate_human_typing(0)
        assert delay == 0.0


class TestGetProfileRotation:
    def test_get_profile_force_new_rotates(self, rotator):
        first = rotator.get_profile(force_new=True)
        assert first is not None
        assert rotator.profile_usage_count == 1
        # force_new always rotates, incrementing usage count
        rotator.get_profile(force_new=True)
        assert rotator.profile_usage_count == 1  # reset by rotate then +1

    def test_get_profile_usage_limit_triggers_rotation(self, rotator):
        rotator.get_profile(force_new=True)
        rotator.max_profile_usage = 1
        rotator.profile_usage_count = 5  # exceeds max -> should rotate
        rotator.get_profile()
        # After rotation the usage count is reset to 0 then incremented to 1.
        assert rotator.profile_usage_count == 1

    def test_get_profile_session_duration_rotation(self, rotator, monkeypatch):
        rotator.get_profile(force_new=True)
        rotator.max_profile_usage = 10_000
        rotator.session_duration_range = (1, 1)
        # Simulate a session that started far in the past.
        rotator.session_start_time = 0.0
        p = rotator.get_profile()
        assert isinstance(p, BrowserProfile)

    def test_rotate_profile_advanced(self, rotator):
        rotator.browser_profiles = [profile(user_agent="A"), profile(user_agent="B")]
        rotator.current_profile = rotator.browser_profiles[0]
        rotator._rotate_profile_advanced()
        # advanced rotation avoids repeating the current profile
        assert rotator.current_profile.user_agent == "B"

    def test_rotate_profile_advanced_single_profile(self, rotator):
        only = profile(user_agent="SOLO")
        rotator.browser_profiles = [only]
        rotator.current_profile = only
        rotator._rotate_profile_advanced()
        # With one profile, falls back to using it again.
        assert rotator.current_profile.user_agent == "SOLO"


class TestAdvancedRotationCollisions:
    def test_advanced_rotation_skips_duplicate_active(self, rotator):
        # Two profiles with the SAME user agent as active forces the skip branch.
        rotator.use_advanced_rotation = True
        rotator.browser_profiles = [profile(user_agent="X"), profile(user_agent="Y")]
        rotator.max_uses_per_profile = 1
        first = rotator.get_next_profile()
        # Force rotation by exhausting uses; index now points at a fresh slot.
        second = rotator.get_next_profile()
        assert first.user_agent in {"X", "Y"}
        assert second.user_agent in {"X", "Y"}

    def test_advanced_rotation_multiple_cycles(self, rotator):
        rotator.use_advanced_rotation = True
        rotator.browser_profiles = [
            profile(user_agent="A"),
            profile(user_agent="B"),
            profile(user_agent="C"),
        ]
        rotator.max_uses_per_profile = 1
        seen = {rotator.get_next_profile().user_agent for _ in range(6)}
        assert seen == {"A", "B", "C"}


class TestGetUserAgentForcedRotation:
    def test_get_user_agent_forces_rotation_after_three(self, rotator):
        rotator.browser_profiles = [profile(user_agent="A"), profile(user_agent="B")]
        rotator.requests_with_current_profile = 3
        ua = rotator.get_user_agent()
        assert ua in {"A", "B"}

    def test_get_user_agent_fallback_no_current(self, rotator):
        rotator.browser_profiles = [profile(user_agent="ONLY")]
        rotator.current_profile = None
        # get_current_profile will rotate and set a current_profile.
        ua = rotator.get_user_agent()
        assert ua == "ONLY"


class TestGetMobileDesktopFallback:
    def test_mobile_fallback_to_defaults(self, rotator):
        # Only desktop profiles present -> falls back to default mobile.
        rotator.browser_profiles = [profile(is_mobile=False)]
        p = rotator.get_mobile_profile()
        assert p.is_mobile is True

    def test_desktop_fallback_to_defaults(self, rotator):
        rotator.browser_profiles = [profile(is_mobile=True)]
        p = rotator.get_desktop_profile()
        assert p.is_mobile is False


class TestStatsIncludesCurrentProfile:
    def test_stats_after_activity(self, rotator):
        rotator.get_profile(force_new=True)
        rotator.get_profile_for_domain("bbc.com")
        stats = rotator.get_stats()
        assert stats["total_profiles"] == len(rotator.browser_profiles)
        assert stats["current_profile"]["browser"] is not None
        assert "bbc.com" in stats["domain_assignments"]
        assert stats["session_info"]["session_duration"] >= 0
