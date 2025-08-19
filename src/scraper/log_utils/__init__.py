"""
Logging package for NeuroNews scrapers.
"""

from .cloudwatch_handler import (CloudWatchLoggingHandler,
                                 configure_cloudwatch_logging)

__all__ = ["CloudWatchLoggingHandler", "configure_cloudwatch_logging"]
