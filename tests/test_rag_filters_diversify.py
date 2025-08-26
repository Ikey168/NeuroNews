"""
Unit tests for RAG Filters and Diversification Services
Issue #237: Filters & ranking fairness (language/date/source)

Tests cover:
- Filter logic for language, date, source, publisher, domain
- Diversification strategies (MMR, domain cap, source cap, round-robin, hybrid)
- Edge cases and error handling
"""

import unittest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from services.rag.filters import (
    RAGFiltersService, FilterCriteria, FilterType, create_filters_service
)
from services.rag.diversify import (
    RAGDiversificationService, DiversificationConfig, DiversificationStrategy,
    create_diversification_service
)


class TestRAGFiltersService(unittest.TestCase):
    """Test cases for RAG Filters Service"""
    
    def setUp(self):
        self.service = RAGFiltersService()
        
        # Sample documents for testing
        self.sample_docs = [
            {
                "id": "doc1",
                "title": "German News Article",
                "content": "Dies ist ein deutscher Artikel",
                "language": "de",
                "date": "2024-01-15",
                "source": "Deutsche Welle",
                "publisher": "DW",
                "domain": "dw.com",
                "url": "https://dw.com/article1",
                "score": 0.9
            },
            {
                "id": "doc2",
                "title": "English News Article",
                "content": "This is an English article",
                "language": "en",
                "date": "2024-01-16",
                "source": "BBC News",
                "publisher": "BBC",
                "domain": "bbc.com",
                "url": "https://bbc.com/article2",
                "score": 0.8
            },
            {
                "id": "doc3",
                "title": "French News Article", 
                "content": "Ceci est un article français",
                "language": "fr",
                "date": "2024-01-17",
                "source": "Le Monde",
                "publisher": "Le Monde",
                "domain": "lemonde.fr",
                "url": "https://lemonde.fr/article3",
                "score": 0.7
            },
            {
                "id": "doc4",
                "title": "Another English Article",
                "content": "Another English news piece",
                "language": "en",
                "date": "2024-01-18",
                "source": "CNN",
                "publisher": "CNN",
                "domain": "cnn.com",
                "url": "https://cnn.com/article4",
                "score": 0.6
            }
        ]
    
    def test_parse_filter_params_language(self):
        """Test parsing of language filter parameters"""
        # Single language
        criteria = self.service.parse_filter_params(lang="de")
        self.assertEqual(criteria.languages, {"de"})
        
        # Multiple languages
        criteria = self.service.parse_filter_params(language=["en", "fr"])
        self.assertEqual(criteria.languages, {"en", "fr"})
        
        # Case insensitive
        criteria = self.service.parse_filter_params(lang="DE")
        self.assertEqual(criteria.languages, {"de"})
    
    def test_parse_filter_params_date(self):
        """Test parsing of date filter parameters"""
        # String dates
        criteria = self.service.parse_filter_params(
            date_from="2024-01-15",
            date_to="2024-01-17"
        )
        self.assertEqual(criteria.date_from, date(2024, 1, 15))
        self.assertEqual(criteria.date_to, date(2024, 1, 17))
        
        # Date objects
        criteria = self.service.parse_filter_params(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 17)
        )
        self.assertEqual(criteria.date_from, date(2024, 1, 15))
        self.assertEqual(criteria.date_to, date(2024, 1, 17))
    
    def test_parse_filter_params_sources(self):
        """Test parsing of source filter parameters"""
        # Single source
        criteria = self.service.parse_filter_params(source="BBC News")
        self.assertEqual(criteria.sources, {"BBC News"})
        
        # Multiple sources
        criteria = self.service.parse_filter_params(sources=["BBC News", "CNN"])
        self.assertEqual(criteria.sources, {"BBC News", "CNN"})
    
    def test_apply_language_filter(self):
        """Test language filtering functionality"""
        criteria = FilterCriteria(languages={"de"})
        filtered = self.service.apply_filters(self.sample_docs, criteria)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "doc1")
        self.assertEqual(filtered[0]["language"], "de")
    
    def test_apply_date_filter(self):
        """Test date range filtering"""
        criteria = FilterCriteria(
            date_from=date(2024, 1, 16),
            date_to=date(2024, 1, 17)
        )
        filtered = self.service.apply_filters(self.sample_docs, criteria)
        
        self.assertEqual(len(filtered), 2)
        doc_ids = {doc["id"] for doc in filtered}
        self.assertEqual(doc_ids, {"doc2", "doc3"})
    
    def test_apply_source_filter(self):
        """Test source filtering"""
        criteria = FilterCriteria(sources={"BBC News", "CNN"})
        filtered = self.service.apply_filters(self.sample_docs, criteria)
        
        self.assertEqual(len(filtered), 2)
        doc_ids = {doc["id"] for doc in filtered}
        self.assertEqual(doc_ids, {"doc2", "doc4"})
    
    def test_apply_domain_filter(self):
        """Test domain filtering"""
        criteria = FilterCriteria(domains={"bbc.com"})
        filtered = self.service.apply_filters(self.sample_docs, criteria)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "doc2")
    
    def test_apply_exclusion_filters(self):
        """Test exclusion filtering"""
        criteria = FilterCriteria(exclude_sources={"BBC News"})
        filtered = self.service.apply_filters(self.sample_docs, criteria)
        
        self.assertEqual(len(filtered), 3)
        sources = {doc["source"] for doc in filtered}
        self.assertNotIn("BBC News", sources)
    
    def test_apply_combined_filters(self):
        """Test combination of multiple filters"""
        criteria = FilterCriteria(
            languages={"en"},
            date_from=date(2024, 1, 16)
        )
        filtered = self.service.apply_filters(self.sample_docs, criteria)
        
        self.assertEqual(len(filtered), 2)
        for doc in filtered:
            self.assertEqual(doc["language"], "en")
            doc_date = self.service._parse_date(doc["date"])
            self.assertGreaterEqual(doc_date, date(2024, 1, 16))
    
    def test_empty_documents(self):
        """Test filtering with empty document list"""
        criteria = FilterCriteria(languages={"en"})
        filtered = self.service.apply_filters([], criteria)
        self.assertEqual(filtered, [])
    
    def test_no_matching_documents(self):
        """Test filtering with no matching documents"""
        criteria = FilterCriteria(languages={"es"})  # Spanish not in test data
        filtered = self.service.apply_filters(self.sample_docs, criteria)
        self.assertEqual(len(filtered), 0)


