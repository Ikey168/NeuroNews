"""
Reuters news spider for NeuroNews.
"""

from datetime import datetime

import scrapy

from ..items import NewsItem


class ReutersSpider(scrapy.Spider):
    """Spider for crawling Reuters articles."""

    name = "reuters"
    allowed_domains = ["reuters.com"]
    start_urls = ["https://www.reuters.com/"]

    def parse(self, response):
        """Parse the main Reuters page to find article links."""
        # Extract article links
        article_links = response.css('a[href*="/article/"]::attr(href)').getall()

        for link in article_links:
            if link.startswith("/"):
                link = response.urljoin(link)
            yield scrapy.Request(url=link, callback=self.parse_article)

    def parse_article(self, response):
        """Parse a Reuters article page."""
        item = NewsItem()

        # Extract title
        item["title"] = (
            response.css('h1[data-testid="Heading"]::text').get()
            or response.css("h1.ArticleHeader_headline::text").get()
            or response.css("h1::text").get()
        )

        item["url"] = response.url
        item["source"] = "Reuters"

        # Extract content
        content_paragraphs = (
            response.css('div[data-testid="paragraph"] p::text').getall()
            or response.css(".StandardArticleBody_body p::text").getall()
            or response.css("article p::text").getall()
        )

        item["content"] = (
            " ".join(content_paragraphs).strip() if content_paragraphs else ""
        )

        # Extract publication date
        date_element = (
            response.css("time::attr(datetime)").get()
            or response.css('span[data-testid="Body"] time::attr(datetime)').get()
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
            response.css('div[data-testid="BylineBar"] a::text').get()
            or response.css(".byline a::text").get()
            or response.css('meta[name="author"]::attr(content)').get()
        )
        item["author"] = author.strip() if author else "Reuters Staff"

        # Extract category
        category = self._extract_category(response.url, response)
        item["category"] = category

        if item["title"] and item["content"]:
            yield item

    def _extract_category(self, url, response):
        """Extract category from URL or page structure."""
        url_lower = url.lower()
        if "/business/" in url_lower:
            return "Business"
        elif "/technology/" in url_lower:
            return "Technology"
        elif "/world/" in url_lower:
            return "World"
        elif "/markets/" in url_lower:
            return "Markets"
        elif "/sports/" in url_lower:
            return "Sports"
        elif "/politics/" in url_lower:
            return "Politics"
        else:
            # Try to extract from breadcrumbs
            breadcrumb = response.css('nav[aria-label="breadcrumb"] a::text').getall()
            if breadcrumb and len(breadcrumb) > 1:
                return breadcrumb[-2].strip()
            return "News"
