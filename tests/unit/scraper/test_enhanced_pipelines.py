"""
Comprehensive tests for Enhanced Pipelines.
Tests data processing, validation, and storage pipeline functionality.
"""

import pytest
import json
import hashlib
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

import scrapy

# Import with proper path handling
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from scraper.enhanced_pipelines import (
    EnhancedPipeline,
    MultiLanguagePipeline,
    S3Pipeline,
    ValidationPipeline,
    DataQualityPipeline,
    DeduplicationPipeline
)
from scraper.items import NewsItem
from scraper.spiders.npr_spider import NPRSpider


class TestEnhancedPipeline:
    """Test suite for EnhancedPipeline class."""

    @pytest.fixture
    def pipeline(self):
        """EnhancedPipeline fixture for testing."""
        return EnhancedPipeline()

    @pytest.fixture
    def sample_item(self):
        """Sample NewsItem for testing."""
        item = NewsItem()
        item['title'] = "Test Article Title"
        item['url'] = "https://example.com/article"
        item['content'] = "This is a test article with substantial content for processing."
        item['author'] = "Test Author"
        item['published_date'] = "2024-01-15"
        item['source'] = "TestSource"
        item['category'] = "Technology"
        return item

    @pytest.fixture
    def spider(self):
        """Mock spider for testing."""
        return MagicMock(spec=NPRSpider)

    def test_pipeline_initialization(self, pipeline):
        """Test EnhancedPipeline initialization."""
        assert hasattr(pipeline, 'process_item')
        assert pipeline.enabled is True

    def test_process_item_basic(self, pipeline, sample_item, spider):
        """Test basic item processing."""
        processed_item = pipeline.process_item(sample_item, spider)
        
        assert processed_item is not None
        assert processed_item['title'] == sample_item['title']
        assert processed_item['content'] == sample_item['content']

    def test_calculate_word_count(self, pipeline, sample_item, spider):
        """Test word count calculation."""
        processed_item = pipeline.process_item(sample_item, spider)
        
        # Should calculate word count
        expected_words = len(sample_item['content'].split())
        assert processed_item.get('word_count', 0) >= expected_words - 2  # Allow some variance

    def test_calculate_reading_time(self, pipeline, sample_item, spider):
        """Test reading time calculation."""
        processed_item = pipeline.process_item(sample_item, spider)
        
        # Should calculate reading time (minimum 1 minute)
        assert processed_item.get('reading_time', 0) >= 1

    def test_content_length_calculation(self, pipeline, sample_item, spider):
        """Test content length calculation."""
        processed_item = pipeline.process_item(sample_item, spider)
        
        expected_length = len(sample_item['content'])
        assert processed_item.get('content_length') == expected_length

    def test_scraped_date_addition(self, pipeline, sample_item, spider):
        """Test addition of scraped_date field."""
        processed_item = pipeline.process_item(sample_item, spider)
        
        assert 'scraped_date' in processed_item
        # Should be a valid datetime string
        scraped_date = processed_item['scraped_date']
        assert isinstance(scraped_date, str)
        assert len(scraped_date) > 10  # Basic date format check

    def test_empty_content_handling(self, pipeline, spider):
        """Test handling of items with empty content."""
        empty_item = NewsItem()
        empty_item['title'] = "Empty Article"
        empty_item['url'] = "https://example.com/empty"
        empty_item['content'] = ""
        
        processed_item = pipeline.process_item(empty_item, spider)
        
        assert processed_item['word_count'] == 0
        assert processed_item['content_length'] == 0
        assert processed_item['reading_time'] == 1  # Minimum reading time


