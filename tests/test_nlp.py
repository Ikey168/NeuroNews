import pytest
from src.nlp.sentiment_analysis import (
    BaseSentimentAnalyzer,
    VaderSentimentAnalyzer,
    create_analyzer
)

class TestBaseSentimentAnalyzer:
    def setup_method(self):
        self.analyzer = BaseSentimentAnalyzer()

    def test_preprocess_text(self):
        # Test basic preprocessing
        text = "  This is  a  test   text  "
        result = self.analyzer.preprocess_text(text)
        assert result == "This is a test text"

    def test_preprocess_empty_text(self):
        # Test empty text preprocessing
        text = "   "
        result = self.analyzer.preprocess_text(text)
        assert result == ""

    def test_preprocess_invalid_input(self):
        # Test invalid input
        with pytest.raises(ValueError):
            self.analyzer.preprocess_text(None)
        with pytest.raises(ValueError):
            self.analyzer.preprocess_text(123)

class TestVaderSentimentAnalyzer:
    def setup_method(self):
        self.analyzer = VaderSentimentAnalyzer()

    def test_analyze_positive_sentiment(self):
        text = "This is excellent! I love it."
        result = self.analyzer.analyze_sentiment(text)
        
        assert result["sentiment"] == "positive"
        assert result["confidence"] > 0
        assert result["provider"] == "vader"
        assert result["text"] == text

    def test_analyze_negative_sentiment(self):
        text = "This is terrible! I hate it."
        result = self.analyzer.analyze_sentiment(text)
        
        assert result["sentiment"] == "negative"
        assert result["confidence"] > 0
        assert result["provider"] == "vader"
        assert result["text"] == text

    def test_analyze_neutral_sentiment(self):
        text = "This is a neutral statement."
        result = self.analyzer.analyze_sentiment(text)
        
        assert result["sentiment"] == "neutral"
        assert "confidence" in result
        assert result["provider"] == "vader"
        assert result["text"] == text

    def test_analyze_with_all_scores(self):
        text = "This is a test."
        result = self.analyzer.analyze_sentiment(text, return_all_scores=True)
        
        assert "all_scores" in result
        assert all(score in result["all_scores"] for score in ["pos", "neg", "neu", "compound"])

    def test_batch_analyze(self):
        texts = [
            "This is great!",
            "This is terrible!",
            "This is neutral."
        ]
        results = self.analyzer.batch_analyze(texts)
        
        assert len(results) == 3
        assert all("sentiment" in result for result in results)
        assert all("confidence" in result for result in results)
        assert all(result["provider"] == "vader" for result in results)

    def test_empty_text(self):
        with pytest.raises(ValueError):
            self.analyzer.analyze_sentiment("")

    def test_invalid_input(self):
        with pytest.raises(ValueError):
            self.analyzer.analyze_sentiment(None)

class TestAnalyzerFactory:
    def test_create_vader_analyzer(self):
        analyzer = create_analyzer("vader")
        assert isinstance(analyzer, VaderSentimentAnalyzer)

    def test_create_invalid_analyzer(self):
        with pytest.raises(ValueError):
            create_analyzer("invalid_provider")

def test_end_to_end_sentiment_analysis():
    # Test complete sentiment analysis pipeline
    analyzer = create_analyzer("vader")
    text = "The product exceeded all expectations. Highly recommended!"
    
    result = analyzer.analyze_sentiment(text, return_all_scores=True)
    
    assert result["sentiment"] == "positive"
    assert result["confidence"] > 0.5
    assert "all_scores" in result
    assert all(score in result["all_scores"] for score in ["pos", "neg", "neu", "compound"])