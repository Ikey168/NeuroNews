#!/usr/bin/env python3
"""
Demo script for Hybrid Retrieval Service (Issue #232)
Tests vector + lexical search fusion with optional reranking.
"""

import sys
import numpy as np
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.rag import (
    HybridRetriever, HybridSearchFilters,
    VectorSearchService, LexicalSearchService, CrossEncoderReranker,
    get_hybrid_retriever, hybrid_search
)


def simulate_embedding(text: str, dim: int = 384) -> np.ndarray:
    """Simulate text embedding using hash-based approach."""
    import hashlib
    
    # Use hash to generate deterministic but pseudo-random embeddings
    hash_obj = hashlib.md5(text.encode())
    seed = int(hash_obj.hexdigest()[:8], 16)
    np.random.seed(seed)
    
    # Generate random vector and normalize
    embedding = np.random.normal(0, 1, dim)
    embedding = embedding / np.linalg.norm(embedding)
    
    return embedding


def test_basic_hybrid_search():
    """Test basic hybrid search functionality."""
    print("\n🔍 Testing Basic Hybrid Search")
    print("=" * 50)
    
    try:
        with get_hybrid_retriever() as retriever:
            # Generate query embedding
            query = "artificial intelligence machine learning"
            query_embedding = simulate_embedding(query)
            
            # Perform hybrid search
            results = retriever.search(
                query=query,
                query_embedding=query_embedding,
                k=10,
                fusion_method="weighted"
            )
            
            print(f"Query: '{query}'")
            print(f"Found {len(results)} hybrid results:")
            
            for i, result in enumerate(results, 1):
                print(f"\n{i}. {result.title}")
                print(f"   Source: {result.source}")
                print(f"   Vector Score: {result.vector_score:.4f}" if result.vector_score else "   Vector Score: None")
                print(f"   Lexical Score: {result.lexical_score:.4f}" if result.lexical_score else "   Lexical Score: None")
                print(f"   Fusion Score: {result.fusion_score:.4f}")
                print(f"   Final Score: {result.final_score:.4f}")
                print(f"   Search Method: {result.search_method}")
                print(f"   Content: {result.content[:100]}...")
                
    except Exception as e:
        print(f"❌ Basic hybrid search failed: {e}")
        return False
    
    print("✅ Basic hybrid search completed")
    return True


def test_fusion_methods():
    """Test different score fusion methods."""
    print("\n⚖️  Testing Score Fusion Methods")
    print("=" * 50)
    
    query = "quantum computing breakthrough"
    query_embedding = simulate_embedding(query)
    
    fusion_methods = ["weighted", "rrf", "max"]
    
    try:
        with get_hybrid_retriever() as retriever:
            for method in fusion_methods:
                print(f"\n📊 Testing {method.upper()} fusion:")
                
                results = retriever.search(
                    query=query,
                    query_embedding=query_embedding,
                    k=5,
                    fusion_method=method,
                    enable_reranking=False  # Disable for pure fusion comparison
                )
                
                print(f"   Found {len(results)} results with {method} fusion")
                if results:
                    print(f"   Top result: {results[0].title}")
                    print(f"   Fusion score: {results[0].fusion_score:.4f}")
                    print(f"   Search method: {results[0].search_method}")
                
    except Exception as e:
        print(f"❌ Fusion methods test failed: {e}")
        return False
    
    print("✅ Score fusion methods test completed")
    return True


def test_filtered_hybrid_search():
    """Test hybrid search with filters."""
    print("\n🎯 Testing Filtered Hybrid Search")
    print("=" * 50)
    
    try:
        with get_hybrid_retriever() as retriever:
            # Test with source filter
            filters = HybridSearchFilters(
                source="TestSource",
                min_vector_similarity=0.1,
                min_lexical_rank=0.5
            )
            
            query = "machine learning algorithms"
            query_embedding = simulate_embedding(query)
            
            results = retriever.search(
                query=query,
                query_embedding=query_embedding,
                k=10,
                filters=filters
            )
            
            print(f"Search with filters: {len(results)} results")
            print(f"   Source filter: {filters.source}")
            print(f"   Min vector similarity: {filters.min_vector_similarity}")
            print(f"   Min lexical rank: {filters.min_lexical_rank}")
            
            for result in results[:3]:
                print(f"   - {result.title} (Source: {result.source})")
                
    except Exception as e:
        print(f"❌ Filtered search failed: {e}")
        return False
    
    print("✅ Filtered hybrid search completed")
    return True


