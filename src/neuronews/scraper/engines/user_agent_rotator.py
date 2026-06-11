"""
User-Agent rotation and browser fingerprinting evasion for NeuroNews scraper.
Provides realistic browser headers and behavior patterns to avoid detection.
"""

import json
import logging
import random
import threading
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class BrowserProfile:
    """Browser profile with consistent headers and behavior."""

    user_agent: str
    accept: str
    accept_language: str
    accept_encoding: str
    cache_control: str
    dnt: str
    platform: str
    browser_name: str
    version: str
    is_mobile: bool = False

    def get_headers(self) -> Dict[str, str]:
        """Get complete header set for this browser profile."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": self.accept,
            "Accept-Language": self.accept_language,
            "Accept-Encoding": self.accept_encoding,
            "Cache-Control": self.cache_control,
            "DNT": self.dnt,
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        # Add mobile-specific headers
        if self.is_mobile:
            headers["Sec-Fetch-Dest"] = "document"
            headers["Sec-Fetch-Mode"] = "navigate"
            headers["Sec-Fetch-Site"] = "none"
            headers["Sec-Fetch-User"] = "?1"

        return headers


class UserAgentRotator:
    """Advanced User-Agent rotation with realistic browser profiles."""

    DEFAULT_PROFILE_FILE = "user_agent_profiles.json"

    def __init__(
        self,
        config_file: Optional[str] = None,
        profile_file: Optional[str] = None,
    ):
        self.browser_profiles: List[BrowserProfile] = []
        self.current_profile: Optional[BrowserProfile] = None
        self.session_start_time: Optional[float] = None
        self.session_duration_range = (300, 1800)  # 5-30 minutes
        self.profile_usage_count = 0
        self.max_profile_usage = random.randint(50, 150)  # Random usage before rotation
        self.requests_with_current_profile = 0

        # Sequential/advanced rotation state
        self.current_index = 0
        self.use_advanced_rotation = True
        self.max_uses_per_profile = 5
        self.min_rotation_interval = 0.0
        self.domain_profiles: Dict[str, BrowserProfile] = {}
        self.profile_usage: Dict[str, int] = {}
        self._active_profile: Optional[BrowserProfile] = None
        self._active_profile_uses = 0
        self._last_rotation_time = 0.0
        self._performance: Dict[str, Dict[str, float]] = {}
        self._lock = threading.Lock()

        self.logger = logging.getLogger(__name__)

        # Initialize with default profiles if no config provided
        if config_file:
            self.load_config(config_file)
        else:
            loaded = self._load_profiles_from_file(
                profile_file or self.DEFAULT_PROFILE_FILE
            )
            if loaded:
                self.browser_profiles = loaded
            else:
                self._initialize_default_profiles()

    @property
    def profiles(self) -> List[BrowserProfile]:
        """Alias for browser_profiles."""
        return self.browser_profiles

    @profiles.setter
    def profiles(self, value: List[BrowserProfile]) -> None:
        self.browser_profiles = value

    def _load_profiles_from_file(self, profile_file: str) -> List[BrowserProfile]:
        """Load browser profiles from a JSON file, returning [] on any error."""
        allowed = {f.name for f in fields(BrowserProfile)}
        try:
            with open(profile_file, "r") as f:
                data = json.load(f)
            return [
                BrowserProfile(**{k: v for k, v in entry.items() if k in allowed})
                for entry in data
            ]
        except Exception:
            return []

    def _get_default_profiles(self) -> List[BrowserProfile]:
        """Return the built-in default browser profiles."""
        saved = self.browser_profiles
        self._initialize_default_profiles()
        defaults = self.browser_profiles
        self.browser_profiles = saved if saved else defaults
        return defaults

    def get_random_profile(self) -> BrowserProfile:
        """Return a random browser profile."""
        profile = random.choice(self.browser_profiles)
        self._track_usage(profile)
        return profile

    def get_next_profile(self) -> BrowserProfile:
        """Return the next profile using sequential or advanced rotation."""
        with self._lock:
            if not self.use_advanced_rotation:
                profile = self.browser_profiles[self.current_index]
                self.current_index = (
                    self.current_index + 1
                ) % len(self.browser_profiles)
                self._track_usage(profile)
                return profile

            rotation_due = (
                self._active_profile is None
                or self._active_profile_uses >= self.max_uses_per_profile
            )
            interval_elapsed = (
                time.time() - self._last_rotation_time
            ) >= self.min_rotation_interval
            if rotation_due and interval_elapsed:
                next_profile = self.browser_profiles[self.current_index]
                if (
                    self._active_profile is not None
                    and next_profile.user_agent == self._active_profile.user_agent
                    and len(self.browser_profiles) > 1
                ):
                    self.current_index = (
                        self.current_index + 1
                    ) % len(self.browser_profiles)
                    next_profile = self.browser_profiles[self.current_index]
                self.current_index = (
                    self.current_index + 1
                ) % len(self.browser_profiles)
                self._active_profile = next_profile
                self._active_profile_uses = 0
                self._last_rotation_time = time.time()

            self._active_profile_uses += 1
            self._track_usage(self._active_profile)
            return self._active_profile

    def get_profile_for_domain(self, domain: str) -> BrowserProfile:
        """Return a stable profile for a domain, assigning one if new."""
        if domain not in self.domain_profiles:
            self.domain_profiles[domain] = self.get_random_profile()
        return self.domain_profiles[domain]

    def get_browser_specific_profile(self, browser_name: str) -> BrowserProfile:
        """Return a profile for the requested browser, or any profile."""
        for profile in self.browser_profiles:
            if profile.browser_name.lower() == browser_name.lower():
                return profile
        return self.get_random_profile()

    def reset_profile_usage(self) -> None:
        """Reset rotation usage tracking, restarting from the first profile."""
        self._active_profile = None
        self._active_profile_uses = 0
        self.current_index = 0
        self.profile_usage.clear()

    def get_mobile_profile(self) -> BrowserProfile:
        """Return a mobile profile, falling back to built-in defaults."""
        for profile in self.browser_profiles:
            if profile.is_mobile:
                return profile
        for profile in self._get_default_profiles():
            if profile.is_mobile:
                return profile
        return self.get_random_profile()

    def get_desktop_profile(self) -> BrowserProfile:
        """Return a desktop (non-mobile) profile."""
        for profile in self.browser_profiles:
            if not profile.is_mobile:
                return profile
        for profile in self._get_default_profiles():
            if not profile.is_mobile:
                return profile
        return self.get_random_profile()

    def add_custom_profile(self, profile: BrowserProfile) -> None:
        """Add a custom browser profile to the rotation pool."""
        self.browser_profiles.append(profile)

    def remove_profile(self, profile: BrowserProfile) -> None:
        """Remove a profile from the rotation pool if present."""
        if profile in self.browser_profiles:
            self.browser_profiles.remove(profile)

    def save_profiles_to_file(self, output_file: str) -> None:
        """Persist the current profiles to a JSON file."""
        with open(output_file, "w") as f:
            json.dump([asdict(p) for p in self.browser_profiles], f, indent=2)

    def record_profile_performance(
        self, profile: BrowserProfile, success: bool, response_time: float
    ) -> None:
        """Record request outcome statistics for a profile."""
        stats = self._performance.setdefault(
            profile.user_agent,
            {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_response_time": 0.0,
            },
        )
        stats["total_requests"] += 1
        if success:
            stats["successful_requests"] += 1
        else:
            stats["failed_requests"] += 1
        stats["total_response_time"] += response_time

    def get_profile_performance(self, profile: BrowserProfile) -> Dict[str, float]:
        """Get recorded performance statistics for a profile."""
        stats = self._performance.get(
            profile.user_agent,
            {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_response_time": 0.0,
            },
        )
        result = dict(stats)
        total = stats["total_requests"]
        result["average_response_time"] = (
            stats["total_response_time"] / total if total else 0.0
        )
        return result

    def _track_usage(self, profile: Optional[BrowserProfile]) -> None:
        if profile is not None:
            self.profile_usage[profile.user_agent] = (
                self.profile_usage.get(profile.user_agent, 0) + 1
            )

    def get_user_agent(self) -> str:
        """Return the User-Agent string from the current profile."""
        # Force rotation every few requests for better variety
        if self.requests_with_current_profile >= 3:
            self._rotate_profile()
        
        profile = self.get_current_profile()
        self.requests_with_current_profile += 1
        if profile:
            return profile.user_agent
        # fallback to random profile
        if self.browser_profiles:
            return random.choice(self.browser_profiles).user_agent
        return "Mozilla/5.0 (compatible; NeuroNewsBot/1.0)"

    def get_random_headers(self) -> Dict[str, str]:
        """Get headers from a random browser profile."""
        if not self.browser_profiles:
            self._initialize_default_profiles()

        profile = random.choice(self.browser_profiles)
        return profile.get_headers()

    def get_current_profile(self) -> BrowserProfile:
        """Get current browser profile, rotating if needed."""
        if self._should_rotate_profile():
            self._rotate_profile()
        return self.current_profile

    def _should_rotate_profile(self) -> bool:
        """Determine if profile should be rotated."""
        if not self.current_profile:
            return True

        # Rotate based on usage count
        if self.profile_usage_count >= self.max_profile_usage:
            return True

        # Rotate based on session duration
        if self.session_start_time:
            session_duration = time.time() - self.session_start_time
            max_duration = random.uniform(*self.session_duration_range)
            if session_duration > max_duration:
                return True

        return False

    def _rotate_profile(self):
        """Rotate to a new browser profile."""
        if not self.browser_profiles:
            self._initialize_default_profiles()

        # Select a different profile than current
        available_profiles = [p for p in self.browser_profiles if p != self.current_profile]
        if available_profiles:
            self.current_profile = random.choice(available_profiles)
        else:
            self.current_profile = random.choice(self.browser_profiles)

        # Reset counters
        self.profile_usage_count = 0
        self.requests_with_current_profile = 0
        self.session_start_time = time.time()
        self.max_profile_usage = random.randint(50, 150)

        # Select a different profile than current
        available_profiles = [
            p for p in self.browser_profiles if p != self.current_profile
        ]
        if available_profiles:
            self.current_profile = random.choice(available_profiles)
        else:
            self.current_profile = random.choice(self.browser_profiles)

        # Reset counters
        self.profile_usage_count = 0
        self.session_start_time = time.time()
        self.max_profile_usage = random.randint(50, 150)

        self.logger.info(
            "Rotated to new browser profile: {0} {1}".format(
                self.current_profile.browser_name, self.current_profile.version
            )
        )

    def _initialize_default_profiles(self):
        """Initialize with realistic browser profiles."""
        # Chrome profiles (Windows, Mac, Linux)
        chrome_profiles = [
            BrowserProfile(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                accept_language="en-US,en;q=0.9",
                accept_encoding="gzip, deflate, br, zstd",
                cache_control="max-age=0",
                dnt="1",
                platform="Windows",
                browser_name="Chrome",
                version="131.0.0.0",
            ),
            BrowserProfile(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                accept_language="en-US,en;q=0.9",
                accept_encoding="gzip, deflate, br, zstd",
                cache_control="max-age=0",
                dnt="1",
                platform="macOS",
                browser_name="Chrome",
                version="131.0.0.0",
            ),
            BrowserProfile(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                accept_language="en-US,en;q=0.9",
                accept_encoding="gzip, deflate, br, zstd",
                cache_control="max-age=0",
                dnt="1",
                platform="Linux",
                browser_name="Chrome",
                version="131.0.0.0",
            ),
        ]

        # Firefox profiles
        firefox_profiles = [
            BrowserProfile(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
                accept_language="en-US,en;q=0.5",
                accept_encoding="gzip, deflate, br, zstd",
                cache_control="max-age=0",
                dnt="1",
                platform="Windows",
                browser_name="Firefox",
                version="132.0",
            ),
            BrowserProfile(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
                accept_language="en-US,en;q=0.5",
                accept_encoding="gzip, deflate, br, zstd",
                cache_control="max-age=0",
                dnt="1",
                platform="macOS",
                browser_name="Firefox",
                version="132.0",
            ),
        ]

        # Safari profiles
        safari_profiles = [
            BrowserProfile(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                accept_language="en-US,en;q=0.9",
                accept_encoding="gzip, deflate, br",
                cache_control="max-age=0",
                dnt="1",
                platform="macOS",
                browser_name="Safari",
                version="18.1",
            )
        ]

        # Edge profiles
        edge_profiles = [
            BrowserProfile(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                accept_language="en-US,en;q=0.9",
                accept_encoding="gzip, deflate, br, zstd",
                cache_control="max-age=0",
                dnt="1",
                platform="Windows",
                browser_name="Edge",
                version="131.0.0.0",
            )
        ]

        # Mobile profiles
        mobile_profiles = [
            BrowserProfile(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                accept_language="en-US,en;q=0.9",
                accept_encoding="gzip, deflate, br",
                cache_control="max-age=0",
                dnt="1",
                platform="iOS",
                browser_name="Safari",
                version="18.1",
                is_mobile=True,
            ),
            BrowserProfile(
                user_agent="Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                accept_language="en-US,en;q=0.9",
                accept_encoding="gzip, deflate, br, zstd",
                cache_control="max-age=0",
                dnt="1",
                platform="Android",
                browser_name="Chrome",
                version="131.0.0.0",
                is_mobile=True,
            ),
        ]

        # Combine all profiles
        self.browser_profiles = (
            chrome_profiles
            + firefox_profiles
            + safari_profiles
            + edge_profiles
            + mobile_profiles
        )

        self.logger.info(
            "Initialized {0} browser profiles".format(len(self.browser_profiles))
        )

    def load_config(self, config_file: str):
        """Load browser profiles from configuration file."""
        try:
            config_path = Path(config_file)
            if not config_path.exists():
                self.logger.warning(
                    "User-Agent config file not found: {0}, using defaults".format(
                        config_file
                    )
                )
                self._initialize_default_profiles()
                return

            with open(config_path, "r") as f:
                config = json.load(f)

            self.browser_profiles = []
            for profile_data in config.get("browser_profiles", []):
                profile = BrowserProfile(**profile_data)
                self.browser_profiles.append(profile)

            # Load settings
            settings = config.get("settings", {})
            self.session_duration_range = tuple(
                settings.get("session_duration_range", [300, 1800])
            )
            self.max_profile_usage = settings.get("max_profile_usage", 100)

            self.logger.info(
                "Loaded {0} browser profiles from {1}".format(
                    len(self.browser_profiles), config_file
                )
            )

        except Exception as e:
            self.logger.error("Error loading user-agent config: {0}".format(e))
            self._initialize_default_profiles()

    def get_profile(self, force_new: bool = False) -> BrowserProfile:
        """Get current browser profile or rotate to new one."""
        current_time = time.time()

        # Force rotation conditions
        should_rotate = (
            force_new
            or self.current_profile is None
            or self.profile_usage_count >= self.max_profile_usage
            or (
                self.session_start_time
                and current_time - self.session_start_time
                > random.randint(*self.session_duration_range)
            )
        )

        if should_rotate:
            self._rotate_profile()

        self.profile_usage_count += 1
        return self.current_profile

    def _rotate_profile_advanced(self):
        """Rotate to a new browser profile (advanced method)."""
        # Select new profile (avoid same as current)
        available_profiles = [
            p for p in self.browser_profiles if p != self.current_profile
        ]
        if not available_profiles:
            available_profiles = self.browser_profiles

        self.current_profile = random.choice(available_profiles)
        self.session_start_time = time.time()
        self.profile_usage_count = 0
        self.max_profile_usage = random.randint(50, 150)  # Randomize next rotation

        self.logger.info(
            "Rotated to new profile: {0} {1} on {2}".format(
                self.current_profile.browser_name,
                self.current_profile.version,
                self.current_profile.platform,
            )
        )

    def get_headers(
        self, additional_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Get complete headers for current profile."""
        profile = self.get_profile()
        headers = profile.get_headers()

        # Add additional headers if provided
        if additional_headers:
            headers.update(additional_headers)

        # Add some randomization to make requests more realistic
        headers["Sec-Ch-Ua"] = self._generate_sec_ch_ua(profile)
        headers["Sec-Ch-Ua-Mobile"] = "?1" if profile.is_mobile else "?0"
        headers["Sec-Ch-Ua-Platform"] = f'"{profile.platform}"'

        return headers

    def _generate_sec_ch_ua(self, profile: BrowserProfile) -> str:
        """Generate realistic Sec-CH-UA header."""
        if profile.browser_name == "Chrome":
            return f'"Google Chrome";v="{profile.version.split(".")[0]}", "Chromium";v="{profile.version.split(".")[0]}", "Not_A Brand";v="8"'
        elif profile.browser_name == "Firefox":
            return f'"Firefox";v="{profile.version.split(".")[0]}"'
        elif profile.browser_name == "Safari":
            return f'"Safari";v="{profile.version.split(".")[0]}"'
        elif profile.browser_name == "Edge":
            return f'"Microsoft Edge";v="{profile.version.split(".")[0]}", "Chromium";v="{profile.version.split(".")[0]}", "Not_A Brand";v="8"'
        else:
            return f'"{profile.browser_name}";v="{profile.version.split(".")[0]}"'

    def get_realistic_delays(self) -> Tuple[float, float]:
        """Get realistic delay ranges for human-like behavior."""
        profile = self.get_profile()

        if profile.is_mobile:
            # Mobile users tend to be slower
            return (2.0, 5.0)
        else:
            # Desktop users are typically faster
            return (1.0, 3.0)

    def simulate_human_typing(self, text_length: int) -> float:
        """Calculate realistic typing delay based on text length."""
        # Average human typing speed: 40 WPM = 200 characters per minute
        base_delay = text_length / 200 * 60  # Convert to seconds

        # Add some randomization (±25%)
        variation = base_delay * 0.25
        return base_delay + random.uniform(-variation, variation)

    def get_stats(self) -> Dict[str, any]:
        """Get user-agent rotation statistics."""
        return {
            "total_profiles": len(self.browser_profiles),
            "current_index": self.current_index,
            "profile_usage": dict(self.profile_usage),
            "domain_assignments": {
                domain: profile.user_agent
                for domain, profile in self.domain_profiles.items()
            },
            "current_profile": {
                "browser": (
                    self.current_profile.browser_name if self.current_profile else None
                ),
                "version": (
                    self.current_profile.version if self.current_profile else None
                ),
                "platform": (
                    self.current_profile.platform if self.current_profile else None
                ),
                "is_mobile": (
                    self.current_profile.is_mobile if self.current_profile else False
                ),
            },
            "session_info": {
                "usage_count": self.profile_usage_count,
                "max_usage": self.max_profile_usage,
                "session_duration": (
                    time.time() - self.session_start_time
                    if self.session_start_time
                    else 0
                ),
                "session_duration_range": self.session_duration_range,
            },
            "profile_distribution": {
                profile.browser_name: len(
                    [
                        p
                        for p in self.browser_profiles
                        if p.browser_name == profile.browser_name
                    ]
                )
                for profile in self.browser_profiles
            },
        }
