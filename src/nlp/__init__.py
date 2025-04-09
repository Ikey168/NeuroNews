"""
NLP package for NeuroNews
Contains modules for natural language processing tasks including sentiment analysis.
"""

from .sentiment_analysis import (
    create_analyzer,
    BaseSentimentAnalyzer,
    TransformersSentimentAnalyzer,
    AWSComprehendAnalyzer
)
from .article_processor import ArticleProcessor

__all__ = [
    'create_analyzer',
    'BaseSentimentAnalyzer',
    'TransformersSentimentAnalyzer',
    'AWSComprehendAnalyzer',
    'ArticleProcessor'
]