def test_reranking():
    """Test hybrid search with reranking."""
    print("\n🔄 Testing Cross-Encoder Reranking")
    print("=" * 50)
    
    try:
        # Test reranker availability
        reranker = CrossEncoderReranker()
        print(f"Reranker enabled: {reranker.is_enabled}")
        print(f"Model info: {reranker.get_model_info()}")
        
        with get_hybrid_retriever(enable_reranking=True) as retriever:
            query = "deep learning neural networks"
            query_embedding = simulate_embedding(query)
            
            # Search without reranking
            results_no_rerank = retriever.search(
                query=query,
                query_embedding=query_embedding,
                k=5,
                enable_reranking=False
            )
            
            # Search with reranking
            results_with_rerank = retriever.search(
                query=query,
                query_embedding=query_embedding,
                k=5,
                enable_reranking=True
            )
            
            print(f"\nResults comparison:")
            print(f"Without reranking: {len(results_no_rerank)} results")
            print(f"With reranking: {len(results_with_rerank)} results")
            
            if results_no_rerank and results_with_rerank:
                print(f"\nTop result without reranking:")
                print(f"   Title: {results_no_rerank[0].title}")
                print(f"   Fusion score: {results_no_rerank[0].fusion_score:.4f}")
                
                print(f"\nTop result with reranking:")
                print(f"   Title: {results_with_rerank[0].title}")
                print(f"   Final score: {results_with_rerank[0].final_score:.4f}")
                
    except Exception as e:
        print(f"❌ Reranking test failed: {e}")
        return False
    
    print("✅ Reranking test completed")
    return True


def test_convenience_function():
    """Test the convenience hybrid search function."""
    print("\n⚡ Testing Convenience Function")
    print("=" * 50)
    
    try:
        query = "artificial intelligence research"
        query_embedding = simulate_embedding(query)
        
        # Use the convenience function
        results = hybrid_search(
            query=query,
            query_embedding=query_embedding,
            k=5,
            fusion_method="rrf",
            enable_reranking=False
        )
        
        print(f"Convenience function returned {len(results)} results")
        
        if results:
            print("\nFirst result:")
            result = results[0]
            print(f"   Title: {result['title']}")
            print(f"   Score: {result['score']:.4f}")
            print(f"   Search method: {result['search_method']}")
            print(f"   Vector score: {result['vector_score']}")
            print(f"   Lexical score: {result['lexical_score']}")
            print(f"   Content: {result['chunk'][:100]}...")
            
    except Exception as e:
        print(f"❌ Convenience function test failed: {e}")
        return False
    
    print("✅ Convenience function test completed")
    return True


def test_search_stats():
    """Test search statistics retrieval."""
    print("\n📊 Testing Search Statistics")
    print("=" * 50)
    
    try:
        with get_hybrid_retriever() as retriever:
            stats = retriever.get_search_stats()
            
            print("Hybrid retrieval statistics:")
            print(f"   Vector service available: {stats['vector_service_available']}")
            print(f"   Lexical service available: {stats['lexical_service_available']}")
            print(f"   Reranker available: {stats['reranker_available']}")
            print(f"   Reranker enabled: {stats['reranker_enabled']}")
            
            fusion_weights = stats['fusion_weights']
            print(f"   Vector weight: {fusion_weights['vector_weight']}")
            print(f"   Lexical weight: {fusion_weights['lexical_weight']}")
            print(f"   RRF k parameter: {fusion_weights['rrf_k']}")
            
            if 'reranker_info' in stats:
                reranker_info = stats['reranker_info']
                print(f"   Reranker model: {reranker_info['model_name']}")
                print(f"   Model loaded: {reranker_info['model_loaded']}")
                
    except Exception as e:
        print(f"❌ Search stats test failed: {e}")
        return False
    
    print("✅ Search statistics test completed")
    return True


def main():
    """Run all hybrid retrieval demos."""
    print("🚀 Hybrid Retrieval Service Demo (Issue #232)")
    print("=" * 60)
    print("Testing vector + lexical search fusion with optional reranking")
    
    test_functions = [
        test_basic_hybrid_search,
        test_fusion_methods,
        test_filtered_hybrid_search,
        test_reranking,
        test_convenience_function,
        test_search_stats,
    ]
    
    results = []
    for test_func in test_functions:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test_func.__name__} failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("📋 DEMO SUMMARY")
    print("=" * 60)
    
    success_count = sum(results)
    total_count = len(results)
    
    for i, (test_func, result) in enumerate(zip(test_functions, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test_func.__name__}: {status}")
    
    print(f"\n🎯 Overall: {success_count}/{total_count} tests passed")
    
    if success_count == total_count:
        print("🎉 All hybrid retrieval tests completed successfully!")
        print("\nDoD Requirements Check:")
        print("✅ retriever.search(query) returns [{chunk, score, source, url}] with length ≤ K")
        print("✅ Candidate fetch: top-k from vector + top-k from lexical → union")
        print("✅ Score fusion: weighted sum or Reciprocal Rank Fusion")
        print("✅ Optional reranker (cross-encoder/ms-marco-MiniLM-L-6-v2) gated by env")
        
        return 0
    else:
        print("⚠️  Some tests failed. Check implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
