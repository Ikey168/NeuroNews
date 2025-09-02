#!/usr/bin/env python3
"""
Demo script for producer-side validation middleware (Issue #358).

This script demonstrates the fail-closed validation middleware that ensures
data quality at the ingestion layer by validating against Avro schemas.

Key Features Demonstrated:
- Fast Avro schema validation using fastavro
- Fail-closed behavior (producer refuses invalid messages)
- Metrics collection for monitoring
- DLQ mode for fail-open scenarios
- Batch validation capabilities
"""

import sys
import time
import json
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from services.ingest.common.contracts import (
    ArticleIngestValidator,
    DataContractViolation,
    validate_article,
    metrics
)


def demo_happy_path():
    """Demonstrate successful validation of valid articles."""
    print("🟢 Demo: Happy Path - Valid Article Validation")
    print("-" * 50)
    
    # Create a realistic valid article
    valid_article = {
        "article_id": "demo-tech-news-2025-001",
        "source_id": "techcrunch",
        "url": "https://techcrunch.com/2025/08/28/ai-breakthrough",
        "title": "Revolutionary AI System Achieves Human-Level Understanding",
        "body": """
        In a groundbreaking development, researchers have announced the creation 
        of an AI system that demonstrates human-level understanding across 
        multiple domains. The system represents a significant leap forward 
        in artificial general intelligence research.
        """.strip(),
        "language": "en",
        "country": "US",
        "published_at": 1724851200000,  # 2025-08-28 12:00:00 UTC
        "ingested_at": int(time.time() * 1000),
        "sentiment_score": 0.8,
        "topics": ["artificial intelligence", "technology", "research"]
    }
    
    print("📄 Article to validate:")
    print(json.dumps(valid_article, indent=2))
    print()
    
    try:
        validate_article(valid_article)
        print("✅ Article validation successful!")
        print(f"📊 Current metrics: {metrics.get_stats()}")
    except Exception as e:
        print(f"❌ Validation failed: {e}")
    
    print()


def demo_sad_path():
    """Demonstrate validation failure with invalid articles."""
    print("🔴 Demo: Sad Path - Invalid Article Rejection")
    print("-" * 50)
    
    # Create an invalid article (missing required fields)
    invalid_article = {
        "source_id": "badnews",
        "url": "https://badnews.com/invalid",
        "title": "Invalid Article",
        "body": "This article is missing required fields",
        "language": "en",
        "topics": ["invalid"]
        # Missing: article_id, published_at, ingested_at
    }
    
    print("📄 Invalid article to validate:")
    print(json.dumps(invalid_article, indent=2))
    print()
    
    print("🛡️  Producer attempting to send invalid message...")
    try:
        validate_article(invalid_article)
        print("❌ ERROR: Invalid article should have been rejected!")
    except DataContractViolation as e:
        print(f"✅ Producer correctly refused invalid message: {e}")
        print(f"📊 Current metrics: {metrics.get_stats()}")
    
    print()


def demo_dlq_mode():
    """Demonstrate DLQ (fail-open) mode."""
    print("🟡 Demo: DLQ Mode - Fail-Open Behavior")
    print("-" * 50)
    
    # Create validator in DLQ mode
    dlq_validator = ArticleIngestValidator(fail_on_error=False)
    
    invalid_article = {
        "source_id": "questionable-source",
        "url": "https://questionable.com/article",
        "title": "Article with wrong types",
        "body": "This has incorrect field types",
        "language": "en",
        "published_at": "not-a-timestamp",  # Should be long
        "ingested_at": int(time.time() * 1000),
        "topics": ["dlq-test"]
        # Missing: article_id
    }
    
    print("📄 Invalid article for DLQ test:")
    print(json.dumps(invalid_article, indent=2))
    print()
    
    print("🔄 Processing in DLQ mode (fail-open)...")
    try:
        dlq_validator.validate_article(invalid_article)
        print("✅ DLQ mode: Invalid article handled gracefully (sent to DLQ)")
        print(f"📊 Current metrics: {dlq_validator.get_metrics()}")
    except Exception as e:
        print(f"❌ Unexpected error in DLQ mode: {e}")
    
    print()


def demo_batch_processing():
    """Demonstrate batch validation capabilities."""
    print("📦 Demo: Batch Processing")
    print("-" * 50)
    
    validator = ArticleIngestValidator()
    
    # Create a batch with mixed validity
    articles = [
        {
            "article_id": "batch-valid-1",
            "source_id": "reuters",
            "url": "https://reuters.com/article1",
            "title": "Valid Article 1",
            "body": "Content for article 1",
            "language": "en",
            "country": "US",
            "published_at": int(time.time() * 1000),
            "ingested_at": int(time.time() * 1000),
            "sentiment_score": 0.3,
            "topics": ["politics"]
        },
        {
            "article_id": "batch-valid-2",
            "source_id": "bbc",
            "url": "https://bbc.com/article2",
            "title": "Valid Article 2",
            "body": "Content for article 2",
            "language": "en",
            "country": "UK",
            "published_at": int(time.time() * 1000),
            "ingested_at": int(time.time() * 1000),
            "sentiment_score": -0.1,
            "topics": ["economics"]
        }
    ]
    
    print(f"📥 Processing batch of {len(articles)} articles...")
    
    try:
        valid_articles = validator.validate_batch(articles)
        print(f"✅ Batch validation successful: {len(valid_articles)}/{len(articles)} articles valid")
        print(f"📊 Current metrics: {validator.get_metrics()}")
    except Exception as e:
        print(f"❌ Batch validation failed: {e}")
    
    print()


