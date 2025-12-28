import pytest
from src.database.data_validation_pipeline import HTMLCleaner, DuplicateDetector, ValidationResult

class TestHTMLCleaner:
    """Test HTMLCleaner class."""

    def setup_method(self):
        self.cleaner = HTMLCleaner()

    def test_clean_content_html_tags(self):
        """Test removing HTML tags."""
        content = "<p>This is <b>bold</b> text.</p>"
        cleaned = self.cleaner.clean_content(content)
        assert cleaned == "This is bold text."

    def test_clean_content_scripts(self):
        """Test removing script tags."""
        content = "Content <script>alert('xss')</script> here."
        cleaned = self.cleaner.clean_content(content)
        assert cleaned == "Content here."

    def test_clean_content_whitespace(self):
        """Test normalizing whitespace."""
        content = "  This   is  \n  spaced  "
        cleaned = self.cleaner.clean_content(content)
        assert cleaned == "This is spaced"

    def test_clean_content_entities(self):
        """Test decoding HTML entities."""
        content = "Fish &amp; Chips"
        cleaned = self.cleaner.clean_content(content)
        assert cleaned == "Fish & Chips"

    def test_clean_title(self):
        """Test cleaning title."""
        title = "  Breaking News: Something Happened - CNN  "
        cleaned = self.cleaner.clean_title(title)
        assert cleaned == "Breaking News: Something Happened"

class TestDuplicateDetector:
    """Test DuplicateDetector class."""

    def setup_method(self):
        self.detector = DuplicateDetector()

    def test_is_duplicate_url(self):
        """Test duplicate detection by URL."""
        article1 = {"url": "http://example.com/1", "title": "Title 1", "content": "Content 1"}
        
        is_dup, reason = self.detector.is_duplicate(article1)
        assert is_dup is False
        assert reason == "unique"
        
        is_dup, reason = self.detector.is_duplicate(article1)
        assert is_dup is True
        assert reason == "duplicate_url"

    def test_is_duplicate_title(self):
        """Test duplicate detection by title."""
        article1 = {"url": "http://example.com/1", "title": "Unique Title", "content": "Content 1"}
        article2 = {"url": "http://example.com/2", "title": "Unique Title", "content": "Content 2"}
        
        self.detector.is_duplicate(article1)
        
        is_dup, reason = self.detector.is_duplicate(article2)
        assert is_dup is True
        assert reason == "duplicate_title"

    def test_is_duplicate_content(self):
        """Test duplicate detection by content hash."""
        article1 = {"url": "http://example.com/1", "title": "Title 1", "content": "Same Content"}
        article2 = {"url": "http://example.com/2", "title": "Title 2", "content": "Same Content"}
        
        self.detector.is_duplicate(article1)
        
        is_dup, reason = self.detector.is_duplicate(article2)
        assert is_dup is True
        assert reason == "duplicate_content"

    def test_is_duplicate_fuzzy_title(self):
        """Test duplicate detection by fuzzy title."""
        article1 = {"url": "http://example.com/1", "title": "The quick brown fox", "content": "Content 1"}
        article2 = {"url": "http://example.com/2", "title": "The quick brown fox jumps", "content": "Content 2"}
        
        self.detector.is_duplicate(article1)
        
        is_dup, reason = self.detector.is_duplicate(article2)
        # Similarity should be high enough
        assert is_dup is True
        assert reason == "similar_title"

class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_initialization(self):
        result = ValidationResult(
            score=0.9,
            is_valid=True,
            issues=[],
            warnings=["warning"],
            cleaned_data={}
        )
        assert result.score == 0.9
        assert result.is_valid is True
        assert result.issues == []
        assert result.warnings == ["warning"]
