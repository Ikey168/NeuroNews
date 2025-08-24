"""
Updated Configuration for Snowflake-based NeuroNews Dashboard

Contains settings and configuration for the Snowflake-integrated dashboard application.

Issue #244: Update analytics queries and integrations for Snowflake
"""

import os
from typing import Any, Dict

# Dashboard Configuration
DASHBOARD_CONFIG = {
    "title": "NeuroNews Analytics Dashboard",
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

# Snowflake Configuration
SNOWFLAKE_CONFIG = {
    "account": os.getenv("SNOWFLAKE_ACCOUNT"),
    "user": os.getenv("SNOWFLAKE_USER"),
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "ANALYTICS_WH"),
    "database": os.getenv("SNOWFLAKE_DATABASE", "NEURONEWS"),
    "schema": os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
    "role": os.getenv("SNOWFLAKE_ROLE", "ANALYTICS_ROLE"),
    "connection_timeout": 30,
    "query_timeout": 300,  # 5 minutes
    "retry_attempts": 3,
}

# Analytics Configuration
ANALYTICS_CONFIG = {
    "default_time_range": 7,  # days
    "max_entities": 100,
    "max_keywords": 50,
    "cache_ttl": {
        "sentiment_trends": 300,  # 5 minutes
        "entity_data": 300,
        "keyword_trends": 180,  # 3 minutes
        "source_stats": 600,  # 10 minutes
        "custom_queries": 60,   # 1 minute
    },
    "query_limits": {
        "max_rows": 10000,
        "entity_limit": 100,
        "keyword_limit": 50,
        "source_limit": 50,
    },
}

# Visualization Configuration
VIZ_CONFIG = {
    "color_schemes": {
        "entities": {
            "PERSON": "#FF6B6B",
            "ORG": "#4ECDC4", 
            "GPE": "#45B7D1",
            "LOC": "#96CEB4",
            "EVENT": "#FFA07A",
            "PRODUCT": "#98D8C8",
            "unknown": "#FFEAA7",
        },
        "sentiment": {
            "positive": "#2ECC71",
            "negative": "#E74C3C",
            "neutral": "#95A5A6",
            "mixed": "#F39C12",
        },
        "categories": {
            "technology": "#6C5CE7",
            "politics": "#FD79A8",
            "business": "#FDCB6E",
            "health": "#00B894",
            "sports": "#E17055",
            "entertainment": "#A29BFE",
            "science": "#00CEC9",
            "world": "#FF7675",
        },
        "trending": {
            "high_velocity": "#E74C3C",
            "medium_velocity": "#F39C12",
            "low_velocity": "#2ECC71",
            "declining": "#95A5A6",
        }
    },
    "chart_defaults": {
        "height": 400,
        "margin": {"l": 50, "r": 50, "t": 50, "b": 50},
        "font_size": 12,
        "line_width": 2,
        "marker_size": 8,
    },
    "network_graph": {
        "max_nodes": 50,
        "spring_k": 1.5,
        "iterations": 100,
        "node_size_range": [10, 50],
        "edge_width": 0.5,
        "layout_algorithm": "spring",
    },
    "performance": {
        "enable_webgl": True,
        "max_points": 5000,
        "decimation_threshold": 1000,
    }
}

# Data Processing Configuration
DATA_CONFIG = {
    "cache_ttl": 300,  # 5 minutes default
    "max_articles": 10000,
    "max_entities": 500,
    "max_events": 100,
    "default_topic": "technology",
    "default_hours": 24,
    "batch_size": 1000,
    "parallel_queries": True,
    "max_concurrent_queries": 5,
}

# Performance Configuration
PERFORMANCE_CONFIG = {
    "enable_caching": True,
    "lazy_loading": True,
    "chunk_size": 500,
    "max_concurrent_requests": 10,
    "compression": "gzip",
    "connection_pooling": True,
    "query_optimization": True,
}

# Security Configuration
SECURITY_CONFIG = {
    "require_authentication": os.getenv("DASHBOARD_AUTH_REQUIRED", "false").lower() == "true",
    "session_timeout": 3600,  # 1 hour
    "max_query_execution_time": 300,  # 5 minutes
    "allowed_query_patterns": [
        r"^SELECT\s+.*FROM\s+news_articles.*",
        r"^WITH\s+.*SELECT\s+.*FROM\s+.*",
    ],
    "blocked_operations": ["DROP", "DELETE", "UPDATE", "INSERT", "CREATE", "ALTER"],
}

# Dashboard Sections Configuration
DASHBOARD_SECTIONS = {
    "sentiment_analysis": {
        "enabled": True,
        "refresh_interval": 300,  # 5 minutes
        "default_view": "trends",
        "available_metrics": [
            "avg_sentiment",
            "sentiment_volatility", 
            "article_count",
            "source_distribution"
        ],
    },
    "entity_analysis": {
        "enabled": True,
        "refresh_interval": 300,
        "default_entity_type": "ORG",
        "entity_types": ["ORG", "PERSON", "LOC", "GPE", "EVENT"],
        "network_analysis": True,
        "co_occurrence_analysis": True,
    },
    "keyword_trends": {
        "enabled": True,
        "refresh_interval": 180,  # 3 minutes
        "velocity_analysis": True,
        "trend_detection": True,
        "keyword_clustering": False,  # Advanced feature
    },
    "source_statistics": {
        "enabled": True,
        "refresh_interval": 600,  # 10 minutes
        "performance_metrics": True,
        "quality_metrics": True,
        "coverage_analysis": True,
    },
    "custom_queries": {
        "enabled": True,
        "query_validation": True,
        "result_caching": True,
        "export_enabled": True,
        "max_execution_time": 300,
    },
}

