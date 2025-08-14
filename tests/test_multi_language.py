"""
Test suite for multi-language news processing functionality.
Tests language detection, translation, quality checking, and pipeline integration.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

# Import our multi-language components
from src.nlp.language_processor import LanguageDetector, AWSTranslateService, TranslationQualityChecker
from src.nlp.multi_language_processor import MultiLanguageArticleProcessor
from src.scraper.pipelines.multi_language_pipeline import MultiLanguagePipeline, LanguageFilterPipeline


class TestLanguageDetector:
    """Test language detection functionality."""
    
    def setup_method(self):
        self.detector = LanguageDetector()
    
    def test_english_detection(self):
        """Test English language detection."""
        english_text = "This is a news article about technology and innovation in the modern world."
        result = self.detector.detect_language(english_text)
        assert result['language'] == 'en'
        assert result['confidence'] > 0.5
    
    def test_spanish_detection(self):
        """Test Spanish language detection."""
        spanish_text = "Esta es una noticia sobre tecnología y innovación en el mundo moderno."
        result = self.detector.detect_language(spanish_text)
        assert result['language'] == 'es'
        assert result['confidence'] > 0.5
    
    def test_french_detection(self):
        """Test French language detection."""
        french_text = "Ceci est un article de presse sur la technologie et l'innovation dans le monde moderne."
        result = self.detector.detect_language(french_text)
        assert result['language'] == 'fr'
        assert result['confidence'] > 0.5
    
    def test_german_detection(self):
        """Test German language detection."""
        german_text = "Dies ist ein Nachrichtenartikel über Technologie und Innovation in der modernen Welt."
        result = self.detector.detect_language(german_text)
        assert result['language'] == 'de'
        assert result['confidence'] > 0.5
    
    def test_chinese_detection(self):
        """Test Chinese language detection."""
        chinese_text = "这是一篇关于现代世界技术和创新的新闻文章。"
        result = self.detector.detect_language(chinese_text)
        assert result['language'] == 'zh'
        assert result['confidence'] > 0.5
    
    def test_japanese_detection(self):
        """Test Japanese language detection."""
        japanese_text = "これは現代世界のテクノロジーとイノベーションに関するニュース記事です。"
        result = self.detector.detect_language(japanese_text)
        assert result['language'] == 'ja'
        assert result['confidence'] > 0.5
    
    def test_short_text_fallback(self):
        """Test handling of very short text."""
        short_text = "Hi"
        result = self.detector.detect_language(short_text)
        assert result['language'] == 'unknown'
        assert result['confidence'] == 0.0
    
    def test_mixed_language_text(self):
        """Test handling of mixed language content."""
        mixed_text = "Hello world. Bonjour le monde. Hola mundo."
        result = self.detector.detect_language(mixed_text)
        # Should detect the most prominent language
        assert result['language'] in ['en', 'fr', 'es']


class TestAWSTranslateService:
    """Test AWS Translate service integration."""
    
    def setup_method(self):
        with patch('boto3.client'):
            self.service = AWSTranslateService()
    
    @patch('boto3.client')
    def test_translate_text_success(self, mock_boto):
        """Test successful text translation."""
        # Mock AWS Translate response
        mock_translate = Mock()
        mock_translate.translate_text.return_value = {
            'TranslatedText': 'This is a test',
            'SourceLanguageCode': 'es',
            'TargetLanguageCode': 'en'
        }
        mock_boto.return_value = mock_translate
        
        service = AWSTranslateService()
        result = service.translate_text("Esto es una prueba", 'es', 'en')
        
        assert result['success'] is True
        assert result['translated_text'] == 'This is a test'
        assert result['source_language'] == 'es'
        assert result['target_language'] == 'en'
    
    @patch('boto3.client')
    def test_translate_text_error(self, mock_boto):
        """Test translation error handling."""
        mock_translate = Mock()
        mock_translate.translate_text.side_effect = Exception("Translation failed")
        mock_boto.return_value = mock_translate
        
        service = AWSTranslateService()
        result = service.translate_text("Test text", 'es', 'en')
        
        assert result['success'] is False
        assert 'error' in result
    
    @patch('boto3.client')
    def test_cache_functionality(self, mock_boto):
        """Test translation caching."""
        mock_translate = Mock()
        mock_translate.translate_text.return_value = {
            'TranslatedText': 'Cached translation',
            'SourceLanguageCode': 'es',
            'TargetLanguageCode': 'en'
        }
        mock_boto.return_value = mock_translate
        
        service = AWSTranslateService()
        
        # First call
        result1 = service.translate_text("Test", 'es', 'en')
        # Second call (should use cache)
        result2 = service.translate_text("Test", 'es', 'en')
        
        # Should only call AWS once
        mock_translate.translate_text.assert_called_once()
        assert result1 == result2


class TestTranslationQualityChecker:
    """Test translation quality assessment."""
    
    def setup_method(self):
        self.checker = TranslationQualityChecker()
    
    def test_good_quality_translation(self):
        """Test assessment of good quality translation."""
        original = "This is a technology news article about artificial intelligence."
        translated = "Este es un artículo de noticias de tecnología sobre inteligencia artificial."
        
        quality = self.checker.assess_translation_quality(
            original, translated, 'en', 'es'
        )
        
        assert quality['overall_score'] >= 0.7
        assert quality['length_ratio_ok'] is True
    
    def test_poor_quality_translation(self):
        """Test assessment of poor quality translation."""
        original = "This is a long technology news article about artificial intelligence and machine learning."
        translated = "Bad"  # Very short translation
        
        quality = self.checker.assess_translation_quality(
            original, translated, 'en', 'es'
        )
        
        assert quality['overall_score'] < 0.5
        assert quality['length_ratio_ok'] is False
    
    def test_encoding_issue_detection(self):
        """Test detection of encoding issues."""
        original = "Technology news"
        translated = "Tech�ology news"  # Contains replacement character
        
        quality = self.checker.assess_translation_quality(
            original, translated, 'en', 'es'
        )
        
        assert 'encoding_problems' in quality['issues']
    
    def test_untranslated_content_detection(self):
        """Test detection of untranslated content."""
        original = "Technology news article"
        translated = "Technology noticias article"  # Partially untranslated
        
        quality = self.checker.assess_translation_quality(
            original, translated, 'en', 'es'
        )
        
        assert 'untranslated_text' in quality['issues']


class TestMultiLanguageArticleProcessor:
    """Test multi-language article processing."""
    
    def setup_method(self):
        with patch('psycopg2.connect'):
            self.processor = MultiLanguageArticleProcessor()
    
    def test_language_detection_workflow(self):
        """Test the language detection workflow."""
        article_data = {
            'id': 'test_123',
            'title': 'Noticia de Tecnología',
            'content': 'Esta es una noticia sobre tecnología moderna.',
            'url': 'https://example.com/news'
        }
        
        with patch.object(self.processor.language_detector, 'detect_language') as mock_detect:
            mock_detect.return_value = {
                'language': 'es',
                'confidence': 0.85,
                'method': 'pattern_based'
            }
            
            result = self.processor.detect_and_store_language(article_data)
            
            assert result['detected_language'] == 'es'
            assert result['confidence'] == 0.85
    
    def test_translation_workflow(self):
        """Test the translation workflow."""
        article_data = {
            'id': 'test_123',
            'title': 'Noticia de Tecnología',
            'content': 'Esta es una noticia sobre tecnología moderna.'
        }
        
        with patch.object(self.processor.translate_service, 'translate_text') as mock_translate:
            mock_translate.return_value = {
                'success': True,
                'translated_text': 'This is news about modern technology.',
                'source_language': 'es',
                'target_language': 'en'
            }
            
            result = self.processor.translate_article(article_data, 'es', 'en')
            
            assert result['success'] is True
            assert 'translated_content' in result
    
    @patch('psycopg2.connect')
    def test_database_integration(self, mock_connect):
        """Test database storage integration."""
        mock_cursor = Mock()
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        processor = MultiLanguageArticleProcessor()
        
        # Test language detection storage
        detection_data = {
            'article_id': 'test_123',
            'detected_language': 'es',
            'confidence': 0.85
        }
        
        processor.store_language_detection(detection_data)
        mock_cursor.execute.assert_called()
    
    def test_statistics_tracking(self):
        """Test statistics tracking functionality."""
        processor = self.processor
        
        # Test language distribution tracking
        processor.update_language_stats('es')
        processor.update_language_stats('fr')
        processor.update_language_stats('es')
        
        stats = processor.get_processing_statistics()
        
        assert 'language_distribution' in stats
        assert stats['language_distribution']['es'] == 2
        assert stats['language_distribution']['fr'] == 1


class TestMultiLanguagePipeline:
    """Test Scrapy pipeline integration."""
    
    def setup_method(self):
        self.spider = Mock()
        self.spider.settings = {
            'MULTI_LANGUAGE_ENABLED': True,
            'MULTI_LANGUAGE_TARGET_LANGUAGE': 'en',
            'MULTI_LANGUAGE_QUALITY_THRESHOLD': 0.7
        }
        
        with patch('psycopg2.connect'):
            self.pipeline = MultiLanguagePipeline()
    
    def test_pipeline_initialization(self):
        """Test pipeline initialization."""
        pipeline = self.pipeline
        pipeline.open_spider(self.spider)
        
        assert pipeline.enabled is True
        assert pipeline.target_language == 'en'
        assert pipeline.quality_threshold == 0.7
    
    def test_item_processing(self):
        """Test item processing through pipeline."""
        from src.scraper.items import NewsItem
        
        item = NewsItem()
        item['title'] = 'Noticia de Tecnología'
        item['content'] = 'Esta es una noticia sobre tecnología moderna.'
        item['url'] = 'https://example.com/news'
        
        with patch.object(self.pipeline.processor, 'process_article') as mock_process:
            mock_process.return_value = {
                'detected_language': 'es',
                'translated': True,
                'translation_quality': 0.85
            }
            
            result = self.pipeline.process_item(item, self.spider)
            
            assert 'language_info' in result
            assert result['language_info']['detected_language'] == 'es'
    
    def test_disabled_pipeline(self):
        """Test pipeline when disabled."""
        spider = Mock()
        spider.settings = {'MULTI_LANGUAGE_ENABLED': False}
        
        pipeline = self.pipeline
        pipeline.open_spider(spider)
        
        from src.scraper.items import NewsItem
        item = NewsItem()
        
        result = pipeline.process_item(item, spider)
        assert result == item  # Should pass through unchanged


class TestLanguageFilterPipeline:
    """Test language filtering pipeline."""
    
    def setup_method(self):
        self.spider = Mock()
        self.spider.settings = {
            'LANGUAGE_FILTER_ENABLED': True,
            'LANGUAGE_FILTER_ALLOWED': ['en', 'es'],
            'LANGUAGE_FILTER_REQUIRE_TRANSLATION': True
        }
        
        self.pipeline = LanguageFilterPipeline()
    
    def test_allowed_language_pass(self):
        """Test that allowed languages pass through."""
        from scrapy.exceptions import DropItem
        from src.scraper.items import NewsItem
        
        item = NewsItem()
        item['language_info'] = {'detected_language': 'en'}
        
        self.pipeline.open_spider(self.spider)
        result = self.pipeline.process_item(item, self.spider)
        
        assert result == item
    
    def test_blocked_language_drop(self):
        """Test that blocked languages are dropped."""
        from scrapy.exceptions import DropItem
        from src.scraper.items import NewsItem
        
        item = NewsItem()
        item['language_info'] = {'detected_language': 'de'}  # Not in allowed list
        
        self.pipeline.open_spider(self.spider)
        
        with pytest.raises(DropItem):
            self.pipeline.process_item(item, self.spider)


class TestIntegrationWorkflow:
    """Test end-to-end integration workflow."""
    
    @patch('boto3.client')
    @patch('psycopg2.connect')
    def test_full_processing_workflow(self, mock_db, mock_boto):
        """Test complete multi-language processing workflow."""
        # Setup mocks
        mock_translate = Mock()
        mock_translate.translate_text.return_value = {
            'TranslatedText': 'This is a technology news article.',
            'SourceLanguageCode': 'es',
            'TargetLanguageCode': 'en'
        }
        mock_boto.return_value = mock_translate
        
        mock_cursor = Mock()
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.return_value = mock_conn
        
        # Create processor
        processor = MultiLanguageArticleProcessor()
        
        # Test article
        article = {
            'id': 'test_integration',
            'title': 'Avances en Inteligencia Artificial',
            'content': 'Este artículo discute los últimos avances en inteligencia artificial y aprendizaje automático.',
            'url': 'https://example.com/ai-news'
        }
        
        # Process article
        result = processor.process_article(article)
        
        # Verify results
        assert result['detected_language'] == 'es'
        assert result['translated'] is True
        assert 'translation_quality' in result
        assert 'processing_time' in result
    
    def test_error_handling_workflow(self):
        """Test error handling in processing workflow."""
        with patch('psycopg2.connect'):
            processor = MultiLanguageArticleProcessor()
        
        # Test with invalid article data
        invalid_article = {'title': ''}  # Missing required fields
        
        result = processor.process_article(invalid_article)
        
        assert result['success'] is False
        assert 'error' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