class TestValidationPipeline:
    """Test suite for ValidationPipeline class."""

    @pytest.fixture
    def pipeline(self):
        """ValidationPipeline fixture for testing."""
        return ValidationPipeline()

    @pytest.fixture
    def valid_item(self):
        """Valid NewsItem for testing."""
        item = NewsItem()
        item['title'] = "Valid Article Title"
        item['url'] = "https://valid-source.com/article"
        item['content'] = "This is a valid article with sufficient content for validation."
        item['author'] = "Valid Author"
        item['published_date'] = "2024-01-15"
        item['source'] = "ValidSource"
        return item

    @pytest.fixture
    def spider(self):
        """Mock spider for testing."""
        return MagicMock(spec=NPRSpider)

    def test_valid_item_passes(self, pipeline, valid_item, spider):
        """Test that valid items pass validation."""
        result = pipeline.process_item(valid_item, spider)
        
        assert result is not None
        assert result['validation_score'] > 7  # Should be high quality
        assert result['content_quality'] in ['good', 'excellent']

    def test_missing_required_fields(self, pipeline, spider):
        """Test validation with missing required fields."""
        invalid_item = NewsItem()
        invalid_item['title'] = ""  # Missing title
        invalid_item['url'] = "https://example.com/test"
        invalid_item['content'] = ""  # Missing content
        
        with pytest.raises(scrapy.exceptions.DropItem):
            pipeline.process_item(invalid_item, spider)

    def test_invalid_url_format(self, pipeline, spider):
        """Test validation with invalid URL format."""
        invalid_item = NewsItem()
        invalid_item['title'] = "Test Article"
        invalid_item['url'] = "not-a-valid-url"
        invalid_item['content'] = "Some content"
        
        with pytest.raises(scrapy.exceptions.DropItem):
            pipeline.process_item(invalid_item, spider)

    def test_content_too_short(self, pipeline, spider):
        """Test validation with content that's too short."""
        short_item = NewsItem()
        short_item['title'] = "Short Article"
        short_item['url'] = "https://example.com/short"
        short_item['content'] = "Too short."
        
        result = pipeline.process_item(short_item, spider)
        
        # Should pass but with low quality score
        assert result['validation_score'] <= 5
        assert result['content_quality'] == 'poor'

    def test_quality_score_calculation(self, pipeline, valid_item, spider):
        """Test quality score calculation."""
        result = pipeline.process_item(valid_item, spider)
        
        score = result['validation_score']
        quality = result['content_quality']
        
        assert 0 <= score <= 10
        assert quality in ['poor', 'fair', 'good', 'excellent']
        
        # High quality content should have high score
        if len(valid_item['content']) > 100 and valid_item['title']:
            assert score >= 6

    def test_duplicate_detection(self, pipeline, valid_item, spider):
        """Test basic duplicate detection."""
        # Process same item twice
        result1 = pipeline.process_item(valid_item, spider)
        result2 = pipeline.process_item(valid_item, spider)
        
        # Both should process, but duplicate_check field should be set
        assert 'duplicate_check' in result1
        assert 'duplicate_check' in result2


class TestDeduplicationPipeline:
    """Test suite for DeduplicationPipeline class."""

    @pytest.fixture
    def pipeline(self):
        """DeduplicationPipeline fixture for testing."""
        return DeduplicationPipeline()

    @pytest.fixture
    def spider(self):
        """Mock spider for testing."""
        return MagicMock(spec=NPRSpider)

    def test_first_item_passes(self, pipeline, spider):
        """Test that first occurrence of item passes through."""
        item = NewsItem()
        item['title'] = "Unique Article"
        item['url'] = "https://example.com/unique"
        item['content'] = "This is unique content"
        
        result = pipeline.process_item(item, spider)
        
        assert result is not None
        assert result['duplicate_check'] == 'unique'

    def test_duplicate_item_dropped(self, pipeline, spider):
        """Test that duplicate items are dropped."""
        item1 = NewsItem()
        item1['title'] = "Duplicate Article"
        item1['url'] = "https://example.com/duplicate"
        item1['content'] = "This content will be duplicated"
        
        item2 = NewsItem()
        item2['title'] = "Duplicate Article"
        item2['url'] = "https://example.com/duplicate"  # Same URL
        item2['content'] = "This content will be duplicated"
        
        # Process first item
        result1 = pipeline.process_item(item1, spider)
        assert result1 is not None
        
        # Process duplicate - should be dropped
        with pytest.raises(scrapy.exceptions.DropItem):
            pipeline.process_item(item2, spider)

    def test_content_hash_generation(self, pipeline):
        """Test content hash generation for deduplication."""
        content = "This is test content for hashing"
        hash1 = pipeline._generate_content_hash(content)
        hash2 = pipeline._generate_content_hash(content)
        
        assert hash1 == hash2  # Same content should generate same hash
        assert len(hash1) == 64  # SHA-256 hash length
        
        # Different content should generate different hash
        different_content = "This is different content"
        hash3 = pipeline._generate_content_hash(different_content)
        assert hash1 != hash3

    def test_url_normalization(self, pipeline):
        """Test URL normalization for deduplication."""
        url1 = "https://example.com/article?utm_source=twitter"
        url2 = "https://example.com/article?utm_campaign=email"
        url3 = "https://example.com/article"
        
        normalized1 = pipeline._normalize_url(url1)
        normalized2 = pipeline._normalize_url(url2)
        normalized3 = pipeline._normalize_url(url3)
        
        # All should normalize to same URL (removing UTM parameters)
        assert normalized1 == normalized2 == normalized3


