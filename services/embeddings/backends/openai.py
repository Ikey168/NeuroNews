"""
OpenAI Embeddings Backend
Issue #228: Embedding provider (local + cloud pluggable)

This backend uses OpenAI's embeddings API for cloud-based embedding generation.
Optional backend that requires OPENAI_API_KEY environment variable.
"""

import logging
import os
from typing import List, Optional
import numpy as np

try:
    import openai
except ImportError:
    raise ImportError(
        "openai package is required for OpenAI backend. "
        "Install it with: pip install openai"
    )

from ..provider import EmbeddingBackend

logger = logging.getLogger(__name__)


class OpenAIBackend(EmbeddingBackend):
    """
    OpenAI embeddings backend.
    
    Uses OpenAI's embeddings API to generate embeddings.
    Requires OPENAI_API_KEY environment variable to be set.
    """
    
    def __init__(
        self,
        model_name: str = "text-embedding-ada-002",
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize OpenAI embedding backend.
        
        Args:
            model_name: OpenAI embedding model name
            api_key: OpenAI API key (if not provided, uses OPENAI_API_KEY env var)
            **kwargs: Additional arguments for OpenAI client
        """
        self.model_name = model_name
        
        # Get API key from parameter or environment
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # Initialize OpenAI client
        openai.api_key = self.api_key
        
        # Model dimension mapping
        self._model_dimensions = {
            "text-embedding-ada-002": 1536,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
        }
        
        if model_name not in self._model_dimensions:
            logger.warning(
                f"Unknown model '{model_name}'. "
                f"Supported models: {list(self._model_dimensions.keys())}"
            )
            # Try to get dimension from API (this will make a test call)
            self._embedding_dimension = self._get_dimension_from_api()
        else:
            self._embedding_dimension = self._model_dimensions[model_name]
        
        logger.info(
            f"Initialized OpenAI backend with model '{model_name}' "
            f"({self._embedding_dimension} dimensions)"
        )
    
    def _get_dimension_from_api(self) -> int:
        """Get embedding dimension by making a test API call."""
        try:
            response = openai.Embedding.create(
                model=self.model_name,
                input=["test"]
            )
            return len(response["data"][0]["embedding"])
        except Exception as e:
            logger.error(f"Failed to determine embedding dimension: {e}")
            # Default fallback
            return 1536
    
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts using OpenAI API.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            numpy array of shape [N, dim] where N is len(texts)
        """
        if not texts:
            return np.empty((0, self._embedding_dimension))
        
        try:
            # Call OpenAI API
            response = openai.Embedding.create(
                model=self.model_name,
                input=texts
            )
            
            # Extract embeddings
            embeddings = []
            for item in response["data"]:
                embeddings.append(item["embedding"])
            
            return np.array(embeddings)
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"Failed to generate embeddings via OpenAI: {e}")
    
    def dim(self) -> int:
        """Return the embedding dimension."""
        return self._embedding_dimension
    
    def name(self) -> str:
        """Return the backend name."""
        return f"openai:{self.model_name}"
    
    def get_model_info(self) -> dict:
        """Get detailed model information."""
        return {
            "model_name": self.model_name,
            "embedding_dimension": self._embedding_dimension,
            "provider": "openai",
            "api_key_set": bool(self.api_key),
        }
