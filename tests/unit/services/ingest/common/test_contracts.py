"""
Unit tests for producer-side validation middleware.

Tests cover both happy path (valid data) and sad path (invalid data)
scenarios as required by the Definition of Done.
"""

import json
import pytest
import tempfile
import time
from pathlib import Path
from typing import Dict, Any

from services.ingest.common.contracts import (
    ArticleIngestValidator,
    DataContractViolation,
    validate_article,
    get_default_validator,
    metrics
)


class TestArticleIngestValidator:
    """Test suite for ArticleIngestValidator class."""
    
    @pytest.fixture
    def valid_article_payload(self) -> Dict[str, Any]:
        """Valid article payload that should pass validation."""
        return {
            "article_id": "test-article-123",
            "source_id": "test-source",
            "url": "https://example.com/article",
            "title": "Test Article Title",
            "body": "This is a test article body with some content.",
            "language": "en",
            "country": "US",
            "published_at": int(time.time() * 1000),  # Current timestamp in milliseconds
            "ingested_at": int(time.time() * 1000),
            "sentiment_score": 0.5,
            "topics": ["technology", "AI"]
        }
    
    @pytest.fixture
    def minimal_valid_payload(self) -> Dict[str, Any]:
        """Minimal valid payload with only required fields."""
        return {
            "article_id": "minimal-123",
            "source_id": "minimal-source",
            "url": "https://example.com/minimal",
            "title": None,  # Optional field
            "body": None,   # Optional field
            "language": "en",
            "country": None,  # Optional field
            "published_at": int(time.time() * 1000),
            "ingested_at": int(time.time() * 1000),
            "sentiment_score": None,  # Optional field
            "topics": []  # Default empty array
        }
    
    @pytest.fixture
    def invalid_missing_required_field(self) -> Dict[str, Any]:
        """Invalid payload missing required field."""
        return {
            "source_id": "test-source",
            "url": "https://example.com/article",
            "language": "en",
            "published_at": int(time.time() * 1000),
            "ingested_at": int(time.time() * 1000),
            "topics": []
            # Missing required 'article_id' field
        }
    
    @pytest.fixture
    def invalid_wrong_type(self) -> Dict[str, Any]:
        """Invalid payload with wrong field type."""
        return {
            "article_id": "test-article-123",
            "source_id": "test-source",
            "url": "https://example.com/article",
            "title": "Test Article",
            "body": "Test body",
            "language": "en",
            "country": "US",
            "published_at": "not-a-timestamp",  # Should be long
            "ingested_at": int(time.time() * 1000),
            "sentiment_score": 0.5,
            "topics": ["test"]
        }
    
    @pytest.fixture
    def invalid_sentiment_range(self) -> Dict[str, Any]:
        """Invalid payload with sentiment score out of range."""
        return {
            "article_id": "test-article-123",
            "source_id": "test-source",
            "url": "https://example.com/article",
            "title": "Test Article",
            "body": "Test body",
            "language": "en",
            "country": "US",
            "published_at": int(time.time() * 1000),
            "ingested_at": int(time.time() * 1000),
            "sentiment_score": 2.0,  # Should be between -1 and 1
            "topics": ["test"]
        }
    
    def test_validator_initialization_default_schema(self):
        """Test validator initializes correctly with default schema."""
        validator = ArticleIngestValidator()
        assert validator.schema is not None
        assert validator.fail_on_error is True
    
    def test_validator_initialization_custom_settings(self):
        """Test validator initializes with custom settings."""
        validator = ArticleIngestValidator(fail_on_error=False)
        assert validator.fail_on_error is False
    
    def test_validate_article_happy_path(self, valid_article_payload):
        """Test successful validation of valid article (happy path)."""
        validator = ArticleIngestValidator()
        
        # Reset metrics
        metrics.contracts_validation_success_total = 0
        
        # Should not raise any exception
        validator.validate_article(valid_article_payload)
        
        # Check metrics were updated
        assert metrics.contracts_validation_success_total == 1
    
    def test_validate_article_minimal_payload(self, minimal_valid_payload):
        """Test validation of minimal valid payload."""
        validator = ArticleIngestValidator()
        
        # Reset metrics
        metrics.contracts_validation_success_total = 0
        
        # Should not raise any exception
        validator.validate_article(minimal_valid_payload)
        
        # Check metrics were updated
        assert metrics.contracts_validation_success_total == 1
    
    def test_validate_article_missing_required_field_fail_closed(self, invalid_missing_required_field):
        """Test validation failure with missing required field (sad path - fail closed)."""
        validator = ArticleIngestValidator(fail_on_error=True)
        
        # Reset metrics
        metrics.contracts_validation_fail_total = 0
        
        with pytest.raises(DataContractViolation) as exc_info:
            validator.validate_article(invalid_missing_required_field)
        
        assert "Data contract validation failed" in str(exc_info.value)
        assert metrics.contracts_validation_fail_total == 1
    
    def test_validate_article_wrong_type_fail_closed(self, invalid_wrong_type):
        """Test validation failure with wrong field type (sad path - fail closed)."""
        validator = ArticleIngestValidator(fail_on_error=True)
        
        # Reset metrics
        metrics.contracts_validation_fail_total = 0
        
        with pytest.raises(DataContractViolation) as exc_info:
            validator.validate_article(invalid_wrong_type)
        
        assert "Data contract validation failed" in str(exc_info.value)
        assert metrics.contracts_validation_fail_total == 1
    
    def test_validate_article_dlq_mode(self, invalid_missing_required_field):
        """Test validation in DLQ mode (fail open)."""
        validator = ArticleIngestValidator(fail_on_error=False)
        
        # Reset metrics
        metrics.contracts_validation_dlq_total = 0
        
        # Should not raise exception in DLQ mode
        validator.validate_article(invalid_missing_required_field)
        
        # Check DLQ metrics were updated
        assert metrics.contracts_validation_dlq_total == 1
    
    def test_validate_batch_happy_path(self, valid_article_payload, minimal_valid_payload):
        """Test batch validation with all valid payloads."""
        validator = ArticleIngestValidator()
        payloads = [valid_article_payload, minimal_valid_payload]
        
        result = validator.validate_batch(payloads)
        
        assert len(result) == 2
        assert result == payloads
    
    def test_validate_batch_mixed_validity_fail_closed(self, valid_article_payload, invalid_missing_required_field):
        """Test batch validation with mixed validity in fail-closed mode."""
        validator = ArticleIngestValidator(fail_on_error=True)
        payloads = [valid_article_payload, invalid_missing_required_field]
        
        with pytest.raises(DataContractViolation):
            validator.validate_batch(payloads)
    
    def test_validate_batch_mixed_validity_dlq_mode(self, valid_article_payload, invalid_missing_required_field):
        """Test batch validation with mixed validity in DLQ mode."""
        validator = ArticleIngestValidator(fail_on_error=False)
        payloads = [valid_article_payload, invalid_missing_required_field]
        
        result = validator.validate_batch(payloads)
        
        # Only valid payload should be returned
        assert len(result) == 1
        assert result[0] == valid_article_payload
    
    def test_get_metrics(self):
        """Test metrics retrieval."""
        validator = ArticleIngestValidator()
        
        # Reset metrics
        metrics.contracts_validation_success_total = 5
        metrics.contracts_validation_fail_total = 3
        metrics.contracts_validation_dlq_total = 2
        
        stats = validator.get_metrics()
        
        assert stats["validation_successes"] == 5
        assert stats["validation_failures"] == 3
        assert stats["dlq_messages"] == 2
    
    def test_custom_schema_path(self):
        """Test validator with custom schema path."""
        # Create a temporary schema file
        schema_dict = {
            "type": "record",
            "name": "TestRecord",
            "fields": [
                {"name": "id", "type": "string"},
                {"name": "value", "type": "int"}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.avsc', delete=False) as f:
            json.dump(schema_dict, f)
            temp_schema_path = f.name
        
        try:
            validator = ArticleIngestValidator(schema_path=temp_schema_path)
            assert validator.schema is not None
        finally:
            # Clean up temp file
            Path(temp_schema_path).unlink()
    
    def test_invalid_schema_path(self):
        """Test validator with invalid schema path."""
        with pytest.raises(FileNotFoundError):
            ArticleIngestValidator(schema_path="/nonexistent/path/schema.avsc")


class TestConvenienceFunctions:
    """Test convenience functions and global state."""
    
    def test_get_default_validator_singleton(self):
        """Test that get_default_validator returns singleton."""
        validator1 = get_default_validator()
        validator2 = get_default_validator()
        
        assert validator1 is validator2
    
    def test_validate_article_convenience_function(self, valid_article_payload):
        """Test the convenience validate_article function."""
        # Reset metrics
        metrics.contracts_validation_success_total = 0
        
        # Should not raise exception
        validate_article(valid_article_payload)
        
        # Check metrics were updated
        assert metrics.contracts_validation_success_total >= 1
    
    def test_validate_article_convenience_function_sad_path(self, invalid_missing_required_field):
        """Test convenience function with invalid data."""
        with pytest.raises(DataContractViolation):
            validate_article(invalid_missing_required_field)


class TestMetrics:
    """Test metrics functionality."""
    
    def test_metrics_initialization(self):
        """Test metrics start at zero."""
        test_metrics = metrics.__class__()
        assert test_metrics.contracts_validation_fail_total == 0
        assert test_metrics.contracts_validation_success_total == 0
        assert test_metrics.contracts_validation_dlq_total == 0
    
    def test_metrics_increment_operations(self):
        """Test metrics increment correctly."""
        test_metrics = metrics.__class__()
        
        test_metrics.increment_failure()
        assert test_metrics.contracts_validation_fail_total == 1
        
        test_metrics.increment_success()
        assert test_metrics.contracts_validation_success_total == 1
        
        test_metrics.increment_dlq()
        assert test_metrics.contracts_validation_dlq_total == 1
    
    def test_metrics_get_stats(self):
        """Test metrics stats retrieval."""
        test_metrics = metrics.__class__()
        test_metrics.contracts_validation_fail_total = 5
        test_metrics.contracts_validation_success_total = 10
        test_metrics.contracts_validation_dlq_total = 2
        
        stats = test_metrics.get_stats()
        expected = {
            "validation_failures": 5,
            "validation_successes": 10,
            "dlq_messages": 2
        }
        
        assert stats == expected


class TestIntegrationScenarios:
    """Integration test scenarios for real-world usage."""
    
    def test_producer_refuses_invalid_messages(self, invalid_missing_required_field):
        """Test that producer refuses to send invalid messages (DoD requirement)."""
        validator = ArticleIngestValidator(fail_on_error=True)
        
        # This simulates a producer trying to send an invalid message
        with pytest.raises(DataContractViolation) as exc_info:
            validator.validate_article(invalid_missing_required_field)
        
        # The producer should refuse to send the message
        assert "Data contract validation failed" in str(exc_info.value)
    
    def test_high_volume_validation_performance(self, valid_article_payload):
        """Test validation performance with high volume of messages."""
        validator = ArticleIngestValidator()
        
        # Create a batch of 1000 valid messages
        payloads = [valid_article_payload.copy() for _ in range(1000)]
        for i, payload in enumerate(payloads):
            payload["article_id"] = f"test-article-{i}"
        
        # Validate batch - should complete quickly
        import time
        start_time = time.time()
        result = validator.validate_batch(payloads)
        end_time = time.time()
        
        assert len(result) == 1000
        assert end_time - start_time < 5.0  # Should complete in under 5 seconds
    
    def test_real_world_article_structure(self):
        """Test with realistic article data structure."""
        realistic_article = {
            "article_id": "cnn-2025-08-28-tech-breakthrough",
            "source_id": "cnn",
            "url": "https://www.cnn.com/2025/08/28/tech/ai-breakthrough-news",
            "title": "Revolutionary AI System Achieves Human-Level Understanding",
            "body": """
            In a groundbreaking development, researchers at a leading tech company 
            have announced the creation of an AI system that demonstrates 
            human-level understanding across multiple domains. The system, 
            called NeuralMind-7, represents a significant leap forward in 
            artificial general intelligence (AGI) research.
            
            The announcement comes after months of rigorous testing and 
            validation by independent research institutions. Early results 
            suggest that NeuralMind-7 can perform complex reasoning tasks, 
            understand nuanced language, and even demonstrate creativity 
            in problem-solving scenarios.
            """.strip(),
            "language": "en",
            "country": "US",
            "published_at": 1724851200000,  # 2025-08-28 12:00:00 UTC
            "ingested_at": 1724851500000,   # 5 minutes later
            "sentiment_score": 0.8,          # Positive sentiment
            "topics": ["artificial intelligence", "technology", "research", "AGI"]
        }
        
        validator = ArticleIngestValidator()
        
        # Should validate successfully
        validator.validate_article(realistic_article)
    
    def test_multilingual_article_support(self):
        """Test validation with articles in different languages."""
        articles = [
            {
                "article_id": "lemonde-fr-001",
                "source_id": "lemonde",
                "url": "https://lemonde.fr/article/001",
                "title": "Révolution technologique en Intelligence Artificielle",
                "body": "Une nouvelle ère commence dans le domaine de l'IA...",
                "language": "fr",
                "country": "FR",
                "published_at": int(time.time() * 1000),
                "ingested_at": int(time.time() * 1000),
                "sentiment_score": 0.6,
                "topics": ["technologie", "IA"]
            },
            {
                "article_id": "elmundo-es-001",
                "source_id": "elmundo",
                "url": "https://elmundo.es/articulo/001",
                "title": "Avances en Inteligencia Artificial",
                "body": "Los últimos desarrollos en IA están transformando...",
                "language": "es",
                "country": "ES",
                "published_at": int(time.time() * 1000),
                "ingested_at": int(time.time() * 1000),
                "sentiment_score": 0.4,
                "topics": ["tecnología", "inteligencia artificial"]
            }
        ]
        
        validator = ArticleIngestValidator()
        
        for article in articles:
            validator.validate_article(article)
