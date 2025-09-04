"""
Final surgical tests to hit the last remaining 10 lines.
Current coverage: 97% (10 missing lines: 345-346, 430, 634-636, 663, 678, 818-819)
"""
import pytest
from unittest.mock import Mock, patch
import datetime
from src.database.data_validation_pipeline import DataValidationPipeline


class TestSurgicalPrecision:
    
    def test_caps_detection_with_minimal_caps_line_430(self):
        """Hit line 430 with exactly 3 caps and minimal content to avoid other flags."""
        pipeline = DataValidationPipeline()
        
        # Create a title with exactly 3 consecutive caps
        test_content = {
            'url': 'https://test.com/article',
            'domain': 'test.com',
            'title': 'This is NEWS and important information about health',  # NEWS = 4 caps
            'description': 'Brief description here',
            'content': 'A' * 100 + ' some content here ' + 'B' * 100 + ' more text to avoid thin content flag',  # Avoid thin_content
            'author': 'Test Author',
            'category': 'news',
            'publish_date': '2024-01-01'
        }
        
        print(f"Title: {test_content['title']}")
        print(f"Content length: {len(test_content['content'])}")
        
        result = pipeline.process_article(test_content)
        
        # Test the source analyzer directly to hit the caps detection
        source_result = pipeline.source_analyzer.analyze_source(test_content)
        flags = source_result.get("flags", [])
        
        print(f"Flags returned: {flags}")
        
        assert "excessive_caps" in flags, f"Expected excessive_caps flag, got: {flags}"

    def test_caps_detection_with_ABC_pattern_line_430(self):
        """Try with ABC pattern to hit line 430."""
        pipeline = DataValidationPipeline()
        
        test_content = {
            'url': 'https://test.com/article',
            'domain': 'test.com',
            'title': 'Breaking ABC News Today',  # ABC = 3 caps
            'description': 'Brief description here',
            'content': 'Long content ' * 30,  # Avoid thin content
            'author': 'Test Author',
            'category': 'news',
            'publish_date': '2024-01-01'
        }
        
        # Test source analyzer directly
        source_result = pipeline.source_analyzer.analyze_source(test_content)
        flags = source_result.get("flags", [])
        
        print(f"Title: {test_content['title']}")
        print(f"Flags: {flags}")
        
        assert "excessive_caps" in flags

    def test_base_exception_in_pipeline_lines_345_346(self):
        """Try to trigger BaseException in URL parsing."""
        pipeline = DataValidationPipeline()
        
        # Mock urlparse to raise BaseException
        with patch('src.database.data_validation_pipeline.urlparse') as mock_urlparse:
            # Use a custom exception that inherits from BaseException but not Exception
            class CustomBaseException(BaseException):
                pass
            
            mock_urlparse.side_effect = CustomBaseException("Critical system error")
            
            test_content = {
                'url': 'https://test.com/article',
                'title': 'Test Article',
                'description': 'Test description',
                'content': 'Test content',
                'author': 'Test Author',
                'category': 'news',
                'publish_date': '2024-01-01'
            }
            
            # This should catch the BaseException 
            result = pipeline.source_analyzer.analyze_source(test_content)
            
            # The BaseException should be caught and domain should be empty
            assert result.get("domain") == "", f"Expected empty domain, got: {result.get('domain')}"

    def test_duplicate_detection_exception_line_663(self):
        """Try to hit line 663 in duplicate detection."""
        pipeline = DataValidationPipeline()
        
        # Mock the duplicate detector to raise an exception
        with patch.object(pipeline.duplicate_detector, 'is_duplicate') as mock_check:
            mock_check.side_effect = Exception("Database connection error")
            
            test_content = {
                'url': 'https://test.com/article',
                'domain': 'test.com',
                'title': 'Test Article',
                'description': 'Test description',
                'content': 'Test content',
                'author': 'Test Author',
                'category': 'news',
                'publish_date': '2024-01-01'
            }
            
            result = pipeline.process_article(test_content)
            
            # Should handle the exception and continue
            assert result is not None

    def test_date_validation_boundary_conditions_lines_634_636(self):
        """Test specific date validation boundary conditions."""
        pipeline = DataValidationPipeline()
        
        # Test with a date exactly at the 30-day future boundary
        future_date = (datetime.datetime.now() + datetime.timedelta(days=31)).strftime('%Y-%m-%d')
        
        test_content = {
            'url': 'https://test.com/article',
            'domain': 'test.com', 
            'title': 'Future Article',
            'description': 'Description',
            'content': 'Content here',
            'author': 'Author',
            'category': 'news',
            'publish_date': future_date
        }
        
        # Test content validator directly
        date_result = pipeline.content_validator._validate_date(future_date)
        
        print(f"Future date validation result: {date_result}")
        
        # This should trigger the future date path
        assert date_result.get("score_adjustment") == -10
        assert "future_publication_date" in date_result.get("issues", [])

    def test_statistics_calculation_lines_818_819(self):
        """Try to hit the statistics calculation lines."""
        pipeline = DataValidationPipeline()
        
        # Create content that will generate various scores and flags
        test_content = {
            'url': 'https://unreliable-source.com/fake-news',
            'domain': 'unreliable-source.com',
            'title': 'SHOCKING!!! You WONT Believe This!!!',  # Multiple flags
            'description': 'Click here now!',
            'content': 'Very short',  # Thin content
            'author': 'Unknown',
            'category': 'news', 
            'publish_date': '2024-01-01'
        }
        
        # Process multiple times to build up statistics
        for i in range(5):
            result = pipeline.process_article(test_content)
            
        # Check that statistics are tracked
        assert pipeline.processed_count > 0
