"""
Tests for keyword extraction and topic modeling functionality (Issue #29).
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.nlp.keyword_topic_extractor import (
    KeywordTopicExtractor, TFIDFKeywordExtractor, LDATopicModeler,
    TextPreprocessor, KeywordResult, TopicResult, ExtractionResult,
    SimpleKeywordExtractor, create_keyword_extractor
)
from src.nlp.keyword_topic_database import KeywordTopicDatabase
from src.api.routes.topic_routes import router
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Create test app
app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestTextPreprocessor:
    """Test text preprocessing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.preprocessor = TextPreprocessor()
    
    def test_clean_text_basic(self):
        """Test basic text cleaning."""
        text = "This is a <b>test</b> with HTML tags and http://example.com URLs."
        cleaned = self.preprocessor.clean_text(text)
        
        assert "<b>" not in cleaned
        assert "</b>" not in cleaned
        assert "http://example.com" not in cleaned
        assert "test" in cleaned
    
    def test_extract_sentences(self):
        """Test sentence extraction."""
        text = "This is sentence one. This is sentence two! And a third sentence?"
        sentences = self.preprocessor.extract_sentences(text)
        
        assert len(sentences) == 3
        assert "This is sentence one." in sentences[0]
    
    def test_extract_keywords_pos(self):
        """Test POS-based keyword extraction."""
        text = "Machine learning algorithms use artificial intelligence techniques."
        keywords = self.preprocessor.extract_keywords_pos(text)
        
        assert "machine" in keywords or "learning" in keywords
        assert "algorithm" in keywords or "artificial" in keywords
        assert len(keywords) > 0


class TestTFIDFKeywordExtractor:
    """Test TF-IDF keyword extraction."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = TFIDFKeywordExtractor(max_features=100)
    
    def test_extract_keywords_single_text(self):
        """Test keyword extraction from single text."""
        texts = ["Machine learning and artificial intelligence are transforming technology"]
        results = self.extractor.extract_keywords(texts, top_k=5)
        
        assert len(results) == 1
        assert len(results[0]) <= 5
        
        # Check that keywords are KeywordResult objects
        for keyword in results[0]:
            assert isinstance(keyword, KeywordResult)
            assert keyword.method == 'tfidf'
            assert keyword.score > 0
    
    def test_extract_keywords_multiple_texts(self):
        """Test keyword extraction from multiple texts."""
        texts = [
            "Machine learning algorithms use neural networks",
            "Climate change affects global warming patterns",
            "Healthcare technology improves patient outcomes"
        ]
        results = self.extractor.extract_keywords(texts, top_k=3)
        
        assert len(results) == 3
        for result in results:
            assert len(result) <= 3
    
    def test_extract_keywords_empty_input(self):
        """Test handling of empty input."""
        results = self.extractor.extract_keywords([], top_k=5)
        assert results == []


class TestLDATopicModeler:
    """Test LDA topic modeling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.modeler = LDATopicModeler(n_topics=3, max_features=100)
    
    def test_fit_topics_success(self):
        """Test successful topic fitting."""
        texts = [
            "Machine learning and artificial intelligence research advances",
            "Climate change and environmental sustainability issues",
            "Healthcare technology and medical innovation progress",
            "Artificial intelligence transforms healthcare diagnostics",
            "Environmental protection and climate action policies"
        ]
        
        topic_info = self.modeler.fit_topics(texts)
        
        assert topic_info["model_fitted"] is True
        assert len(topic_info["topics"]) == 3
        assert "perplexity" in topic_info
        
        for topic in topic_info["topics"]:
            assert "topic_id" in topic
            assert "topic_name" in topic
            assert "topic_words" in topic
            assert len(topic["topic_words"]) > 0
    
    def test_fit_topics_insufficient_data(self):
        """Test handling of insufficient data."""
        texts = ["Short text"]
        topic_info = self.modeler.fit_topics(texts)
        
        assert topic_info["model_fitted"] is False
        assert len(topic_info["topics"]) == 0
    
    def test_predict_topics_without_fitting(self):
        """Test topic prediction without fitted model."""
        texts = ["Test text for prediction"]
        results = self.modeler.predict_topics(texts)
        
        assert len(results) == 1
        assert results[0] == []  # Empty since model not fitted


