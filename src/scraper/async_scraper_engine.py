"""
AsyncIO-based news scraper for NeuroNews.
This module provides high-performance async scraping with Playwright and ThreadPoolExecutor.
"""

import asyncio
import aiohttp
import aiofiles
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
import hashlib
import re
from urllib.parse import urljoin, urlparse

# Playwright imports
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# Performance monitoring
import psutil
import threading
from collections import defaultdict, deque

@dataclass
class Article:
    """Article data structure."""
    title: str
    url: str
    content: str
    author: str
    published_date: str
    source: str
    scraped_date: str
    language: str = "en"
    content_length: int = 0
    word_count: int = 0
    reading_time: int = 0
    category: str = "News"
    validation_score: int = 0
    content_quality: str = "unknown"
    duplicate_check: str = "unique"

@dataclass
class NewsSource:
    """News source configuration."""
    name: str
    base_url: str
    article_selectors: Dict[str, str]
    link_patterns: List[str]
    requires_js: bool = False
    rate_limit: float = 1.0
    timeout: int = 30

class PerformanceMonitor:
    """Real-time performance monitoring for async scraper."""
    
    def __init__(self):
        self.start_time = time.time()
        self.articles_scraped = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.source_stats = defaultdict(lambda: {"articles": 0, "errors": 0})
        self.response_times = deque(maxlen=100)
        self.memory_usage = deque(maxlen=50)
        self.cpu_usage = deque(maxlen=50)
        self.lock = threading.Lock()
        
        # Start monitoring thread
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_system, daemon=True)
        self.monitor_thread.start()
    
    def _monitor_system(self):
        """Monitor system resources."""
        while self.monitoring:
            try:
                process = psutil.Process()
                with self.lock:
                    self.memory_usage.append(process.memory_info().rss / 1024 / 1024)  # MB
                    self.cpu_usage.append(process.cpu_percent())
                time.sleep(1)
            except:
                pass
    
    def record_article(self, source: str):
        """Record a successfully scraped article."""
        with self.lock:
            self.articles_scraped += 1
            self.source_stats[source]["articles"] += 1
    
    def record_success(self, response_time: float):
        """Record a successful request."""
        with self.lock:
            self.successful_requests += 1
            self.response_times.append(response_time)
    
    def record_error(self, source: str):
        """Record a failed request."""
        with self.lock:
            self.failed_requests += 1
            self.source_stats[source]["errors"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current performance statistics."""
        with self.lock:
            elapsed_time = time.time() - self.start_time
            
            return {
                "elapsed_time": elapsed_time,
                "articles_per_second": self.articles_scraped / max(elapsed_time, 1),
                "total_articles": self.articles_scraped,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": self.successful_requests / max(self.successful_requests + self.failed_requests, 1) * 100,
                "avg_response_time": sum(self.response_times) / max(len(self.response_times), 1),
                "avg_memory_mb": sum(self.memory_usage) / max(len(self.memory_usage), 1),
                "avg_cpu_percent": sum(self.cpu_usage) / max(len(self.cpu_usage), 1),
                "source_stats": dict(self.source_stats)
            }
    
    def stop(self):
        """Stop monitoring."""
        self.monitoring = False

class AsyncNewsScraperEngine:
    """High-performance async news scraper with Playwright and ThreadPoolExecutor."""
    
    def __init__(self, max_concurrent: int = 10, max_threads: int = 4, headless: bool = True):
        self.max_concurrent = max_concurrent
        self.max_threads = max_threads
        self.headless = headless
        
        # Performance monitoring
        self.monitor = PerformanceMonitor()
        
        # Rate limiting
        self.semaphores = {}
        
        # Browser management
        self.playwright = None
        self.browser = None
        self.browser_contexts = []
        
        # Thread pool for CPU-intensive tasks
        self.thread_pool = ThreadPoolExecutor(max_workers=max_threads)
        
        # Session management
        self.session = None
        
        # Results storage
        self.articles: List[Article] = []
        self.articles_lock = asyncio.Lock()
        
        # Deduplication
        self.seen_urls: Set[str] = set()
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def start(self):
        """Initialize async components."""
        # Create aiohttp session
        connector = aiohttp.TCPConnector(limit=self.max_concurrent * 2)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        
        # Initialize Playwright for JS-heavy sites
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        # Create browser contexts for parallel browsing
        for _ in range(min(self.max_concurrent // 2, 5)):
            context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            self.browser_contexts.append(context)
        
        self.logger.info(f"AsyncNewsScraperEngine started with {self.max_concurrent} concurrent connections")
    
    async def close(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()
        
        for context in self.browser_contexts:
            await context.close()
        
        if self.browser:
            await self.browser.close()
        
        if self.playwright:
            await self.playwright.stop()
        
        self.thread_pool.shutdown(wait=True)
        self.monitor.stop()
        
        self.logger.info("AsyncNewsScraperEngine closed")
    
    def get_rate_limiter(self, source: NewsSource) -> asyncio.Semaphore:
        """Get or create rate limiter for source."""
        if source.name not in self.semaphores:
            # Convert rate limit to semaphore value
            max_concurrent = max(1, int(source.rate_limit * 2))
            self.semaphores[source.name] = asyncio.Semaphore(max_concurrent)
        return self.semaphores[source.name]
    
    async def scrape_sources_async(self, sources: List[NewsSource]) -> List[Article]:
        """Scrape multiple sources concurrently."""
        self.logger.info(f"Starting async scraping of {len(sources)} sources")
        
        # Create tasks for each source
        tasks = []
        for source in sources:
            task = asyncio.create_task(self.scrape_source_async(source))
            tasks.append(task)
        
        # Wait for all sources to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect all articles
        all_articles = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Error scraping {sources[i].name}: {result}")
                self.monitor.record_error(sources[i].name)
            else:
                all_articles.extend(result)
        
        self.logger.info(f"Async scraping completed: {len(all_articles)} articles collected")
        return all_articles
    
    async def scrape_source_async(self, source: NewsSource) -> List[Article]:
        """Scrape a single source asynchronously."""
        rate_limiter = self.get_rate_limiter(source)
        
        async with rate_limiter:
            try:
                self.logger.info(f"Scraping {source.name} ({'JS' if source.requires_js else 'HTTP'})")
                
                if source.requires_js:
                    return await self.scrape_js_source(source)
                else:
                    return await self.scrape_http_source(source)
                    
            except Exception as e:
                self.logger.error(f"Error scraping {source.name}: {e}")
                self.monitor.record_error(source.name)
                return []
    
    async def scrape_http_source(self, source: NewsSource) -> List[Article]:
        """Scrape source using async HTTP requests."""
        start_time = time.time()
        
        try:
            # Get article links
            links = await self.get_article_links_http(source)
            self.logger.info(f"Found {len(links)} links for {source.name}")
            
            # Scrape articles concurrently
            semaphore = asyncio.Semaphore(self.max_concurrent)
            tasks = []
            
            for link in links:
                if link not in self.seen_urls:
                    self.seen_urls.add(link)
                    task = asyncio.create_task(
                        self.scrape_article_http(semaphore, source, link)
                    )
                    tasks.append(task)
            
            # Wait for all articles
            articles = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter successful results
            valid_articles = [
                article for article in articles 
                if isinstance(article, Article)
            ]
            
            # Record performance
            response_time = time.time() - start_time
            self.monitor.record_success(response_time)
            
            for article in valid_articles:
                self.monitor.record_article(source.name)
            
            return valid_articles
            
        except Exception as e:
            self.logger.error(f"HTTP scraping error for {source.name}: {e}")
            self.monitor.record_error(source.name)
            return []
    
    async def get_article_links_http(self, source: NewsSource) -> List[str]:
        """Get article links using HTTP request."""
        try:
            async with self.session.get(source.base_url) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Use thread pool for CPU-intensive parsing
                    loop = asyncio.get_event_loop()
                    links = await loop.run_in_executor(
                        self.thread_pool,
                        self.extract_links_from_html,
                        html, source
                    )
                    return links
                else:
                    self.logger.warning(f"HTTP {response.status} for {source.base_url}")
                    return []
                    
        except Exception as e:
            self.logger.error(f"Error getting links from {source.base_url}: {e}")
            return []
    
    def extract_links_from_html(self, html: str, source: NewsSource) -> List[str]:
        """Extract article links from HTML (runs in thread pool)."""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        # Find all links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            
            # Convert relative URLs to absolute
            if href.startswith('/'):
                href = urljoin(source.base_url, href)
            
            # Check if link matches patterns
            for pattern in source.link_patterns:
                if re.search(pattern, href):
                    links.append(href)
                    break
        
        return list(set(links))  # Remove duplicates
    
    async def scrape_article_http(self, semaphore: asyncio.Semaphore, 
                                source: NewsSource, url: str) -> Optional[Article]:
        """Scrape individual article using HTTP."""
        async with semaphore:
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # Parse article in thread pool
                        loop = asyncio.get_event_loop()
                        article = await loop.run_in_executor(
                            self.thread_pool,
                            self.parse_article_html,
                            html, url, source
                        )
                        return article
                    else:
                        self.logger.debug(f"HTTP {response.status} for {url}")
                        return None
                        
            except Exception as e:
                self.logger.debug(f"Error scraping {url}: {e}")
                return None
    
    def parse_article_html(self, html: str, url: str, source: NewsSource) -> Optional[Article]:
        """Parse article from HTML (runs in thread pool)."""
        from bs4 import BeautifulSoup
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract article data
            title = self.extract_text_by_selector(soup, source.article_selectors.get('title', 'h1'))
            content = self.extract_content_by_selector(soup, source.article_selectors.get('content', 'p'))
            author = self.extract_text_by_selector(soup, source.article_selectors.get('author', '.author'))
            date = self.extract_text_by_selector(soup, source.article_selectors.get('date', 'time'))
            
            if not title or not content:
                return None
            
            # Create article
            article = Article(
                title=title.strip(),
                url=url,
                content=content.strip(),
                author=author.strip() if author else f"{source.name} Staff",
                published_date=date if date else datetime.now().isoformat(),
                source=source.name,
                scraped_date=datetime.now().isoformat(),
                content_length=len(content),
                word_count=len(content.split()),
                category=self.extract_category_from_url(url)
            )
            
            # Calculate reading time
            article.reading_time = max(1, article.word_count // 200)
            
            # Validate article
            article.validation_score = self.validate_article(article)
            article.content_quality = self.get_quality_label(article.validation_score)
            
            return article if article.validation_score >= 50 else None
            
        except Exception as e:
            self.logger.debug(f"Error parsing article {url}: {e}")
            return None
    
    def extract_text_by_selector(self, soup, selector: str) -> str:
        """Extract text using CSS selector."""
        try:
            element = soup.select_one(selector)
            return element.get_text(strip=True) if element else ""
        except:
            return ""
    
    def extract_content_by_selector(self, soup, selector: str) -> str:
        """Extract content from multiple elements."""
        try:
            elements = soup.select(selector)
            return " ".join(elem.get_text(strip=True) for elem in elements)
        except:
            return ""
    
    async def scrape_js_source(self, source: NewsSource) -> List[Article]:
        """Scrape JavaScript-heavy source using Playwright."""
        if not self.browser_contexts:
            self.logger.warning(f"No browser contexts available for {source.name}")
            return []
        
        # Use available browser context
        context = self.browser_contexts[0]
        
        try:
            self.logger.info(f"Using Playwright for {source.name}")
            
            # Get article links
            links = await self.get_article_links_js(context, source)
            self.logger.info(f"Found {len(links)} JS links for {source.name}")
            
            # Scrape articles with controlled concurrency
            articles = []
            semaphore = asyncio.Semaphore(2)  # Limit browser concurrency
            
            tasks = []
            for link in links[:20]:  # Limit for JS scraping
                if link not in self.seen_urls:
                    self.seen_urls.add(link)
                    task = asyncio.create_task(
                        self.scrape_article_js(semaphore, context, source, link)
                    )
                    tasks.append(task)
            
            # Wait for all articles
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter successful results
            valid_articles = [
                article for article in results 
                if isinstance(article, Article)
            ]
            
            for article in valid_articles:
                self.monitor.record_article(source.name)
            
            return valid_articles
            
        except Exception as e:
            self.logger.error(f"JS scraping error for {source.name}: {e}")
            self.monitor.record_error(source.name)
            return []
    
    async def get_article_links_js(self, context: BrowserContext, source: NewsSource) -> List[str]:
        """Get article links using Playwright."""
        page = await context.new_page()
        
        try:
            # Navigate to source
            await page.goto(source.base_url, wait_until="networkidle", timeout=30000)
            
            # Wait for content to load
            await page.wait_for_timeout(3000)
            
            # Extract links
            links = await page.evaluate(f"""
                () => {{
                    const patterns = {json.dumps(source.link_patterns)};
                    const links = Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(href => patterns.some(pattern => new RegExp(pattern).test(href)));
                    return [...new Set(links)];
                }}
            """)
            
            return links
            
        except Exception as e:
            self.logger.error(f"Error getting JS links from {source.base_url}: {e}")
            return []
        finally:
            await page.close()
    
    async def scrape_article_js(self, semaphore: asyncio.Semaphore, 
                              context: BrowserContext, source: NewsSource, url: str) -> Optional[Article]:
        """Scrape individual article using Playwright."""
        async with semaphore:
            page = await context.new_page()
            
            try:
                # Navigate to article
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Wait for content
                await page.wait_for_timeout(2000)
                
                # Extract article data using JavaScript
                article_data = await page.evaluate(f"""
                    () => {{
                        const selectors = {json.dumps(source.article_selectors)};
                        
                        const getTextBySelector = (selector) => {{
                            const element = document.querySelector(selector);
                            return element ? element.textContent.trim() : '';
                        }};
                        
                        const getContentBySelector = (selector) => {{
                            const elements = document.querySelectorAll(selector);
                            return Array.from(elements).map(el => el.textContent.trim()).join(' ');
                        }};
                        
                        return {{
                            title: getTextBySelector(selectors.title || 'h1'),
                            content: getContentBySelector(selectors.content || 'p'),
                            author: getTextBySelector(selectors.author || '.author'),
                            date: getTextBySelector(selectors.date || 'time')
                        }};
                    }}
                """)
                
                if not article_data['title'] or not article_data['content']:
                    return None
                
                # Create article
                article = Article(
                    title=article_data['title'],
                    url=url,
                    content=article_data['content'],
                    author=article_data['author'] or f"{source.name} Staff",
                    published_date=article_data['date'] or datetime.now().isoformat(),
                    source=source.name,
                    scraped_date=datetime.now().isoformat(),
                    content_length=len(article_data['content']),
                    word_count=len(article_data['content'].split()),
                    category=self.extract_category_from_url(url)
                )
                
                # Calculate reading time
                article.reading_time = max(1, article.word_count // 200)
                
                # Validate article
                article.validation_score = self.validate_article(article)
                article.content_quality = self.get_quality_label(article.validation_score)
                
                return article if article.validation_score >= 50 else None
                
            except Exception as e:
                self.logger.debug(f"Error scraping JS article {url}: {e}")
                return None
            finally:
                await page.close()
    
    def extract_category_from_url(self, url: str) -> str:
        """Extract category from URL."""
        url_lower = url.lower()
        
        categories = {
            "Technology": ["tech", "technology", "gadgets", "ai", "software"],
            "Politics": ["politics", "political", "government", "election"],
            "Business": ["business", "finance", "economy", "market"],
            "Sports": ["sports", "sport", "football", "basketball"],
            "Health": ["health", "medical", "medicine", "covid"],
            "Science": ["science", "research", "study", "discovery"]
        }
        
        for category, keywords in categories.items():
            if any(keyword in url_lower for keyword in keywords):
                return category
        
        return "News"
    
    def validate_article(self, article: Article) -> int:
        """Validate article quality (same logic as Python ValidationPipeline)."""
        score = 100
        
        # Check required fields
        if not article.title:
            score -= 25
        if not article.content:
            score -= 30
        if not article.author:
            score -= 10
        
        # Content length validation
        if article.content_length < 100:
            score -= 20
        elif article.content_length > 10000:
            score -= 5
        
        # Title length validation
        if len(article.title) < 10:
            score -= 10
        elif len(article.title) > 200:
            score -= 5
        
        return max(0, score)
    
    def get_quality_label(self, score: int) -> str:
        """Get quality label from score."""
        if score >= 80:
            return "high"
        elif score >= 60:
            return "medium"
        else:
            return "low"
    
    async def save_articles(self, articles: List[Article], output_path: str):
        """Save articles to JSON file asynchronously."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert articles to dictionaries
        articles_data = [asdict(article) for article in articles]
        
        # Save asynchronously
        async with aiofiles.open(output_file, 'w') as f:
            await f.write(json.dumps(articles_data, indent=2, ensure_ascii=False))
        
        self.logger.info(f"Saved {len(articles)} articles to {output_file}")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics."""
        return self.monitor.get_stats()

# Pre-configured news sources
ASYNC_NEWS_SOURCES = [
    NewsSource(
        name="BBC",
        base_url="https://www.bbc.com/news",
        article_selectors={
            "title": "h1[data-testid='headline'], h1",
            "content": "div[data-component='text-block'] p",
            "author": "span[data-testid='byline']",
            "date": "time[datetime]"
        },
        link_patterns=[r"/news/.*"],
        requires_js=False,
        rate_limit=1.0
    ),
    NewsSource(
        name="CNN",
        base_url="https://www.cnn.com",
        article_selectors={
            "title": "h1.headline__text, h1",
            "content": ".zn-body__paragraph, article p",
            "author": ".byline__name",
            "date": ".update-time"
        },
        link_patterns=[r"/2024/.*", r"/2025/.*"],
        requires_js=False,
        rate_limit=1.0
    ),
    NewsSource(
        name="TechCrunch",
        base_url="https://techcrunch.com",
        article_selectors={
            "title": "h1.article__title, h1",
            "content": ".article-content p",
            "author": ".article__byline a",
            "date": "time[datetime]"
        },
        link_patterns=[r"/2024/.*", r"/2025/.*"],
        requires_js=False,
        rate_limit=2.0
    ),
    NewsSource(
        name="The Verge",
        base_url="https://www.theverge.com",
        article_selectors={
            "title": "h1.c-page-title, h1",
            "content": ".c-entry-content p",
            "author": ".c-byline__author-name",
            "date": "time[datetime]"
        },
        link_patterns=[r"/2024/.*", r"/2025/.*"],
        requires_js=True,
        rate_limit=1.0
    ),
    NewsSource(
        name="Wired",
        base_url="https://www.wired.com",
        article_selectors={
            "title": "h1[data-testid='ContentHeaderHed'], h1",
            "content": "div[data-testid='ArticleBodyWrapper'] p",
            "author": "a[data-testid='ContentHeaderAuthorLink']",
            "date": "time[data-testid='ContentHeaderPublishDate']"
        },
        link_patterns=[r"/story/.*"],
        requires_js=True,
        rate_limit=1.0
    )
]
