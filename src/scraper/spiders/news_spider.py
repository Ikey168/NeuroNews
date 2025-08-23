"""
News spider for NeuroNews.
"""

from datetime import datetime

from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule

from ..items import NewsItem
from ..settings import SCRAPING_SOURCES


class NewsSpider(CrawlSpider):
    """Spider for crawling news websites and extracting articles."""

    name = "news"
    allowed_domains = [url.split("/")[2] for url in SCRAPING_SOURCES]
    start_urls = SCRAPING_SOURCES

    # Rules for following links
    rules = (
        # Extract links matching '/news/', '/article/', etc. and follow them
        Rule(
            LinkExtractor(
                allow=(r"/news/", r"/article/", r"/tech/", r"/politics/", r"/business/")
            ),
            callback="parse_article",
            follow=True,
        ),
    )

    def parse_article(self, response):
        """Parse a news article page."""
        # This is a basic implementation that would need to be customized
        # for each specific news site's HTML structure

        # Create a new NewsItem
        item = NewsItem()

        # Extract information using CSS or XPath selectors
        # These selectors are generic and would need to be adjusted for real
        # sites
        item["title"] = (
            response.css("h1::text").get() or response.css("title::text").get()
        )
        item["url"] = response.url

        # Extract the main content
        # This is a simplified approach; real implementation would be more
        # complex
        content_selectors = [
            "article p::text",
            ".article-body p::text",
            ".content p::text",
            "#main-content p::text",
        ]

        for selector in content_selectors:
            content = response.css(selector).getall()
            if content:
                item["content"] = " ".join(content)
                break
        else:
            # If none of the selectors matched, use a fallback
            item["content"] = " ".join(response.css("p::text").getall())

        # Try to extract the publication date
        date_selectors = [
            "time::attr(datetime)",
            ".date::text",
            ".published-date::text",
            'meta[property="article:published_time"]::attr(content)',
        ]

        for selector in date_selectors:
            date = response.css(selector).get()
            if date:
                item["published_date"] = date
                break
        else:
            # If no date found, use current time
            item["published_date"] = datetime.now().isoformat()

        # Extract the source (domain name)
        item["source"] = response.url.split("/")[2]

        # Try to extract the author
        author_selectors = [
            ".author::text",
            ".byline::text",
            'meta[name="author"]::attr(content)',
        ]

        for selector in author_selectors:
            author = response.css(selector).get()
            if author:
                item["author"] = author.strip()
                break
        else:
            item["author"] = "Unknown"

        # Try to extract the category
        category_selectors = [
            ".category::text",
            ".section::text",
            'meta[property="article:section"]::attr(content)',
        ]

        for selector in category_selectors:
            category = response.css(selector).get()
            if category:
                item["category"] = category.strip()
                break
        else:
            # Try to infer category from URL
            url_path = response.url.split("/")
            for category in [
                "news",
                "tech",
                "politics",
                "business",
                "sports",
                "entertainment",
            ]:
                if category in url_path:
                    item["category"] = category
                    break
            else:
                item["category"] = "General"

        return item