class TestMultiLanguagePipeline:
    """Test suite for MultiLanguagePipeline class."""

    @pytest.fixture
    def pipeline(self):
        """MultiLanguagePipeline fixture for testing."""
        return MultiLanguagePipeline()

    @pytest.fixture
    def english_item(self):
        """English NewsItem for testing."""
        item = NewsItem()
        item['title'] = "English Article Title"
        item['content'] = "This is an English article with substantial content."
        item['url'] = "https://example.com/english"
        return item

    @pytest.fixture
    def spanish_item(self):
        """Spanish NewsItem for testing."""
        item = NewsItem()
        item['title'] = "Artículo en Español"
        item['content'] = "Este es un artículo en español con contenido sustancial."
        item['url'] = "https://example.com/spanish"
        return item

    @pytest.fixture
    def spider(self):
        """Mock spider for testing."""
        return MagicMock(spec=NPRSpider)

    def test_language_detection(self, pipeline, english_item, spider):
        """Test language detection functionality."""
        with patch('langdetect.detect', return_value='en'):
            with patch('langdetect.detect_langs', return_value=[MagicMock(lang='en', prob=0.95)]):
                result = pipeline.process_item(english_item, spider)
                
                assert result['language'] == 'en'
                assert result['detection_confidence'] >= 0.9

    def test_translation_required(self, pipeline, spanish_item, spider):
        """Test translation of non-English content."""
        with patch('langdetect.detect', return_value='es'):
            with patch('googletrans.Translator') as mock_translator:
                mock_translator.return_value.translate.return_value = MagicMock(
                    text="This is a Spanish article with substantial content.",
                    src='es',
                    dest='en'
                )
                
                result = pipeline.process_item(spanish_item, spider)
                
                assert result['original_language'] == 'es'
                assert result['translation_performed'] is True
                assert 'translated_content' in result

    def test_english_content_no_translation(self, pipeline, english_item, spider):
        """Test that English content is not translated."""
        with patch('langdetect.detect', return_value='en'):
            result = pipeline.process_item(english_item, spider)
            
            assert result['language'] == 'en'
            assert result.get('translation_performed', False) is False

    def test_translation_error_handling(self, pipeline, spanish_item, spider):
        """Test handling of translation errors."""
        with patch('langdetect.detect', return_value='es'):
            with patch('googletrans.Translator') as mock_translator:
                mock_translator.return_value.translate.side_effect = Exception("Translation failed")
                
                result = pipeline.process_item(spanish_item, spider)
                
                # Should still process item even if translation fails
                assert result is not None
                assert result.get('translation_performed', False) is False


class TestS3Pipeline:
    """Test suite for S3Pipeline class."""

    @pytest.fixture
    def pipeline(self):
        """S3Pipeline fixture for testing."""
        return S3Pipeline(
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            bucket_name="test-bucket"
        )

    @pytest.fixture
    def sample_item(self):
        """Sample NewsItem for testing."""
        item = NewsItem()
        item['title'] = "S3 Test Article"
        item['url'] = "https://example.com/s3-test"
        item['content'] = "Content for S3 storage testing"
        item['source'] = "TestSource"
        item['published_date'] = "2024-01-15"
        return item

    @pytest.fixture
    def spider(self):
        """Mock spider for testing."""
        return MagicMock(spec=NPRSpider)

    @patch('boto3.client')
    def test_s3_upload_success(self, mock_boto_client, pipeline, sample_item, spider):
        """Test successful S3 upload."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.put_object.return_value = {'ETag': '"test-etag"'}
        
        result = pipeline.process_item(sample_item, spider)
        
        assert result is not None
        mock_s3.put_object.assert_called_once()
        
        # Verify S3 call parameters
        call_args = mock_s3.put_object.call_args
        assert call_args[1]['Bucket'] == 'test-bucket'
        assert 'Key' in call_args[1]
        assert 'Body' in call_args[1]

    @patch('boto3.client')
    def test_s3_upload_failure(self, mock_boto_client, pipeline, sample_item, spider):
        """Test S3 upload failure handling."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.put_object.side_effect = Exception("S3 upload failed")
        
        # Should not raise exception, but handle gracefully
        result = pipeline.process_item(sample_item, spider)
        
        # Item should still be returned even if S3 upload fails
        assert result is not None

    def test_generate_s3_key(self, pipeline, sample_item):
        """Test S3 key generation."""
        key = pipeline._generate_s3_key(sample_item)
        
        assert isinstance(key, str)
        assert len(key) > 0
        # Should include date and some unique identifier
        assert "2024" in key or "s3-test" in key.lower()

    def test_serialize_item(self, pipeline, sample_item):
        """Test item serialization for S3 storage."""
        serialized = pipeline._serialize_item(sample_item)
        
        assert isinstance(serialized, str)
        # Should be valid JSON
        parsed = json.loads(serialized)
        assert parsed['title'] == sample_item['title']
        assert parsed['content'] == sample_item['content']


