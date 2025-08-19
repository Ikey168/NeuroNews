"""
BBC news spider for NeuroNews.
"""

import re
from datetime import datetime

import scrapy

from ..items import NewsItem


class BBCSpider(scrapy.Spider):
    """Spider for crawling BBC news articles."""

    name = "bbc"
    allowed_domains = ["bbc.com"]
    start_urls = ["https://www.bbc.com/news"]

    def parse(self, response):
        """Parse the main BBC page to find article links."""
        # Extract article links from the main page
        article_links = response.css('a[href*="/news/"]::attr(href)').getall()

        for link in article_links:
            if link.startswith("/"):
                link = response.urljoin(link)
            # Filter for actual article URLs (contain numbers indicating
            # article ID)
            if re.search(r"/news/[a-z-]+-\d+", link):
                yield scrapy.Request(url=link, callback=self.parse_article)

    def parse_article(self, response):
        """Parse a BBC article page."""
        item = NewsItem()

        # Extract title
        item["title"] = (
            response.css('h1[data-testid="headline"]::text').get()
            or response.css("h1.story-headline::text").get()
            or response.css("h1::text").get()
        )

        item["url"] = response.url
        item["source"] = "BBC"

        # Extract content from BBC's specific structure
        content_paragraphs = (
            response.css('div[data-component="text-block"] p::text').getall()
            or response.css(".story-body__inner p::text").getall()
            or response.css("article p::text").getall()
        )

        item["content"] = (
            " ".join(content_paragraphs).strip() if content_paragraphs else ""
        )

        # Extract publication date
        date_element = (
            response.css("time::attr(datetime)").get()
            or response.css('div[data-testid="timestamp"]::text').get()
            or response.css(".date::text").get()
        )

        if date_element:
            item["published_date"] = self._parse_bbc_date(date_element)
        else:
            item["published_date"] = datetime.now().isoformat()

        # Extract author
        author = (
            response.css('div[data-testid="byline-name"]::text').get()
            or response.css(".byline__name::text").get()
            or response.css('meta[name="author"]::attr(content)').get()
        )
        item["author"] = author.strip() if author else "BBC Staff"

        # Extract category
        category = self._extract_category(response.url, response)
        item["category"] = category

        if item["title"] and item["content"]:
            yield item

    def _parse_bbc_date(self, date_string):
        """Parse BBC's date format."""
        try:
            # BBC uses ISO format or relative dates
            if "T" in date_string and "Z" in date_string:
                # ISO format
                return date_string
            else:
                # Try to parse relative dates like "2 hours ago"
                return datetime.now().isoformat()
        except BaseException:
            return datetime.now().isoformat()

    def _extract_category(self, url, response):
        """Extract category from URL or page structure."""
        url_lower = url.lower()
        if "/politics/" in url_lower:
            return "Politics"
        elif "/business/" in url_lower:
            return "Business"
        elif "/technology/" in url_lower:
            return "Technology"
        elif "/health/" in url_lower:
            return "Health"
        elif "/sport/" in url_lower:
            return "Sports"
        elif "/entertainment/" in url_lower:
            return "Entertainment"
        elif "/science/" in url_lower:
            return "Science"
        elif "/world/" in url_lower:
            return "World"
        else:
            # Try to extract from breadcrumbs or section indicators
            breadcrumb = response.css(
                'nav[aria-label="Breadcrumb"] span::text'
            ).getall()
            if breadcrumb and len(breadcrumb) > 1:
                return breadcrumb[1].strip()
            return "News"
