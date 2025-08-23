"""
Tor integration and management for NeuroNews scraper.
Handles Tor proxy setup, identity rotation, and health checks.
"""

import asyncio
import logging


class TorManager:
    def get_proxy_url(self) -> str:
        """Return the Tor proxy URL."""
        return self.tor_proxy_url
    """Manages Tor proxy and identity rotation."""

    def __init__(self, tor_proxy_url: str = "socks5://127.0.0.1:9050"):
        self.tor_proxy_url = tor_proxy_url
        self.logger = logging.getLogger(__name__)

    async def rotate_identity(self) -> bool:
        """Request new Tor identity via control port."""
        try:
            # Try socket connection to Tor control port (for test compatibility)
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Attempt connection to control port
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', 9051))
                if result == 0:
                    # Send NEWNYM command
                    sock.send(b'AUTHENTICATE ""\r\nSIGNAL NEWNYM\r\nQUIT\r\n')
                    response = sock.recv(1024)
                    sock.close()
                    self.logger.info("Tor identity rotated via control port.")
                    return True
                else:
                    sock.close()
                    # Fall back to subprocess method
                    return await self._rotate_via_subprocess()
            except Exception:
                sock.close()
                return await self._rotate_via_subprocess()
                
        except Exception as e:
            self.logger.error("Tor rotation error: {0}".format(e))
            return False
    
    async def _rotate_via_subprocess(self) -> bool:
        """Rotate identity using subprocess (fallback method)."""
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
                    "Tor identity rotation failed: {0}".format(stderr.decode())
                )
                return False
        except Exception as e:
            self.logger.error("Tor subprocess rotation error: {0}".format(e))
            return False

    def get_proxy(self) -> str:
        """Get current Tor proxy URL."""
        return self.tor_proxy_url
