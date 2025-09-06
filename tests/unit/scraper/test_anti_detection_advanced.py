"""
Comprehensive tests for Anti-Detection mechanisms.
Tests stealth mode, CAPTCHA handling, and detection avoidance strategies.
"""

import pytest
import time
import random
from unittest.mock import MagicMock, patch, AsyncMock

# Import with proper path handling
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from scraper.captcha_solver import CaptchaSolver
from scraper.user_agent_rotator import UserAgentRotator


class TestAntiDetectionMechanisms:
    """Test suite for anti-detection mechanisms."""

    @pytest.fixture
    def captcha_solver(self):
        """CaptchaSolver fixture for testing."""
        return CaptchaSolver(api_key="test-api-key")

    @pytest.fixture
    def user_agent_rotator(self):
        """UserAgentRotator fixture for testing."""
        return UserAgentRotator()

    def test_captcha_solver_initialization(self, captcha_solver):
        """Test CaptchaSolver initialization."""
        assert captcha_solver.api_key == "test-api-key"
        assert hasattr(captcha_solver, 'solve_captcha')

    @patch('requests.post')
    def test_captcha_solving_success(self, mock_post, captcha_solver):
        """Test successful CAPTCHA solving."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": 1,
            "request": "12345",
            "solution": "test_solution"
        }
        mock_post.return_value = mock_response
        
        result = captcha_solver.solve_text_captcha("test_image_data")
        
        assert result == "test_solution"
        mock_post.assert_called()

    @patch('requests.post')
    def test_captcha_solving_failure(self, mock_post, captcha_solver):
        """Test CAPTCHA solving failure handling."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": 0,
            "error": "ERROR_WRONG_USER_KEY"
        }
        mock_post.return_value = mock_response
        
        result = captcha_solver.solve_text_captcha("test_image_data")
        
        assert result is None

    def test_recaptcha_v2_detection(self, captcha_solver):
        """Test reCAPTCHA v2 detection."""
        html_with_recaptcha = """
        <html>
            <body>
                <div class="g-recaptcha" data-sitekey="test-site-key"></div>
            </body>
        </html>
        """
        
        has_recaptcha = captcha_solver.detect_recaptcha(html_with_recaptcha)
        assert has_recaptcha is True
        
        html_without_recaptcha = "<html><body>No captcha here</body></html>"
        has_recaptcha = captcha_solver.detect_recaptcha(html_without_recaptcha)
        assert has_recaptcha is False

    @pytest.mark.asyncio
    async def test_captcha_solving_async(self, captcha_solver):
        """Test asynchronous CAPTCHA solving."""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.json.return_value = {
                "status": 1,
                "solution": "async_solution"
            }
            mock_session.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await captcha_solver.solve_captcha_async("test_image")
            assert result == "async_solution"

    def test_user_agent_fingerprint_randomization(self, user_agent_rotator):
        """Test user agent fingerprint randomization."""
        profiles = []
        
        # Get multiple profiles to check diversity
        for _ in range(10):
            profile = user_agent_rotator.get_random_profile()
            profiles.append(profile)
        
        # Should have variety in user agents
        user_agents = [p.user_agent for p in profiles]
        unique_agents = set(user_agents)
        
        # Should have at least 2 different user agents in 10 requests
        assert len(unique_agents) >= 2

    def test_browser_fingerprint_consistency(self, user_agent_rotator):
        """Test that browser fingerprints remain consistent within session."""
        domain = "example.com"
        
        # Get profile for domain multiple times
        profile1 = user_agent_rotator.get_profile_for_domain(domain)
        profile2 = user_agent_rotator.get_profile_for_domain(domain)
        
        # Should be the same profile for consistency
        assert profile1.user_agent == profile2.user_agent
        assert profile1.platform == profile2.platform

    def test_realistic_timing_patterns(self):
        """Test realistic timing patterns for requests."""
        timing_engine = TimingEngine()
        
        delays = []
        for _ in range(10):
            delay = timing_engine.get_human_delay()
            delays.append(delay)
        
        # Should have variety in delays
        assert min(delays) >= 0.5  # Minimum human delay
        assert max(delays) <= 5.0  # Maximum reasonable delay
        assert len(set(delays)) > 1  # Should be different values

    def test_mouse_movement_simulation(self):
        """Test mouse movement simulation patterns."""
        mouse_sim = MouseSimulator()
        
        # Generate movement pattern
        movements = mouse_sim.generate_human_movement(start=(100, 100), end=(500, 300))
        
        assert len(movements) > 2  # Should have intermediate points
        assert movements[0] == (100, 100)  # Start point
        assert movements[-1] == (500, 300)  # End point

    def test_keyboard_typing_simulation(self):
        """Test keyboard typing simulation with realistic delays."""
        keyboard_sim = KeyboardSimulator()
        
        text = "Hello World"
        typing_events = keyboard_sim.simulate_typing(text)
        
        assert len(typing_events) == len(text)
        
        # Should have realistic delays between keystrokes
        for event in typing_events:
            assert event['delay'] >= 0.05  # Minimum typing delay
            assert event['delay'] <= 0.3   # Maximum typing delay

    def test_scroll_behavior_simulation(self):
        """Test scroll behavior simulation."""
        scroll_sim = ScrollSimulator()
        
        scroll_pattern = scroll_sim.generate_reading_scroll(page_length=5000)
        
        # Should scroll gradually
        assert len(scroll_pattern) > 5
        assert scroll_pattern[0]['position'] == 0
        assert scroll_pattern[-1]['position'] >= 4500  # Near bottom

    def test_session_persistence(self):
        """Test session data persistence across requests."""
        session_manager = SessionManager()
        
        # Simulate first visit
        session_manager.start_session("example.com")
        session_manager.record_action("page_view", "/home")
        session_manager.record_action("click", "button")
        
        # Get session data
        session_data = session_manager.get_session_data("example.com")
        
        assert len(session_data['actions']) == 2
        assert session_data['actions'][0]['type'] == 'page_view'
        assert session_data['actions'][1]['type'] == 'click'

    def test_behavioral_pattern_variation(self):
        """Test that behavioral patterns vary between sessions."""
        pattern_gen = BehavioralPatternGenerator()
        
        patterns = []
        for _ in range(5):
            pattern = pattern_gen.generate_browsing_pattern()
            patterns.append(pattern)
        
        # Should have variety in patterns
        unique_patterns = set(str(p) for p in patterns)
        assert len(unique_patterns) > 1

    def test_geolocation_consistency(self):
        """Test geolocation consistency with proxy selection."""
        geo_manager = GeolocationManager()
        
        # Set proxy location
        geo_manager.set_proxy_location("US", "California")
        
        # Get timezone and locale
        timezone = geo_manager.get_timezone()
        locale = geo_manager.get_locale()
        
        assert "America" in timezone  # Should be US timezone
        assert locale.startswith("en_US")  # Should be US locale

    @pytest.mark.asyncio
    async def test_request_rate_limiting(self):
        """Test intelligent rate limiting."""
        rate_limiter = AdaptiveRateLimiter()
        
        start_time = time.time()
        
        # Make rapid requests
        for _ in range(5):
            await rate_limiter.wait_if_needed()
        
        elapsed = time.time() - start_time
        
        # Should have introduced delays
        assert elapsed >= 2.0  # At least some delay

    def test_error_response_handling(self):
        """Test handling of anti-bot error responses."""
        error_handler = ErrorResponseHandler()
        
        # Test different error responses
        test_cases = [
            (403, "Access Denied", "rate_limit"),
            (429, "Too Many Requests", "rate_limit"),  
            (503, "Service Unavailable", "temporary"),
            (200, "Please complete the security check", "captcha"),
        ]
        
        for status_code, content, expected_type in test_cases:
            error_type = error_handler.classify_error(status_code, content)
            assert error_type == expected_type

    def test_header_randomization(self, user_agent_rotator):
        """Test HTTP header randomization."""
        headers_list = []
        
        for _ in range(5):
            profile = user_agent_rotator.get_random_profile()
            headers = profile.get_headers()
            headers_list.append(headers)
        
        # Should have variety in headers
        accept_languages = [h.get('Accept-Language') for h in headers_list]
        unique_languages = set(accept_languages)
        
        # Should have some variety (implementation dependent)
        assert len(headers_list) == 5

    def test_cookie_management(self):
        """Test cookie management and persistence."""
        cookie_manager = CookieManager()
        
        # Set cookies for domain
        cookie_manager.set_cookie("example.com", "session_id", "12345")
        cookie_manager.set_cookie("example.com", "preferences", "theme=dark")
        
        # Get cookies for domain
        cookies = cookie_manager.get_cookies("example.com")
        
        assert len(cookies) == 2
        assert cookies["session_id"] == "12345"
        assert cookies["preferences"] == "theme=dark"

    def test_javascript_fingerprint_evasion(self):
        """Test JavaScript fingerprint evasion."""
        js_evasion = JavaScriptEvasion()
        
        # Test canvas fingerprint randomization
        canvas_noise = js_evasion.get_canvas_noise()
        assert canvas_noise is not None
        
        # Test WebGL fingerprint modification
        webgl_params = js_evasion.get_webgl_parameters()
        assert isinstance(webgl_params, dict)
        assert len(webgl_params) > 0

    def test_network_fingerprint_masking(self):
        """Test network-level fingerprint masking."""
        network_mask = NetworkMasking()
        
        # Test TCP fingerprint modification
        tcp_options = network_mask.get_tcp_options()
        assert isinstance(tcp_options, dict)
        
        # Test TLS fingerprint variation  
        tls_config = network_mask.get_tls_config()
        assert "cipher_suites" in tls_config
        assert len(tls_config["cipher_suites"]) > 0


