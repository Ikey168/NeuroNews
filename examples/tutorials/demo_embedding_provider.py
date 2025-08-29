#!/usr/bin/env python3
"""
Demo script for Embedding Provider
Issue #228: Embedding provider (local + cloud pluggable)

Demonstrates the unified API with local and cloud backends.
"""

import os
import sys
import logging
import numpy as np
from typing import List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.embeddings import EmbeddingProvider, get_embedding_provider

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def demo_local_provider():
    """Demonstrate local sentence-transformers provider."""
    print("\n" + "="*60)
    print("🤖 DEMO: Local Sentence Transformers Provider")
    print("="*60)
    
    # Initialize provider
    provider = EmbeddingProvider(
        provider="local",
        model_name="all-MiniLM-L6-v2",
        batch_size=4,
        deterministic_seed=42
    )
    
    print(f"Provider: {provider.name()}")
    print(f"Embedding dimension: {provider.dim()}")
    
    # Sample news texts
    texts = [
        "Breaking: Scientists discover new method for renewable energy production",
        "Tech company announces major breakthrough in artificial intelligence",
        "Global markets respond positively to economic policy changes",
        "Climate change summit reaches historic international agreement",
        "Healthcare innovation improves patient outcomes significantly",
    ]
    
    print(f"\nEmbedding {len(texts)} news articles...")
    
    # Generate embeddings
    embeddings = provider.embed_texts(texts)
    
    print(f"Generated embeddings shape: {embeddings.shape}")
    print(f"Embedding dtype: {embeddings.dtype}")
    
    # Show sample statistics
    for i, (text, embedding) in enumerate(zip(texts, embeddings)):
        norm = np.linalg.norm(embedding)
        mean_val = np.mean(embedding)
        std_val = np.std(embedding)
        
        print(f"\nText {i+1}: {text[:50]}...")
        print(f"  Norm: {norm:.4f}, Mean: {mean_val:.6f}, Std: {std_val:.6f}")
    
    # Demonstrate similarity calculation
    print(f"\n🔍 Similarity Analysis:")
    print("-" * 40)
    
    # Calculate pairwise cosine similarities
    def cosine_similarity(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            similarity = cosine_similarity(embeddings[i], embeddings[j])
            print(f"Text {i+1} ↔ Text {j+1}: {similarity:.4f}")
    
    return embeddings


def demo_consistency():
    """Demonstrate deterministic behavior."""
    print("\n" + "="*60)
    print("🔄 DEMO: Deterministic Behavior")
    print("="*60)
    
    texts = ["Reproducible embedding test", "Another test text"]
    
    # Generate embeddings twice with same seed
    provider1 = EmbeddingProvider(
        provider="local",
        model_name="all-MiniLM-L6-v2",
        deterministic_seed=42
    )
    embeddings1 = provider1.embed_texts(texts)
    
    provider2 = EmbeddingProvider(
        provider="local", 
        model_name="all-MiniLM-L6-v2",
        deterministic_seed=42
    )
    embeddings2 = provider2.embed_texts(texts)
    
    # Check if identical
    are_identical = np.allclose(embeddings1, embeddings2, atol=1e-6)
    max_diff = np.max(np.abs(embeddings1 - embeddings2))
    
    print(f"Embeddings identical: {are_identical}")
    print(f"Maximum difference: {max_diff:.10f}")
    
    if are_identical:
        print("✅ Deterministic behavior confirmed!")
    else:
        print("❌ Non-deterministic behavior detected")


def demo_batch_processing():
    """Demonstrate batch processing with different batch sizes."""
    print("\n" + "="*60)
    print("📦 DEMO: Batch Processing")
    print("="*60)
    
    # Create many texts
    texts = [f"News article number {i} with unique content" for i in range(25)]
    
    print(f"Processing {len(texts)} texts with different batch sizes...")
    
    batch_sizes = [1, 5, 10, 32]
    results = {}
    
    for batch_size in batch_sizes:
        provider = EmbeddingProvider(
            provider="local",
            model_name="all-MiniLM-L6-v2", 
            batch_size=batch_size,
            deterministic_seed=42
        )
        
        import time
        start_time = time.time()
        embeddings = provider.embed_texts(texts)
        processing_time = time.time() - start_time
        
        results[batch_size] = {
            'embeddings': embeddings,
            'time': processing_time,
            'throughput': len(texts) / processing_time
        }
        
        print(f"Batch size {batch_size:2d}: {processing_time:.3f}s ({results[batch_size]['throughput']:.1f} texts/sec)")
    
    # Verify all results are identical
    base_embeddings = results[batch_sizes[0]]['embeddings']
    for batch_size in batch_sizes[1:]:
        if np.allclose(base_embeddings, results[batch_size]['embeddings'], atol=1e-5):
            print(f"✅ Batch size {batch_size} results match baseline")
        else:
            print(f"❌ Batch size {batch_size} results differ from baseline")


def demo_factory_function():
    """Demonstrate the factory function."""
    print("\n" + "="*60)
    print("🏭 DEMO: Factory Function")
    print("="*60)
    
    # Using factory function with defaults
    provider1 = get_embedding_provider()
    print(f"Default provider: {provider1.name()}")
    
    # Using factory function with parameters
    provider2 = get_embedding_provider(
        provider="local",
        model_name="all-MiniLM-L6-v2",
        batch_size=16
    )
    print(f"Custom provider: {provider2.name()}")
    print(f"Batch size: {provider2.batch_size}")
    
    # Test with environment variables
    os.environ["EMBEDDING_PROVIDER"] = "local"
    os.environ["EMBEDDING_MODEL_NAME"] = "all-MiniLM-L6-v2"
    
    provider3 = get_embedding_provider()
    print(f"Environment-configured provider: {provider3.name()}")


def demo_openai_provider():
    """Demonstrate OpenAI provider (if API key available)."""
    print("\n" + "="*60)
    print("☁️  DEMO: OpenAI Provider (Optional)")
    print("="*60)
    
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not set - skipping OpenAI demo")
        print("   Set OPENAI_API_KEY environment variable to test cloud provider")
        return
    
    try:
        provider = EmbeddingProvider(
            provider="openai",
            model_name="text-embedding-ada-002"
        )
        
        print(f"Provider: {provider.name()}")
        print(f"Embedding dimension: {provider.dim()}")
        
        # Test with a small sample
        texts = ["OpenAI embedding test", "Cloud provider demo"]
        
        print(f"\nGenerating embeddings via OpenAI API...")
        embeddings = provider.embed_texts(texts)
        
        print(f"Generated embeddings shape: {embeddings.shape}")
        print(f"Sample embedding norm: {np.linalg.norm(embeddings[0]):.4f}")
        
        print("✅ OpenAI provider working correctly!")
        
    except Exception as e:
        print(f"❌ OpenAI provider error: {e}")


def demo_api_compliance():
    """Demonstrate API compliance and method signatures."""
    print("\n" + "="*60)
    print("🔧 DEMO: API Compliance")
    print("="*60)
    
    provider = EmbeddingProvider(provider="local", model_name="all-MiniLM-L6-v2")
    
    # Test required methods
    print("Testing required API methods...")
    
    # embed_texts(list[str]) -> np.ndarray
    texts = ["test1", "test2", "test3"]
    embeddings = provider.embed_texts(texts)
    print(f"✅ embed_texts: {type(embeddings)} shape {embeddings.shape}")
    
    # dim() -> int
    dimension = provider.dim()
    print(f"✅ dim: {type(dimension)} value {dimension}")
    
    # name() -> str
    name = provider.name()
    print(f"✅ name: {type(name)} value '{name}'")
    
    # Test edge cases
    print("\nTesting edge cases...")
    
    # Empty input
    empty_embeddings = provider.embed_texts([])
    print(f"✅ Empty input: shape {empty_embeddings.shape}")
    
    # Single text
    single_embeddings = provider.embed_texts(["single text"])
    print(f"✅ Single text: shape {single_embeddings.shape}")
    
    # Shape consistency
    assert embeddings.shape == (len(texts), dimension)
    assert empty_embeddings.shape == (0, dimension)
    assert single_embeddings.shape == (1, dimension)
    
    print("✅ All API compliance tests passed!")


def main():
    """Run all demonstrations."""
    print("🚀 Embedding Provider Demo - Issue #228")
    print("Unified API for local + cloud pluggable embeddings")
    
    try:
        # Core functionality demos
        demo_local_provider()
        demo_consistency()
        demo_batch_processing()
        demo_factory_function()
        demo_api_compliance()
        
        # Optional cloud provider demo
        demo_openai_provider()
        
        print("\n" + "="*60)
        print("🎉 All demos completed successfully!")
        print("="*60)
        print("\nKey features demonstrated:")
        print("✅ Unified API: embed_texts(), dim(), name()")
        print("✅ Local backend: sentence-transformers")
        print("✅ Deterministic behavior with seeds")
        print("✅ Batch processing with configurable sizes")
        print("✅ Shape consistency: [N, dim]")
        print("✅ Factory function with environment variables")
        print("✅ Cloud backend: OpenAI (when API key available)")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise


if __name__ == "__main__":
    main()