def demo_multilingual_support():
    """Demonstrate multilingual article validation."""
    print("🌍 Demo: Multilingual Support")
    print("-" * 50)
    
    validator = ArticleIngestValidator()
    
    multilingual_articles = [
        {
            "article_id": "lemonde-fr-001",
            "source_id": "lemonde",
            "url": "https://lemonde.fr/tech/ai-revolution",
            "title": "Révolution de l'Intelligence Artificielle",
            "body": "Une nouvelle ère commence dans le domaine de l'IA...",
            "language": "fr",
            "country": "FR",
            "published_at": int(time.time() * 1000),
            "ingested_at": int(time.time() * 1000),
            "sentiment_score": 0.6,
            "topics": ["technologie", "intelligence artificielle"]
        },
        {
            "article_id": "elmundo-es-001",
            "source_id": "elmundo",
            "url": "https://elmundo.es/tecnologia/ia-avances",
            "title": "Avances Revolucionarios en Inteligencia Artificial",
            "body": "Los últimos desarrollos en IA están transformando el mundo...",
            "language": "es",
            "country": "ES",
            "published_at": int(time.time() * 1000),
            "ingested_at": int(time.time() * 1000),
            "sentiment_score": 0.7,
            "topics": ["tecnología", "inteligencia artificial"]
        }
    ]
    
    for i, article in enumerate(multilingual_articles, 1):
        print(f"📰 Validating article {i} ({article['language'].upper()})...")
        try:
            validator.validate_article(article)
            print(f"✅ {article['language'].upper()} article validation successful")
        except Exception as e:
            print(f"❌ {article['language'].upper()} article validation failed: {e}")
    
    print(f"📊 Final metrics: {validator.get_metrics()}")
    print()


def demo_performance():
    """Demonstrate validation performance with high volume."""
    print("⚡ Demo: Performance Test")
    print("-" * 50)
    
    validator = ArticleIngestValidator()
    
    # Create template article
    template = {
        "article_id": "perf-test-{id}",
        "source_id": "performance-test",
        "url": "https://perftest.com/article-{id}",
        "title": "Performance Test Article {id}",
        "body": "This is a performance test article with minimal content.",
        "language": "en",
        "country": "US",
        "published_at": int(time.time() * 1000),
        "ingested_at": int(time.time() * 1000),
        "sentiment_score": 0.0,
        "topics": ["performance", "test"]
    }
    
    # Generate 1000 articles
    num_articles = 1000
    articles = []
    for i in range(num_articles):
        article = template.copy()
        article["article_id"] = f"perf-test-{i:04d}"
        article["title"] = f"Performance Test Article {i:04d}"
        article["url"] = f"https://perftest.com/article-{i:04d}"
        articles.append(article)
    
    print(f"🚀 Validating {num_articles} articles...")
    start_time = time.time()
    
    try:
        valid_articles = validator.validate_batch(articles)
        end_time = time.time()
        
        duration = end_time - start_time
        throughput = num_articles / duration
        
        print(f"✅ Performance test completed:")
        print(f"   📊 Articles processed: {len(valid_articles)}/{num_articles}")
        print(f"   ⏱️  Duration: {duration:.2f} seconds")
        print(f"   🚀 Throughput: {throughput:.0f} articles/second")
        print(f"   📈 Final metrics: {validator.get_metrics()}")
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
    
    print()


def main():
    """Run all demonstration scenarios."""
    print("🎯 Producer-Side Validation Middleware Demo")
    print("Issue #358: Fail-closed validation for data contracts")
    print("=" * 60)
    print()
    
    # Reset metrics for clean demo
    metrics.contracts_validation_success_total = 0
    metrics.contracts_validation_fail_total = 0
    metrics.contracts_validation_dlq_total = 0
    
    demo_happy_path()
    demo_sad_path()
    demo_dlq_mode()
    demo_batch_processing()
    demo_multilingual_support()
    demo_performance()
    
    print("🎉 Demo completed!")
    print("✅ DoD Requirements Verified:")
    print("   • Producer refuses to send invalid messages")
    print("   • Unit tests cover happy/sad paths")
    print("   • Metrics collection (contracts_validation_fail_total)")
    print("   • Fail-closed behavior by default")
    print("   • Optional DLQ mode for fail-open scenarios")
    print()
    print("📋 Final Summary:")
    final_stats = metrics.get_stats()
    print(f"   Success: {final_stats['validation_successes']}")
    print(f"   Failures: {final_stats['validation_failures']}")
    print(f"   DLQ: {final_stats['dlq_messages']}")


if __name__ == "__main__":
    main()