class TestDataQualityPipeline:
    """Test suite for DataQualityPipeline class."""

    @pytest.fixture
    def pipeline(self):
        """DataQualityPipeline fixture for testing."""
        return DataQualityPipeline()

    @pytest.fixture
    def spider(self):
        """Mock spider for testing."""
        return MagicMock(spec=NPRSpider)

    def test_high_quality_content(self, pipeline, spider):
        """Test processing of high quality content."""
        high_quality_item = NewsItem()
        high_quality_item['title'] = "Comprehensive Analysis of Market Trends"
        high_quality_item['content'] = ("This is a detailed analysis " * 50)  # Long content
        high_quality_item['author'] = "Expert Author"
        high_quality_item['url'] = "https://reputable-source.com/analysis"
        
        result = pipeline.process_item(high_quality_item, spider)
        
        assert result['content_quality'] == 'excellent'
        assert result['validation_score'] >= 8

    def test_low_quality_content(self, pipeline, spider):
        """Test processing of low quality content."""
        low_quality_item = NewsItem()
        low_quality_item['title'] = "Short"
        low_quality_item['content'] = "Very brief."
        low_quality_item['author'] = ""
        low_quality_item['url'] = "https://unknown-source.com/brief"
        
        result = pipeline.process_item(low_quality_item, spider)
        
        assert result['content_quality'] == 'poor'
        assert result['validation_score'] <= 4

    def test_spam_detection(self, pipeline, spider):
        """Test spam content detection."""
        spam_item = NewsItem()
        spam_item['title'] = "CLICK HERE NOW!!! AMAZING OFFER!!!"
        spam_item['content'] = "BUY NOW!!! SPECIAL DISCOUNT!!! LIMITED TIME!!!"
        spam_item['url'] = "https://spam-site.com/offer"
        
        # Should be dropped as spam
        with pytest.raises(scrapy.exceptions.DropItem):
            pipeline.process_item(spam_item, spider)

    def test_content_sanitization(self, pipeline, spider):
        """Test content sanitization."""
        unsanitized_item = NewsItem()
        unsanitized_item['title'] = "Title with <script>alert('xss')</script>"
        unsanitized_item['content'] = "Content with <div onclick='malicious()'>text</div>"
        unsanitized_item['url'] = "https://example.com/unsanitized"
        
        result = pipeline.process_item(unsanitized_item, spider)
        
        # Should remove dangerous HTML/JS
        assert "<script>" not in result['title']
        assert "onclick" not in result['content']
        assert "alert" not in result['title']

    def test_profanity_filtering(self, pipeline, spider):
        """Test profanity filtering."""
        profane_item = NewsItem()
        profane_item['title'] = "Article with inappropriate content"
        profane_item['content'] = "This content contains some inappropriate language."
        profane_item['url'] = "https://example.com/profane"
        
        result = pipeline.process_item(profane_item, spider)
        
        # Should still process but mark appropriately
        assert result is not None
        # Quality score might be affected
        assert 'content_quality' in result

    def test_image_url_validation(self, pipeline, spider):
        """Test image URL validation."""
        item_with_image = NewsItem()
        item_with_image['title'] = "Article with Image"
        item_with_image['content'] = "Content with image"
        item_with_image['image_url'] = "https://example.com/image.jpg"
        item_with_image['url'] = "https://example.com/with-image"
        
        result = pipeline.process_item(item_with_image, spider)
        
        # Should validate and possibly normalize image URL
        assert result['image_url'].startswith('https://')

    def test_reading_time_accuracy(self, pipeline, spider):
        """Test reading time calculation accuracy."""
        timed_item = NewsItem()
        timed_item['title'] = "Timed Reading Article"
        # Approximately 200 words (1 minute read)
        timed_item['content'] = ("word " * 200)
        timed_item['url'] = "https://example.com/timed"
        
        result = pipeline.process_item(timed_item, spider)
        
        # Should calculate approximately 1 minute
        assert result.get('reading_time', 0) >= 1
        assert result.get('word_count', 0) >= 190  # Allow some variance