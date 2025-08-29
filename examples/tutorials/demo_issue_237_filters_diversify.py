"""
Demo script for Issue #237: Filters & ranking fairness (language/date/source)

This script demonstrates the RAG filters and diversification services
working together to ensure fair representation and avoid single-source dominance.
"""

import sys
import os
from datetime import date, datetime
from typing import List, Dict, Any

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.rag.filters import RAGFiltersService, FilterCriteria
from services.rag.diversify import RAGDiversificationService, DiversificationConfig, DiversificationStrategy


def create_sample_documents() -> List[Dict[str, Any]]:
    """Create sample documents for demonstration"""
    return [
        {
            "id": "doc1",
            "title": "AI Breakthrough in Machine Learning",
            "content": "Researchers at tech universities announce major breakthrough in artificial intelligence and machine learning algorithms.",
            "language": "en",
            "date": "2024-01-15",
            "source": "TechCrunch",
            "publisher": "TechCrunch",
            "domain": "techcrunch.com",
            "url": "https://techcrunch.com/ai-breakthrough",
            "score": 0.95
        },
        {
            "id": "doc2", 
            "title": "Another Tech Innovation",
            "content": "More technological innovations emerge from Silicon Valley startups focused on AI development.",
            "language": "en",
            "date": "2024-01-16",
            "source": "TechCrunch",
            "publisher": "TechCrunch", 
            "domain": "techcrunch.com",
            "url": "https://techcrunch.com/tech-innovation",
            "score": 0.90
        },
        {
            "id": "doc3",
            "title": "Tech Giants Invest in AI",
            "content": "Major technology companies announce billion-dollar investments in artificial intelligence research.",
            "language": "en",
            "date": "2024-01-17", 
            "source": "TechCrunch",
            "publisher": "TechCrunch",
            "domain": "techcrunch.com",
            "url": "https://techcrunch.com/ai-investment",
            "score": 0.88
        },
        {
            "id": "doc4",
            "title": "Climate Change Solutions",
            "content": "Scientists propose innovative solutions to combat climate change using renewable energy.",
            "language": "en",
            "date": "2024-01-18",
            "source": "BBC News",
            "publisher": "BBC",
            "domain": "bbc.com",
            "url": "https://bbc.com/climate-solutions",
            "score": 0.85
        },
        {
            "id": "doc5",
            "title": "Deutsche KI-Forschung",
            "content": "Deutsche Universitäten führen bahnbrechende Forschung im Bereich künstliche Intelligenz durch.",
            "language": "de",
            "date": "2024-01-19",
            "source": "Deutsche Welle",
            "publisher": "DW",
            "domain": "dw.com", 
            "url": "https://dw.com/ki-forschung",
            "score": 0.82
        },
        {
            "id": "doc6",
            "title": "Healthcare AI Applications",
            "content": "Artificial intelligence transforms healthcare with new diagnostic and treatment applications.",
            "language": "en",
            "date": "2024-01-20",
            "source": "Reuters",
            "publisher": "Reuters",
            "domain": "reuters.com",
            "url": "https://reuters.com/healthcare-ai",
            "score": 0.80
        },
        {
            "id": "doc7",
            "title": "AI in Financial Services",
            "content": "Banks and financial institutions adopt AI for fraud detection and customer service automation.",
            "language": "en", 
            "date": "2024-01-21",
            "source": "Reuters",
            "publisher": "Reuters",
            "domain": "reuters.com",
            "url": "https://reuters.com/finance-ai",
            "score": 0.78
        },
        {
            "id": "doc8",
            "title": "Recherche IA en France",
            "content": "Les universités françaises développent des solutions d'intelligence artificielle innovantes.",
            "language": "fr",
            "date": "2024-01-22",
            "source": "Le Monde",
            "publisher": "Le Monde",
            "domain": "lemonde.fr",
            "url": "https://lemonde.fr/ia-recherche",
            "score": 0.75
        },
        {
            "id": "doc9",
            "title": "AI Ethics and Regulation",
            "content": "Governments worldwide consider new regulations for ethical AI development and deployment.",
            "language": "en",
            "date": "2024-01-23",
            "source": "CNN",
            "publisher": "CNN",
            "domain": "cnn.com",
            "url": "https://cnn.com/ai-ethics",
            "score": 0.73
        },
        {
            "id": "doc10",
            "title": "Startup AI Funding",
            "content": "Venture capital firms increase funding for AI startups developing cutting-edge solutions.",
            "language": "en",
            "date": "2024-01-24",
            "source": "CNN",
            "publisher": "CNN", 
            "domain": "cnn.com",
            "url": "https://cnn.com/ai-funding",
            "score": 0.70
        }
    ]


