"""
API Routes module for NeuroNews.

This module contains all the API route definitions for the application.
"""

from . import (
    api_key_routes,
    article_routes,
    auth_routes,
    event_routes,
    event_timeline_routes,
    graph_routes,
    knowledge_graph_routes,
    news_routes,
    sentiment_routes,
    sentiment_trends_routes,
    summary_routes,
    topic_routes,
    veracity_routes,
    waf_security_routes,
)

# Import modules with optional dependencies
try:
    from . import enhanced_graph_routes
    from . import enhanced_kg_routes
    from . import quicksight_routes
    from . import rate_limit_routes
    from . import rbac_routes
except ImportError:
    # These modules have optional dependencies (redis, etc.)
    pass

__all__ = [
    "api_key_routes",
    "article_routes",
    "auth_routes",
    "event_routes",
    "event_timeline_routes",
    "graph_routes",
    "knowledge_graph_routes",
    "news_routes",
    "sentiment_routes",
    "sentiment_trends_routes",
    "summary_routes",
    "topic_routes",
    "veracity_routes",
    "waf_security_routes",
    "search_routes",
]
