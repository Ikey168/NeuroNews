"""
Extensions package for NeuroNews scrapers.
"""

from .cloudwatch_logging import CloudWatchLoggingExtension, LocalFileLoggingExtension

__all__ = ["CloudWatchLoggingExtension", "LocalFileLoggingExtension"]
