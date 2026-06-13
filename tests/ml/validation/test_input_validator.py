"""Tests for input validation module."""
import pytest
from neuronews.ml.validation.input_validator import InputValidator, ValidatedArticle, ValidationError


def test_validator_none_inputs():
    """Test validation with None inputs."""
    validator = InputValidator()
    
    with pytest.raises(ValidationError, match="title and content are required"):
        validator.validate(None, "content")
    
    with pytest.raises(ValidationError, match="title and content are required"):
        validator.validate("title", None)
    
    with pytest.raises(ValidationError, match="title and content are required"):
        validator.validate(None, None)


def test_validator_safe_method_with_none():
    """Test safe validation method with None inputs."""
    validator = InputValidator()
    
    # Test with None title
    result, errors = validator.safe(None, "content")
    assert len(errors) == 1
    assert "title and content are required" in errors[0]
    assert result.title == ""
    assert result.content == "content"
    
    # Test with None content
    result, errors = validator.safe("title", None)
    assert len(errors) == 1
    assert "title and content are required" in errors[0]
    assert result.title == "title"
    assert result.content == ""
    
    # Test with both None
    result, errors = validator.safe(None, None)
    assert len(errors) == 1
    assert "title and content are required" in errors[0]
    assert result.title == ""
    assert result.content == ""


def test_validator_safe_method_success():
    """Test safe validation method with valid inputs."""
    validator = InputValidator()
    
    result, errors = validator.safe("Valid Title", "Valid content here")
    assert len(errors) == 0
    assert result.title == "Valid Title"
    assert result.content == "Valid content here"


def test_validator_safe_method_short_inputs():
    """Test safe validation method with short inputs."""
    validator = InputValidator()
    
    # Test with short title
    result, errors = validator.safe("Ti", "Valid content")
    assert len(errors) == 1
    assert "title too short" in errors[0]
    
    # Test with short content
    result, errors = validator.safe("Valid Title", "shrt")
    assert len(errors) == 1
    assert "content too short" in errors[0]


def test_validator_truncation():
    """Test content truncation when total length exceeds maximum."""
    validator = InputValidator(max_total_len=100)
    
    long_title = "This is a very long title that takes up space"
    long_content = "This is very long content " * 20  # Much longer than limit
    
    result = validator.validate(long_title, long_content)
    
    assert result.title == long_title
    assert len(result.title) + len(result.content) <= 100
    assert len(result.content) < len(long_content)  # Content was truncated


def test_validated_article_combined():
    """Test ValidatedArticle combined method."""
    article = ValidatedArticle(title="Test Title", content="Test content")
    combined = article.combined()
    
    assert combined == "Test Title. Test content"
