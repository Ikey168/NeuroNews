"""
Comprehensive tests for AI-based fake news detection functionality.
Tests the FakeNewsDetector class and API endpoints.
"""

import pytest
import os
import sys
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.nlp.fake_news_detector import FakeNewsDetector, FakeNewsConfig
from fastapi.testclient import TestClient


class TestFakeNewsDetector:
    """Test suite for FakeNewsDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a FakeNewsDetector instance for testing."""
        return FakeNewsDetector(model_name="roberta-base")

    @pytest.fixture
    def sample_texts(self):
        """Sample texts for testing."""
        return [
            "The government announced new infrastructure spending plans.",
            "BREAKING: Scientists prove that essential oils cure cancer!",
            "Stock market shows steady growth this quarter.",
            "SHOCKING: Aliens control the weather using secret technology!",
        ]

    @pytest.fixture
    def sample_labels(self):
        """Sample labels corresponding to sample texts."""
        return [1, 0, 1, 0]  # 1 = real, 0 = fake

    def test_detector_initialization(self, detector):
        """Test FakeNewsDetector initialization."""
        assert detector.model_name == "roberta-base"
        assert isinstance(detector.config, FakeNewsConfig)
        assert detector.model is None  # Not loaded initially
        assert detector.tokenizer is None  # Not loaded initially

    def test_config_initialization(self):
        """Test FakeNewsConfig initialization."""
        config = FakeNewsConfig()
        assert config.model_name == "roberta-base"
        assert config.max_length == 512
        assert config.confidence_threshold == 0.6
        assert config.batch_size == 16
        assert config.num_epochs == 3
        assert config.learning_rate == 2e-5

    @patch("src.nlp.fake_news_detector.AutoTokenizer")
    @patch("src.nlp.fake_news_detector.AutoModelForSequenceClassification")
    def test_model_loading(self, mock_model, mock_tokenizer, detector):
        """Test model and tokenizer loading."""
        # Setup mocks
        mock_tokenizer.from_pretrained.return_value = Mock()
        mock_model.from_pretrained.return_value = Mock()

        # Load model
        detector._load_model()

        # Verify calls
        mock_tokenizer.from_pretrained.assert_called_once_with("roberta-base")
        mock_model.from_pretrained.assert_called_once_with("roberta-base", num_labels=2)

        assert detector.tokenizer is not None
        assert detector.model is not None

    def test_prepare_liar_dataset(self, detector):
        """Test LIAR dataset preparation."""
        texts, labels = detector.prepare_liar_dataset()

        assert isinstance(texts, list)
        assert isinstance(labels, list)
        assert len(texts) == len(labels)
        assert len(texts) > 0

        # Check that all labels are 0 or 1
        for label in labels:
            assert label in [0, 1]

        # Check that texts are strings
        for text in texts:
            assert isinstance(text, str)
            assert len(text) > 0

    def test_preprocess_text(self, detector):
        """Test text preprocessing."""
        # Test various inputs
        test_cases = [
            ("Normal text", "Normal text"),
            ("TEXT WITH CAPS", "text with caps"),
            ("Text   with    spaces", "Text with spaces"),
            ("Text\nwith\nnewlines", "Text with newlines"),
            ("", ""),
            ("  ", ""),
        ]

        for input_text, expected in test_cases:
            result = detector._preprocess_text(input_text)
            assert result == expected

    @patch("src.nlp.fake_news_detector.Trainer")
    @patch("src.nlp.fake_news_detector.TrainingArguments")
    def test_training(
        self, mock_training_args, mock_trainer, detector, sample_texts, sample_labels
    ):
        """Test model training."""
        # Setup mocks
        mock_trainer_instance = Mock()
        mock_trainer.return_value = mock_trainer_instance
        mock_trainer_instance.train.return_value = None
        mock_trainer_instance.evaluate.return_value = {
            "eval_loss": 0.3,
            "eval_accuracy": 0.85,
            "eval_f1": 0.82,
        }

        # Mock model and tokenizer
        detector.model = Mock()
        detector.tokenizer = Mock()
        detector.tokenizer.return_value = {
            "input_ids": [[1, 2, 3]],
            "attention_mask": [[1, 1, 1]],
        }

        # Train model
        with tempfile.TemporaryDirectory() as temp_dir:
            metrics = detector.train(
                texts=sample_texts,
                labels=sample_labels,
                num_epochs=1,
                batch_size=2,
                output_dir=temp_dir,
            )

        # Verify training was called
        mock_trainer_instance.train.assert_called_once()
        mock_trainer_instance.evaluate.assert_called_once()

        # Check metrics
        assert "accuracy" in metrics
        assert "f1_score" in metrics
        assert "loss" in metrics

    @patch("torch.no_grad")
    def test_predict_trustworthiness(self, mock_no_grad, detector):
        """Test trustworthiness prediction."""
        # Mock model and tokenizer
        detector.model = Mock()
        detector.tokenizer = Mock()

        # Mock tokenizer output
        detector.tokenizer.return_value = {
            "input_ids": Mock(),
            "attention_mask": Mock(),
        }

        # Mock model output
        mock_logits = Mock()
        mock_logits.cpu.return_value.numpy.return_value = [
            [0.2, 0.8]
        ]  # High confidence for "real"
        detector.model.return_value.logits = mock_logits

        # Test prediction
        result = detector.predict_trustworthiness("This is a test article.")

        # Verify result structure
        assert isinstance(result, dict)
        assert "trustworthiness_score" in result
        assert "classification" in result
        assert "confidence" in result
        assert "trust_level" in result

        # Verify values
        assert result["classification"] in ["real", "fake"]
        assert 0 <= result["trustworthiness_score"] <= 100
        assert 0 <= result["confidence"] <= 100
        assert result["trust_level"] in ["low", "medium", "high"]

    def test_classify_trust_level(self, detector):
        """Test trust level classification."""
        test_cases = [
            (95, "high"),
            (85, "high"),
            (75, "medium"),
            (65, "medium"),
            (45, "low"),
            (25, "low"),
        ]

        for score, expected_level in test_cases:
            result = detector._classify_trust_level(score)
            assert result == expected_level


