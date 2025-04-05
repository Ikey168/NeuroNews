"""
Items for the NeuroNews scrapers.
"""
import scrapy


class NewsItem(scrapy.Item):
    """Item for storing scraped news articles."""
    title = scrapy.Field()
    url = scrapy.Field()
    content = scrapy.Field()
    published_date = scrapy.Field()
    source = scrapy.Field()
    author = scrapy.Field()
    category = scrapy.Field()
