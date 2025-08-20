"""
The Verge news spider for NeuroNews.
"""

from datetime import datetime

import scrapy

from ..items import NewsItem


class VergeSpider(scrapy.Spider):
    """Spider for crawling The Verge articles."""

    name = "theverge"
    allowed_domains = ["theverge.com"]
    start_urls = ["https://www.theverge.com/"]

    def parse(self, response):
        """Parse the main Verge page to find article links."""
        # Extract article links
        article_links = response.css(
            'a[href*="/2024/"], a[href*="/2025/"]::attr(href)'
        ).getall()

        for link in article_links:
            if link.startswith("/"):
                link = response.urljoin(link)
            yield scrapy.Request(url=link, callback=self.parse_article)

    def parse_article(self, response):
        """Parse a Verge article page."""
        item = NewsItem()

        # Extract title
        item["title"] = (
            response.css("h1.c-page-title::text").get()
            or response.css('h1[data-testid="ArticleTitle"]::text').get()
            or response.css("h1::text").get()
        )

        item["url"] = response.url
        item["source"] = "The Verge"

        # Extract content
        content_paragraphs = (
            response.css(".c-entry-content p::text").getall()
            or response.css('div[data-testid="ArticleBody"] p::text').getall()
            or response.css("article p::text").getall()
        )

        item["content"] = (
            " ".join(content_paragraphs).strip() if content_paragraphs else ""
        )

        # Extract publication date
        date_element = (
            response.css("time[datetime]::attr(datetime)").get()
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
            response.css(".c-byline__author-name::text").get()
            or response.css('span[data-testid="BylineAuthor"]::text').get()
            or response.css('meta[name="author"]::attr(content)').get()
        )
        item["author"] = author.strip() if author else "The Verge Sta"

        # Extract category
        category = self._extract_category(response.url, response)
        item["category"] = category

        if item["title"] and item["content"]:
            yield item

    def _extract_category(self, url, response):
        """Extract category from URL or page structure."""
        url_lower = url.lower()
        if "/tech/" in url_lower:
            return "Technology"
        elif "/gaming/" in url_lower:
            return "Gaming"
        elif "/science/" in url_lower:
            return "Science"
        elif "/mobile/" in url_lower:
            return "Mobile"
        elif "/apps/" in url_lower:
            return "Apps"
        elif "/cars/" in url_lower:
            return "Transportation"
        elif "/policy/" in url_lower:
            return "Policy"
        else:
            # Try to extract from tags or categories
            category_tag = response.css(".c-entry-group-labels__item::text").get()
            return category_tag.strip() if category_tag else "Technology"
