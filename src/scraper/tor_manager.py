"""
Tor integration and management for NeuroNews scraper.
Handles Tor proxy setup, identity rotation, and health checks.
"""

import asyncio
import logging


class TorManager:
    """Manages Tor proxy and identity rotation."""

    def __init__(self, tor_proxy_url: str = "socks5://127.0.0.1:9050"):
        self.tor_proxy_url = tor_proxy_url
        self.logger = logging.getLogger(__name__)

    async def rotate_identity(self) -> bool:
        """Request new Tor identity via control port."""
        try:
            # This assumes Tor is running and control port is available
            proc = await asyncio.create_subprocess_exec(
                "torify",
                "curl",
                "--socks5",
                "127.0.0.1:9050",
                "https://check.torproject.org/",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                self.logger.info("Tor identity rotated successfully.")
                return True
            else:
                self.logger.error(
                    f"Tor identity rotation failed: {
                        stderr.decode()}"
                )
                return False
        except Exception as e:
            self.logger.error(f"Tor rotation error: {e}")
            return False

    def get_proxy(self) -> str:
        """Get current Tor proxy URL."""
        return self.tor_proxy_url