class TestKeywordTopicExtractor:
    """Test main keyword topic extractor."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = KeywordTopicExtractor()
        self.sample_articles = [
            {
                "id": "test_1",
                "title": "AI Revolution in Healthcare",
                "content": "Artificial intelligence and machine learning are revolutionizing healthcare through advanced diagnostic tools.",
                "url": "https://example.com/1"
            },
            {
                "id": "test_2", 
                "title": "Climate Change Impact",
                "content": "Climate change is causing significant environmental changes affecting global weather patterns.",
                "url": "https://example.com/2"
            }
        ]
    
    def test_fit_corpus(self):
        """Test corpus fitting for topic modeling."""
        topic_info = self.extractor.fit_corpus(self.sample_articles)
        
        # Should have attempted to fit (though may not succeed with small dataset)
        assert "model_fitted" in topic_info
        assert "topics" in topic_info
    
    def test_extract_keywords_and_topics(self):
        """Test keyword and topic extraction from article."""
        article = self.sample_articles[0]
        result = self.extractor.extract_keywords_and_topics(article)
        
        assert isinstance(result, ExtractionResult)
        assert result.article_id == "test_1"
        assert result.title == "AI Revolution in Healthcare"
        assert result.url == "https://example.com/1"
        assert result.extraction_method == 'tfidf_lda'
        assert result.processing_time > 0
        assert isinstance(result.processed_at, datetime)
    
    def test_extract_empty_article(self):
        """Test handling of empty article."""
        empty_article = {"id": "empty", "title": "", "content": "", "url": ""}
        result = self.extractor.extract_keywords_and_topics(empty_article)
        
        assert result.extraction_method == 'empty'
        assert len(result.keywords) == 0
        assert len(result.topics) == 0
    
    def test_process_batch(self):
        """Test batch processing of articles."""
        results = self.extractor.process_batch(self.sample_articles)
        
        assert len(results) == 2
        for result in results:
            assert isinstance(result, ExtractionResult)
            assert result.article_id in ["test_1", "test_2"]
    
    def test_process_empty_batch(self):
        """Test handling of empty batch."""
        results = self.extractor.process_batch([])
        assert results == []


class TestKeywordTopicDatabase:
    """Test database operations for keyword and topic data."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_db = AsyncMock()
        self.database = KeywordTopicDatabase(self.mock_db)
    
    @pytest.mark.asyncio
    async def test_store_extraction_results(self):
        """Test storing extraction results."""
        sample_result = ExtractionResult(
            article_id="test_1",
            url="https://example.com/1",
            title="Test Article",
            keywords=[KeywordResult("test", 0.5, "tfidf")],
            topics=[TopicResult(0, "test_topic", ["word1", "word2"], 0.7)],
            dominant_topic=TopicResult(0, "test_topic", ["word1", "word2"], 0.7),
            extraction_method="tfidf_lda",
            processed_at=datetime.now(),
            processing_time=1.5
        )
        
        results = await self.database.store_extraction_results([sample_result])
        
        assert results["success_count"] == 1
        assert results["error_count"] == 0
        assert results["total_processed"] == 1
        self.mock_db.execute_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_articles_by_topic(self):
        """Test retrieving articles by topic."""
        self.mock_db.execute_query.return_value = [
            ("id1", "url1", "title1", "source1", datetime.now(), '[]', '[]', '{}', "method", datetime.now())
        ]
        
        articles = await self.database.get_articles_by_topic("test_topic")
        
        assert len(articles) == 1
        assert articles[0]["id"] == "id1"
        self.mock_db.execute_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_topic_statistics(self):
        """Test retrieving topic statistics."""
        self.mock_db.execute_query.return_value = [
            ("topic1", 10, 0.8, datetime.now(), datetime.now()),
            ("topic2", 5, 0.6, datetime.now(), datetime.now())
        ]
        
        stats = await self.database.get_topic_statistics(days=30)
        
        assert len(stats) == 2
        assert stats[0]["topic_name"] == "topic1"
        assert stats[0]["article_count"] == 10
        self.mock_db.execute_query.assert_called_once()


