"""
Web scraping connector for extracting data from web pages.
"""

import aiohttp
import asyncio
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import re
from .base import BaseConnector, ConnectionError, DataFormatError


class WebScrapingConnector(BaseConnector):
    """
    Web scraping connector for extracting data from HTML pages.
    """

    def __init__(self, config: Dict[str, Any], auth_config: Optional[Dict[str, Any]] = None):
        """
        Initialize web scraping connector.
        
        Args:
            config: Web scraping configuration containing URL and extraction rules
            auth_config: Authentication configuration (if needed)
        """
        super().__init__(config, auth_config)
        self._session = None
        self._headers = {}

    def validate_config(self) -> bool:
        """Validate web scraping connector configuration."""
        required_fields = ['base_url']
        
        for field in required_fields:
            if field not in self.config:
                return False
                
        # Validate URL format
        try:
            result = urlparse(self.config['base_url'])
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    async def connect(self) -> bool:
        """Establish HTTP session for web scraping."""
        try:
            if self._session and not self._session.closed:
                self._connected = True
                return True
                
            timeout = aiohttp.ClientTimeout(total=self.config.get('timeout', 30))
            self._session = aiohttp.ClientSession(timeout=timeout)
            
            # Set up headers
            self._headers = {
                'User-Agent': self.config.get('user_agent', 'Mozilla/5.0 (compatible; NeuroNews-Scraper/1.0)'),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            # Add custom headers if provided
            if 'headers' in self.config:
                self._headers.update(self.config['headers'])
            
            # Test connection
            async with self._session.get(self.config['base_url'], headers=self._headers) as response:
                if response.status in [200, 301, 302, 403]:  # 403 might be due to bot detection but connection works
                    self._connected = True
                    return True
                else:
                    self._last_error = ConnectionError(f"HTTP {response.status}: {response.reason}")
                    return False
                    
        except Exception as e:
            self._last_error = ConnectionError(f"Failed to connect to web source: {e}")
            return False

    async def disconnect(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._connected = False

    async def fetch_data(self, url_path: str = "", selectors: Optional[Dict] = None, 
                        follow_links: bool = False, max_pages: int = 1, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch data from web pages using CSS selectors.
        
        Args:
            url_path: Path to append to base URL
            selectors: CSS selectors for data extraction
            follow_links: Whether to follow pagination links
            max_pages: Maximum number of pages to scrape
            
        Returns:
            List of extracted data records
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to web source")

        try:
            url = urljoin(self.config['base_url'], url_path)
            selectors = selectors or self.config.get('selectors', {})
            
            all_data = []
            urls_to_scrape = [url]
            pages_scraped = 0
            
            while urls_to_scrape and pages_scraped < max_pages:
                current_url = urls_to_scrape.pop(0)
                page_data = await self._scrape_page(current_url, selectors)
                
                if page_data:
                    all_data.extend(page_data)
                
                # Find pagination links if requested
                if follow_links and pages_scraped < max_pages - 1:
                    next_urls = await self._find_pagination_links(current_url, selectors.get('next_page'))
                    urls_to_scrape.extend(next_urls)
                
                pages_scraped += 1
                
                # Rate limiting
                delay = self.config.get('delay', 1)
                if delay > 0:
                    await asyncio.sleep(delay)
            
            return all_data
                    
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to fetch web data: {e}")

    async def _scrape_page(self, url: str, selectors: Dict) -> List[Dict[str, Any]]:
        """
        Scrape data from a single page.
        
        Args:
            url: URL to scrape
            selectors: CSS selectors for extraction
            
        Returns:
            List of extracted data records
        """
        try:
            async with self._session.get(url, headers=self._headers) as response:
                if response.status != 200:
                    self.logger.warning(f"HTTP {response.status} for URL: {url}")
                    return []
                
                html = await response.text()
                
            soup = BeautifulSoup(html, 'html.parser')
            extracted_data = []
            
            # Check if we have container selector for multiple items
            container_selector = selectors.get('container')
            if container_selector:
                containers = soup.select(container_selector)
                
                for container in containers:
                    item_data = {'source_url': url}
                    
                    # Extract data using selectors
                    for field, selector_info in selectors.items():
                        if field in ['container', 'next_page']:
                            continue
                            
                        if isinstance(selector_info, str):
                            # Simple selector
                            element = container.select_one(selector_info)
                            item_data[field] = element.get_text(strip=True) if element else ""
                        elif isinstance(selector_info, dict):
                            # Advanced selector with options
                            selector = selector_info.get('selector')
                            attribute = selector_info.get('attribute', 'text')
                            element = container.select_one(selector) if selector else None
                            
                            if element:
                                if attribute == 'text':
                                    item_data[field] = element.get_text(strip=True)
                                elif attribute == 'html':
                                    item_data[field] = str(element)
                                else:
                                    item_data[field] = element.get(attribute, "")
                            else:
                                item_data[field] = ""
                    
                    if self.validate_data_format(item_data):
                        extracted_data.append(item_data)
            
            else:
                # Single item extraction
                item_data = {'source_url': url}
                
                for field, selector_info in selectors.items():
                    if field == 'next_page':
                        continue
                        
                    if isinstance(selector_info, str):
                        elements = soup.select(selector_info)
                        if len(elements) == 1:
                            item_data[field] = elements[0].get_text(strip=True)
                        elif len(elements) > 1:
                            item_data[field] = [elem.get_text(strip=True) for elem in elements]
                        else:
                            item_data[field] = ""
                    elif isinstance(selector_info, dict):
                        selector = selector_info.get('selector')
                        attribute = selector_info.get('attribute', 'text')
                        elements = soup.select(selector) if selector else []
                        
                        if len(elements) == 1:
                            element = elements[0]
                            if attribute == 'text':
                                item_data[field] = element.get_text(strip=True)
                            elif attribute == 'html':
                                item_data[field] = str(element)
                            else:
                                item_data[field] = element.get(attribute, "")
                        elif len(elements) > 1:
                            if attribute == 'text':
                                item_data[field] = [elem.get_text(strip=True) for elem in elements]
                            else:
                                item_data[field] = [elem.get(attribute, "") for elem in elements]
                        else:
                            item_data[field] = ""
                
                if self.validate_data_format(item_data):
                    extracted_data = [item_data]
            
            return extracted_data
            
        except Exception as e:
            self.logger.error(f"Error scraping page {url}: {e}")
            return []

    async def _find_pagination_links(self, current_url: str, next_selector: Optional[str]) -> List[str]:
        """
        Find pagination links on the current page.
        
        Args:
            current_url: Current page URL
            next_selector: CSS selector for next page links
            
        Returns:
            List of next page URLs
        """
        if not next_selector:
            return []
            
        try:
            async with self._session.get(current_url, headers=self._headers) as response:
                if response.status != 200:
                    return []
                    
                html = await response.text()
                
            soup = BeautifulSoup(html, 'html.parser')
            next_links = soup.select(next_selector)
            
            urls = []
            for link in next_links:
                href = link.get('href')
                if href:
                    absolute_url = urljoin(current_url, href)
                    urls.append(absolute_url)
            
            return urls
            
        except Exception as e:
            self.logger.error(f"Error finding pagination links: {e}")
            return []

    def validate_data_format(self, data: Any) -> bool:
        """
        Validate scraped data format.
        
        Args:
            data: Scraped data to validate
            
        Returns:
            True if data format is valid
        """
        if not isinstance(data, dict):
            return False
            
        # Should have source URL and at least one other field
        return 'source_url' in data and len(data) > 1

    async def extract_links(self, url_path: str = "", link_selector: str = "a[href]") -> List[str]:
        """
        Extract all links from a page.
        
        Args:
            url_path: Path to append to base URL
            link_selector: CSS selector for links
            
        Returns:
            List of absolute URLs
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to web source")

        try:
            url = urljoin(self.config['base_url'], url_path)
            
            async with self._session.get(url, headers=self._headers) as response:
                if response.status != 200:
                    return []
                    
                html = await response.text()
                
            soup = BeautifulSoup(html, 'html.parser')
            link_elements = soup.select(link_selector)
            
            links = []
            for link in link_elements:
                href = link.get('href')
                if href:
                    absolute_url = urljoin(url, href)
                    links.append(absolute_url)
            
            return list(set(links))  # Remove duplicates
            
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to extract links: {e}")

    async def check_robots_txt(self) -> Dict[str, Any]:
        """
        Check robots.txt for scraping permissions.
        
        Returns:
            Dictionary containing robots.txt information
        """
        try:
            robots_url = urljoin(self.config['base_url'], '/robots.txt')
            
            async with self._session.get(robots_url, headers=self._headers) as response:
                if response.status == 200:
                    content = await response.text()
                    
                    # Basic robots.txt parsing
                    disallowed = []
                    allowed = []
                    crawl_delay = None
                    
                    for line in content.split('\n'):
                        line = line.strip().lower()
                        if line.startswith('disallow:'):
                            path = line.split(':', 1)[1].strip()
                            if path:
                                disallowed.append(path)
                        elif line.startswith('allow:'):
                            path = line.split(':', 1)[1].strip()
                            if path:
                                allowed.append(path)
                        elif line.startswith('crawl-delay:'):
                            delay = line.split(':', 1)[1].strip()
                            try:
                                crawl_delay = float(delay)
                            except ValueError:
                                pass
                    
                    return {
                        'exists': True,
                        'disallowed_paths': disallowed,
                        'allowed_paths': allowed,
                        'crawl_delay': crawl_delay,
                        'content': content
                    }
                else:
                    return {'exists': False}
                    
        except Exception as e:
            self.logger.error(f"Error checking robots.txt: {e}")
            return {'exists': False, 'error': str(e)}
