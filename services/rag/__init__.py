"""
RAG (Retrieval Augmented Generation) services package.

Issue #229: Chunking & normalization pipeline
Issue #231: Lexical search (Postgres FTS) for hybrid retrieval
Provides text normalization, chunking, and lexical search services for articles.
"""

from .normalization import ArticleNormalizer, normalize_article
from .chunking import TextChunker, ChunkConfig, SplitStrategy, TextChunk, chunk_text
from .lexical import (
    LexicalSearchService, LexicalSearchResult, SearchFilters,
    get_lexical_search_service, lexical_search, simple_lexical_search
)

__all__ = [
    'ArticleNormalizer', 'normalize_article',
    'TextChunker', 'ChunkConfig', 'SplitStrategy', 'TextChunk', 'chunk_text',
    'LexicalSearchService', 'LexicalSearchResult', 'SearchFilters',
    'get_lexical_search_service', 'lexical_search', 'simple_lexical_search'
]