class TestTopicAPIRoutes:
    """Test API routes for topic functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock the database dependency
        async def mock_get_db():
            mock_db = AsyncMock()
            mock_db.get_articles_by_topic.return_value = [
                {
                    "id": "test_1",
                    "title": "Test Article",
                    "url": "https://example.com/1",
                    "source": "Test Source",
                    "published_date": "2025-08-15T00:00:00",
                    "keywords": [],
                    "topics": [],
                    "dominant_topic": {"topic_name": "test_topic", "probability": 0.8}
                }
            ]
            mock_db.get_topic_statistics.return_value = [
                {
                    "topic_name": "test_topic",
                    "article_count": 10,
                    "avg_probability": 0.8,
                    "percentage": 50.0
                }
            ]
            mock_db.get_keyword_statistics.return_value = [
                {
                    "keyword": "test_keyword",
                    "frequency": 15,
                    "avg_score": 0.7
                }
            ]
            mock_db.search_articles_by_content_and_topics.return_value = {
                "articles": [],
                "total_count": 0,
                "returned_count": 0,
                "has_more": False,
                "search_params": {}
            }
            return mock_db
        
        # Override the dependency
        from src.api.routes.topic_routes import get_keyword_topic_db
        app.dependency_overrides[get_keyword_topic_db] = mock_get_db
    
    def teardown_method(self):
        """Clean up after tests."""
        app.dependency_overrides.clear()
    
    def test_get_articles_by_topic_endpoint(self):
        """Test the get articles by topic endpoint."""
        response = client.get("/topics/articles?topic=test_topic&min_probability=0.2")
        assert response.status_code == 200
        
        data = response.json()
        assert "articles" in data
        assert "total_count" in data
        assert "search_params" in data
        assert data["search_params"]["topic"] == "test_topic"
    
    def test_get_topic_statistics_endpoint(self):
        """Test the topic statistics endpoint."""
        response = client.get("/topics/statistics?days=30")
        assert response.status_code == 200
        
        data = response.json()
        assert "topics" in data
        assert "analysis_period" in data
        assert "total_topics" in data
        assert data["analysis_period"]["days"] == 30
    
    def test_get_keyword_statistics_endpoint(self):
        """Test the keyword statistics endpoint."""
        response = client.get("/topics/keywords/statistics?days=7&min_frequency=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "keywords" in data
        assert "analysis_period" in data
        assert "min_frequency" in data
        assert data["min_frequency"] == 5
    
    def test_advanced_search_endpoint(self):
        """Test the advanced search endpoint."""
        response = client.get("/topics/search?search_term=test&topic=ai&keyword=machine")
        assert response.status_code == 200
        
        data = response.json()
        assert "articles" in data
        assert "total_count" in data
        assert "search_params" in data
    
    def test_advanced_search_no_params(self):
        """Test advanced search with no parameters (should fail)."""
        response = client.get("/topics/search")
        assert response.status_code == 400
    
    def test_trending_topics_endpoint(self):
        """Test the trending topics endpoint."""
        response = client.get("/topics/trending?days=7&min_articles=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "trending_topics" in data
        assert "analysis_period" in data
        assert "criteria" in data


class TestKeywordTopicIntegration:
    """Integration tests for complete keyword topic pipeline."""
    
    def test_configuration_loading(self):
        """Test loading configuration from file."""
        # Test with default config
        extractor = create_keyword_extractor()
        assert extractor is not None
        assert hasattr(extractor, 'config')
    
    def test_end_to_end_processing(self):
        """Test complete processing pipeline."""
        extractor = create_keyword_extractor()
        
        sample_articles = [
            {
                "id": "integration_test",
                "title": "Machine Learning in Healthcare Technology",
                "content": "Artificial intelligence and machine learning technologies are revolutionizing healthcare diagnostics and treatment.",
                "url": "https://example.com/test"
            }
        ]
        
        results = extractor.process_batch(sample_articles)
        
        assert len(results) == 1
        result = results[0]
        assert result.article_id == "integration_test"
        assert len(result.keywords) > 0  # Should extract some keywords
    
    def test_performance_metrics(self):
        """Test performance and timing metrics."""
        extractor = create_keyword_extractor()
        
        sample_article = {
            "id": "perf_test",
            "title": "Performance Test Article",
            "content": "This is a test article for measuring processing performance metrics.",
            "url": "https://example.com/perf"
        }
        
        start_time = datetime.now()
        result = extractor.extract_keywords_and_topics(sample_article)
        end_time = datetime.now()
        
        # Verify processing time is reasonable
        assert result.processing_time > 0
        assert result.processing_time < 10  # Should complete within 10 seconds
        
        # Verify timing consistency
        total_time = (end_time - start_time).total_seconds()
        assert abs(result.processing_time - total_time) < 1.0  # Within 1 second tolerance


class TestSimpleKeywordExtractor:
    """Test simple keyword extractor functionality (fallback for missing dependencies)."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = SimpleKeywordExtractor()
    
    def test_simple_extractor_initialization(self):
        """Test simple extractor initialization."""
        assert self.extractor.config is not None
        assert 'keywords_per_article' in self.extractor.config
        assert self.extractor.preprocessor is not None
    
    def test_simple_keyword_extraction(self):
        """Test basic keyword extraction without ML dependencies."""
        article = {
            "id": "test_simple",
            "title": "Artificial Intelligence in Healthcare",
            "content": "Machine learning algorithms are revolutionizing medical diagnosis and treatment.",
            "url": "https://example.com/simple"
        }
        
        result = self.extractor.extract_keywords_and_topics(article)
        
        assert result.article_id == "test_simple"
        assert result.title == "Artificial Intelligence in Healthcare"
        assert len(result.keywords) > 0
        assert all(kw.method == 'simple' for kw in result.keywords)
        assert result.extraction_method == 'simple'
        assert result.processing_time > 0
    
    def test_simple_extractor_batch_processing(self):
        """Test batch processing with simple extractor."""
        articles = [
            {
                "id": "batch_1",
                "title": "Technology News",
                "content": "Latest developments in artificial intelligence and machine learning.",
                "url": "https://example.com/1"
            },
            {
                "id": "batch_2", 
                "title": "Climate Science Update",
                "content": "New research on climate change and environmental protection.",
                "url": "https://example.com/2"
            }
        ]
        
        results = self.extractor.process_batch(articles)
        
        assert len(results) == 2
        assert all(r.extraction_method == 'simple' for r in results)
        assert all(len(r.keywords) > 0 for r in results)
    
    def test_simple_extractor_empty_content(self):
        """Test simple extractor with empty content."""
        article = {
            "id": "empty_test",
            "title": "",
            "content": "",
            "url": "https://example.com/empty"
        }
        
        result = self.extractor.extract_keywords_and_topics(article)
        
        assert result.article_id == "empty_test"
        assert len(result.keywords) == 0
        assert result.extraction_method == 'simple'


