#!/usr/bin/env python3
"""
Manual test runner for producer-side validation middleware.

This script directly tests the contract validation functionality
to verify DoD requirements without relying on pytest's import system.
"""

import sys
import os
import time

# Add the project root to Python path
sys.path.insert(0, '/workspaces/NeuroNews')

from services.ingest.common.contracts import (
    ArticleIngestValidator,
    DataContractViolation,
    validate_article,
    get_default_validator,
    metrics
)


def test_happy_path():
    """Test validation of valid article (happy path)."""
    print("🧪 Testing happy path (valid article)...")
    
    valid_payload = {
        "article_id": "test-article-123",
        "source_id": "test-source",
        "url": "https://example.com/article",
        "title": "Test Article Title",
        "body": "This is a test article body with some content.",
        "language": "en",
        "country": "US",
        "published_at": int(time.time() * 1000),
        "ingested_at": int(time.time() * 1000),
        "sentiment_score": 0.5,
        "topics": ["technology", "AI"]
    }
    
    # Reset metrics
    metrics.contracts_validation_success_total = 0
    
    try:
        validate_article(valid_payload)
        print("✅ Valid article passed validation")
        assert metrics.contracts_validation_success_total >= 1, "Metrics not updated"
        print("✅ Metrics correctly updated")
        return True
    except Exception as e:
        print(f"❌ Valid article failed validation: {e}")
        return False


def test_sad_path_missing_field():
    """Test validation failure with missing required field (sad path)."""
    print("\n🧪 Testing sad path (missing required field)...")
    
    invalid_payload = {
        "source_id": "test-source",
        "url": "https://example.com/article",
        "language": "en",
        "published_at": int(time.time() * 1000),
        "ingested_at": int(time.time() * 1000),
        "topics": []
        # Missing required 'article_id' field
    }
    
    # Reset metrics
    metrics.contracts_validation_fail_total = 0
    
    try:
        validate_article(invalid_payload)
        print("❌ Invalid article should have failed validation")
        return False
    except DataContractViolation as e:
        print(f"✅ Invalid article correctly failed validation: {e}")
        assert metrics.contracts_validation_fail_total >= 1, "Metrics not updated"
        print("✅ Metrics correctly updated")
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_sad_path_wrong_type():
    """Test validation failure with wrong field type."""
    print("\n🧪 Testing sad path (wrong field type)...")
    
    invalid_payload = {
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
    
    try:
        validate_article(invalid_payload)
        print("❌ Invalid article should have failed validation")
        return False
    except DataContractViolation as e:
        print(f"✅ Invalid article correctly failed validation: {e}")
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_dlq_mode():
    """Test DLQ mode (fail open)."""
    print("\n🧪 Testing DLQ mode (fail open)...")
    
    validator = ArticleIngestValidator(fail_on_error=False)
    
    invalid_payload = {
        "source_id": "test-source",
        "url": "https://example.com/article",
        "language": "en",
        "topics": []
        # Missing required 'article_id' field
    }
    
    # Reset metrics
    metrics.contracts_validation_dlq_total = 0
    
    try:
        validator.validate_article(invalid_payload)
        print("✅ DLQ mode handled invalid article without exception")
        assert metrics.contracts_validation_dlq_total >= 1, "DLQ metrics not updated"
        print("✅ DLQ metrics correctly updated")
        return True
    except Exception as e:
        print(f"❌ DLQ mode should not raise exception: {e}")
        return False


def test_batch_validation():
    """Test batch validation functionality."""
    print("\n🧪 Testing batch validation...")
    
    validator = ArticleIngestValidator()
    
    valid_payload = {
        "article_id": "batch-test-1",
        "source_id": "test-source",
        "url": "https://example.com/article1",
        "title": "Test Article 1",
        "body": "Test body 1",
        "language": "en",
        "country": "US",
        "published_at": int(time.time() * 1000),
        "ingested_at": int(time.time() * 1000),
        "sentiment_score": 0.3,
        "topics": ["test"]
    }
    
    valid_payload_2 = valid_payload.copy()
    valid_payload_2["article_id"] = "batch-test-2"
    valid_payload_2["title"] = "Test Article 2"
    
    payloads = [valid_payload, valid_payload_2]
    
    try:
        result = validator.validate_batch(payloads)
        assert len(result) == 2, f"Expected 2 valid results, got {len(result)}"
        print("✅ Batch validation successful")
        return True
    except Exception as e:
        print(f"❌ Batch validation failed: {e}")
        return False


def test_producer_refuses_invalid_messages():
    """Test DoD requirement: Producer refuses to send invalid messages."""
    print("\n🧪 Testing DoD requirement: Producer refuses invalid messages...")
    
    validator = ArticleIngestValidator(fail_on_error=True)
    
    # Simulate producer trying to send invalid message
    invalid_message = {
        "url": "https://example.com/invalid",
        "language": "en",
        "topics": []
        # Missing required fields: article_id, source_id, published_at, ingested_at
    }
    
    try:
        validator.validate_article(invalid_message)
        print("❌ Producer should refuse to send invalid messages")
        return False
    except DataContractViolation:
        print("✅ Producer correctly refused to send invalid message")
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_metrics_functionality():
    """Test metrics collection."""
    print("\n🧪 Testing metrics functionality...")
    
    validator = ArticleIngestValidator()
    
    # Reset metrics
    metrics.contracts_validation_success_total = 0
    metrics.contracts_validation_fail_total = 0
    
    # Valid message
    valid_payload = {
        "article_id": "metrics-test",
        "source_id": "test-source",
        "url": "https://example.com/metrics",
        "title": "Metrics Test",
        "body": "Testing metrics",
        "language": "en",
        "published_at": int(time.time() * 1000),
        "ingested_at": int(time.time() * 1000),
        "topics": []
    }
    
    validator.validate_article(valid_payload)
    
    # Invalid message
    try:
        validator.validate_article({"invalid": "payload"})
    except DataContractViolation:
        pass
    
    stats = validator.get_metrics()
    success_count = stats["validation_successes"]
    failure_count = stats["validation_failures"]
    
    if success_count >= 1 and failure_count >= 1:
        print("✅ Metrics correctly tracking success and failure counts")
        return True
    else:
        print(f"❌ Metrics not working: success={success_count}, failures={failure_count}")
        return False


def main():
    """Run all tests and report results."""
    print("🚀 Running producer-side validation middleware tests...")
    print("=" * 60)
    
    tests = [
        ("Happy Path", test_happy_path),
        ("Sad Path - Missing Field", test_sad_path_missing_field),
        ("Sad Path - Wrong Type", test_sad_path_wrong_type),
        ("DLQ Mode", test_dlq_mode),
        ("Batch Validation", test_batch_validation),
        ("Producer Refusal (DoD)", test_producer_refuses_invalid_messages),
        ("Metrics", test_metrics_functionality),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! DoD requirements satisfied.")
        return True
    else:
        print("❌ Some tests failed. Please review the implementation.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
