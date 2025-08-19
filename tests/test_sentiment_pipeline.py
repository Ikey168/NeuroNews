"""
Tests for sentiment analysis pipeline functionality (Issue #28).
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.sentiment_routes import get_db, router
from src.nlp.sentiment_analysis import create_analyzer

# Create test app
app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestSentimentAnalysisPipeline:
    """Test suite for sentiment analysis pipeline (Issue #28)."""

    def test_sentiment_analyzer_initialization(self):
        """Test that sentiment analyzer initializes correctly."""
        analyzer = create_analyzer()
        assert analyzer is not None
        assert analyzer.model_name == "distilbert-base-uncased-finetuned-sst-2-english"

    def test_single_text_analysis(self):
        """Test sentiment analysis for single text."""
        analyzer = create_analyzer()

        # Test positive sentiment
        positive_result = analyzer.analyze(
            "This is absolutely wonderful news! Great job!"
        )
        assert positive_result["label"] == "POSITIVE"
        assert isinstance(positive_result["score"], float)
        assert 0 <= positive_result["score"] <= 1

        # Test negative sentiment
        negative_result = analyzer.analyze("This is terrible and disappointing news.")
        assert negative_result["label"] == "NEGATIVE"
        assert isinstance(negative_result["score"], float)

        # Test empty text
        empty_result = analyzer.analyze("")
        assert empty_result["label"] == "ERROR"
        assert empty_result["score"] == 0.0

    def test_batch_text_analysis(self):
        """Test sentiment analysis for multiple texts."""
        analyzer = create_analyzer()

        texts = [
            "Amazing breakthrough in technology!",
            "Concerning developments in the market",
            "Standard quarterly report released",
            "",  # Empty text should return ERROR
        ]

        results = analyzer.analyze_batch(texts)
        assert len(results) == len(texts)

        # Check that all results have required fields
        for result in results:
            assert "label" in result
            assert "score" in result
            assert "text" in result
            assert result["label"] in ["POSITIVE", "NEGATIVE", "NEUTRAL", "ERROR"]

    def test_sentiment_trends_endpoint(self):
        """Test the sentiment trends API endpoint."""

        # Mock the get_db dependency completely
        async def mock_get_db():
            mock_db = AsyncMock()
            mock_db.execute_query.side_effect = [
                # Trends query results
                [
                    (datetime.now() - timedelta(days=1), "POSITIVE", 5, 0.8, 0.6, 0.9),
                    (datetime.now() - timedelta(days=1), "NEGATIVE", 3, 0.3, 0.1, 0.4),
                ],
                # Overall stats query results
                [("POSITIVE", 5, 0.8, 62.5), ("NEGATIVE", 3, 0.3, 37.5)],
                # Count query results
                [(8,)],
            ]
            yield mock_db

        # Override the dependency
        app.dependency_overrides[get_db] = mock_get_db

        try:
            # Test endpoint
            response = client.get("/news_sentiment?topic=Technology")
            print(f"Response status: {response.status_code}")
            print(f"Response content: {response.content}")
            if response.status_code != 200:
                print(f"Response text: {response.text}")
            assert response.status_code == 200

            data = response.json()
            assert "sentiment_trends" in data
            assert "overall_sentiment" in data
            assert "article_count" in data
            assert "topic_filter" in data
            assert data["topic_filter"] == "Technology"
            assert data["article_count"] == 8
        finally:
            # Clean up
            app.dependency_overrides.clear()

    def test_sentiment_summary_endpoint(self):
        """Test the sentiment summary API endpoint."""

        # Mock the get_db dependency
        async def mock_get_db():
            mock_db = AsyncMock()
            mock_db.execute_query.return_value = [
                ("POSITIVE", 10, 0.8, 0.1),
                ("NEGATIVE", 5, 0.3, 0.05),
                ("NEUTRAL", 3, 0.5, 0.02),
            ]
            yield mock_db

        # Override the dependency
        app.dependency_overrides[get_db] = mock_get_db

        try:
            response = client.get("/news_sentiment/summary?topic=AI&days=7")
            assert response.status_code == 200

            data = response.json()
            assert "summary" in data
            assert "total_articles" in data
            assert "days_analyzed" in data
            assert "topic_filter" in data
            assert data["topic_filter"] == "AI"
            assert data["days_analyzed"] == 7
        finally:
            app.dependency_overrides.clear()

    def test_topic_sentiment_endpoint(self):
        """Test the topic sentiment analysis endpoint."""

        # Mock the get_db dependency
        async def mock_get_db():
            mock_db = AsyncMock()
            mock_db.execute_query.return_value = [
                ("TECH", "POSITIVE", 8, 0.8),
                ("TECH", "NEGATIVE", 2, 0.3),
                ("MARKET", "NEGATIVE", 6, 0.4),
                ("MARKET", "POSITIVE", 4, 0.7),
            ]
            yield mock_db

        # Override the dependency
        app.dependency_overrides[get_db] = mock_get_db

        try:
            response = client.get("/news_sentiment/topics?days=7&min_articles=5")
            assert response.status_code == 200

            data = response.json()
            assert isinstance(data, list)
            if data:  # If there are results
                topic_data = data[0]
                assert "topic" in topic_data
                assert "total_articles" in topic_data
                assert "sentiments" in topic_data
        finally:
            app.dependency_overrides.clear()


class TestSentimentPipelineIntegration:
    """Integration tests for complete sentiment pipeline."""

    def test_pipeline_configuration_loading(self):
        """Test loading pipeline configuration."""
        try:
            with open("config/sentiment_pipeline_settings.json", "r") as f:
                config = json.load(f)

            assert "sentiment_analysis" in config
            assert "providers" in config["sentiment_analysis"]
            assert "pipeline_settings" in config["sentiment_analysis"]
            assert "demo_settings" in config

            # Check required provider configs
            providers = config["sentiment_analysis"]["providers"]
            assert "huggingface" in providers
            assert "aws_comprehend" in providers
            assert "rule_based" in providers

        except FileNotFoundError:
            pytest.skip("Configuration file not found")

    def test_sentiment_trend_analysis(self):
        """Test trend analysis functionality."""
        # This would test the trend analysis logic
        # In a real scenario, we'd test with sample data
        analyzer = create_analyzer()

        sample_texts = [
            "Excellent quarterly results!",
            "Market volatility concerns investors",
            "Standard infrastructure update",
            "Revolutionary breakthrough achieved!",
            "Economic uncertainty persists",
        ]

        results = analyzer.analyze_batch(sample_texts)

        # Count sentiments
        sentiment_counts = {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0}
        for result in results:
            if result["label"] != "ERROR":
                sentiment_counts[result["label"]] += 1

        # Should have a mix of sentiments
        assert sum(sentiment_counts.values()) == len(sample_texts)
        assert sentiment_counts["POSITIVE"] > 0
        assert sentiment_counts["NEGATIVE"] > 0

    def test_error_handling(self):
        """Test error handling in sentiment analysis."""
        analyzer = create_analyzer()

        # Test various edge cases
        edge_cases = [
            "",  # Empty string
            "   ",  # Whitespace only
            None,  # None value (if passed through)
            "a" * 10000,  # Very long text
        ]

        for case in edge_cases:
            try:
                if case is None:
                    continue  # Skip None case as it would cause TypeError
                result = analyzer.analyze(case)
                assert "label" in result
                assert "score" in result
            except (ValueError, TypeError):
                # Expected for invalid inputs
                pass


class TestSentimentPipelinePerformance:
    """Performance tests for sentiment analysis pipeline."""

    def test_batch_processing_performance(self):
        """Test performance of batch processing."""
        analyzer = create_analyzer()

        # Create batch of sample texts
        sample_text = "This is a sample news article for performance testing."
        batch_sizes = [10, 50, 100]

        for batch_size in batch_sizes:
            texts = [sample_text] * batch_size

            start_time = datetime.now()
            results = analyzer.analyze_batch(texts)
            end_time = datetime.now()

            processing_time = (end_time - start_time).total_seconds()

            # Basic performance assertions
            assert len(results) == batch_size
            assert processing_time < 60  # Should complete within 60 seconds

            # Log performance for monitoring
            print(f"Batch size {batch_size}: {processing_time:.2f} seconds")


# Integration test for demo script
class TestSentimentDemo:
    """Test the sentiment analysis demo functionality."""

    @pytest.mark.asyncio
    async def test_demo_initialization(self):
        """Test demo script initialization."""
        # Import demo classes
        try:
            from demo_sentiment_pipeline import SentimentPipelineDemo

            demo = SentimentPipelineDemo()
            initialized = await demo.initialize()

            assert initialized is True
            assert demo.analyzer is not None

        except ImportError:
            pytest.skip("Demo script not available")

    def test_demo_sample_data(self):
        """Test demo sample data structure."""
        try:
            from demo_sentiment_pipeline import SAMPLE_ARTICLES

            assert len(SAMPLE_ARTICLES) > 0

            for article in SAMPLE_ARTICLES:
                assert "id" in article
                assert "title" in article
                assert "content" in article
                assert "topic" in article
                assert "source" in article

        except ImportError:
            pytest.skip("Demo script not available")


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
