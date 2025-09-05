"""
Data source connectors for scraper extensions.
"""

from .base import BaseConnector, ConnectorError
from .rss_connector import RSSConnector
from .api_connector import APIConnector, RESTConnector, GraphQLConnector
from .database_connector import DatabaseConnector
from .filesystem_connector import FileSystemConnector
from .web_connector import WebScrapingConnector
from .social_media_connector import SocialMediaConnector
from .news_aggregator_connector import NewsAggregatorConnector

__all__ = [
    "BaseConnector",
    "ConnectorError",
    "RSSConnector",
    "APIConnector",
    "RESTConnector", 
    "GraphQLConnector",
    "DatabaseConnector",
    "FileSystemConnector",
    "WebScrapingConnector",
    "SocialMediaConnector",
    "NewsAggregatorConnector",
]
