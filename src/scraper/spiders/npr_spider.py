"""
NPR news spider for NeuroNews.
"""
import scrapy
from datetime import datetime
from ..items import NewsItem
import re


class NPRSpider(scrapy.Spider):
    """Spider for crawling NPR articles."""
    name = 'npr'
    allowed_domains = ['npr.org']
    start_urls = ['https://www.npr.org/']
    
    def parse(self, response):
        """Parse the main NPR page to find article links."""
        # Extract article links
        article_links = response.css('a[href*="/2024/"], a[href*="/2025/"]::attr(href)').getall()
        
        for link in article_links:
            if link.startswith('/'):
                link = response.urljoin(link)
            # Filter for actual story URLs
            if '/sections/' in link or '/story/' in link:
                yield scrapy.Request(url=link, callback=self.parse_article)

    def parse_article(self, response):
        """Parse an NPR article page."""
        item = NewsItem()
        
        # Extract title
        item['title'] = (
            response.css('h1.storytitle::text').get() or
            response.css('h1.story-title::text').get() or
            response.css('h1::text').get()
        )
        
        item['url'] = response.url
        item['source'] = 'NPR'
        
        # Extract content
        content_paragraphs = (
            response.css('#storytext p::text').getall() or
            response.css('.storytext p::text').getall() or
            response.css('article p::text').getall()
        )
        
        item['content'] = ' '.join(content_paragraphs).strip() if content_paragraphs else ''
        
        # Extract publication date
        date_element = (
            response.css('.dateblock time::attr(datetime)').get() or
            response.css('time::attr(datetime)').get() or
            response.css('meta[property="article:published_time"]::attr(content)').get()
        )
        
        if date_element:
            item['published_date'] = date_element
        else:
            item['published_date'] = datetime.now().isoformat()
        
        # Extract author
        author = (
            response.css('.byline__name a::text').get() or
            response.css('.byline a::text').get() or
            response.css('meta[name="author"]::attr(content)').get()
        )
        item['author'] = author.strip() if author else 'NPR Staff'
        
        # Extract category
        category = self._extract_category(response.url, response)
        item['category'] = category
        
        if item['title'] and item['content']:
            yield item

    def _extract_category(self, url, response):
        """Extract category from URL or page structure."""
        url_lower = url.lower()
        if '/politics/' in url_lower:
            return 'Politics'
        elif '/business/' in url_lower:
            return 'Business'
        elif '/health/' in url_lower:
            return 'Health'
        elif '/science/' in url_lower:
            return 'Science'
        elif '/technology/' in url_lower:
            return 'Technology'
        elif '/world/' in url_lower:
            return 'World'
        elif '/national/' in url_lower:
            return 'National'
        elif '/music/' in url_lower:
            return 'Music'
        elif '/books/' in url_lower:
            return 'Books'
        else:
            # Try to extract from section path
            if '/sections/' in url_lower:
                section_part = url_lower.split('/sections/')[1].split('/')[0]
                return section_part.replace('-', ' ').title()
            return 'News'
