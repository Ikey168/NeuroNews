"""
CNN news spider for NeuroNews.
"""

import re
from datetime import datetime

import scrapy

from ..items import NewsItem


class CNNSpider(scrapy.Spider):
    """Spider for crawling CNN news articles."""

    name = "cnn"
    allowed_domains = ["cnn.com"]
    start_urls = ["https://www.cnn.com/"]

    def parse(self, response):
        """Parse the main CNN page to find article links."""
        # Extract article links from the main page
        article_links = response.css(
            'a[href*="/2024/"], a[href*="/2025/"]::attr(href)'
        ).getall()

        for link in article_links:
            if link.startswith("/"):
                link = response.urljoin(link)
            if (
                "/index.html" in link
                or "/politics/" in link
                or "/business/" in link
                or "/tech/" in link
            ):
                yield scrapy.Request(url=link, callback=self.parse_article)

        # Follow pagination if available
        next_page = response.css("a.pagination-arrow-right::attr(href)").get()
        if next_page:
            yield response.follow(next_page, self.parse)

    def parse_article(self, response):
        """Parse a CNN article page."""
        item = NewsItem()

        # Extract title
        item["title"] = (
            response.css("h1.headline__text::text").get()
            or response.css("h1::text").get()
            or response.css("title::text").get()
        )

        item["url"] = response.url
        item["source"] = "CNN"

        # Extract content from CNN's specific structure
        content_paragraphs = response.css(
            ".zn-body__paragraph::text, .zn-body__paragraph p::text"
        ).getall()
        if not content_paragraphs:
            content_paragraphs = response.css(
                'div[data-component-name="ArticleBody"] p::text'
            ).getall()

        item["content"] = (
            " ".join(content_paragraphs).strip() if content_paragraphs else ""
        )

        # Extract publication date
        date_element = (
            response.css("div.timestamp::text").get()
            or response.css("p.update-time::text").get()
            or response.css(
                'meta[property="article:published_time"]::attr(content)'
            ).get()
        )

        if date_element:
            item["published_date"] = self._parse_cnn_date(date_element)
        else:
            item["published_date"] = datetime.now().isoformat()

        # Extract author
        author = (
            response.css(".byline__name::text").get()
            or response.css("span.metadata__byline__author::text").get()
            or response.css('meta[name="author"]::attr(content)').get()
        )
        item["author"] = author.strip() if author else "CNN Staff"

        # Extract category from URL or page structure
        category = self._extract_category(response.url, response)
        item["category"] = category

        if item["title"] and item["content"]:
            yield item

    def _parse_cnn_date(self, date_string):
        """Parse CNN's date format."""
        try:
            # CNN often uses formats like "Updated 1234 GMT (5678 HKT) January 1, 2024"
            # Extract the actual date part
            date_match = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})", date_string)
            if date_match:
                date_str = date_match.group(1)
                parsed_date = datetime.strptime(date_str, "%B %d, %Y")
                return parsed_date.isoformat()
        except:
            pass
        return datetime.now().isoformat()

    def _extract_category(self, url, response):
        """Extract category from URL or page structure."""
        url_lower = url.lower()
        if "/politics/" in url_lower:
            return "Politics"
        elif "/business/" in url_lower:
            return "Business"
        elif "/tech/" in url_lower:
            return "Technology"
        elif "/health/" in url_lower:
            return "Health"
        elif "/sport/" in url_lower:
            return "Sports"
        elif "/entertainment/" in url_lower:
            return "Entertainment"
        else:
            # Try to extract from page breadcrumbs
            breadcrumb = response.css(".breadcrumb__item::text").get()
            return breadcrumb.strip() if breadcrumb else "News"
