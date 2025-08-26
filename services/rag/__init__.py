"""
RAG (Retrieval Augmented Generation) services package.

Issue #229: Chunking & normalization pipeline
Issue #231: Lexical search (Postgres FTS) for hybrid retrieval
Issue #232: Hybrid retrieval combining vector + lexical search
Provides text normalization, chunking, lexical search, vector search, and hybrid retrieval services for articles.
"""

from .normalization import ArticleNormalizer, normalize_article
from .chunking import TextChunker, ChunkConfig, SplitStrategy, TextChunk, chunk_text
from .lexical import (
    LexicalSearchService, LexicalSearchResult, SearchFilters,
    get_lexical_search_service, lexical_search, simple_lexical_search
)
from .vector import VectorSearchService, VectorSearchResult, VectorSearchFilters
from .rerank import CrossEncoderReranker
from .retriever import HybridRetriever

__all__ = [
    'ArticleNormalizer', 'normalize_article',
    'TextChunker', 'ChunkConfig', 'SplitStrategy', 'TextChunk', 'chunk_text',
    'LexicalSearchService', 'LexicalSearchResult', 'SearchFilters',
    'get_lexical_search_service', 'lexical_search', 'simple_lexical_search',
    'VectorSearchService', 'VectorSearchResult', 'VectorSearchFilters',
    'CrossEncoderReranker',
    'HybridRetriever'
]
