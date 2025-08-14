"""
NLP package for NeuroNews
Contains modules for natural language processing tasks including sentiment analysis and named entity recognition.
"""

from .sentiment_analysis import (
    create_analyzer,
    SentimentAnalyzer  # Corrected import
)
from .article_processor import ArticleProcessor
from .ner_processor import (
    NERProcessor,
    create_ner_processor
)
from .ner_article_processor import (
    NERArticleProcessor,
    create_ner_article_processor
)

__all__ = [
    'create_analyzer',
    'SentimentAnalyzer',  # Corrected export
    'ArticleProcessor',
    'NERProcessor',
    'create_ner_processor',
    'NERArticleProcessor',
    'create_ner_article_processor'
]