class TestFakeNewsAPI:
    """Test suite for fake news detection API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        from src.api.app import app

        return TestClient(app)

    @pytest.fixture
    def mock_detector(self):
        """Mock FakeNewsDetector for API tests."""
        with patch("src.api.routes.veracity_routes.detector") as mock:
            mock.predict_trustworthiness.return_value = {
                "trustworthiness_score": 75.5,
                "classification": "real",
                "confidence": 80.2,
                "trust_level": "medium",
            }
            yield mock

    def test_news_veracity_endpoint(self, client, mock_detector):
        """Test /news_veracity endpoint."""
        response = client.get(
            "/api/veracity/news_veracity",
            params={"article_id": "test_001", "text": "This is a test news article."},
        )

        assert response.status_code == 200
        data = response.json()

        assert "article_id" in data
        assert "veracity_analysis" in data
        assert "status" in data
        assert "source" in data

        analysis = data["veracity_analysis"]
        assert "trustworthiness_score" in analysis
        assert "classification" in analysis
        assert "confidence" in analysis
        assert "trust_level" in analysis

    def test_news_veracity_missing_text(self, client):
        """Test /news_veracity endpoint with missing text."""
        response = client.get(
            "/api/veracity/news_veracity", params={"article_id": "test_001"}
        )

        assert response.status_code == 422  # Validation error

    def test_batch_veracity_endpoint(self, client, mock_detector):
        """Test /batch_veracity endpoint."""
        request_data = {
            "articles": [
                {"article_id": "test_001", "text": "First test article."},
                {"article_id": "test_002", "text": "Second test article."},
            ]
        }

        response = client.post("/api/veracity/batch_veracity", json=request_data)

        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert "total_processed" in data
        assert "status" in data

        assert len(data["results"]) == 2
        assert data["total_processed"] == 2

        for result in data["results"]:
            assert "article_id" in result
            assert "veracity_analysis" in result
            assert "status" in result

    def test_batch_veracity_empty_list(self, client):
        """Test /batch_veracity endpoint with empty article list."""
        response = client.post("/api/veracity/batch_veracity", json={"articles": []})

        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    @patch("src.api.routes.veracity_routes.get_redshift_connection")
    def test_veracity_stats_endpoint(self, mock_db, client):
        """Test /veracity_stats endpoint."""
        # Mock database response
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1250, 67.3, 823, 427)
        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_db.return_value = mock_connection

        response = client.get("/api/veracity/veracity_stats", params={"days": 30})

        assert response.status_code == 200
        data = response.json()

        assert "statistics" in data
        assert "status" in data

        stats = data["statistics"]
        assert "total_articles_analyzed" in stats
        assert "average_trustworthiness_score" in stats
        assert "real_articles_count" in stats
        assert "fake_articles_count" in stats

    def test_model_info_endpoint(self, client, mock_detector):
        """Test /model_info endpoint."""
        response = client.get("/api/veracity/model_info")

        assert response.status_code == 200
        data = response.json()

        assert "model_info" in data
        assert "status" in data

        model_info = data["model_info"]
        assert "model_name" in model_info
        assert "model_type" in model_info
        assert "task" in model_info
        assert "labels" in model_info


class TestIntegration:
    """Integration tests for the complete fake news detection system."""

    @pytest.fixture
    def detector(self):
        """Create a detector for integration testing."""
        return FakeNewsDetector(model_name="roberta-base")

    def test_end_to_end_workflow(self, detector):
        """Test complete workflow from text input to API response."""
        # Sample article
        article_text = "Scientists at a major university have developed a new renewable energy technology."

        # This would be a full integration test in a real environment
        # For now, we test the workflow structure

        # Step 1: Preprocess text
        processed_text = detector._preprocess_text(article_text)
        assert isinstance(processed_text, str)

        # Step 2: Would call predict_trustworthiness in real scenario
        # Step 3: Would store results in Redshift
        # Step 4: Would return API response

        # For now, just verify the workflow structure exists
        assert hasattr(detector, "predict_trustworthiness")
        assert hasattr(detector, "_preprocess_text")
        assert hasattr(detector, "train")

    def test_performance_requirements(self, detector):
        """Test performance requirements for fake news detection."""
        # Test response time for single prediction
        import time

        start_time = time.time()

        # Mock a prediction (would be real in production)
        article = "This is a test article for performance testing."
        processed = detector._preprocess_text(article)

        end_time = time.time()
        response_time = end_time - start_time

        # Preprocessing should be very fast
        assert response_time < 1.0  # Less than 1 second

        # Test batch processing capability
        batch_articles = ["Article " + str(i) for i in range(10)]
        start_time = time.time()

        for article in batch_articles:
            detector._preprocess_text(article)

        end_time = time.time()
        batch_time = end_time - start_time

        # Batch processing should scale reasonably
        assert batch_time < 5.0  # Less than 5 seconds for 10 articles


@pytest.fixture(scope="session")
def test_config():
    """Test configuration fixture."""
    return {
        "test_model": "roberta-base",
        "test_data_size": 100,
        "confidence_threshold": 0.6,
        "batch_size": 4,
    }


def test_fake_news_config_validation():
    """Test configuration validation."""
    # Test default config
    config = FakeNewsConfig()
    assert config.model_name == "roberta-base"

    # Test custom config
    custom_config = FakeNewsConfig(
        model_name="deberta-base", max_length=256, confidence_threshold=0.7
    )
    assert custom_config.model_name == "deberta-base"
    assert custom_config.max_length == 256
    assert custom_config.confidence_threshold == 0.7


def test_error_handling():
    """Test error handling in fake news detection."""
    detector = FakeNewsDetector(model_name="roberta-base")

    # Test empty text handling
    result = detector._preprocess_text("")
    assert result == ""

    # Test None text handling
    result = detector._preprocess_text(None)
    assert result == ""

    # Test very long text handling
    long_text = "This is a test. " * 1000
    result = detector._preprocess_text(long_text)
    assert isinstance(result, str)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
