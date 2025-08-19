"""
NLP package for NeuroNews
Contains modules for natural language processing tasks including sentiment analysis and named entity recognition.
"""

# Event Detection Components (Issue #31)
from .article_embedder import ArticleEmbedder
from .article_processor import ArticleProcessor
from .event_clusterer import EventClusterer
from .ner_article_processor import (NERArticleProcessor,
                                    create_ner_article_processor)
from .ner_processor import NERProcessor, create_ner_processor
from .sentiment_analysis import (SentimentAnalyzer,  # Corrected import
                                 create_analyzer)

__all__ = [
    "create_analyzer",
    "SentimentAnalyzer",  # Corrected export
    "ArticleProcessor",
    "NERProcessor",
    "create_ner_processor",
    "NERArticleProcessor",
    "create_ner_article_processor",
]
