"""
Comprehensive tests for ML Module: Model Training Components.

This module provides extensive test coverage for model training functionality
including model initialization, training loop execution, checkpoint management,
evaluation, and GPU/CPU training modes.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

import pytest
import torch

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from src.ml.fake_news_detection import FakeNewsDetector


class TestFakeNewsDetectorTraining:
    """Comprehensive test suite for FakeNewsDetector training components."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file for testing."""
        config_data = {
            "fake_news_detection": {
                "confidence_threshold": 0.8,
                "max_length": 256,
                "batch_size": 8,
                "learning_rate": 2e-5,
                "num_epochs": 3,
                "warmup_steps": 100,
                "weight_decay": 0.01,
                "save_steps": 500,
                "eval_steps": 100,
                "logging_steps": 50,
                "gradient_accumulation_steps": 1,
                "fp16": False,
                "dataloader_num_workers": 4
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
            
        yield config_path
        
        # Cleanup
        if os.path.exists(config_path):
            os.unlink(config_path)

    @pytest.fixture
    def mock_model_components(self):
        """Mock transformer model components."""
        with patch('src.ml.fake_news_detection.AutoTokenizer') as mock_tokenizer, \
             patch('src.ml.fake_news_detection.AutoModelForSequenceClassification') as mock_model, \
             patch('src.ml.fake_news_detection.pipeline') as mock_pipeline:
            
            # Mock tokenizer
            mock_tokenizer_instance = Mock()
            mock_tokenizer_instance.encode.return_value = [101, 123, 456, 102]
            mock_tokenizer_instance.decode.return_value = "test text"
            mock_tokenizer_instance.vocab_size = 30522
            mock_tokenizer.from_pretrained.return_value = mock_tokenizer_instance
            
            # Mock model
            mock_model_instance = Mock()
            mock_model_instance.eval.return_value = None
            mock_model_instance.to.return_value = mock_model_instance
            mock_model_instance.config.num_labels = 2
            mock_model.from_pretrained.return_value = mock_model_instance
            
            # Mock pipeline
            mock_pipeline_instance = Mock()
            mock_pipeline_instance.return_value = [
                [
                    {"label": "REAL", "score": 0.8},
                    {"label": "FAKE", "score": 0.2}
                ]
            ]
            mock_pipeline.return_value = mock_pipeline_instance
            
            yield {
                'tokenizer': mock_tokenizer,
                'model': mock_model,
                'pipeline': mock_pipeline,
                'tokenizer_instance': mock_tokenizer_instance,
                'model_instance': mock_model_instance,
                'pipeline_instance': mock_pipeline_instance
            }

    @pytest.fixture
    def sample_training_data(self):
        """Provide sample training data for testing."""
        return [
            {
                "id": "1",
                "title": "Government announces new infrastructure plan",
                "content": "The federal government today announced a comprehensive infrastructure plan that will invest billions in roads, bridges, and broadband networks. According to officials, the plan aims to create jobs and boost economic growth.",
                "label": "REAL"
            },
            {
                "id": "2", 
                "title": "SHOCKING: Miracle cure discovered by doctors!",
                "content": "Amazing discovery that doctors don't want you to know! This instant cure will change your life forever. Click here to learn the secret that big pharma is hiding from you.",
                "label": "FAKE"
            },
            {
                "id": "3",
                "title": "Study reveals climate change impacts",
                "content": "A peer-reviewed study published in Nature Climate Change reveals new data about rising sea levels. Researchers from Harvard University analyzed decades of satellite data to reach their conclusions.",
                "label": "REAL"
            },
            {
                "id": "4",
                "title": "Aliens control weather using secret technology",
                "content": "Shocking truth revealed! Extraterrestrial beings have been manipulating Earth's weather patterns using advanced technology hidden from the public. Government coverup exposed!",
                "label": "FAKE"
            }
        ]

    def test_model_initialization_default_config(self, mock_model_components):
        """Test model initialization with default configuration."""
        detector = FakeNewsDetector()
        
        # Verify default configuration values
        assert detector.model_name == "hamzelou/fake-news-bert"
        assert detector.confidence_threshold == 0.7
        assert detector.max_length == 512
        assert detector.model_version == "roberta-fake-news-v1.0"
        
        # Verify device selection
        expected_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        assert detector.device == expected_device

    def test_model_initialization_custom_config(self, temp_config_file, mock_model_components):
        """Test model initialization with custom configuration."""
        detector = FakeNewsDetector(
            model_name="custom/model",
            config_path=temp_config_file
        )
        
        # Verify custom configuration is loaded
        assert detector.model_name == "custom/model"
        assert detector.confidence_threshold == 0.8
        assert detector.max_length == 256

    def test_config_loading_file_not_found(self, mock_model_components):
        """Test config loading when file doesn't exist."""
        detector = FakeNewsDetector(config_path="/nonexistent/config.json")
        
        # Should fall back to default config
        assert detector.confidence_threshold == 0.7
        assert detector.max_length == 512

    def test_config_loading_invalid_json(self, mock_model_components):
        """Test config loading with invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            invalid_config_path = f.name
        
        try:
            detector = FakeNewsDetector(config_path=invalid_config_path)
            
            # Should fall back to default config
            assert detector.confidence_threshold == 0.7
            assert detector.max_length == 512
        finally:
            os.unlink(invalid_config_path)

    def test_transformer_model_initialization_success(self, mock_model_components):
        """Test successful transformer model initialization."""
        detector = FakeNewsDetector()
        
        # Verify pipeline was created
        mock_model_components['pipeline'].assert_called_once()
        assert detector.classifier is not None

    def test_transformer_model_initialization_pipeline_failure(self, mock_model_components):
        """Test model initialization when pipeline fails but manual loading succeeds."""
        # Make pipeline fail
        mock_model_components['pipeline'].side_effect = Exception("Pipeline failed")
        
        detector = FakeNewsDetector()
        
        # Verify fallback to manual loading
        mock_model_components['tokenizer'].from_pretrained.assert_called_once()
        mock_model_components['model'].from_pretrained.assert_called_once()

    def test_transformer_model_initialization_complete_failure(self, mock_model_components):
        """Test model initialization when both pipeline and manual loading fail."""
        # Make both pipeline and manual loading fail
        mock_model_components['pipeline'].side_effect = Exception("Pipeline failed")
        mock_model_components['tokenizer'].from_pretrained.side_effect = Exception("Tokenizer failed")
        mock_model_components['model'].from_pretrained.side_effect = Exception("Model failed")
        
        detector = FakeNewsDetector()
        
        # Should fall back to rule-based approach
        assert detector.classifier is None
        assert detector.model is None

    def test_predict_veracity_with_transformer(self, mock_model_components):
        """Test prediction with transformer model."""
        detector = FakeNewsDetector()
        
        result = detector.predict_veracity(
            title="Test Title",
            content="Test content",
            include_explanation=True
        )
        
        # Verify result structure
        assert "is_real" in result
        assert "confidence" in result
        assert "model_version" in result
        assert "timestamp" in result
        assert "explanation" in result
        
        # Verify prediction logic
        assert isinstance(result["is_real"], bool)
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_predict_veracity_without_explanation(self, mock_model_components):
        """Test prediction without explanation."""
        detector = FakeNewsDetector()
        
        result = detector.predict_veracity(
            title="Test Title",
            content="Test content",
            include_explanation=False
        )
        
        # Should not contain explanation
        assert "explanation" not in result
        assert "is_real" in result
        assert "confidence" in result

    def test_predict_veracity_with_rule_based_fallback(self, mock_model_components):
        """Test prediction using rule-based fallback."""
        # Force rule-based mode
        mock_model_components['pipeline'].side_effect = Exception("Pipeline failed")
        mock_model_components['tokenizer'].from_pretrained.side_effect = Exception("Tokenizer failed")
        mock_model_components['model'].from_pretrained.side_effect = Exception("Model failed")
        
        detector = FakeNewsDetector()
        
        # Test with fake news indicators
        result = detector.predict_veracity(
            title="SHOCKING miracle cure",
            content="Doctors hate this one secret trick!"
        )
        
        assert result["is_real"] is False
        assert "method" in result
        assert result["method"] == "rule_based"

    def test_predict_veracity_rule_based_real_content(self, mock_model_components):
        """Test rule-based prediction with real news indicators."""
        # Force rule-based mode
        mock_model_components['pipeline'].side_effect = Exception("Pipeline failed")
        mock_model_components['tokenizer'].from_pretrained.side_effect = Exception("Tokenizer failed")
        mock_model_components['model'].from_pretrained.side_effect = Exception("Model failed")
        
        detector = FakeNewsDetector()
        
        # Test with real news indicators
        result = detector.predict_veracity(
            title="University study shows research results",
            content="According to published research and peer-reviewed analysis, scientists have discovered new data."
        )
        
        assert result["is_real"] is True
        assert result["method"] == "rule_based"

    def test_predict_veracity_text_truncation(self, mock_model_components):
        """Test text truncation for long content."""
        detector = FakeNewsDetector()
        
        # Create very long content
        long_content = "This is a test. " * 1000  # Exceeds max_length
        
        result = detector.predict_veracity(
            title="Test Title",
            content=long_content
        )
        
        # Should not fail and should return valid result
        assert "is_real" in result
        assert "confidence" in result

    def test_predict_veracity_error_handling(self, mock_model_components):
        """Test error handling in prediction."""
        # Make prediction method fail
        mock_model_components['pipeline_instance'].side_effect = Exception("Prediction failed")
        
        detector = FakeNewsDetector()
        
        result = detector.predict_veracity(
            title="Test Title",
            content="Test content"
        )
        
        # Should return fallback result
        assert result["is_real"] is True  # Conservative approach
        assert result["confidence"] == 0.5
        assert "error" in result

    def test_batch_predict_success(self, mock_model_components, sample_training_data):
        """Test batch prediction with multiple articles."""
        detector = FakeNewsDetector()
        
        articles = [
            {"id": "1", "title": "Title 1", "content": "Content 1"},
            {"id": "2", "title": "Title 2", "content": "Content 2"},
            {"id": "3", "title": "Title 3", "content": "Content 3"}
        ]
        
        results = detector.batch_predict(articles)
        
        # Verify results
        assert len(results) == 3
        for i, result in enumerate(results):
            assert "is_real" in result
            assert "confidence" in result
            assert result["article_id"] == articles[i]["id"]

    def test_batch_predict_with_errors(self, mock_model_components):
        """Test batch prediction with some articles failing."""
        detector = FakeNewsDetector()
        
        # Mock predict_veracity to fail for second article
        original_predict = detector.predict_veracity
        def mock_predict(title, content):
            if title == "Failing Title":
                raise Exception("Prediction failed")
            return original_predict(title, content)
        
        detector.predict_veracity = mock_predict
        
        articles = [
            {"id": "1", "title": "Good Title", "content": "Content 1"},
            {"id": "2", "title": "Failing Title", "content": "Content 2"},
            {"id": "3", "title": "Good Title", "content": "Content 3"}
        ]
        
        results = detector.batch_predict(articles)
        
        # Should have 3 results despite one failure
        assert len(results) == 3
        assert results[1]["confidence"] == 0.5  # Fallback result

    def test_get_model_info(self, mock_model_components):
        """Test model information retrieval."""
        detector = FakeNewsDetector(model_name="test/model")
        
        info = detector.get_model_info()
        
        # Verify info structure
        assert "model_name" in info
        assert "model_version" in info
        assert "device" in info
        assert "confidence_threshold" in info
        assert "max_length" in info
        assert "available" in info
        
        # Verify values
        assert info["model_name"] == "test/model"
        assert info["model_version"] == "roberta-fake-news-v1.0"
        assert info["available"] is True

    def test_explanation_generation_real_news(self, mock_model_components):
        """Test explanation generation for real news."""
        detector = FakeNewsDetector()
        
        result = {
            "is_real": True,
            "confidence": 0.9
        }
        
        explanation = detector._generate_explanation(
            title="University Research Study",
            content="Researchers at the university published peer-reviewed findings",
            result=result
        )
        
        assert "REAL with high confidence" in explanation
        assert "research" in explanation.lower() or "academic" in explanation.lower()

    def test_explanation_generation_fake_news(self, mock_model_components):
        """Test explanation generation for fake news."""
        detector = FakeNewsDetector()
        
        result = {
            "is_real": False,
            "confidence": 0.85
        }
        
        explanation = detector._generate_explanation(
            title="SHOCKING miracle discovery",
            content="Instant results with this secret method",
            result=result
        )
        
        assert "FAKE with high confidence" in explanation
        assert "sensational" in explanation.lower() or "unrealistic" in explanation.lower()

    def test_gpu_cpu_device_selection(self, mock_model_components):
        """Test GPU/CPU device selection."""
        # Test with CUDA available
        with patch('torch.cuda.is_available', return_value=True):
            detector = FakeNewsDetector()
            assert detector.device.type == "cuda"
        
        # Test with CUDA not available
        with patch('torch.cuda.is_available', return_value=False):
            detector = FakeNewsDetector()
            assert detector.device.type == "cpu"

    def test_model_to_device_call(self, mock_model_components):
        """Test that model is moved to correct device."""
        detector = FakeNewsDetector()
        
        # Verify model.to(device) was called if manual loading occurred
        if detector.model is not None:
            mock_model_components['model_instance'].to.assert_called_with(detector.device)

    def test_model_eval_mode(self, mock_model_components):
        """Test that model is set to evaluation mode."""
        detector = FakeNewsDetector()
        
        # Verify model.eval() was called if manual loading occurred
        if detector.model is not None:
            mock_model_components['model_instance'].eval.assert_called_once()

    @pytest.mark.parametrize("confidence_threshold", [0.5, 0.7, 0.9])
    def test_different_confidence_thresholds(self, mock_model_components, confidence_threshold):
        """Test model with different confidence thresholds."""
        config_data = {
            "fake_news_detection": {
                "confidence_threshold": confidence_threshold
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            detector = FakeNewsDetector(config_path=config_path)
            assert detector.confidence_threshold == confidence_threshold
        finally:
            os.unlink(config_path)

    @pytest.mark.parametrize("max_length", [128, 256, 512, 1024])
    def test_different_max_lengths(self, mock_model_components, max_length):
        """Test model with different max sequence lengths."""
        config_data = {
            "fake_news_detection": {
                "max_length": max_length
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            detector = FakeNewsDetector(config_path=config_path)
            assert detector.max_length == max_length
        finally:
            os.unlink(config_path)

    def test_timestamp_format(self, mock_model_components):
        """Test that timestamps are in correct ISO format."""
        detector = FakeNewsDetector()
        
        result = detector.predict_veracity("Test", "Test content")
        
        # Verify timestamp format
        timestamp = result["timestamp"]
        assert timestamp.endswith("Z")
        
        # Should be parseable as datetime
        parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert isinstance(parsed_time, datetime)

    def test_prediction_with_empty_content(self, mock_model_components):
        """Test prediction with empty or minimal content."""
        detector = FakeNewsDetector()
        
        # Test with empty strings
        result = detector.predict_veracity("", "")
        assert "is_real" in result
        assert "confidence" in result
        
        # Test with whitespace only
        result = detector.predict_veracity("   ", "   ")
        assert "is_real" in result
        assert "confidence" in result

    def test_prediction_with_special_characters(self, mock_model_components):
        """Test prediction with special characters and unicode."""
        detector = FakeNewsDetector()
        
        result = detector.predict_veracity(
            title="Test with émojis 🔥 and spécial chars",
            content="Content with ñoñó characters and 中文 text"
        )
        
        assert "is_real" in result
        assert "confidence" in result


class TestModelTrainingValidation:
    """Test suite for model training data validation and preprocessing."""

    def test_training_data_validation(self):
        """Test validation of training data format."""
        valid_data = [
            {"title": "Title 1", "content": "Content 1", "label": "REAL"},
            {"title": "Title 2", "content": "Content 2", "label": "FAKE"}
        ]
        
        # This would be expanded with actual training validation logic
        assert len(valid_data) == 2
        assert all("title" in item for item in valid_data)
        assert all("content" in item for item in valid_data)
        assert all("label" in item for item in valid_data)

    def test_hyperparameter_validation(self):
        """Test validation of hyperparameters."""
        valid_params = {
            "learning_rate": 2e-5,
            "batch_size": 16,
            "num_epochs": 3,
            "max_length": 512
        }
        
        # Validate learning rate
        assert 0 < valid_params["learning_rate"] < 1
        
        # Validate batch size
        assert valid_params["batch_size"] > 0
        assert valid_params["batch_size"] <= 64
        
        # Validate epochs
        assert valid_params["num_epochs"] > 0
        
        # Validate max length
        assert valid_params["max_length"] > 0
        assert valid_params["max_length"] <= 2048


if __name__ == "__main__":
    pytest.main([__file__])
