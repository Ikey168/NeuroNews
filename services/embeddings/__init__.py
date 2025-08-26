"""
Embedding services package for NeuroNews.

Provides unified API for embedding generation with pluggable backends
supporting both local and cloud providers.

Issue #228: Embedding provider (local + cloud pluggable)
"""

from .provider import EmbeddingProvider, EmbeddingBackend, get_embedding_provider

__all__ = ['EmbeddingProvider', 'EmbeddingBackend', 'get_embedding_provider']