# Snowflake Query Templates
QUERY_TEMPLATES = {
    "sentiment_trends": """
        SELECT
            source,
            DATE_TRUNC('day', published_date) as date,
            AVG(sentiment) as avg_sentiment,
            COUNT(*) as article_count,
            STDDEV(sentiment) as sentiment_volatility
        FROM news_articles
        WHERE sentiment IS NOT NULL
            AND published_date >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
            {source_filter}
        GROUP BY source, DATE_TRUNC('day', published_date)
        ORDER BY source, date
    """,
    
    "top_entities": """
        WITH entity_extraction AS (
            SELECT 
                source,
                f.value::string as entity_name
            FROM news_articles,
            LATERAL FLATTEN(input => PARSE_JSON(entities):{entity_type}) f
            WHERE entities IS NOT NULL
                AND published_date >= DATEADD('day', -7, CURRENT_TIMESTAMP())
        )
        SELECT
            entity_name,
            COUNT(*) as mention_count,
            COUNT(DISTINCT source) as source_count
        FROM entity_extraction
        WHERE entity_name IS NOT NULL
        GROUP BY entity_name
        ORDER BY mention_count DESC
        LIMIT {limit}
    """,
    
    "keyword_velocity": """
        WITH hourly_keywords AS (
            SELECT
                DATE_TRUNC('hour', published_date) as hour,
                f.value::string as keyword
            FROM news_articles,
            LATERAL FLATTEN(input => PARSE_JSON(keywords)) f
            WHERE keywords IS NOT NULL
                AND published_date >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
        ),
        keyword_velocity AS (
            SELECT
                keyword,
                hour,
                COUNT(*) as hourly_count,
                COUNT(*) - LAG(COUNT(*), 1, 0) OVER (
                    PARTITION BY keyword 
                    ORDER BY hour
                ) as velocity
            FROM hourly_keywords
            GROUP BY keyword, hour
        )
        SELECT
            keyword,
            SUM(hourly_count) as total_mentions,
            AVG(velocity) as avg_velocity,
            MAX(velocity) as peak_velocity,
            STDDEV(velocity) as velocity_stddev
        FROM keyword_velocity
        WHERE keyword IS NOT NULL
        GROUP BY keyword
        HAVING SUM(hourly_count) >= 3
        ORDER BY avg_velocity DESC
        LIMIT {limit}
    """,
}


def get_config(section: str) -> Dict[str, Any]:
    """Get configuration for a specific section."""
    configs = {
        "dashboard": DASHBOARD_CONFIG,
        "snowflake": SNOWFLAKE_CONFIG,
        "analytics": ANALYTICS_CONFIG,
        "viz": VIZ_CONFIG,
        "data": DATA_CONFIG,
        "performance": PERFORMANCE_CONFIG,
        "security": SECURITY_CONFIG,
        "sections": DASHBOARD_SECTIONS,
    }
    return configs.get(section, {})


def get_query_template(template_name: str) -> str:
    """Get SQL query template."""
    return QUERY_TEMPLATES.get(template_name, "")


def validate_snowflake_config() -> Dict[str, Any]:
    """Validate Snowflake configuration."""
    config = get_config("snowflake")
    required_fields = ["account", "user", "password"]
    
    missing = [field for field in required_fields if not config.get(field)]
    
    return {
        "valid": len(missing) == 0,
        "missing_fields": missing,
        "config": config,
        "recommendations": {
            "warehouse": "Consider using a dedicated analytics warehouse",
            "role": "Use a role with read-only permissions for dashboards",
            "timeout": "Adjust timeouts based on query complexity",
        }
    }


def get_chart_config(chart_type: str) -> Dict[str, Any]:
    """Get chart-specific configuration."""
    base_config = VIZ_CONFIG["chart_defaults"].copy()
    
    chart_specific = {
        "sentiment_line": {
            "height": 500,
            "line_width": 3,
            "markers": True,
        },
        "entity_network": {
            "height": 600,
            "show_labels": True,
            "interactive": True,
        },
        "keyword_bubble": {
            "height": 500,
            "color_scale": "Viridis",
            "size_scale": [5, 50],
        },
        "source_bar": {
            "height": 400,
            "orientation": "horizontal",
            "color_scale": "Blues",
        }
    }
    
    if chart_type in chart_specific:
        base_config.update(chart_specific[chart_type])
    
    return base_config


# Environment-specific overrides
environment = os.getenv("ENVIRONMENT", "development")

if environment == "production":
    # Production optimizations
    DATA_CONFIG["cache_ttl"] = 600  # 10 minutes
    PERFORMANCE_CONFIG["max_concurrent_requests"] = 20
    SECURITY_CONFIG["require_authentication"] = True
    ANALYTICS_CONFIG["cache_ttl"]["sentiment_trends"] = 600
    
elif environment == "development":
    # Development settings
    DATA_CONFIG["cache_ttl"] = 60  # 1 minute
    PERFORMANCE_CONFIG["enable_caching"] = False
    SECURITY_CONFIG["require_authentication"] = False
    
elif environment == "testing":
    # Testing settings
    DATA_CONFIG["cache_ttl"] = 0  # No caching
    PERFORMANCE_CONFIG["enable_caching"] = False
    ANALYTICS_CONFIG["query_limits"]["max_rows"] = 100
