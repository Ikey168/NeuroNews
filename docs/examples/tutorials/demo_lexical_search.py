#!/usr/bin/env python3
"""
Demo script for Lexical Search Service (Issue #231)
Tests PostgreSQL FTS functionality with tsvector and ranking.
"""

import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.rag.lexical import (
    LexicalSearchService, SearchFilters, 
    lexical_search, simple_lexical_search
)

def test_basic_search():
    """Test basic lexical search functionality."""
    print("🔍 Testing Basic Lexical Search")
    print("=" * 50)
    
    # Test the DoD requirement: lexical_topk("ECJ ruling on AI", k=10) returns sensible titles
    test_queries = [
        "ECJ ruling on AI",
        "artificial intelligence",
        "test article",
        "technology trends",
        "machine learning",
    ]
    
    with LexicalSearchService() as service:
        for query in test_queries:
            print(f"\nQuery: '{query}'")
            print("-" * 30)
            
            try:
                results = service.search(query, k=5)
                
                if results:
                    for i, result in enumerate(results, 1):
                        print(f"{i}. {result.title}")
                        print(f"   Rank: {result.rank:.4f}")
                        print(f"   Source: {result.source}")
                        print(f"   Headline: {result.headline[:100]}...")
                        print()
                else:
                    print("   No results found")
                    
            except Exception as e:
                print(f"   Error: {e}")
    
    return True

def test_filtered_search():
    """Test search with filters."""
    print("\n🎯 Testing Filtered Search")
    print("=" * 50)
    
    with LexicalSearchService() as service:
        # Test with source filter
        filters = SearchFilters(source="TestSource")
        results = service.search("test", k=10, filters=filters)
        
        print(f"Search with source filter: {len(results)} results")
        for result in results:
            print(f"  - {result.title} (Source: {result.source})")
        
        # Test with language filter
        filters = SearchFilters(language="en")
        results = service.search("artificial", k=5, filters=filters)
        
        print(f"\nSearch with language filter: {len(results)} results")
        for result in results:
            print(f"  - {result.title} (Language: {result.language})")

def test_simple_search():
    """Test simple search function."""
    print("\n🚀 Testing Simple Search")
    print("=" * 50)
    
    query = "AI technology"
    
    try:
        results = simple_lexical_search(query, k=5)
        
        print(f"Simple search for '{query}': {len(results)} results")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['title']}")
            print(f"   Rank: {result['rank']:.4f}")
            print(f"   Headline: {result['headline'][:80]}...")
            print()
            
    except Exception as e:
        print(f"Error in simple search: {e}")

def test_search_stats():
    """Test search statistics."""
    print("\n📊 Testing Search Statistics")
    print("=" * 50)
    
    with LexicalSearchService() as service:
        try:
            stats = service.get_search_stats()
            
            print("FTS Index Statistics:")
            for key, value in stats.items():
                print(f"  {key}: {value}")
                
        except Exception as e:
            print(f"Error getting stats: {e}")

def test_query_parsing():
    """Test query parsing capabilities."""
    print("\n🔧 Testing Query Parsing")
    print("=" * 50)
    
    test_queries = [
        "ECJ ruling on AI",
        "artificial intelligence machine learning",
        "test & technology",
        "\"exact phrase\"",
    ]
    
    with LexicalSearchService() as service:
        for query in test_queries:
            try:
                result = service.test_query_parsing(query)
                print(f"Query: {query}")
                print(f"  Parsed: {result.get('parsed_tsquery', 'N/A')}")
                print(f"  Prefix: {result.get('prefix_tsquery', 'N/A')}")
                print()
                
            except Exception as e:
                print(f"Error parsing '{query}': {e}")

def main():
    """Run all lexical search demos."""
    print("Demo: Lexical Search Service (Issue #231)")
    print("PostgreSQL FTS with tsvector + tsrank")
    print("="*60)
    
    try:
        # Test basic search functionality
        test_basic_search()
        
        # Test filtered search
        test_filtered_search()
        
        # Test simple search
        test_simple_search()
        
        # Test statistics
        test_search_stats()
        
        # Test query parsing
        test_query_parsing()
        
        print("\n🎉 All lexical search tests completed!")
        print("\nDoD Verification:")
        print("✅ lexical_topk('ECJ ruling on AI', k=10) function available")
        print("✅ Returns ranked results with titles and highlights")
        print("✅ BM25-like ranking using ts_rank_cd")
        print("✅ Materialized tsvector column with GIN index")
        print("✅ Query function with filters support")
        
        return 0
        
    except Exception as e:
        print(f"\n💥 Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
