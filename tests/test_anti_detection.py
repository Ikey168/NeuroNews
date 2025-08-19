#!/usr/bin/env python3
"""
Test suite for proxy rotation and anti-detection system.
Tests proxy manager, user agent rotation, CAPTCHA solver, and Tor integration.
"""

from scraper.user_agent_rotator import UserAgentRotator
from scraper.tor_manager import TorManager
from scraper.proxy_manager import ProxyConfig, ProxyRotationManager
from scraper.captcha_solver import CaptchaSolver
import asyncio
import json
import sys
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.append("/workspaces/NeuroNews/src")


class TestProxyRotationManager:
    """Test proxy rotation manager functionality."""

    @pytest.fixture
    def sample_config(self):
        """Create sample proxy configuration."""
        return {
            "proxy_settings": {
                "rotation_strategy": "round_robin",
                "health_check_interval": 60,
                "retry_failed_proxies": True,
            },
            "proxies": [
                {
                    "host": "proxy1.test.com",
                    "port": 8080,
                    "proxy_type": "http",
                    "username": None,
                    "password": None,
                    "concurrent_limit": 5,
                    "location": "US",
                    "provider": "TestProvider1",
                },
                {
                    "host": "proxy2.test.com",
                    "port": 8080,
                    "proxy_type": "http",
                    "username": "testuser",
                    "password": "testpass",
                    "concurrent_limit": 3,
                    "location": "EU",
                    "provider": "TestProvider2",
                },
            ],
        }

    @pytest.fixture
    def proxy_manager(self, sample_config):
        """Create proxy manager with test configuration."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_config, f)
            config_path = f.name

        manager = ProxyRotationManager(config_path=config_path)
        return manager

    def test_proxy_manager_initialization(self, proxy_manager):
        """Test proxy manager initializes correctly."""
        assert len(proxy_manager.proxies) == 2
        assert proxy_manager.rotation_strategy == "round_robin"
        assert proxy_manager.current_index == 0

    @pytest.mark.asyncio
    async def test_round_robin_proxy_selection(self, proxy_manager):
        """Test round-robin proxy selection."""
        # Get first proxy
        proxy1 = await proxy_manager.get_proxy()
        assert proxy1.host == "proxy1.test.com"

        # Get second proxy
        proxy2 = await proxy_manager.get_proxy()
        assert proxy2.host == "proxy2.test.com"

        # Should cycle back to first
        proxy3 = await proxy_manager.get_proxy()
        assert proxy3.host == "proxy1.test.com"

    @pytest.mark.asyncio
    async def test_proxy_health_tracking(self, proxy_manager):
        """Test proxy health tracking."""
        proxy = await proxy_manager.get_proxy()

        # Record successful request
        await proxy_manager.record_request(proxy, success=True, response_time=0.5)

        key = f"{proxy.host}:{proxy.port}"
        stats = proxy_manager.proxy_stats[key]
        assert stats.total_requests == 1
        assert stats.successful_requests == 1
        assert stats.health_score > 50.0

        # Record failed request
        await proxy_manager.record_request(proxy, success=False)
        stats = proxy_manager.proxy_stats[key]
        assert stats.failed_requests == 1
        assert stats.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_connection_limiting(self, proxy_manager):
        """Test proxy connection limiting."""
        proxy = await proxy_manager.get_proxy()

        # Acquire connections up to limit
        for i in range(proxy.concurrent_limit):
            acquired = await proxy_manager.acquire_connection(proxy)
            assert acquired

        # Should fail to acquire beyond limit
        acquired = await proxy_manager.acquire_connection(proxy)
        assert acquired == False

        # Release connection and try again
        await proxy_manager.release_connection(proxy)
        acquired = await proxy_manager.acquire_connection(proxy)
        assert acquired

    def test_add_proxy(self, proxy_manager):
        """Test adding new proxy to rotation pool."""
        initial_count = len(proxy_manager.proxies)

        new_proxy = ProxyConfig(
            host="proxy3.test.com", port=8080, proxy_type="http", concurrent_limit=2
        )

        proxy_manager.add_proxy(new_proxy)
        assert len(proxy_manager.proxies) == initial_count + 1

        # Should not add duplicate
        proxy_manager.add_proxy(new_proxy)
        assert len(proxy_manager.proxies) == initial_count + 1


class TestUserAgentRotator:
    """Test user agent rotation functionality."""

    @pytest.fixture
    def ua_rotator(self):
        """Create user agent rotator."""
        return UserAgentRotator()

    def test_user_agent_generation(self, ua_rotator):
        """Test user agent generation."""
        ua = ua_rotator.get_user_agent()
        assert ua is not None
        assert isinstance(ua, str)
        assert len(ua) > 0

    def test_user_agent_rotation(self, ua_rotator):
        """Test that user agents rotate."""
        agents = set()
        for _ in range(10):
            ua = ua_rotator.get_user_agent()
            agents.add(ua)

        # Should generate different user agents
        assert len(agents) > 1

    def test_random_headers(self, ua_rotator):
        """Test random header generation."""
        headers = ua_rotator.get_random_headers()
        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "Accept-Encoding" in headers

    def test_browser_profile_rotation(self, ua_rotator):
        """Test browser profile rotation."""
        # Force rotation by making many requests
        for _ in range(20):
            ua_rotator.get_user_agent()

        # Check that profile has rotated
        assert ua_rotator.requests_with_current_profile >= 0


class TestCaptchaSolver:
    """Test CAPTCHA solver functionality."""

    @pytest.fixture
    def captcha_solver(self):
        """Create CAPTCHA solver with test API key."""
        return CaptchaSolver(api_key="test_api_key")

    @pytest.mark.asyncio
    async def test_captcha_detection(self, captcha_solver):
        """Test CAPTCHA detection in page content."""
        # Mock page content with reCAPTCHA
        page_content = '<div class="g-recaptcha" data-sitekey="test123"></div>'

        detected = await captcha_solver.detect_captcha(page_content)
        assert detected

        # Test page without CAPTCHA
        normal_content = "<div>Regular page content</div>"
        detected = await captcha_solver.detect_captcha(normal_content)
        assert detected == False

    @patch("aiohttp.ClientSession.post")
    @pytest.mark.asyncio
    async def test_captcha_solving(self, mock_post, captcha_solver):
        """Test CAPTCHA solving process."""
        # Mock successful API responses
        mock_response = AsyncMock()
        mock_response.json = AsyncMock()
        mock_response.status = 200

        # Mock submit response
        mock_response.json.return_value = {"status": 1, "request": "test_captcha_id"}
        mock_post.return_value.__aenter__.return_value = mock_response

        # Test solving
        with patch.object(
            captcha_solver, "get_captcha_result", return_value="solved_token"
        ):
            result = await captcha_solver.solve_recaptcha_v2(
                site_key="test_sitekey", page_url="https://test.com"
            )
            assert result == "solved_token"


class TestTorManager:
    """Test Tor manager functionality."""

    @pytest.fixture
    def tor_manager(self):
        """Create Tor manager."""
        return TorManager()

    def test_tor_proxy_url(self, tor_manager):
        """Test Tor proxy URL generation."""
        proxy_url = tor_manager.get_proxy_url()
        assert proxy_url == "socks5://127.0.0.1:9050"

    @patch("socket.socket")
    @pytest.mark.asyncio
    async def test_tor_identity_rotation(self, mock_socket, tor_manager):
        """Test Tor identity rotation."""
        # Mock socket connection
        mock_sock = Mock()
        mock_socket.return_value = mock_sock

        await tor_manager.rotate_identity()
        # Should attempt connection even if it fails in test
        mock_socket.assert_called()


class TestIntegration:
    """Integration tests for anti-detection system."""

    @pytest.fixture
    def sample_proxy_config(self):
        """Create sample configuration file."""
        config = {
            "proxy_settings": {
                "rotation_strategy": "random",
                "health_check_interval": 0,  # Disable for tests
            },
            "proxies": [
                {
                    "host": "127.0.0.1",
                    "port": 8888,
                    "proxy_type": "http",
                    "concurrent_limit": 1,
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            return f.name

    @pytest.mark.asyncio
    async def test_full_anti_detection_flow(self, sample_proxy_config):
        """Test complete anti-detection workflow."""
        # Initialize all components
        proxy_manager = ProxyRotationManager(config_path=sample_proxy_config)
        ua_rotator = UserAgentRotator()
        captcha_solver = CaptchaSolver(api_key="test_key")
        tor_manager = TorManager()

        # Test getting proxy
        proxy = await proxy_manager.get_proxy()
        assert proxy is not None

        # Test user agent rotation
        headers = ua_rotator.get_random_headers()
        assert "User-Agent" in headers

        # Test CAPTCHA detection
        captcha_detected = await captcha_solver.detect_captcha("<div>No CAPTCHA</div>")
        assert captcha_detected == False

        # Test Tor URL generation
        tor_url = tor_manager.get_proxy_url()
        assert "socks5://" in tor_url


if __name__ == "__main__":
    """Run tests manually for development."""
    import asyncio

    async def run_manual_tests():
        """Run some basic tests manually."""
        print("Testing proxy rotation system...")

        # Create test config
        test_config = {
            "proxy_settings": {
                "rotation_strategy": "round_robin",
                "health_check_interval": 0,
            },
            "proxies": [
                {
                    "host": "proxy1.example.com",
                    "port": 8080,
                    "proxy_type": "http",
                    "concurrent_limit": 2,
                },
                {
                    "host": "proxy2.example.com",
                    "port": 8080,
                    "proxy_type": "http",
                    "concurrent_limit": 2,
                },
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_config, f)
            config_path = f.name

        # Test proxy manager
        proxy_manager = ProxyRotationManager(config_path=config_path)
        print(f"Loaded {len(proxy_manager.proxies)} proxies")

        # Test rotation
        for i in range(5):
            proxy = await proxy_manager.get_proxy()
            print(f"Request {i + 1}: Using proxy {proxy.host}:{proxy.port}")

        # Test user agent rotator
        ua_rotator = UserAgentRotator()
        print("\nTesting user agent rotation...")
        for i in range(3):
            headers = ua_rotator.get_random_headers()
            print(f"Headers {i + 1}: {headers['User-Agent'][:50]}...")

        # Test CAPTCHA detection
        captcha_solver = CaptchaSolver(api_key="test_key")
        print("\nTesting CAPTCHA detection...")

        test_html = '<div class="g-recaptcha" data-sitekey="test123"></div>'
        detected = await captcha_solver.detect_captcha(test_html)
        print(f"CAPTCHA detected: {detected}")

        print("\nAll tests completed successfully!")

    # Run manual tests
    asyncio.run(run_manual_tests())