class TestRAGDiversificationService(unittest.TestCase):
    """Test cases for RAG Diversification Service"""
    
    def setUp(self):
        self.config = DiversificationConfig(
            max_per_domain=2,
            max_per_source=2,
            lambda_param=0.7
        )
        self.service = RAGDiversificationService(self.config)
        
        # Sample documents with varying domains and sources
        self.sample_docs = [
            {
                "id": "doc1",
                "title": "Article 1",
                "content": "Content about technology and AI",
                "source": "TechNews",
                "domain": "technews.com",
                "score": 0.9
            },
            {
                "id": "doc2", 
                "title": "Article 2",
                "content": "Content about technology and programming",
                "source": "TechNews",
                "domain": "technews.com", 
                "score": 0.85
            },
            {
                "id": "doc3",
                "title": "Article 3", 
                "content": "Content about sports and football",
                "source": "SportNews",
                "domain": "sportnews.com",
                "score": 0.8
            },
            {
                "id": "doc4",
                "title": "Article 4",
                "content": "Content about health and medicine",
                "source": "HealthNews", 
                "domain": "healthnews.com",
                "score": 0.75
            },
            {
                "id": "doc5",
                "title": "Article 5",
                "content": "More content about technology and innovation",
                "source": "TechNews",
                "domain": "technews.com",
                "score": 0.7
            },
            {
                "id": "doc6",
                "title": "Article 6",
                "content": "Content about business and finance",
                "source": "BusinessNews",
                "domain": "businessnews.com",
                "score": 0.65
            }
        ]
    
    def test_domain_cap_diversification(self):
        """Test per-domain result capping"""
        self.service.config.strategy = DiversificationStrategy.DOMAIN_CAP
        diversified = self.service.diversify_results(self.sample_docs, 5)
        
        # Count documents per domain
        domain_counts = {}
        for doc in diversified:
            domain = doc["domain"]
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        # Check that no domain exceeds the cap
        for count in domain_counts.values():
            self.assertLessEqual(count, self.config.max_per_domain)
    
    def test_source_cap_diversification(self):
        """Test per-source result capping"""
        self.service.config.strategy = DiversificationStrategy.SOURCE_CAP
        diversified = self.service.diversify_results(self.sample_docs, 5)
        
        # Count documents per source
        source_counts = {}
        for doc in diversified:
            source = doc["source"]
            source_counts[source] = source_counts.get(source, 0) + 1
        
        # Check that no source exceeds the cap
        for count in source_counts.values():
            self.assertLessEqual(count, self.config.max_per_source)
    
    def test_round_robin_diversification(self):
        """Test round-robin selection across sources"""
        self.service.config.strategy = DiversificationStrategy.ROUND_ROBIN
        diversified = self.service.diversify_results(self.sample_docs, 4)
        
        # Should get one document from each unique source
        sources = [doc["source"] for doc in diversified]
        unique_sources = set(sources)
        
        # Should have good source diversity
        self.assertGreater(len(unique_sources), 1)
    
    def test_mmr_diversification(self):
        """Test Maximal Marginal Relevance diversification"""
        self.service.config.strategy = DiversificationStrategy.MMR
        diversified = self.service.diversify_results(self.sample_docs, 4)
        
        self.assertEqual(len(diversified), 4)
        
        # First document should be the highest scoring
        self.assertEqual(diversified[0]["id"], "doc1")
        
        # Should maintain some relevance ordering while promoting diversity
        scores = [doc["score"] for doc in diversified]
        self.assertGreater(scores[0], 0.8)  # High relevance maintained
    
    def test_hybrid_diversification(self):
        """Test hybrid diversification strategy"""
        self.service.config.strategy = DiversificationStrategy.HYBRID
        diversified = self.service.diversify_results(self.sample_docs, 5)
        
        # Should respect both domain and source caps
        domain_counts = {}
        source_counts = {}
        
        for doc in diversified:
            domain = doc["domain"]
            source = doc["source"]
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            source_counts[source] = source_counts.get(source, 0) + 1
        
        # Check constraints
        for count in domain_counts.values():
            self.assertLessEqual(count, self.config.max_per_domain)
        for count in source_counts.values():
            self.assertLessEqual(count, self.config.max_per_source)
    
    def test_similarity_calculation(self):
        """Test document similarity calculation"""
        doc1 = {"content": "technology and artificial intelligence"}
        doc2 = {"content": "technology and programming"}
        doc3 = {"content": "sports and football"}
        
        sim_12 = self.service._calculate_similarity(doc1, doc2)
        sim_13 = self.service._calculate_similarity(doc1, doc3)
        
        # Technology docs should be more similar than tech vs sports
        self.assertGreater(sim_12, sim_13)
        self.assertGreater(sim_12, 0)
        self.assertGreaterEqual(sim_13, 0)
    
    def test_diversity_stats(self):
        """Test diversity statistics calculation"""
        stats = self.service.get_diversity_stats(self.sample_docs)
        
        self.assertEqual(stats["total_documents"], 6)
        self.assertEqual(stats["unique_domains"], 4)
        self.assertEqual(stats["unique_sources"], 4)
        self.assertIn("domain_distribution", stats)
        self.assertIn("source_distribution", stats)
        self.assertGreater(stats["domain_diversity_ratio"], 0)
        self.assertGreater(stats["source_diversity_ratio"], 0)
    
    def test_empty_documents_diversification(self):
        """Test diversification with empty document list"""
        diversified = self.service.diversify_results([], 5)
        self.assertEqual(diversified, [])
    
    def test_target_count_larger_than_documents(self):
        """Test when target count is larger than available documents"""
        diversified = self.service.diversify_results(self.sample_docs, 10)
        self.assertLessEqual(len(diversified), len(self.sample_docs))
    
    def test_extract_domain_from_url(self):
        """Test domain extraction from URL"""
        doc = {"url": "https://example.com/article/123"}
        domain = self.service._extract_domain(doc)
        self.assertEqual(domain, "example.com")
    
    def test_extract_text_multiple_fields(self):
        """Test text extraction from multiple fields"""
        doc = {
            "title": "Test Title",
            "summary": "Test Summary",
            "content": "Test Content"
        }
        text = self.service._extract_text(doc)
        self.assertIn("Test Content", text)
        
        # Test fallback to title and summary
        doc_no_content = {
            "title": "Test Title",
            "summary": "Test Summary"
        }
        text = self.service._extract_text(doc_no_content)
        self.assertIn("Test Title", text)
        self.assertIn("Test Summary", text)