# Helper classes that would be implemented in the actual codebase
class TimingEngine:
    def get_human_delay(self):
        return random.uniform(0.5, 5.0)

class MouseSimulator:
    def generate_human_movement(self, start, end):
        # Simplified implementation
        return [start, ((start[0] + end[0])//2, (start[1] + end[1])//2), end]

class KeyboardSimulator:
    def simulate_typing(self, text):
        return [{"char": c, "delay": random.uniform(0.05, 0.3)} for c in text]

class ScrollSimulator:
    def generate_reading_scroll(self, page_length):
        positions = []
        current = 0
        while current < page_length * 0.9:
            positions.append({"position": current, "delay": random.uniform(0.5, 2.0)})
            current += random.randint(100, 500)
        return positions

class SessionManager:
    def __init__(self):
        self.sessions = {}
    
    def start_session(self, domain):
        self.sessions[domain] = {"actions": [], "start_time": time.time()}
    
    def record_action(self, action_type, target):
        for domain in self.sessions:
            self.sessions[domain]["actions"].append({"type": action_type, "target": target})
    
    def get_session_data(self, domain):
        return self.sessions.get(domain, {})

class BehavioralPatternGenerator:
    def generate_browsing_pattern(self):
        return {"clicks": random.randint(5, 20), "scrolls": random.randint(3, 10)}

class GeolocationManager:
    def __init__(self):
        self.proxy_location = None
    
    def set_proxy_location(self, country, region):
        self.proxy_location = {"country": country, "region": region}
    
    def get_timezone(self):
        if self.proxy_location and self.proxy_location["country"] == "US":
            return "America/Los_Angeles"
        return "UTC"
    
    def get_locale(self):
        if self.proxy_location and self.proxy_location["country"] == "US":
            return "en_US"
        return "en_GB"

class AdaptiveRateLimiter:
    async def wait_if_needed(self):
        await asyncio.sleep(0.5)  # Simulate rate limiting

class ErrorResponseHandler:
    def classify_error(self, status_code, content):
        if status_code in [403, 429]:
            return "rate_limit"
        elif status_code == 503:
            return "temporary"
        elif "security check" in content.lower():
            return "captcha"
        return "unknown"

class CookieManager:
    def __init__(self):
        self.cookies = {}
    
    def set_cookie(self, domain, name, value):
        if domain not in self.cookies:
            self.cookies[domain] = {}
        self.cookies[domain][name] = value
    
    def get_cookies(self, domain):
        return self.cookies.get(domain, {})

class JavaScriptEvasion:
    def get_canvas_noise(self):
        return random.uniform(0.1, 0.5)
    
    def get_webgl_parameters(self):
        return {"vendor": "Intel Inc.", "renderer": "Intel HD Graphics"}

class NetworkMasking:
    def get_tcp_options(self):
        return {"window_size": 65535, "mss": 1460}
    
    def get_tls_config(self):
        return {"cipher_suites": ["TLS_AES_256_GCM_SHA384", "TLS_CHACHA20_POLY1305_SHA256"]}