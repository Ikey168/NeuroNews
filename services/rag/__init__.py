"""
RAG (Retrieval Augmented Generation) services package.

Issue #229: Chunking & normalization pipeline
Provides text normalization and chunking services for articles.
"""

from .normalization import ArticleNormalizer, normalize_article
from .chunking import TextChunker, ChunkConfig, SplitStrategy, TextChunk, chunk_text

__all__ = [
    'ArticleNormalizer', 'normalize_article',
    'TextChunker', 'ChunkConfig', 'SplitStrategy', 'TextChunk', 'chunk_text'
]
