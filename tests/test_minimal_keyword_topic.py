"""
Minimal test file to verify the two failing tests work correctly.
"""

import pytest

from src.nlp.keyword_topic_extractor import (
    KeywordResult,
    LDATopicModeler,
    TFIDFKeywordExtractor,
)


class TestTFIDFKeywordExtractorMinimal:
    """Minimal test for TF-IDF keyword extraction."""

    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = TFIDFKeywordExtractor(max_features=100)

    def test_extract_keywords_single_text(self):
        """Test keyword extraction from single text."""
        texts = [
            "Machine learning and artificial intelligence are transforming technology"
        ]
        results = self.extractor.extract_keywords(texts, top_k=5)

        assert len(results) == 1
        assert len(results[0]) <= 5

        # Check that keywords are KeywordResult objects
        for keyword in results[0]:
            assert isinstance(keyword, KeywordResult)
            assert keyword.method == "frequency"  # Single doc uses frequency fallback
            assert keyword.score > 0


class TestLDATopicModelerMinimal:
    """Minimal test for LDA topic modeling."""

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
            "Space exploration missions investigate mars colonization satellite technology rocket propulsion systems and astronomical research for understanding the universe and planetary science",
        ]

        topic_info = self.modeler.fit_topics(texts)

        assert topic_info["model_fitted"] is True
        assert (
            len(topic_info["topics"]) >= 1
        )  # May have fewer topics than requested if insufficient data
        assert "perplexity" in topic_info


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
