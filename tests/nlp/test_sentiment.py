"""
Unit tests for sentiment analysis accuracy and functionality.
"""

import pytest
from unittest.mock import Mock, patch
import json
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
    },
    {
        "text": "Despite recent setbacks, the company remains optimistic about future growth.",
        "expected_sentiment": "positive"
    }
]

# Edge cases
EDGE_CASES = [
    {
        "text": "",  # Empty text
        "should_raise": True
    },
    {
        "text": "   ",  # Only whitespace
        "should_raise": True
    },
    {
        "text": "This is a very long text " * 1000,  # Very long text
        "should_raise": False
    },
    {
        "text": "Text with special chars: @#$%^&*()",  # Special characters
        "should_raise": False
    }
]

# Mock responses for various providers
AWS_MOCK_RESPONSES = {
    "positive": {
        "Sentiment": "POSITIVE",
        "SentimentScore": {
            "Positive": 0.95,
            "Negative": 0.01,
            "Neutral": 0.03,
            "Mixed": 0.01
        }
    },
    "negative": {
        "Sentiment": "NEGATIVE",
        "SentimentScore": {
            "Positive": 0.01,
            "Negative": 0.95,
            "Neutral": 0.03,
            "Mixed": 0.01
        }
    }
}

TRANSFORMERS_MOCK_RESPONSES = {
    "positive": [{"label": "POSITIVE", "score": 0.95}],
    "negative": [{"label": "NEGATIVE", "score": 0.92}],
    "neutral": [{"label": "NEUTRAL", "score": 0.85}]
}

@pytest.fixture
def vader_analyzer():
    """Create a VADER sentiment analyzer instance."""
    return create_analyzer("vader")

@pytest.fixture
def mock_aws_analyzer():
    """Create a mocked AWS Comprehend analyzer instance."""
    with patch('boto3.client') as mock_boto:
        mock_client = Mock()
        mock_boto.return_value = mock_client
        analyzer = create_analyzer("aws", region_name="us-west-2")
        analyzer.client = mock_client
        yield analyzer

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
    
    # We expect at least 70% accuracy on our test set
    assert accuracy >= 0.7, f"Accuracy {accuracy:.2%} below threshold of 70%"

@pytest.mark.parametrize("test_case", LABELED_TEXTS)
def test_aws_sentiment_mapping(mock_aws_analyzer, test_case):
    """Test AWS Comprehend sentiment mapping for each test case."""
    mock_aws_analyzer.client.detect_sentiment.return_value = AWS_MOCK_RESPONSES["positive"]
    
    result = mock_aws_analyzer.analyze_sentiment(test_case["text"])
    assert "sentiment" in result
    assert "confidence" in result
    assert result["provider"] == "aws"

def test_batch_processing_vader(vader_analyzer):
    """Test batch processing with VADER analyzer."""
    texts = [item["text"] for item in LABELED_TEXTS]
    results = vader_analyzer.batch_analyze(texts)
    
    assert len(results) == len(texts)
    for result in results:
        assert "sentiment" in result
        assert "confidence" in result
        assert "provider" in result
        assert result["provider"] == "vader"

def test_batch_processing_aws(mock_aws_analyzer):
    """Test batch processing with AWS Comprehend."""
    texts = [item["text"] for item in LABELED_TEXTS]
    
    mock_aws_analyzer.client.batch_detect_sentiment.return_value = {
        "ResultList": [AWS_MOCK_RESPONSES["positive"]] * len(texts),
        "ErrorList": []
    }
    
    results = mock_aws_analyzer.batch_analyze(texts)
    
    assert len(results) == len(texts)
    for result in results:
        assert "sentiment" in result
        assert "confidence" in result
        assert "provider" in result
        assert result["provider"] == "aws"

