"""
TechCrunch news spider for NeuroNews.
"""
import scrapy
from datetime import datetime
from ..items import NewsItem
import re


class TechCrunchSpider(scrapy.Spider):
    """Spider for crawling TechCrunch articles."""
    name = 'techcrunch'
    allowed_domains = ['techcrunch.com']
    start_urls = ['https://techcrunch.com/']
    
    def parse(self, response):
        """Parse the main TechCrunch page to find article links."""
        # Extract article links
        article_links = response.css('a[href*="techcrunch.com/2024/"], a[href*="techcrunch.com/2025/"]::attr(href)').getall()
        
        for link in article_links:
            if not link.startswith('http'):
                link = response.urljoin(link)
            yield scrapy.Request(url=link, callback=self.parse_article)
        
        # Also check for relative links
        relative_links = response.css('a[href^="/2024/"], a[href^="/2025/"]::attr(href)').getall()
        for link in relative_links:
            full_url = response.urljoin(link)
            yield scrapy.Request(url=full_url, callback=self.parse_article)

    def parse_article(self, response):
        """Parse a TechCrunch article page."""
        item = NewsItem()
        
        # Extract title
        item['title'] = (
            response.css('h1.article__title::text').get() or
            response.css('h1.entry-title::text').get() or
            response.css('h1::text').get()
        )
        
        item['url'] = response.url
        item['source'] = 'TechCrunch'
        
        # Extract content from TechCrunch's structure
        content_paragraphs = (
            response.css('.article-content p::text').getall() or
            response.css('.entry-content p::text').getall() or
            response.css('div[class*="articleContent"] p::text').getall()
        )
        
        item['content'] = ' '.join(content_paragraphs).strip() if content_paragraphs else ''
        
        # Extract publication date
        date_element = (
            response.css('time.full-date-time::attr(datetime)').get() or
            response.css('.byline time::attr(datetime)').get() or
            response.css('meta[property="article:published_time"]::attr(content)').get()
        )
        
        if date_element:
            item['published_date'] = self._parse_techcrunch_date(date_element)
        else:
            item['published_date'] = datetime.now().isoformat()
        
        # Extract author
        author = (
            response.css('.byline a[rel="author"]::text').get() or
            response.css('.article__byline a::text').get() or
            response.css('meta[name="author"]::attr(content)').get()
        )
        item['author'] = author.strip() if author else 'TechCrunch Staff'
        
        # TechCrunch is primarily technology focused
        item['category'] = self._extract_category(response.url, response)
        
        if item['title'] and item['content']:
            yield item

    def _parse_techcrunch_date(self, date_string):
        """Parse TechCrunch's date format."""
        try:
            if 'T' in date_string:
                # ISO format
                return date_string
            else:
                return datetime.now().isoformat()
        except:
            return datetime.now().isoformat()

    def _extract_category(self, url, response):
        """Extract category from URL or page structure."""
        url_lower = url.lower()
        if '/startups/' in url_lower:
            return 'Startups'
        elif '/apps/' in url_lower:
            return 'Apps'
        elif '/gadgets/' in url_lower:
            return 'Gadgets'
        elif '/venture/' in url_lower:
            return 'Venture Capital'
        elif '/security/' in url_lower:
            return 'Security'
        elif '/mobile/' in url_lower:
            return 'Mobile'
        elif '/ai/' in url_lower:
            return 'Artificial Intelligence'
        else:
            # Try to extract from tags or categories
            category_tag = response.css('.tags a::text').get()
            return category_tag.strip() if category_tag else 'Technology'
