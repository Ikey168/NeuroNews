"""
Basic NLP tests focusing on VADER sentiment analysis
"""

import pytest
from src.nlp import create_analyzer

# Test fixtures with labeled data
LABELED_TEXTS = [
    {
        "text": "The company's revenue grew by 50% this quarter, exceeding all expectations.",
        "expected_sentiment": "positive"
    },
    {
        "text": "The stock market crashed today, wiping out billions in value.",
        "expected_sentiment": "negative"
    },
    {
        "text": "The company announced its quarterly earnings report today.",
        "expected_sentiment": "neutral"
    }
]

@pytest.fixture
def vader_analyzer():
    """Create a VADER sentiment analyzer instance."""
    return create_analyzer("vader")

def test_vader_accuracy(vader_analyzer):
    """Test VADER sentiment analyzer accuracy on labeled data."""
    correct = 0
    total = len(LABELED_TEXTS)
    
    for item in LABELED_TEXTS:
        result = vader_analyzer.analyze_sentiment(item["text"])
        if result["sentiment"] == item["expected_sentiment"]:
            correct += 1
            
    accuracy = correct / total
    print(f"VADER Accuracy: {accuracy:.2%}")
    assert accuracy >= 0.7, f"Accuracy {accuracy:.2%} below threshold of 70%"

def test_preprocessing():
    """Test text preprocessing functionality."""
    analyzer = create_analyzer("vader")
    
    # Test whitespace handling
    assert analyzer.preprocess_text("  test  text  ") == "test text"
    
    # Test empty input
    with pytest.raises(ValueError):
        analyzer.preprocess_text("")
    
    # Test non-string input
    with pytest.raises(ValueError):
        analyzer.preprocess_text(123)

def test_sentiment_scores():
    """Test sentiment scores are properly returned."""
    analyzer = create_analyzer("vader")
    
    result = analyzer.analyze_sentiment(
        "This is a test.",
        return_all_scores=True
    )
    
    assert "all_scores" in result
    assert isinstance(result["all_scores"], dict)
    assert result["confidence"] >= 0
    assert result["confidence"] <= 1
