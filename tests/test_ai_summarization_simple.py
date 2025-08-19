"""
Simple tests for AI summarization that can run in CI environments.

These tests focus on core logic and structure without requiring
large model downloads or GPU resources.

Author: NeuroNews Development Team
Created: August 2025
"""

import os
import sys

import pytest

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from src.nlp.ai_summarizer import (AIArticleSummarizer, SummarizationModel,
                                   Summary, SummaryConfig, SummaryLength,
                                   create_summary_hash)


class TestBasicFunctionality:
    """Test basic functionality without model loading."""

    def test_summary_length_enum(self):
        """Test SummaryLength enumeration."""
        assert SummaryLength.SHORT.value == "short"
        assert SummaryLength.MEDIUM.value == "medium"
        assert SummaryLength.LONG.value == "long"

    def test_summarization_model_enum(self):
        """Test SummarizationModel enumeration."""
        assert SummarizationModel.BART.value == "facebook/bart-large-cnn"
        assert SummarizationModel.PEGASUS.value == "google/pegasus-cnn_dailymail"
        assert SummarizationModel.T5.value == "t5-small"
        assert SummarizationModel.DISTILBART.value == "sshleifer/distilbart-cnn-12-6"

    def test_summary_config(self):
        """Test SummaryConfig data class."""
        config = SummaryConfig(
            model=SummarizationModel.BART,
            max_length=100,
            min_length=20,
            length_penalty=1.5,
        )

        assert config.model == SummarizationModel.BART
        assert config.max_length == 100
        assert config.min_length == 20
        assert config.length_penalty == 1.5
        assert config.num_beams == 4  # default value

    def test_summary_object(self):
        """Test Summary data class."""
        summary = Summary(
            text="This is a test summary.",
            length=SummaryLength.MEDIUM,
            model=SummarizationModel.BART,
            confidence_score=0.85,
            processing_time=2.5,
            word_count=5,
            sentence_count=1,
            compression_ratio=0.2,
            created_at="2025-08-15 10:30:00",
        )

        assert summary.text == "This is a test summary."
        assert summary.length == SummaryLength.MEDIUM
        assert summary.model == SummarizationModel.BART
        assert summary.confidence_score == 0.85
        assert summary.processing_time == 2.5
        assert summary.word_count == 5
        assert summary.sentence_count == 1
        assert summary.compression_ratio == 0.2
        assert summary.created_at == "2025-08-15 10:30:00"

    def test_create_summary_hash(self):
        """Test summary hash generation."""
        text = "This is a test article."
        length = SummaryLength.MEDIUM
        model = SummarizationModel.BART

        hash1 = create_summary_hash(text, length, model)
        hash2 = create_summary_hash(text, length, model)

        # Same inputs should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

        # Different inputs should produce different hashes
        hash3 = create_summary_hash(text, SummaryLength.SHORT, model)
        assert hash1 != hash3

    def test_summarizer_initialization(self):
        """Test basic summarizer initialization."""
        summarizer = AIArticleSummarizer(
            default_model=SummarizationModel.DISTILBART,
            device="cpu",
            enable_caching=True,
        )

        assert summarizer.default_model == SummarizationModel.DISTILBART
        assert summarizer.device == "cpu"
        assert summarizer.enable_caching is True

        # Check that configs are initialized
        assert len(summarizer.configs) == 3
        assert SummaryLength.SHORT in summarizer.configs
        assert SummaryLength.MEDIUM in summarizer.configs
        assert SummaryLength.LONG in summarizer.configs

        # Check config values
        short_config = summarizer.configs[SummaryLength.SHORT]
        assert short_config.max_length == 50
        assert short_config.min_length == 20

        medium_config = summarizer.configs[SummaryLength.MEDIUM]
        assert medium_config.max_length == 150
        assert medium_config.min_length == 50

        long_config = summarizer.configs[SummaryLength.LONG]
        assert long_config.max_length == 300
        assert long_config.min_length == 100

    def test_text_preprocessing(self):
        """Test text preprocessing functionality."""
        summarizer = AIArticleSummarizer()

        # Test normal text
        text = "  This is a test.   "
        cleaned = summarizer._preprocess_text(text)
        assert cleaned == "This is a test."

        # Test text without ending punctuation
        text = "This is a test"
        cleaned = summarizer._preprocess_text(text)
        assert cleaned == "This is a test."

        # Test text with multiple spaces
        text = "This  is   a    test."
        cleaned = summarizer._preprocess_text(text)
        assert cleaned == "This is a test."

        # Test empty text
        with pytest.raises(ValueError, match="Text cannot be empty"):
            summarizer._preprocess_text("")

        with pytest.raises(ValueError, match="Text cannot be empty"):
            summarizer._preprocess_text("   ")

        with pytest.raises(ValueError, match="Text cannot be empty"):
            summarizer._preprocess_text(None)

    def test_metrics_calculation(self):
        """Test summary metrics calculation."""
        summarizer = AIArticleSummarizer()

        original_text = "This is a longer original text with multiple sentences. It contains more words than the summary."
        summary_text = "This is a summary."
        processing_time = 2.5

        metrics = summarizer._calculate_metrics(
            original_text, summary_text, processing_time
        )

        assert "word_count" in metrics
        assert "sentence_count" in metrics
        assert "compression_ratio" in metrics
        assert "confidence_score" in metrics
        assert "processing_time" in metrics

        # Check word count using NLTK tokenization (like the actual implementation)
        from nltk.tokenize import word_tokenize

        expected_words = len(word_tokenize(summary_text))
        assert metrics["word_count"] == expected_words
        assert metrics["sentence_count"] == 1
        assert 0 < metrics["compression_ratio"] < 1
        assert 0 <= metrics["confidence_score"] <= 1
        assert metrics["processing_time"] == 2.5

    def test_get_model_info(self):
        """Test model info retrieval."""
        summarizer = AIArticleSummarizer()

        info = summarizer.get_model_info()

        assert "loaded_models" in info
        assert "default_model" in info
        assert "device" in info
        assert "metrics" in info
        assert "configs" in info

        assert info["default_model"] == SummarizationModel.DISTILBART
        assert isinstance(info["loaded_models"], list)
        assert isinstance(info["metrics"], dict)
        assert isinstance(info["configs"], dict)

        # Check metrics structure
        metrics = info["metrics"]
        assert "total_summaries" in metrics
        assert "total_processing_time" in metrics
        assert "average_processing_time" in metrics
        assert "model_usage_count" in metrics

    def test_cache_operations(self):
        """Test cache operations."""
        summarizer = AIArticleSummarizer()

        # Initially cache should be empty
        assert len(summarizer._models) == 0

        # Add something to cache
        summarizer._models[SummarizationModel.BART] = ("mock_model", "mock_tokenizer")
        assert len(summarizer._models) == 1

        # Clear cache
        summarizer.clear_cache()
        assert len(summarizer._models) == 0


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_invalid_inputs(self):
        """Test handling of invalid inputs."""
        summarizer = AIArticleSummarizer()

        # Test empty text preprocessing
        with pytest.raises(ValueError):
            summarizer._preprocess_text("")

        # Test None text preprocessing
        with pytest.raises(ValueError):
            summarizer._preprocess_text(None)

        # Test whitespace-only text
        with pytest.raises(ValueError):
            summarizer._preprocess_text("   \n\t  ")


class TestConfiguration:
    """Test configuration and settings."""

    def test_default_configurations(self):
        """Test default configuration values."""
        summarizer = AIArticleSummarizer()

        # Check all lengths have configurations
        for length in SummaryLength:
            assert length in summarizer.configs
            config = summarizer.configs[length]
            assert config.max_length > config.min_length
            assert config.num_beams > 0
            assert config.length_penalty > 0

    def test_custom_device_setting(self):
        """Test custom device configuration."""
        # Test CPU setting
        summarizer_cpu = AIArticleSummarizer(device="cpu")
        assert summarizer_cpu.device == "cpu"

        # Test auto-detection (should fallback to CPU in test environment)
        summarizer_auto = AIArticleSummarizer(device=None)
        assert summarizer_auto.device in ["cpu", "cuda"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