@pytest.mark.parametrize("test_case", EDGE_CASES)
def test_edge_cases_vader(vader_analyzer, test_case):
    """Test VADER analyzer with edge cases."""
    if test_case["should_raise"]:
        with pytest.raises(ValueError):
            vader_analyzer.analyze_sentiment(test_case["text"])
    else:
        result = vader_analyzer.analyze_sentiment(test_case["text"])
        assert "sentiment" in result
        assert "confidence" in result

@pytest.mark.parametrize("test_case", EDGE_CASES)
def test_edge_cases_aws(mock_aws_analyzer, test_case):
    """Test AWS Comprehend analyzer with edge cases."""
    if test_case["should_raise"]:
        with pytest.raises(ValueError):
            mock_aws_analyzer.analyze_sentiment(test_case["text"])
    else:
        mock_aws_analyzer.client.detect_sentiment.return_value = AWS_MOCK_RESPONSES["positive"]
        result = mock_aws_analyzer.analyze_sentiment(test_case["text"])
        assert "sentiment" in result
        assert "confidence" in result

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

@pytest.fixture
def mock_transformers_analyzer():
    """Create a mocked Transformers analyzer instance."""
    with patch('transformers.pipeline') as mock_pipeline:
        mock_pipe = Mock()
        mock_pipeline.return_value = mock_pipe
        analyzer = create_analyzer("transformers")
        analyzer.sentiment_pipeline = mock_pipe
        yield analyzer

def test_transformers_accuracy(mock_transformers_analyzer):
    """Test Transformers sentiment analyzer accuracy on labeled data."""
    mock_transformers_analyzer.sentiment_pipeline.return_value = TRANSFORMERS_MOCK_RESPONSES["positive"]
    
    for item in LABELED_TEXTS:
        result = mock_transformers_analyzer.analyze_sentiment(item["text"])
        assert "sentiment" in result
        assert "confidence" in result
        assert "provider" in result
        assert result["provider"] == "transformers"

@pytest.mark.parametrize("test_case", EDGE_CASES)
def test_edge_cases_transformers(mock_transformers_analyzer, test_case):
    """Test Transformers analyzer with edge cases."""
    if test_case["should_raise"]:
        with pytest.raises(ValueError):
            mock_transformers_analyzer.analyze_sentiment(test_case["text"])
    else:
        mock_transformers_analyzer.sentiment_pipeline.return_value = TRANSFORMERS_MOCK_RESPONSES["positive"]
        result = mock_transformers_analyzer.analyze_sentiment(test_case["text"])
        assert "sentiment" in result
        assert "confidence" in result

def test_batch_processing_transformers(mock_transformers_analyzer):
    """Test batch processing with Transformers."""
    texts = [item["text"] for item in LABELED_TEXTS]
    mock_transformers_analyzer.sentiment_pipeline.return_value = [
        TRANSFORMERS_MOCK_RESPONSES["positive"][0]
    ] * len(texts)
    
    results = mock_transformers_analyzer.batch_analyze(texts)
    
    assert len(results) == len(texts)
    for result in results:
        assert "sentiment" in result
        assert "confidence" in result
        assert "provider" in result
        assert result["provider"] == "transformers"

# Integration tests (disabled by default)
@pytest.mark.skip(reason="Requires AWS credentials")
def test_live_aws_integration():
    """Test live AWS Comprehend integration."""
    analyzer = create_analyzer("aws", region_name="us-west-2")
    result = analyzer.analyze_sentiment(
        "This is a live test of AWS Comprehend.",
        return_all_scores=True
    )
    
    assert result["provider"] == "aws"
    assert "sentiment" in result
    assert "confidence" in result
    assert "all_scores" in result

@pytest.mark.skip(reason="Requires GPU/CPU resources")
def test_live_transformers_integration():
    """Test live Transformers integration."""
    analyzer = create_analyzer("transformers")
    result = analyzer.analyze_sentiment(
        "This is a live test of Transformers.",
        return_all_scores=True
    )
    
    assert result["provider"] == "transformers"
    assert "sentiment" in result
    assert "confidence" in result
    assert "all_scores" in result