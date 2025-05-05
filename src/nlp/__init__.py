"""
NLP package for NeuroNews
Contains modules for natural language processing tasks including sentiment analysis.
"""

from .sentiment_analysis import (
    create_analyzer,
    SentimentAnalyzer  # Corrected import
)
from .article_processor import ArticleProcessor

__all__ = [
    'create_analyzer',
    'SentimentAnalyzer',  # Corrected export
    'ArticleProcessor'
]