#!/usr/bin/env python3
"""
Demo script for CLI RAG Indexer (Issue #230)
Creates sample data and tests the indexing pipeline.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import pandas as pd
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def create_sample_data():
    """Create sample data for testing the indexer."""
    
    # Sample news articles
    articles = [
        {
            "id": "news_001",
            "title": "AI Breakthrough in Natural Language Processing",
            "content": """
            Researchers at leading tech companies have achieved a significant breakthrough in natural language processing. 
            The new model demonstrates unprecedented accuracy in understanding context and generating human-like responses.
            This advancement could revolutionize how we interact with AI systems, making them more intuitive and helpful.
            The research team used advanced transformer architectures and novel training techniques to achieve these results.
            Industry experts predict this technology will be widely adopted within the next two years.
            """,
            "source": "TechNews",
            "language": "en",
            "published_at": "2024-01-15T10:30:00Z",
            "url": "https://technews.com/ai-breakthrough-nlp",
        },
        {
            "id": "news_002", 
            "title": "Quantum Computing Milestone Reached",
            "content": """
            Scientists have achieved a major milestone in quantum computing by demonstrating quantum supremacy 
            in a practical application. The quantum processor solved a complex optimization problem in minutes 
            that would take classical computers years to complete. This breakthrough opens new possibilities 
            for drug discovery, financial modeling, and cryptography. The research was conducted using a 
            1000-qubit quantum processor with unprecedented stability and error correction capabilities.
            """,
            "source": "ScienceDaily",
            "language": "en", 
            "published_at": "2024-01-16T14:20:00Z",
            "url": "https://sciencedaily.com/quantum-milestone",
        },
        {
            "id": "news_003",
            "title": "Climate Change Action Plan Announced",
            "content": """
            World leaders have announced a comprehensive action plan to address climate change through 
            technological innovation and international cooperation. The plan includes massive investments 
            in renewable energy, carbon capture technologies, and sustainable transportation systems.
            Key initiatives include deploying 500GW of solar capacity globally, developing next-generation 
            battery storage systems, and creating carbon-neutral shipping corridors. The timeline spans 
            the next decade with specific milestones and accountability measures.
            """,
            "source": "ClimateNews",
            "language": "en",
            "published_at": "2024-01-17T09:15:00Z", 
            "url": "https://climatenews.com/action-plan-2024",
        },
        {
            "id": "news_004",
            "title": "Breakthrough in Gene Therapy for Rare Diseases",
            "content": """
            Medical researchers have developed a revolutionary gene therapy treatment that shows remarkable 
            success in treating previously incurable rare diseases. The therapy uses CRISPR-Cas9 technology 
            to precisely edit genetic defects at the cellular level. Clinical trials show 95% success rates 
            with minimal side effects. This treatment could help millions of patients worldwide suffering 
            from genetic disorders. The FDA has granted fast-track approval for several applications.
            """,
            "source": "MedicalNews",
            "language": "en",
            "published_at": "2024-01-18T16:45:00Z",
            "url": "https://medicalnews.com/gene-therapy-breakthrough",
        },
        {
            "id": "news_005",
            "title": "Space Exploration Mission to Mars Approved",
            "content": """
            International space agencies have approved an ambitious mission to establish a permanent research 
            station on Mars. The mission will launch in 2026 and involves sending robotic systems to prepare 
            infrastructure before human arrival. Advanced life support systems, sustainable energy generation, 
            and in-situ resource utilization technologies will enable long-term human presence on Mars.
            The project represents humanity's next major step in becoming a multi-planetary species.
            """,
            "source": "SpaceNews",
            "language": "en",
            "published_at": "2024-01-19T11:30:00Z",
            "url": "https://spacenews.com/mars-mission-approved",
        }
    ]
    
    return articles

def save_sample_data():
    """Save sample data in different formats for testing."""
    articles = create_sample_data()
    
    # Create test data directory
    test_dir = Path("test_data")
    test_dir.mkdir(exist_ok=True)
    
    # Save as parquet
    df = pd.DataFrame(articles)
    parquet_path = test_dir / "sample_news.parquet"
    df.to_parquet(parquet_path, index=False)
    print(f"✅ Saved {len(articles)} articles to {parquet_path}")
    
    # Save as jsonl
    jsonl_path = test_dir / "sample_news.jsonl"
    with open(jsonl_path, 'w') as f:
        for article in articles:
            f.write(json.dumps(article) + '\n')
    print(f"✅ Saved {len(articles)} articles to {jsonl_path}")
    
    return parquet_path, jsonl_path

def test_cli_indexer():
    """Test the CLI indexer with sample data."""
    print("🚀 Testing CLI RAG Indexer")
    print("=" * 50)
    
    # Create sample data
    parquet_path, jsonl_path = save_sample_data()
    
    # Test 1: Dry run with parquet
    print("\n📋 Test 1: Dry run with parquet file")
    print("-" * 30)
    
    from jobs.rag.cli_indexer import CLIIndexer
    
    indexer = CLIIndexer()
    
    try:
        indexer.run(str(parquet_path), dry_run=True)
        print("✅ Parquet dry run completed successfully")
    except Exception as e:
        print(f"❌ Parquet dry run failed: {e}")
        return False
    
    # Test 2: Dry run with jsonl
    print("\n📋 Test 2: Dry run with jsonl file")
    print("-" * 30)
    
    try:
        indexer = CLIIndexer()
        indexer.run(str(jsonl_path), dry_run=True)
        print("✅ JSONL dry run completed successfully")
    except Exception as e:
        print(f"❌ JSONL dry run failed: {e}")
        return False
    
    print("\n🎉 All tests completed successfully!")
    return True

def test_config_loading():
    """Test configuration loading."""
    print("\n🔧 Testing configuration loading")
    print("-" * 30)
    
    from jobs.rag.cli_indexer import CLIIndexer
    
    # Test default config
    indexer = CLIIndexer()
    config = indexer.config
    
    assert 'database' in config
    assert 'embedding' in config
    assert 'chunking' in config
    assert 'processing' in config
    assert 'filters' in config
    
    print("✅ Default configuration loaded successfully")
    
    # Test config file loading
    config_path = Path("configs/indexer.yaml")
    if config_path.exists():
        indexer = CLIIndexer(str(config_path))
        print("✅ Config file loaded successfully")
    else:
        print("⚠️  Config file not found, using defaults")

def main():
    """Run the demo."""
    print("Demo: CLI RAG Indexer (Issue #230)")
    print("="*50)
    
    try:
        # Test configuration
        test_config_loading()
        
        # Test indexer
        success = test_cli_indexer()
        
        if success:
            print("\n🎊 Demo completed successfully!")
            print("\nNext steps:")
            print("1. Start vector database: make rag-up")
            print("2. Run migrations: make rag-migrate") 
            print("3. Run real indexing: make rag-index SAMPLE_PATH=test_data/")
            print("4. Check results: make rag-connect")
            return 0
        else:
            print("\n❌ Demo failed")
            return 1
            
    except Exception as e:
        print(f"\n💥 Demo crashed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup test data
        import shutil
        test_dir = Path("test_data")
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print(f"\n🧹 Cleaned up test data: {test_dir}")

if __name__ == "__main__":
    sys.exit(main())