class TestIntegration(unittest.TestCase):
    """Integration tests for filters and diversification working together"""
    
    def setUp(self):
        self.filters_service = RAGFiltersService()
        self.diversify_service = RAGDiversificationService()
        
        # Sample documents with multiple attributes
        self.docs = [
            {
                "id": "doc1", "language": "en", "source": "Source A", 
                "domain": "a.com", "score": 0.9, "content": "tech news"
            },
            {
                "id": "doc2", "language": "en", "source": "Source A", 
                "domain": "a.com", "score": 0.8, "content": "more tech"
            },
            {
                "id": "doc3", "language": "en", "source": "Source B", 
                "domain": "b.com", "score": 0.7, "content": "sports news"
            },
            {
                "id": "doc4", "language": "de", "source": "Source C", 
                "domain": "c.com", "score": 0.6, "content": "german news"
            },
            {
                "id": "doc5", "language": "en", "source": "Source C", 
                "domain": "c.com", "score": 0.5, "content": "health news"
            }
        ]
    
    def test_filter_then_diversify(self):
        """Test filtering followed by diversification"""
        # First filter by language
        criteria = FilterCriteria(languages={"en"})
        filtered = self.filters_service.apply_filters(self.docs, criteria)
        
        # Then diversify to avoid single-source dominance
        diversified = self.diversify_service.diversify_results(filtered, 3)
        
        # Should have only English documents
        for doc in diversified:
            self.assertEqual(doc["language"], "en")
        
        # Should have good source diversity
        sources = {doc["source"] for doc in diversified}
        self.assertGreater(len(sources), 1)
    
    def test_factory_functions(self):
        """Test factory functions for service creation"""
        filters_service = create_filters_service()
        self.assertIsInstance(filters_service, RAGFiltersService)
        
        diversify_service = create_diversification_service()
        self.assertIsInstance(diversify_service, RAGDiversificationService)
        
        config = DiversificationConfig(max_per_domain=5)
        diversify_service_with_config = create_diversification_service(config)
        self.assertEqual(diversify_service_with_config.config.max_per_domain, 5)


if __name__ == '__main__':
    unittest.main()
