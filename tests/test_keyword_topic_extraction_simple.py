"""Simple test to verify basic functionality works."""

import pytest
from src.nlp.keyword_topic_extractor import (
    create_keyword_extractor,
    SimpleKeywordExtractor,
)


def test_factory_creates_extractor():
    """Test that factory function creates some kind of extractor."""
    extractor = create_keyword_extractor()
    assert extractor is not None


def test_simple_extractor():
    """Test SimpleKeywordExtractor works."""
    extractor = SimpleKeywordExtractor()

    article = {
        "id": "test",
        "title": "Test Article",
        "content": "This is test content about artificial intelligence.",
        "url": "https://example.com",
    }

    result = extractor.extract_keywords_and_topics(article)
    assert result.article_id == "test"
    assert len(result.keywords) > 0
    assert result.extraction_method == "simple"


if __name__ == "__main__":
    test_factory_creates_extractor()
    test_simple_extractor()
    print("All tests passed!")
