"""
Ars Technica news spider for NeuroNews.
"""
import scrapy
from datetime import datetime
from ..items import NewsItem
import re


class ArsTechnicaSpider(scrapy.Spider):
    """Spider for crawling Ars Technica articles."""
    name = 'arstechnica'
    allowed_domains = ['arstechnica.com']
    start_urls = ['https://arstechnica.com/']
    
    def parse(self, response):
        """Parse the main Ars Technica page to find article links."""
        # Extract article links
        article_links = response.css('a[href*="/2024/"], a[href*="/2025/"]::attr(href)').getall()
        
        for link in article_links:
            if link.startswith('/'):
                link = response.urljoin(link)
            if link.endswith('/'):
                yield scrapy.Request(url=link, callback=self.parse_article)

    def parse_article(self, response):
        """Parse an Ars Technica article page."""
        item = NewsItem()
        
        # Extract title
        item['title'] = (
            response.css('h1.post-title::text').get() or
            response.css('h1[itemprop="headline"]::text').get() or
            response.css('h1::text').get()
        )
        
        item['url'] = response.url
        item['source'] = 'Ars Technica'
        
        # Extract content from Ars Technica's structure
        content_paragraphs = (
            response.css('.post-content p::text').getall() or
            response.css('div[itemprop="articleBody"] p::text').getall() or
            response.css('article p::text').getall()
        )
        
        item['content'] = ' '.join(content_paragraphs).strip() if content_paragraphs else ''
        
        # Extract publication date
        date_element = (
            response.css('time[itemprop="datePublished"]::attr(datetime)').get() or
            response.css('.post-meta time::attr(datetime)').get() or
            response.css('meta[property="article:published_time"]::attr(content)').get()
        )
        
        if date_element:
            item['published_date'] = self._parse_ars_date(date_element)
        else:
            item['published_date'] = datetime.now().isoformat()
        
        # Extract author
        author = (
            response.css('span[itemprop="author"] a::text').get() or
            response.css('.byline a[rel="author"]::text').get() or
            response.css('meta[name="author"]::attr(content)').get()
        )
        item['author'] = author.strip() if author else 'Ars Technica Staff'
        
        # Extract category
        category = self._extract_category(response.url, response)
        item['category'] = category
        
        if item['title'] and item['content']:
            yield item

    def _parse_ars_date(self, date_string):
        """Parse Ars Technica's date format."""
        try:
            if 'T' in date_string:
                return date_string
            else:
                return datetime.now().isoformat()
        except:
            return datetime.now().isoformat()

    def _extract_category(self, url, response):
        """Extract category from URL or page structure."""
        url_lower = url.lower()
        if '/tech-policy/' in url_lower:
            return 'Tech Policy'
        elif '/security/' in url_lower:
            return 'Security'
        elif '/gadgets/' in url_lower:
            return 'Gadgets'
        elif '/science/' in url_lower:
            return 'Science'
        elif '/gaming/' in url_lower:
            return 'Gaming'
        elif '/cars/' in url_lower:
            return 'Automotive'
        elif '/space/' in url_lower:
            return 'Space'
        else:
            # Try to extract from section indicators
            section = response.css('.post-meta .section::text').get()
            return section.strip() if section else 'Technology'
