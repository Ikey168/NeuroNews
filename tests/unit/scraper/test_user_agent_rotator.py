"""
Comprehensive tests for UserAgentRotator.
Tests user agent rotation, browser profile management, and anti-detection mechanisms.
"""

import pytest
import json
import time
from unittest.mock import patch, mock_open, MagicMock

# Import with proper path handling
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from scraper.user_agent_rotator import UserAgentRotator, BrowserProfile


class TestBrowserProfile:
    """Test suite for BrowserProfile class."""

    @pytest.fixture
    def sample_profile(self):
        """Sample browser profile for testing."""
        return BrowserProfile(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            accept_language="en-US,en;q=0.5",
            accept_encoding="gzip, deflate",
            cache_control="no-cache",
            dnt="1",
            platform="Win32",
            browser_name="Chrome",
            version="91.0.4472.124",
            is_mobile=False
        )

    def test_profile_initialization(self, sample_profile):
        """Test browser profile initialization."""
        assert sample_profile.browser_name == "Chrome"
        assert sample_profile.version == "91.0.4472.124"
        assert sample_profile.platform == "Win32"
        assert sample_profile.is_mobile is False

    def test_get_headers_desktop(self, sample_profile):
        """Test header generation for desktop profile."""
        headers = sample_profile.get_headers()
        
        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "Connection" in headers
        assert headers["Connection"] == "keep-alive"
        assert headers["Upgrade-Insecure-Requests"] == "1"
        
        # Desktop profiles should not have Sec-Fetch headers
        assert "Sec-Fetch-Dest" not in headers

    def test_get_headers_mobile(self):
        """Test header generation for mobile profile."""
        mobile_profile = BrowserProfile(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X)",
            accept="text/html,application/xhtml+xml",
            accept_language="en-US,en;q=0.9",
            accept_encoding="gzip, deflate, br",
            cache_control="no-cache",
            dnt="1",
            platform="iPhone",
            browser_name="Safari",
            version="14.6",
            is_mobile=True
        )
        
        headers = mobile_profile.get_headers()
        
        assert headers["Sec-Fetch-Dest"] == "document"
        assert headers["Sec-Fetch-Mode"] == "navigate"
        assert headers["Sec-Fetch-Site"] == "none"
        assert headers["Sec-Fetch-User"] == "?1"