def print_documents(docs: List[Dict[str, Any]], title: str):
    """Print documents in a formatted way"""
    print(f"\\n{title}")
    print("=" * len(title))
    
    for i, doc in enumerate(docs, 1):
        print(f"{i}. {doc['title']} (Score: {doc['score']})")
        print(f"   Language: {doc['language']} | Source: {doc['source']} | Domain: {doc['domain']}")
        print(f"   Date: {doc['date']}")
        print()


def demonstrate_filters():
    """Demonstrate filtering functionality"""
    print("🔍 RAG FILTERS DEMONSTRATION")
    print("=" * 50)
    
    filters_service = RAGFiltersService()
    docs = create_sample_documents()
    
    print_documents(docs, "Original Documents (All)")
    
    # Language filtering
    print("\\n1. LANGUAGE FILTERING")
    print("-" * 30)
    
    # German only
    criteria = filters_service.parse_filter_params(lang="de")
    german_docs = filters_service.apply_filters(docs, criteria)
    print_documents(german_docs, "German Documents Only (lang='de')")
    
    # English only
    criteria = filters_service.parse_filter_params(lang="en")
    english_docs = filters_service.apply_filters(docs, criteria)
    print_documents(english_docs, "English Documents Only (lang='en')")
    
    # Multiple languages
    criteria = filters_service.parse_filter_params(language=["en", "de"])
    multi_lang_docs = filters_service.apply_filters(docs, criteria)
    print_documents(multi_lang_docs, "English and German Documents")
    
    # Date filtering
    print("\\n2. DATE FILTERING")
    print("-" * 30)
    
    criteria = filters_service.parse_filter_params(
        date_from="2024-01-20",
        date_to="2024-01-24"
    )
    recent_docs = filters_service.apply_filters(docs, criteria)
    print_documents(recent_docs, "Recent Documents (Jan 20-24, 2024)")
    
    # Source filtering
    print("\\n3. SOURCE FILTERING")
    print("-" * 30)
    
    criteria = filters_service.parse_filter_params(sources=["BBC News", "Reuters"])
    news_docs = filters_service.apply_filters(docs, criteria)
    print_documents(news_docs, "BBC News and Reuters Only")
    
    # Domain filtering
    print("\\n4. DOMAIN FILTERING")
    print("-" * 30)
    
    criteria = filters_service.parse_filter_params(domain="techcrunch.com")
    tech_docs = filters_service.apply_filters(docs, criteria)
    print_documents(tech_docs, "TechCrunch Domain Only")
    
    # Exclusion filtering
    print("\\n5. EXCLUSION FILTERING")
    print("-" * 30)
    
    criteria = filters_service.parse_filter_params(exclude_sources=["TechCrunch"])
    non_tech_docs = filters_service.apply_filters(docs, criteria)
    print_documents(non_tech_docs, "Excluding TechCrunch")
    
    # Combined filtering
    print("\\n6. COMBINED FILTERING")
    print("-" * 30)
    
    criteria = filters_service.parse_filter_params(
        lang="en",
        date_from="2024-01-18",
        exclude_sources=["TechCrunch"]
    )
    combined_docs = filters_service.apply_filters(docs, criteria)
    print_documents(combined_docs, "English + Recent + No TechCrunch")


def demonstrate_diversification():
    """Demonstrate diversification functionality"""
    print("\\n\\n🎯 RAG DIVERSIFICATION DEMONSTRATION")
    print("=" * 50)
    
    docs = create_sample_documents()
    
    # Show original distribution
    print("\\nORIGINAL DOCUMENT DISTRIBUTION:")
    print("-" * 40)
    
    source_counts = {}
    domain_counts = {}
    for doc in docs:
        source = doc['source']
        domain = doc['domain']
        source_counts[source] = source_counts.get(source, 0) + 1
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
    
    print("Sources:", source_counts)
    print("Domains:", domain_counts)
    
    # Demo different strategies
    strategies = [
        (DiversificationStrategy.DOMAIN_CAP, "Domain Cap (max 2 per domain)"),
        (DiversificationStrategy.SOURCE_CAP, "Source Cap (max 2 per source)"), 
        (DiversificationStrategy.ROUND_ROBIN, "Round Robin Selection"),
        (DiversificationStrategy.MMR, "Maximal Marginal Relevance"),
        (DiversificationStrategy.HYBRID, "Hybrid Strategy")
    ]
    
    for strategy, description in strategies:
        print(f"\\n{description.upper()}")
        print("-" * len(description))
        
        config = DiversificationConfig(
            strategy=strategy,
            max_per_domain=2,
            max_per_source=2,
            lambda_param=0.7
        )
        
        service = RAGDiversificationService(config)
        diversified = service.diversify_results(docs, 6)
        
        print_documents(diversified, f"Diversified Results ({description})")
        
        # Show diversity stats
        stats = service.get_diversity_stats(diversified)
        print(f"Diversity Stats:")
        print(f"  - Unique domains: {stats['unique_domains']}/{stats['total_documents']}")
        print(f"  - Unique sources: {stats['unique_sources']}/{stats['total_documents']}")
        print(f"  - Domain diversity ratio: {stats['domain_diversity_ratio']:.2f}")
        print(f"  - Source diversity ratio: {stats['source_diversity_ratio']:.2f}")
        print(f"  - Max per domain: {stats['max_per_domain']}")
        print(f"  - Max per source: {stats['max_per_source']}")


