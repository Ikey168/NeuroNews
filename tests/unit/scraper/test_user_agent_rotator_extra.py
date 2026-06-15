"""Additional tests for src/scraper/user_agent_rotator.py."""

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
        user_agent="UA/1.0", accept="text/html", accept_language="en",
        accept_encoding="gzip", cache_control="no-cache", dnt="1",
        platform="Windows", browser_name="Chrome", version="131", is_mobile=False,
    )
    base.update(over)
    return BrowserProfile(**base)


@pytest.fixture
def rotator():
    return UserAgentRotator()


class TestBrowserProfile:
    def test_desktop_headers(self):
        h = profile().get_headers()
        assert h["User-Agent"] == "UA/1.0"
        assert "Sec-Fetch-Dest" not in h

    def test_mobile_headers(self):
        h = profile(is_mobile=True).get_headers()
        assert h["Sec-Fetch-Dest"] == "document"
        assert h["Sec-Fetch-Mode"] == "navigate"


class TestProfileSelection:
    def test_has_default_profiles(self, rotator):
        assert len(rotator.browser_profiles) > 0

    def test_profiles_property(self, rotator):
        rotator.profiles = [profile()]
        assert rotator.browser_profiles == [profile()]

    def test_get_random_profile(self, rotator):
        p = rotator.get_random_profile()
        assert isinstance(p, BrowserProfile)

    def test_get_next_profile_sequential(self, rotator):
        rotator.use_advanced_rotation = False
        rotator.browser_profiles = [profile(user_agent="A"), profile(user_agent="B")]
        first = rotator.get_next_profile()
        second = rotator.get_next_profile()
        assert {first.user_agent, second.user_agent} == {"A", "B"}

    def test_get_next_profile_advanced(self, rotator):
        rotator.use_advanced_rotation = True
        rotator.browser_profiles = [profile(user_agent="A"), profile(user_agent="B")]
        rotator.max_uses_per_profile = 2
        p1 = rotator.get_next_profile()
        p2 = rotator.get_next_profile()  # same active (uses < max)
        assert p1.user_agent == p2.user_agent

    def test_get_profile_for_domain_stable(self, rotator):
        p1 = rotator.get_profile_for_domain("bbc.com")
        p2 = rotator.get_profile_for_domain("bbc.com")
        assert p1.user_agent == p2.user_agent

    def test_get_browser_specific(self, rotator):
        rotator.browser_profiles = [profile(browser_name="Firefox", user_agent="FF")]
        assert rotator.get_browser_specific_profile("firefox").user_agent == "FF"

    def test_get_browser_specific_fallback(self, rotator):
        rotator.browser_profiles = [profile(browser_name="Chrome")]
        assert isinstance(rotator.get_browser_specific_profile("Opera"), BrowserProfile)

    def test_mobile_and_desktop(self, rotator):
        assert rotator.get_mobile_profile().is_mobile is True
        assert rotator.get_desktop_profile().is_mobile is False


class TestMutationAndPersistence:
    def test_add_remove_profile(self, rotator):
        p = profile(user_agent="CUSTOM")
        rotator.add_custom_profile(p)
        assert p in rotator.browser_profiles
        rotator.remove_profile(p)
        assert p not in rotator.browser_profiles

    def test_reset_profile_usage(self, rotator):
        rotator.get_random_profile()
        rotator.reset_profile_usage()
        assert rotator.current_index == 0
        assert rotator.profile_usage == {}

    def test_save_and_load_roundtrip(self, rotator, tmp_path):
        rotator.browser_profiles = [profile(user_agent="SAVED")]
        out = tmp_path / "profiles.json"
        rotator.save_profiles_to_file(str(out))
        data = json.loads(out.read_text())
        assert data[0]["user_agent"] == "SAVED"
        # Loading a rotator from that file restores the profiles
        loaded = UserAgentRotator(profile_file=str(out))
        assert any(p.user_agent == "SAVED" for p in loaded.browser_profiles)


class TestPerformanceTracking:
    def test_record_and_get_performance(self, rotator):
        p = profile(user_agent="PERF")
        rotator.record_profile_performance(p, success=True, response_time=1.0)
        rotator.record_profile_performance(p, success=False, response_time=3.0)
        stats = rotator.get_profile_performance(p)
        assert stats["total_requests"] == 2
        assert stats["successful_requests"] == 1
        assert stats["failed_requests"] == 1
        assert stats["average_response_time"] == 2.0

    def test_get_performance_unknown_profile(self, rotator):
        stats = rotator.get_profile_performance(profile(user_agent="NEW"))
        assert stats["total_requests"] == 0
        assert stats["average_response_time"] == 0.0


class TestUserAgentAndHeaders:
    def test_get_user_agent(self, rotator):
        ua = rotator.get_user_agent()
        assert isinstance(ua, str) and ua

    def test_get_random_headers(self, rotator):
        headers = rotator.get_random_headers()
        assert "User-Agent" in headers

    def test_get_current_profile_rotates(self, rotator):
        p = rotator.get_current_profile()
        assert isinstance(p, BrowserProfile)
        assert rotator.current_profile is not None

    def test_should_rotate_when_no_current(self, rotator):
        rotator.current_profile = None
        assert rotator._should_rotate_profile() is True