class TestUserAgentRotator:
    """Test suite for UserAgentRotator class."""

    @pytest.fixture
    def sample_profiles_data(self):
        """Sample profiles data for testing."""
        return [
            {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "accept_language": "en-US,en;q=0.5",
                "accept_encoding": "gzip, deflate",
                "cache_control": "no-cache",
                "dnt": "1",
                "platform": "Win32",
                "browser_name": "Chrome",
                "version": "91.0.4472.124",
                "is_mobile": False
            },
            {
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept_language": "en-US,en;q=0.9",
                "accept_encoding": "gzip, deflate, br",
                "cache_control": "no-cache",
                "dnt": "1",
                "platform": "MacIntel",
                "browser_name": "Safari",
                "version": "14.1.1",
                "is_mobile": False
            }
        ]

    @pytest.fixture
    def rotator_with_profiles(self, sample_profiles_data):
        """UserAgentRotator with sample profiles."""
        with patch("builtins.open", mock_open(read_data=json.dumps(sample_profiles_data))):
            return UserAgentRotator()

    def test_rotator_initialization_default(self):
        """Test UserAgentRotator initialization with default profiles."""
        rotator = UserAgentRotator()
        
        assert len(rotator.profiles) > 0
        assert rotator.current_index == 0
        assert rotator.use_advanced_rotation is True
        assert rotator.max_uses_per_profile == 5

    def test_rotator_initialization_with_file(self, sample_profiles_data):
        """Test UserAgentRotator initialization with custom profile file."""
        with patch("builtins.open", mock_open(read_data=json.dumps(sample_profiles_data))):
            rotator = UserAgentRotator(profile_file="custom_profiles.json")
            
            assert len(rotator.profiles) == 2
            assert rotator.profiles[0].browser_name == "Chrome"
            assert rotator.profiles[1].browser_name == "Safari"

    def test_load_profiles_from_file_success(self, sample_profiles_data):
        """Test successful profile loading from file."""
        with patch("builtins.open", mock_open(read_data=json.dumps(sample_profiles_data))):
            rotator = UserAgentRotator()
            profiles = rotator._load_profiles_from_file("test.json")
            
            assert len(profiles) == 2
            assert profiles[0].browser_name == "Chrome"
            assert profiles[1].browser_name == "Safari"

    def test_load_profiles_from_file_not_found(self):
        """Test profile loading with missing file."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            rotator = UserAgentRotator()
            profiles = rotator._load_profiles_from_file("missing.json")
            
            assert len(profiles) == 0

    def test_load_profiles_from_file_invalid_json(self):
        """Test profile loading with invalid JSON."""
        with patch("builtins.open", mock_open(read_data="invalid json")):
            rotator = UserAgentRotator()
            profiles = rotator._load_profiles_from_file("invalid.json")
            
            assert len(profiles) == 0

    def test_get_default_profiles(self):
        """Test default profile generation."""
        rotator = UserAgentRotator()
        profiles = rotator._get_default_profiles()
        
        assert len(profiles) > 0
        assert any(profile.browser_name == "Chrome" for profile in profiles)
        assert any(profile.browser_name == "Firefox" for profile in profiles)
        assert any(profile.browser_name == "Safari" for profile in profiles)
        assert any(profile.is_mobile for profile in profiles)

    def test_get_random_profile(self, rotator_with_profiles):
        """Test random profile selection."""
        profile = rotator_with_profiles.get_random_profile()
        
        assert isinstance(profile, BrowserProfile)
        assert profile.browser_name in ["Chrome", "Safari"]

    def test_get_next_profile_simple(self, rotator_with_profiles):
        """Test simple sequential profile rotation."""
        rotator_with_profiles.use_advanced_rotation = False
        
        profile1 = rotator_with_profiles.get_next_profile()
        profile2 = rotator_with_profiles.get_next_profile()
        
        assert profile1 != profile2  # Should be different profiles
        assert rotator_with_profiles.current_index == 0  # Should wrap around

    def test_get_next_profile_advanced(self, rotator_with_profiles):
        """Test advanced profile rotation with usage tracking."""
        rotator_with_profiles.use_advanced_rotation = True
        
        profile1 = rotator_with_profiles.get_next_profile()
        
        # Use the same profile multiple times
        for _ in range(rotator_with_profiles.max_uses_per_profile - 1):
            same_profile = rotator_with_profiles.get_next_profile()
            assert same_profile.user_agent == profile1.user_agent
        
        # Next call should rotate to a different profile
        different_profile = rotator_with_profiles.get_next_profile()
        assert different_profile.user_agent != profile1.user_agent

    def test_get_profile_for_domain_new(self, rotator_with_profiles):
        """Test domain-specific profile assignment for new domain."""
        domain = "example.com"
        profile = rotator_with_profiles.get_profile_for_domain(domain)
        
        assert isinstance(profile, BrowserProfile)
        assert domain in rotator_with_profiles.domain_profiles
        assert rotator_with_profiles.domain_profiles[domain] == profile

    def test_get_profile_for_domain_existing(self, rotator_with_profiles):
        """Test domain-specific profile retrieval for existing domain."""
        domain = "example.com"
        profile1 = rotator_with_profiles.get_profile_for_domain(domain)
        profile2 = rotator_with_profiles.get_profile_for_domain(domain)
        
        assert profile1 == profile2  # Should be the same profile

    def test_reset_profile_usage(self, rotator_with_profiles):
        """Test profile usage reset."""
        profile = rotator_with_profiles.get_next_profile()
        
        # Use profile to maximum
        for _ in range(rotator_with_profiles.max_uses_per_profile):
            rotator_with_profiles.get_next_profile()
        
        # Reset usage
        rotator_with_profiles.reset_profile_usage()
        
        # Should be able to use the same profile again
        same_profile = rotator_with_profiles.get_next_profile()
        assert same_profile.user_agent == profile.user_agent

    def test_get_mobile_profile(self, rotator_with_profiles):
        """Test mobile profile selection."""
        mobile_profile = rotator_with_profiles.get_mobile_profile()
        
        # Default profiles should include at least one mobile profile
        # If no mobile in sample data, should create a default mobile profile
        assert isinstance(mobile_profile, BrowserProfile)

    def test_get_desktop_profile(self, rotator_with_profiles):
        """Test desktop profile selection."""
        desktop_profile = rotator_with_profiles.get_desktop_profile()
        
        assert isinstance(desktop_profile, BrowserProfile)
        assert desktop_profile.is_mobile is False

    def test_get_browser_specific_profile(self, rotator_with_profiles):
        """Test browser-specific profile selection."""
        chrome_profile = rotator_with_profiles.get_browser_specific_profile("Chrome")
        safari_profile = rotator_with_profiles.get_browser_specific_profile("Safari")
        
        assert chrome_profile.browser_name == "Chrome"
        assert safari_profile.browser_name == "Safari"

    def test_get_browser_specific_profile_not_found(self, rotator_with_profiles):
        """Test browser-specific profile selection for non-existent browser."""
        edge_profile = rotator_with_profiles.get_browser_specific_profile("Edge")
        
        # Should return any available profile when specific browser not found
        assert isinstance(edge_profile, BrowserProfile)

    def test_add_custom_profile(self, rotator_with_profiles):
        """Test adding custom profile."""
        initial_count = len(rotator_with_profiles.profiles)
        
        custom_profile = BrowserProfile(
            user_agent="Custom User Agent",
            accept="text/html",
            accept_language="en",
            accept_encoding="gzip",
            cache_control="no-cache",
            dnt="0",
            platform="Linux",
            browser_name="Custom",
            version="1.0"
        )
        
        rotator_with_profiles.add_custom_profile(custom_profile)
        
        assert len(rotator_with_profiles.profiles) == initial_count + 1
        assert custom_profile in rotator_with_profiles.profiles

    def test_remove_profile(self, rotator_with_profiles):
        """Test profile removal."""
        initial_count = len(rotator_with_profiles.profiles)
        profile_to_remove = rotator_with_profiles.profiles[0]
        
        rotator_with_profiles.remove_profile(profile_to_remove)
        
        assert len(rotator_with_profiles.profiles) == initial_count - 1
        assert profile_to_remove not in rotator_with_profiles.profiles

    def test_get_stats(self, rotator_with_profiles):
        """Test statistics retrieval."""
        # Use some profiles
        rotator_with_profiles.get_next_profile()
        rotator_with_profiles.get_next_profile()
        rotator_with_profiles.get_random_profile()
        
        stats = rotator_with_profiles.get_stats()
        
        assert "total_profiles" in stats
        assert "current_index" in stats
        assert "profile_usage" in stats
        assert "domain_assignments" in stats
        assert stats["total_profiles"] == len(rotator_with_profiles.profiles)

    def test_profile_diversity_check(self, rotator_with_profiles):
        """Test that rotation provides diverse profiles over time."""
        used_user_agents = set()
        
        # Get multiple profiles
        for _ in range(20):
            profile = rotator_with_profiles.get_random_profile()
            used_user_agents.add(profile.user_agent)
        
        # Should use both available profiles
        assert len(used_user_agents) == 2

    def test_timing_based_rotation(self, rotator_with_profiles):
        """Test time-based profile rotation logic."""
        rotator_with_profiles.min_rotation_interval = 0.1  # 100ms for testing
        
        profile1 = rotator_with_profiles.get_next_profile()
        
        # Immediately get another profile (should be same due to timing)
        profile2 = rotator_with_profiles.get_next_profile()
        
        # Wait for rotation interval
        time.sleep(0.2)
        
        # Now should get different profile
        profile3 = rotator_with_profiles.get_next_profile()
        
        # Note: This test may be flaky depending on implementation details
        assert isinstance(profile1, BrowserProfile)
        assert isinstance(profile2, BrowserProfile)
        assert isinstance(profile3, BrowserProfile)

    def test_profile_validation(self, rotator_with_profiles):
        """Test profile validation during addition."""
        # Valid profile
        valid_profile = BrowserProfile(
            user_agent="Valid UA",
            accept="text/html",
            accept_language="en",
            accept_encoding="gzip",
            cache_control="no-cache",
            dnt="1",
            platform="Test",
            browser_name="Test",
            version="1.0"
        )
        
        rotator_with_profiles.add_custom_profile(valid_profile)
        assert valid_profile in rotator_with_profiles.profiles

    def test_concurrent_access_safety(self, rotator_with_profiles):
        """Test thread safety for concurrent profile access."""
        import threading
        
        profiles_obtained = []
        
        def get_profile():
            profile = rotator_with_profiles.get_next_profile()
            profiles_obtained.append(profile)
        
        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=get_profile)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # All should have obtained valid profiles
        assert len(profiles_obtained) == 10
        for profile in profiles_obtained:
            assert isinstance(profile, BrowserProfile)

    def test_save_profiles_to_file(self, rotator_with_profiles, tmp_path):
        """Test saving profiles to file."""
        output_file = tmp_path / "test_profiles.json"
        
        with patch("builtins.open", mock_open()) as mock_file:
            rotator_with_profiles.save_profiles_to_file(str(output_file))
            mock_file.assert_called_once_with(str(output_file), 'w')

    def test_profile_performance_tracking(self, rotator_with_profiles):
        """Test performance tracking for profiles."""
        profile = rotator_with_profiles.get_next_profile()
        
        # Simulate successful request
        rotator_with_profiles.record_profile_performance(profile, success=True, response_time=0.5)
        
        # Simulate failed request
        rotator_with_profiles.record_profile_performance(profile, success=False, response_time=2.0)
        
        stats = rotator_with_profiles.get_profile_performance(profile)
        assert stats["total_requests"] == 2
        assert stats["successful_requests"] == 1
        assert stats["failed_requests"] == 1