"""
Wired news spider for NeuroNews.
"""

import re
from datetime import datetime

import scrapy

from ..items import NewsItem


class WiredSpider(scrapy.Spider):
    """Spider for crawling Wired articles."""

    name = "wired"
    allowed_domains = ["wired.com"]
    start_urls = ["https://www.wired.com/"]

    def parse(self, response):
        """Parse the main Wired page to find article links."""
        # Extract article links
        article_links = response.css('a[href*="/story/"]::attr(href)').getall()

        for link in article_links:
            if link.startswith("/"):
                link = response.urljoin(link)
            yield scrapy.Request(url=link, callback=self.parse_article)

    def parse_article(self, response):
        """Parse a Wired article page."""
        item = NewsItem()

        # Extract title
        item["title"] = (
            response.css('h1[data-testid="ContentHeaderHed"]::text').get()
            or response.css("h1.content-header__hed::text").get()
            or response.css("h1::text").get()
        )

        item["url"] = response.url
        item["source"] = "Wired"

        # Extract content
        content_paragraphs = (
            response.css('div[data-testid="ArticleBodyWrapper"] p::text').getall()
            or response.css(".article__body p::text").getall()
            or response.css("article p::text").getall()
        )

        item["content"] = (
            " ".join(content_paragraphs).strip() if content_paragraphs else ""
        )

        # Extract publication date
        date_element = (
            response.css(
                'time[data-testid="ContentHeaderPublishDate"]::attr(datetime)'
            ).get()
            or response.css("time::attr(datetime)").get()
            or response.css(
                'meta[property="article:published_time"]::attr(content)'
            ).get()
        )

        if date_element:
            item["published_date"] = date_element
        else:
            item["published_date"] = datetime.now().isoformat()

        # Extract author
        author = (
            response.css('a[data-testid="ContentHeaderAuthorLink"]::text').get()
            or response.css(".byline__name::text").get()
            or response.css('meta[name="author"]::attr(content)').get()
        )
        item["author"] = author.strip() if author else "Wired Staff"

        # Extract category
        category = self._extract_category(response.url, response)
        item["category"] = category

        if item["title"] and item["content"]:
            yield item

    def _extract_category(self, url, response):
        """Extract category from URL or page structure."""
        url_lower = url.lower()
        if "/gear/" in url_lower:
            return "Gear"
        elif "/science/" in url_lower:
            return "Science"
        elif "/security/" in url_lower:
            return "Security"
        elif "/business/" in url_lower:
            return "Business"
        elif "/culture/" in url_lower:
            return "Culture"
        elif "/ideas/" in url_lower:
            return "Ideas"
        elif "/backchannel/" in url_lower:
            return "Backchannel"
        else:
            # Try to extract from tags or section
            section = response.css('a[data-testid="ContentHeaderRubric"]::text').get()
            return section.strip() if section else "Technology"