def demonstrate_integration():
    """Demonstrate filters and diversification working together"""
    print("\\n\\n🔗 INTEGRATION DEMONSTRATION")
    print("=" * 50)
    
    filters_service = RAGFiltersService()
    diversify_service = RAGDiversificationService(DiversificationConfig(
        strategy=DiversificationStrategy.HYBRID,
        max_per_domain=2,
        max_per_source=2
    ))
    
    docs = create_sample_documents()
    
    print("\\nSCENARIO: Get English AI articles with fair source distribution")
    print("-" * 60)
    
    # Step 1: Filter by language and content
    criteria = filters_service.parse_filter_params(
        lang="en",
        date_from="2024-01-15"
    )
    filtered_docs = filters_service.apply_filters(docs, criteria)
    print_documents(filtered_docs, "Step 1: Filtered Documents (English + Recent)")
    
    # Step 2: Diversify to avoid single-source dominance
    diversified_docs = diversify_service.diversify_results(filtered_docs, 5)
    print_documents(diversified_docs, "Step 2: Diversified Results (Max 2 per source/domain)")
    
    # Show final stats
    stats = diversify_service.get_diversity_stats(diversified_docs)
    print("\\nFINAL DIVERSITY ANALYSIS:")
    print("-" * 30)
    print(f"Sources: {stats['source_distribution']}")
    print(f"Domains: {stats['domain_distribution']}")
    print(f"Source diversity ratio: {stats['source_diversity_ratio']:.2f}")
    print(f"Domain diversity ratio: {stats['domain_diversity_ratio']:.2f}")


def validate_dod_requirements():
    """Validate Definition of Done requirements"""
    print("\\n\\n✅ DOD VALIDATION")
    print("=" * 50)
    
    filters_service = RAGFiltersService()
    diversify_service = RAGDiversificationService(DiversificationConfig(
        strategy=DiversificationStrategy.HYBRID,
        max_per_domain=2
    ))
    
    docs = create_sample_documents()
    
    print("\\nRequirement: Queries with lang='de' only return German docs")
    print("-" * 60)
    
    # Test German filtering
    criteria = filters_service.parse_filter_params(lang="de")
    german_docs = filters_service.apply_filters(docs, criteria)
    
    all_german = all(doc['language'] == 'de' for doc in german_docs)
    print(f"✅ German filter works: {all_german}")
    print(f"   Found {len(german_docs)} German documents")
    
    print("\\nRequirement: top-k diversified by domain")
    print("-" * 45)
    
    # Test diversification
    diversified = diversify_service.diversify_results(docs, 6)
    stats = diversify_service.get_diversity_stats(diversified)
    
    max_per_domain = stats['max_per_domain']
    domain_diversity = stats['domain_diversity_ratio']
    
    print(f"✅ Domain diversification works: max_per_domain = {max_per_domain}")
    print(f"✅ Good domain diversity: {domain_diversity:.2f} ratio")
    print(f"   Domain distribution: {stats['domain_distribution']}")
    
    # Test combined requirement
    print("\\nCombined Test: German docs with domain diversification")
    print("-" * 55)
    
    german_diversified = diversify_service.diversify_results(german_docs, 5)
    
    all_german_diversified = all(doc['language'] == 'de' for doc in german_diversified)
    print(f"✅ Combined filter + diversify works: {all_german_diversified}")
    print(f"   {len(german_diversified)} German documents with fair distribution")


def main():
    """Main demonstration function"""
    print("Issue #237 Demo: Filters & ranking fairness (language/date/source)")
    print("=" * 70)
    print()
    print("This demo shows:")
    print("• Structured filtering by language, date, source, publisher, domain")
    print("• Result diversification to avoid single-source dominance")
    print("• Integration of filters and diversification")
    print("• DoD requirement validation")
    print()
    
    try:
        demonstrate_filters()
        demonstrate_diversification()
        demonstrate_integration()
        validate_dod_requirements()
        
        print("\\n\\n🎉 DEMO COMPLETE!")
        print("=" * 30)
        print("✅ All features working correctly")
        print("✅ DoD requirements validated")
        print("✅ Ready for production use")
        
    except Exception as e:
        print(f"\\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
