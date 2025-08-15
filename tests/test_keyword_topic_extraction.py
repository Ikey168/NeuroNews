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
        text = "The quick brown fox jumps over the lazy dog."
        keywords = self.preprocessor.extract_keywords_pos(text, max_keywords=5)
        
        assert len(keywords) <= 5
        assert "quick" in keywords or "brown" in keywords or "fox" in keywords


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
            assert keyword.method == 'frequency'  # Single doc uses frequency fallback
            assert keyword.score > 0
    
    def test_extract_keywords_multiple_texts(self):
        """Test keyword extraction from multiple texts."""
        texts = [
            "Artificial intelligence and machine learning are transforming technology.",
            "Climate change poses significant environmental challenges globally.",
            "Healthcare innovations improve patient outcomes and medical research."
        ]
        results = self.extractor.extract_keywords(texts, top_k=3)
        
        assert len(results) == 3
        for result_set in results:
            assert len(result_set) <= 3
            for keyword in result_set:
                assert isinstance(keyword, KeywordResult)
                # Multiple documents should use tfidf method
                assert keyword.method == 'tfidf'
                assert keyword.score > 0
    
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
            "Machine learning and artificial intelligence research advances in neural networks and deep learning algorithms for computer vision and natural language processing applications",
            "Climate change and environmental sustainability issues require global cooperation and green technology solutions including renewable energy sources and carbon reduction strategies",
            "Healthcare technology and medical innovation progress through genomic sequencing personalized medicine treatments and telemedicine platform development for patient care",
            "Artificial intelligence transforms healthcare diagnostics with automated medical imaging analysis and predictive analytics for disease prevention and early detection systems",
            "Environmental protection and climate action policies focus on sustainable development goals including biodiversity conservation and ecosystem restoration initiatives worldwide",
            "Financial technology fintech innovations include blockchain cryptocurrency digital payments mobile banking and algorithmic trading systems for modern finance",
            "Space exploration missions investigate mars colonization satellite technology rocket propulsion systems and astronomical research for understanding the universe and planetary science"
        ]
        
        topic_info = self.modeler.fit_topics(texts)
        
        assert topic_info["model_fitted"] is True
        assert len(topic_info["topics"]) >= 1  # May have fewer topics than requested if insufficient data
        assert "perplexity" in topic_info
        
        for topic in topic_info["topics"]:
            assert "topic_id" in topic
            assert "topic_name" in topic
            assert "topic_words" in topic


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


class TestCreateKeywordExtractorFallback:
    """Test factory function with dependency fallback."""
    
    def test_factory_fallback_to_simple(self):
        """Test factory function fallback when ML dependencies missing."""
        # Mock ImportError for sklearn
        with patch('builtins.__import__', side_effect=ImportError("No module named 'sklearn'")):
            extractor = create_keyword_extractor()
            
            # Should return SimpleKeywordExtractor
            assert isinstance(extractor, SimpleKeywordExtractor)


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
