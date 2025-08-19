"""
Configuration for NeuroNews Streamlit Dashboard (Issue #50)

Contains settings and configuration for the custom dashboard application.
"""

import os
from typing import Any, Dict

# Dashboard Configuration
DASHBOARD_CONFIG = {
    "title": "NeuroNews Dashboard",
    "page_icon": "📰",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
    "theme": {
        "primaryColor": "#FF6B6B",
        "backgroundColor": "#FFFFFF",
        "secondaryBackgroundColor": "#F0F2F6",
        "textColor": "#262730",
    },
}

# API Configuration
API_CONFIG = {
    "base_url": os.getenv("NEURONEWS_API_URL", "http://localhost:8000"),
    "timeout": 30,
    "retry_attempts": 3,
    "endpoints": {
        "news": "/news/articles/topic",
        "breaking_news": "/api/v1/breaking-news",
        "entities": "/graph/entities",
        "relationships": "/graph/entity",
        "sentiment": "/sentiment/trends",
        "topics": "/topics/trending",
    },
}

# Visualization Configuration
VIZ_CONFIG = {
    "color_schemes": {
        "entities": {
            "PERSON": "#FF6B6B",
            "ORG": "#4ECDC4",
            "GPE": "#45B7D1",
            "EVENT": "#96CEB4",
            "unknown": "#FFEAA7",
        },
        "categories": {
            "technology": "#6C5CE7",
            "politics": "#FD79A8",
            "business": "#FDCB6E",
            "health": "#00B894",
            "sports": "#E17055",
            "entertainment": "#A29BFE",
        },
    },
    "chart_defaults": {
        "height": 400,
        "margin": {"l": 50, "r": 50, "t": 50, "b": 50},
        "font_size": 12,
    },
    "network_graph": {
        "max_nodes": 100,
        "spring_k": 1,
        "iterations": 50,
        "node_size": 10,
        "edge_width": 0.5,
    },
}

# Data Processing Configuration
DATA_CONFIG = {
    "cache_ttl": 300,  # 5 minutes
    "max_articles": 500,
    "max_entities": 200,
    "max_events": 50,
    "default_topic": "technology",
    "default_hours": 24,
}

# Performance Configuration
PERFORMANCE_CONFIG = {
    "enable_caching": True,
    "lazy_loading": True,
    "chunk_size": 50,
    "max_concurrent_requests": 5,
}


def get_config(section: str) -> Dict[str, Any]:
    """Get configuration for a specific section."""
    configs = {
        "dashboard": DASHBOARD_CONFIG,
        "api": API_CONFIG,
        "viz": VIZ_CONFIG,
        "data": DATA_CONFIG,
        "performance": PERFORMANCE_CONFIG,
    }
    return configs.get(section, {})


def get_api_url(endpoint: str) -> str:
    """Get full API URL for an endpoint."""
    base_url = API_CONFIG["base_url"]
    endpoint_path = API_CONFIG["endpoints"].get(endpoint, "")
    return f"{base_url}{endpoint_path}"


# Environment-specific overrides
if os.getenv("ENVIRONMENT") == "production":
    API_CONFIG["base_url"] = os.getenv("NEURONEWS_API_URL", "https://api.neuronews.com")
    DATA_CONFIG["cache_ttl"] = 600  # 10 minutes in production
    PERFORMANCE_CONFIG["max_concurrent_requests"] = 10

elif os.getenv("ENVIRONMENT") == "development":
    DATA_CONFIG["cache_ttl"] = 60  # 1 minute in development
    PERFORMANCE_CONFIG["enable_caching"] = False  # Disable caching for development