class TestCreateKeywordExtractorFallback:
    """Test factory function with dependency fallback."""
    
    @patch('src.nlp.keyword_topic_extractor.KeywordTopicExtractor')
    def test_factory_with_ml_dependencies(self, mock_kw_extractor):
        """Test factory function when ML dependencies are available."""
        # Mock successful import of sklearn
        with patch('builtins.__import__') as mock_import:
            mock_import.return_value = MagicMock()
            
            extractor = create_keyword_extractor()
            
            # Should attempt to create KeywordTopicExtractor
            mock_kw_extractor.assert_called_once()
    
    def test_factory_fallback_to_simple(self):
        """Test factory function fallback when ML dependencies missing."""
        # Mock ImportError for sklearn
        with patch('builtins.__import__', side_effect=ImportError("No module named 'sklearn'")):
            extractor = create_keyword_extractor()
            
            # Should return SimpleKeywordExtractor
            assert isinstance(extractor, SimpleKeywordExtractor)
    
    def test_factory_with_config_path(self):
        """Test factory function with config path."""
        # Create a temporary config file
        import tempfile
        import os
        
        config_data = {
            "keywords_per_article": 15,
            "min_keyword_length": 4
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Mock ImportError to force simple extractor
            with patch('builtins.__import__', side_effect=ImportError("No module named 'sklearn'")):
                extractor = create_keyword_extractor(config_path)
                
                assert isinstance(extractor, SimpleKeywordExtractor)
                assert extractor.config['keywords_per_article'] == 15
        finally:
            os.unlink(config_path)


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
