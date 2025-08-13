"""
CAPTCHA detection and solving for NeuroNews scraper.
Integrates with 2Captcha and other services for automated bypass.
"""

import aiohttp
import asyncio
import logging
from typing import Optional

class CaptchaSolver:
    """Automated CAPTCHA detection and solving using 2Captcha API."""
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)

    async def detect_captcha(self, page_content: str) -> bool:
        """Detect if page contains CAPTCHA elements."""
        captcha_indicators = [
            'g-recaptcha',
            'h-captcha',
            'data-sitekey',
            'recaptcha',
            'captcha',
            'cf-turnstile',
            'turnstile'
        ]
        
        page_lower = page_content.lower()
        for indicator in captcha_indicators:
            if indicator in page_lower:
                self.logger.info(f"CAPTCHA detected: {indicator}")
                return True
        
        return False

    async def solve_recaptcha_v2(self, site_key: str, url: str, timeout: int = 120) -> Optional[str]:
        """Solve Google reCAPTCHA v2 using 2Captcha."""
        async with aiohttp.ClientSession() as session:
            # Submit CAPTCHA
            data = {
                'key': self.api_key,
                'method': 'userrecaptcha',
                'googlekey': site_key,
                'pageurl': url,
                'json': 1
            }
            async with session.post('https://2captcha.com/in.php', data=data) as resp:
                result = await resp.json()
                if result.get('status') != 1:
                    self.logger.error(f"2Captcha error: {result}")
                    return None
                captcha_id = result['request']

            # Poll for result
            for _ in range(timeout // 5):
                await asyncio.sleep(5)
                async with session.get(f'https://2captcha.com/res.php?key={self.api_key}&action=get&id={captcha_id}&json=1') as resp:
                    result = await resp.json()
                    if result.get('status') == 1:
                        self.logger.info("CAPTCHA solved!")
                        return result['request']
                    elif result.get('request') == 'CAPCHA_NOT_READY':
                        continue
                    else:
                        self.logger.error(f"2Captcha polling error: {result}")
                        return None
            self.logger.error("2Captcha timeout")
            return None

    async def solve_hcaptcha(self, site_key: str, url: str, timeout: int = 120) -> Optional[str]:
        """Solve hCaptcha using 2Captcha."""
        async with aiohttp.ClientSession() as session:
            data = {
                'key': self.api_key,
                'method': 'hcaptcha',
                'sitekey': site_key,
                'pageurl': url,
                'json': 1
            }
            async with session.post('https://2captcha.com/in.php', data=data) as resp:
                result = await resp.json()
                if result.get('status') != 1:
                    self.logger.error(f"2Captcha error: {result}")
                    return None
                captcha_id = result['request']

            for _ in range(timeout // 5):
                await asyncio.sleep(5)
                async with session.get(f'https://2captcha.com/res.php?key={self.api_key}&action=get&id={captcha_id}&json=1') as resp:
                    result = await resp.json()
                    if result.get('status') == 1:
                        self.logger.info("hCaptcha solved!")
                        return result['request']
                    elif result.get('request') == 'CAPCHA_NOT_READY':
                        continue
                    else:
                        self.logger.error(f"2Captcha polling error: {result}")
                        return None
            self.logger.error("2Captcha timeout")
            return None
