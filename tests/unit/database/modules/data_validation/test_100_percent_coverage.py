"""
100% Coverage Tests for Data Validation Pipeline
Targeted tests to hit all missing lines and achieve 100% coverage
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from src.database.data_validation_pipeline import (
    DataValidationPipeline, 
    HTMLCleaner, 
    DuplicateDetector, 
    SourceReputationAnalyzer,
    ContentValidator,
    SourceReputationConfig,
    ValidationResult
)


class Test100PercentCoverage:
    """Tests specifically designed to hit all missing lines for 100% coverage"""
    
    def test_data_validation_pipeline_complete_initialization(self):
        """Test pipeline initialization with all components - hits line 695-705"""
        config = SourceReputationConfig(
            trusted_domains=['reuters.com', 'bbc.com'],
            questionable_domains=['example.com'],
            banned_domains=['fake-news.com'],
            reputation_thresholds={'high': 0.8, 'low': 0.3}
        )
        
        pipeline = DataValidationPipeline(config)
        
        # Verify all components are initialized
        assert hasattr(pipeline, 'html_cleaner')
        assert hasattr(pipeline, 'duplicate_detector') 
        assert hasattr(pipeline, 'source_analyzer')
        assert hasattr(pipeline, 'content_validator')
        assert pipeline.processed_count == 0
        assert pipeline.rejected_count == 0
        assert pipeline.warnings_count == 0
    
    def test_html_cleaner_comprehensive_methods(self):
        """Test HTMLCleaner methods - hits lines around 111-187"""
        cleaner = HTMLCleaner()
        
        # Test clean_content method (not clean_html)
        html_content = """
        <html>
        <head><title>Test</title></head>
        <body>
            <script>alert('malicious');</script>
            <style>.test { color: red; }</style>
            <p>Valid content here</p>
            <div onclick="alert('bad')">Click me</div>
        </body>
        </html>
        """
        
        cleaned = cleaner.clean_content(html_content)
        assert 'Valid content here' in cleaned
        assert 'script' not in cleaned.lower()
        assert 'style' not in cleaned.lower()
        assert 'onclick' not in cleaned.lower()
        
        # Test clean_title method
        dirty_title = "<b>Breaking:</b> Test &amp; News &#8220;Article&#8221;"
        clean_title = cleaner.clean_title(dirty_title)
        # Just check that HTML and entities are cleaned
        assert '<b>' not in clean_title
        assert '&amp;' not in clean_title
        assert '&#8220;' not in clean_title
    
    def test_duplicate_detector_comprehensive(self):
        """Test DuplicateDetector - hits lines around 197-300"""
        detector = DuplicateDetector()
        
        # Test is_duplicate method (not check_duplicate)
        article1 = {
            'title': 'Breaking News: Important Event',
            'content': 'This is the full content of the article about an important event.',
            'url': 'https://example.com/news1'
        }
        
        article2 = {
            'title': 'Breaking News: Important Event', 
            'content': 'This is the full content of the article about an important event.',
            'url': 'https://example.com/news2'  # Different URL but same content
        }
        
        # First article should not be duplicate
        is_dup1, reason1 = detector.is_duplicate(article1)
        assert not is_dup1
        
        # Second article should be detected as duplicate
        is_dup2, reason2 = detector.is_duplicate(article2)
        assert is_dup2
        assert 'duplicate' in reason2.lower()
    
    def test_source_reputation_config_from_file(self):
        """Test SourceReputationConfig.from_file - hits lines 51-65"""
        config_data = {
            'source_reputation': {
                'trusted_domains': ['reuters.com', 'bbc.com', 'ap.com'],
                'questionable_domains': ['tabloid.com', 'gossip.com'],
                'banned_domains': ['fake-news.com', 'misinformation.com'],
                'reputation_thresholds': {
                    'trusted': 0.9,
                    'neutral': 0.6,
                    'questionable': 0.4,
                    'banned': 0.1
                }
            }
        }
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name
        
        try:
            config = SourceReputationConfig.from_file(config_file)
            assert config.trusted_domains == config_data['source_reputation']['trusted_domains']
            assert config.questionable_domains == config_data['source_reputation']['questionable_domains']
            assert config.banned_domains == config_data['source_reputation']['banned_domains']
            assert config.reputation_thresholds == config_data['source_reputation']['reputation_thresholds']
        finally:
            os.unlink(config_file)
    
    def test_source_reputation_analyzer_edge_cases(self):
        """Test SourceReputationAnalyzer edge cases - hits lines 400-500"""
        # Test source reputation analyzer edge cases
        config = SourceReputationConfig(
            trusted_domains=['reuters.com'],
            questionable_domains=[],
            banned_domains=['banned.com'],
            reputation_thresholds={'trusted': 0.9, 'reliable': 0.7, 'questionable': 0.4, 'unreliable': 0.2}
        )
        
        analyzer = SourceReputationAnalyzer(config)
        
        # Test with banned domain - should hit banned domain logic
        banned_article = {
            'url': 'https://banned.com/news',
            'domain': 'banned.com',
            'title': 'Fake News Title'
        }
        
        result = analyzer.analyze_source(banned_article)
        assert result['reputation_score'] <= 0.4  # Should be very low score
        
        # Test with trusted domain - should hit trusted domain logic
        trusted_article = {
            'url': 'https://reuters.com/news',
            'domain': 'reuters.com', 
            'title': 'Reuters News Title'
        }
        
        result = analyzer.analyze_source(trusted_article)
        assert result['reputation_score'] >= 0.8  # Should be high score
    
    def test_content_validator_edge_cases(self):
        """Test ContentValidator edge cases - hits lines 300-400"""
        validator = ContentValidator()
        
        # Test with invalid content - should hit validation logic
        invalid_article = {
            'title': '',  # Empty title
            'content': 'x' * 10,  # Too short content
            'published_date': 'invalid-date'
        }
        
        result = validator.validate_content(invalid_article)
        assert not result['is_valid']
        assert len(result['issues']) > 0
        
        # Test with valid content
        valid_article = {
            'title': 'Valid News Article Title',
            'content': 'This is a sufficiently long article content with meaningful information about the topic.' * 5,
            'published_date': datetime.now().isoformat()
        }
        
        result = validator.validate_content(valid_article)
        assert result['is_valid']
    
    def test_process_article_error_conditions(self):
        """Test process_article error conditions - hits lines 708-750"""
        config = SourceReputationConfig(
            trusted_domains=['reuters.com'],
            questionable_domains=[],
            banned_domains=['fake.com'],
            reputation_thresholds={'high': 0.8, 'low': 0.3}
        )
        
        pipeline = DataValidationPipeline(config)
        
        # Test with None article - should return None
        result = pipeline.process_article(None)
        assert result is None
        
        # Test with non-dict article
        result = pipeline.process_article("not a dict")
        assert result is None
        
        # Test with empty dict
        result = pipeline.process_article({})
        assert result is None or not result.is_valid
    
    def test_pipeline_statistics_tracking(self):
        """Test pipeline statistics tracking - hits lines 702-705 and counter updates"""
        config = SourceReputationConfig(
            trusted_domains=['reuters.com'],
            questionable_domains=[],
            banned_domains=['fake.com'],
            reputation_thresholds={'trusted': 0.9, 'neutral': 0.6, 'questionable': 0.4, 'banned': 0.1}
        )
        
        pipeline = DataValidationPipeline(config)
        
        # Process valid article
        valid_article = {
            'title': 'Valid Article Title',
            'content': 'This is valid article content with sufficient length and quality information.',
            'url': 'https://reuters.com/news',
            'published_date': datetime.now().isoformat()
        }
        
        result = pipeline.process_article(valid_article)
        
        # Check statistics were updated
        assert pipeline.processed_count > 0
    
    @patch('builtins.open')
    def test_source_reputation_config_file_error_handling(self, mock_open):
        """Test SourceReputationConfig.from_file error handling - hits exception lines"""
        # Test file not found
        mock_open.side_effect = FileNotFoundError("Config file not found")
        
        with pytest.raises(FileNotFoundError):
            SourceReputationConfig.from_file('nonexistent.json')
        
        # Test invalid JSON
        mock_open.side_effect = None
        mock_open.return_value.__enter__.return_value.read.return_value = "invalid json"
        
        with pytest.raises(json.JSONDecodeError):
            SourceReputationConfig.from_file('invalid.json')
    
    def test_html_cleaner_advanced_cleaning(self):
        """Test HTMLCleaner advanced cleaning scenarios - hits remaining clean_content lines"""
        cleaner = HTMLCleaner()
        
        # Test with complex HTML that hits all cleaning logic
        complex_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <script type="text/javascript">
                var malicious = "code";
                document.write("bad stuff");
            </script>
            <style type="text/css">
                .hidden { display: none; }
                body { background: url('javascript:alert(1)'); }
            </style>
            <link rel="stylesheet" href="styles.css">
        </head>
        <body onload="alert('xss')">
            <div class="content">
                <p onclick="malicious()">Paragraph with <strong>bold</strong> text</p>
                <a href="javascript:void(0)" onmouseover="bad()">Bad link</a>
                <img src="image.jpg" onerror="alert('error')">
                <span onhover="evil()">Text content here</span>
            </div>
            <script>more_bad_code();</script>
        </body>
        </html>
        """
        
        cleaned = cleaner.clean_content(complex_html)
        
        # Verify all dangerous elements removed
        assert 'script' not in cleaned.lower()
        assert 'style' not in cleaned.lower()
        assert 'onclick' not in cleaned.lower()
        assert 'onload' not in cleaned.lower()
        assert 'onmouseover' not in cleaned.lower()
        assert 'onerror' not in cleaned.lower()
        assert 'onhover' not in cleaned.lower()
        assert 'javascript:' not in cleaned.lower()
        
        # Verify safe content preserved
        assert 'Paragraph with' in cleaned
        assert 'bold' in cleaned
        assert 'Text content here' in cleaned
    
    def test_duplicate_detector_fuzzy_matching(self):
        """Test DuplicateDetector fuzzy matching logic - hits fuzzy match lines"""
        detector = DuplicateDetector()
        
        # Add first article
        article1 = {
            'title': 'Breaking: Major Event Happens',
            'content': 'This is the detailed content about the major event that happened today.',
            'url': 'https://news1.com/article1'
        }
        
        detector.is_duplicate(article1)  # Add to cache
        
        # Test with similar but not identical article
        similar_article = {
            'title': 'Breaking: Different Event Occurred',  # Similar but different enough
            'content': 'This is detailed content about a different event today.',  # Different content
            'url': 'https://news2.com/article2'
        }
        
        is_dup, reason = detector.is_duplicate(similar_article)
        # Should not be flagged as duplicate since it's sufficiently different
        assert not is_dup and reason == "unique"
    
    def test_validation_result_complete(self):
        """Test ValidationResult dataclass - ensure all fields are covered"""
        result = ValidationResult(
            score=0.85,
            is_valid=True,
            issues=[],
            warnings=['Minor formatting issue'],
            cleaned_data={'title': 'Clean Title', 'content': 'Clean Content'}
        )
        
        assert result.score == 0.85
        assert result.is_valid is True
        assert result.issues == []
        assert len(result.warnings) == 1
        assert 'Clean Title' in result.cleaned_data['title']
