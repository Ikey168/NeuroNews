"""
Unit tests for Named Entity Recognition (NER) functionality.
Tests the NER processor and NER-enabled article processor.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import pytest
from datetime import datetime
import json

from src.nlp.ner_processor import NERProcessor, create_ner_processor
from src.nlp.ner_article_processor import NERArticleProcessor, create_ner_article_processor


class TestNERProcessor(unittest.TestCase):
    """Test cases for the NERProcessor class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock the transformers pipeline to avoid downloading models
        self.mock_pipeline_patcher = patch('src.nlp.ner_processor.pipeline')
        self.mock_pipeline = self.mock_pipeline_patcher.start()
        
        # Configure mock pipeline
        self.mock_ner = Mock()
        self.mock_pipeline.return_value = self.mock_ner
        
        # Create processor instance
        self.processor = NERProcessor(
            model_name="test-model",
            confidence_threshold=0.7
        )
    
    def tearDown(self):
        """Clean up after tests."""
        self.mock_pipeline_patcher.stop()
    
    def test_processor_initialization(self):
        """Test NER processor initialization."""
        self.assertIsNotNone(self.processor)
        self.assertEqual(self.processor.model_name, "test-model")
        self.assertEqual(self.processor.confidence_threshold, 0.7)
        self.assertIsNotNone(self.processor.ner_pipeline)
        
        # Check statistics initialization
        self.assertEqual(self.processor.stats['total_texts_processed'], 0)
        self.assertEqual(self.processor.stats['total_entities_extracted'], 0)
    
    def test_extract_entities_success(self):
        """Test successful entity extraction."""
        # Mock NER pipeline response
        mock_entities = [
            {
                'word': 'Apple Inc.',
                'entity_group': 'ORG',
                'score': 0.95,
                'start': 0,
                'end': 10
            },
            {
                'word': 'Tim Cook',
                'entity_group': 'PER',
                'score': 0.88,
                'start': 11,
                'end': 19
            },
            {
                'word': 'Cupertino',
                'entity_group': 'GPE',
                'score': 0.92,
                'start': 23,
                'end': 32
            }
        ]
        self.mock_ner.return_value = mock_entities
        
        # Test text
        text = "Apple Inc. CEO Tim Cook announced from Cupertino..."
        
        # Extract entities
        entities = self.processor.extract_entities(text, "test_article_1")
        
        # Verify results
        self.assertEqual(len(entities), 3)
        
        # Check first entity (Apple Inc.)
        apple_entity = entities[0]  # Should be sorted by confidence
        self.assertEqual(apple_entity['text'], 'Apple Inc.')
        self.assertEqual(apple_entity['type'], 'TECHNOLOGY_ORGANIZATION')  # Enhanced type
        self.assertEqual(apple_entity['confidence'], 0.95)
        self.assertIn('extracted_at', apple_entity)
        
        # Check second entity (Tim Cook)
        tim_entity = next(e for e in entities if e['text'] == 'Tim Cook')
        self.assertEqual(tim_entity['type'], 'PERSON')
        self.assertEqual(tim_entity['confidence'], 0.88)
        
        # Check third entity (Cupertino)
        cupertino_entity = next(e for e in entities if e['text'] == 'Cupertino')
        self.assertEqual(cupertino_entity['type'], 'LOCATION')
        self.assertEqual(cupertino_entity['confidence'], 0.92)
        
        # Check statistics update
        self.assertEqual(self.processor.stats['total_texts_processed'], 1)
        self.assertEqual(self.processor.stats['total_entities_extracted'], 3)
    
    def test_extract_entities_empty_text(self):
        """Test entity extraction with empty text."""
        entities = self.processor.extract_entities("", "test_article_empty")
        self.assertEqual(len(entities), 0)
        
        entities = self.processor.extract_entities(None, "test_article_none")
        self.assertEqual(len(entities), 0)
    
    def test_extract_entities_confidence_filtering(self):
        """Test that low-confidence entities are filtered out."""
        # Mock entities with varying confidence
        mock_entities = [
            {
                'word': 'High Confidence Entity',
                'entity_group': 'ORG',
                'score': 0.9,  # Above threshold
                'start': 0,
                'end': 20
            },
            {
                'word': 'Low Confidence Entity',
                'entity_group': 'PER',
                'score': 0.5,  # Below threshold (0.7)
                'start': 21,
                'end': 42
            }
        ]
        self.mock_ner.return_value = mock_entities
        
        entities = self.processor.extract_entities("Test text", "test_article_filter")
        
        # Only high-confidence entity should remain
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]['text'], 'High Confidence Entity')
        self.assertEqual(entities[0]['confidence'], 0.9)
    
    def test_technology_entity_enhancement(self):
        """Test enhancement of technology-related entities."""
        mock_entities = [
            {
                'word': 'artificial intelligence',
                'entity_group': 'MISC',
                'score': 0.8,
                'start': 0,
                'end': 21
            },
            {
                'word': 'machine learning',
                'entity_group': 'MISC',
                'score': 0.85,
                'start': 25,
                'end': 41
            }
        ]
        self.mock_ner.return_value = mock_entities
        
        text = "artificial intelligence and machine learning are transforming industries"
        entities = self.processor.extract_entities(text, "test_tech")
        
        # Check that technology entities are properly classified
        ai_entity = next(e for e in entities if 'artificial intelligence' in e['text'])
        ml_entity = next(e for e in entities if 'machine learning' in e['text'])
        
        self.assertEqual(ai_entity['type'], 'TECHNOLOGY')
        self.assertEqual(ml_entity['type'], 'TECHNOLOGY')
    
    def test_organization_enhancement(self):
        """Test enhancement of organization entities."""
        mock_entities = [
            {
                'word': 'Microsoft Corp',
                'entity_group': 'ORG',
                'score': 0.9,
                'start': 0,
                'end': 14
            },
            {
                'word': 'Google Inc',
                'entity_group': 'ORG',
                'score': 0.88,
                'start': 18,
                'end': 28
            }
        ]
        self.mock_ner.return_value = mock_entities
        
        text = "Microsoft Corp and Google Inc announced partnership"
        entities = self.processor.extract_entities(text, "test_orgs")
        
        # Check that tech organizations are properly classified
        microsoft_entity = next(e for e in entities if 'Microsoft' in e['text'])
        google_entity = next(e for e in entities if 'Google' in e['text'])
        
        self.assertEqual(microsoft_entity['type'], 'TECHNOLOGY_ORGANIZATION')
        self.assertEqual(google_entity['type'], 'TECHNOLOGY_ORGANIZATION')
    
    def test_text_preprocessing(self):
        """Test text preprocessing functionality."""
        # Test with messy text
        messy_text = "This   is    a\n\n  messy    text   with   lots   of    whitespace"
        cleaned = self.processor._preprocess_text(messy_text)
        
        # Should normalize whitespace
        self.assertNotIn('\n', cleaned)
        self.assertNotIn('  ', cleaned)  # No double spaces
        
        # Test with very long text
        long_text = "This is a very long text. " * 1000
        cleaned_long = self.processor._preprocess_text(long_text)
        
        # Should be truncated
        self.assertLess(len(cleaned_long), len(long_text))
    
    def test_text_splitting(self):
        """Test text splitting for long documents."""
        # Create a long text that exceeds max_length
        long_sentences = ["This is sentence number {}.".format(i) for i in range(100)]
        long_text = " ".join(long_sentences)
        
        chunks = self.processor._split_text(long_text)
        
        # Should be split into multiple chunks
        self.assertGreater(len(chunks), 1)
        
        # Each chunk should be reasonably sized
        for chunk in chunks:
            estimated_tokens = len(chunk) // 4
            self.assertLessEqual(estimated_tokens, self.processor.max_length)
    
    def test_duplicate_entity_filtering(self):
        """Test that duplicate entities are filtered out."""
        mock_entities = [
            {
                'word': 'Apple',
                'entity_group': 'ORG',
                'score': 0.9,
                'start': 0,
                'end': 5
            },
            {
                'word': 'Apple',  # Duplicate
                'entity_group': 'ORG',
                'score': 0.8,
                'start': 10,
                'end': 15
            }
        ]
        self.mock_ner.return_value = mock_entities
        
        entities = self.processor.extract_entities("Apple and Apple again", "test_duplicates")
        
        # Should only have one Apple entity (the higher confidence one)
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]['text'], 'Apple')
        self.assertEqual(entities[0]['confidence'], 0.9)
    
    def test_statistics_tracking(self):
        """Test statistics tracking functionality."""
        # Process multiple texts
        mock_entities_1 = [
            {'word': 'Entity1', 'entity_group': 'PER', 'score': 0.8, 'start': 0, 'end': 7}
        ]
        mock_entities_2 = [
            {'word': 'Entity2', 'entity_group': 'ORG', 'score': 0.9, 'start': 0, 'end': 7},
            {'word': 'Entity3', 'entity_group': 'ORG', 'score': 0.85, 'start': 8, 'end': 15}
        ]
        
        self.mock_ner.side_effect = [mock_entities_1, mock_entities_2]
        
        self.processor.extract_entities("Text 1", "article_1")
        self.processor.extract_entities("Text 2", "article_2")
        
        stats = self.processor.get_statistics()
        
        self.assertEqual(stats['total_texts_processed'], 2)
        self.assertEqual(stats['total_entities_extracted'], 3)
        self.assertEqual(stats['average_entities_per_text'], 1.5)
        self.assertEqual(stats['entity_type_distribution']['PERSON'], 1)
        self.assertEqual(stats['entity_type_distribution']['ORGANIZATION'], 2)
    
    def test_reset_statistics(self):
        """Test statistics reset functionality."""
        # Process some text first
        mock_entities = [
            {'word': 'Test', 'entity_group': 'PER', 'score': 0.8, 'start': 0, 'end': 4}
        ]
        self.mock_ner.return_value = mock_entities
        
        self.processor.extract_entities("Test text", "test_article")
        
        # Verify statistics are not zero
        self.assertGreater(self.processor.stats['total_texts_processed'], 0)
        
        # Reset and verify
        self.processor.reset_statistics()
        self.assertEqual(self.processor.stats['total_texts_processed'], 0)
        self.assertEqual(self.processor.stats['total_entities_extracted'], 0)
    
    def test_create_ner_processor_factory(self):
        """Test the factory function for creating NER processors."""
        processor = create_ner_processor(model_name="custom-model", confidence_threshold=0.8)
        
        self.assertIsInstance(processor, NERProcessor)
        self.assertEqual(processor.model_name, "custom-model")
        self.assertEqual(processor.confidence_threshold, 0.8)


class TestNERArticleProcessor(unittest.TestCase):
    """Test cases for the NERArticleProcessor class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock dependencies
        self.mock_sentiment_analyzer = patch('src.nlp.sentiment_analysis.create_analyzer')
        self.mock_sentiment_analyzer.start()
        
        self.mock_ner_processor = patch('src.nlp.ner_article_processor.create_ner_processor')
        self.mock_ner_create = self.mock_ner_processor.start()
        
        # Mock psycopg2 in both places
        self.mock_psycopg2_ner = patch('src.nlp.ner_article_processor.psycopg2')
        self.mock_psycopg2_article = patch('src.nlp.article_processor.psycopg2')
        self.mock_db_ner = self.mock_psycopg2_ner.start()
        self.mock_db_article = self.mock_psycopg2_article.start()
        
        # Configure mocks
        self.mock_ner_instance = Mock()
        self.mock_ner_create.return_value = self.mock_ner_instance
        
        # Mock database connection for both patches
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_db_ner.connect.return_value.__enter__.return_value = self.mock_conn
        self.mock_db_article.connect.return_value.__enter__.return_value = self.mock_conn
        
        # Test configuration
        self.config = {
            'redshift_host': 'test-host',
            'redshift_port': 5439,
            'redshift_database': 'test-db',
            'redshift_user': 'test-user',
            'redshift_password': 'test-password',
            'sentiment_provider': None,  # Use None to get default model
            'ner_enabled': True
        }
    
    def tearDown(self):
        """Clean up after tests."""
        self.mock_sentiment_analyzer.stop()
        self.mock_ner_processor.stop()
        self.mock_psycopg2_ner.stop()
        self.mock_psycopg2_article.stop()
    
    def test_processor_initialization_with_ner(self):
        """Test processor initialization with NER enabled."""
        processor = NERArticleProcessor(**self.config)
        
        self.assertTrue(processor.ner_enabled)
        self.assertIsNotNone(processor.ner_processor)
        self.mock_ner_create.assert_called_once()
    
    def test_processor_initialization_without_ner(self):
        """Test processor initialization with NER disabled."""
        config = self.config.copy()
        config['ner_enabled'] = False
        
        processor = NERArticleProcessor(**config)
        
        self.assertFalse(processor.ner_enabled)
        self.assertIsNone(processor.ner_processor)
    
    @patch('src.nlp.ner_article_processor.ArticleProcessor.process_articles')
    def test_process_articles_with_ner(self, mock_parent_process):
        """Test article processing with NER enabled."""
        # Mock parent class processing
        mock_sentiment_results = [
            {
                'article_id': 'test_1',
                'sentiment': 'positive',
                'confidence': 0.85
            }
        ]
        mock_parent_process.return_value = mock_sentiment_results
        
        # Mock NER extraction
        mock_entities = [
            {
                'text': 'Apple Inc.',
                'type': 'ORGANIZATION',
                'confidence': 0.9,
                'start_position': 0,
                'end_position': 10
            },
            {
                'text': 'Tim Cook',
                'type': 'PERSON',
                'confidence': 0.85,
                'start_position': 11,
                'end_position': 19
            }
        ]
        self.mock_ner_instance.extract_entities.return_value = mock_entities
        
        # Test articles
        articles = [
            {
                'article_id': 'test_1',
                'title': 'Apple News',
                'content': 'Apple Inc. CEO Tim Cook announced...',
                'url': 'https://example.com/apple-news'
            }
        ]
        
        processor = NERArticleProcessor(**self.config)
        results = processor.process_articles(articles)
        
        # Verify results
        self.assertEqual(len(results), 1)
        result = results[0]
        
        # Check that sentiment data is preserved
        self.assertEqual(result['article_id'], 'test_1')
        self.assertEqual(result['sentiment'], 'positive')
        
        # Check that NER data is added
        self.assertIn('entities', result)
        self.assertEqual(len(result['entities']), 2)
        self.assertEqual(result['entity_count'], 2)
        self.assertIn('ORGANIZATION', result['entity_types'])
        self.assertIn('PERSON', result['entity_types'])
        
        # Verify NER processor was called
        self.mock_ner_instance.extract_entities.assert_called_once()
    
    @patch('src.nlp.ner_article_processor.ArticleProcessor.process_articles')
    def test_process_articles_without_ner(self, mock_parent_process):
        """Test article processing with NER disabled."""
        config = self.config.copy()
        config['ner_enabled'] = False
        
        mock_sentiment_results = [
            {
                'article_id': 'test_1',
                'sentiment': 'positive',
                'confidence': 0.85
            }
        ]
        mock_parent_process.return_value = mock_sentiment_results
        
        articles = [
            {
                'article_id': 'test_1',
                'title': 'Test Article',
                'content': 'Test content...',
                'url': 'https://example.com/test'
            }
        ]
        
        processor = NERArticleProcessor(**config)
        results = processor.process_articles(articles)
        
        # Should return sentiment results without NER data
        self.assertEqual(results, mock_sentiment_results)
    
    def test_store_entities(self):
        """Test entity storage in database."""
        processor = NERArticleProcessor(**self.config)
        
        entities = [
            {
                'article_id': 'test_1',
                'entity_text': 'Apple Inc.',
                'entity_type': 'ORGANIZATION',
                'confidence': 0.9,
                'start_position': 0,
                'end_position': 10
            }
        ]
        
        processor._store_entities(entities)
        
        # Verify database operations
        self.mock_cursor.execute.assert_called()
        self.mock_conn.commit.assert_called()
    
    def test_update_articles_with_entities(self):
        """Test updating main articles table with entity JSON."""
        processor = NERArticleProcessor(**self.config)
        
        results = [
            {
                'article_id': 'test_1',
                'entities': [
                    {
                        'text': 'Apple Inc.',
                        'type': 'ORGANIZATION',
                        'confidence': 0.9
                    }
                ]
            }
        ]
        
        processor._update_articles_with_entities(results)
        
        # Verify database update was called
        self.mock_cursor.execute.assert_called()
        self.mock_conn.commit.assert_called()
    
    def test_entity_statistics(self):
        """Test entity statistics retrieval."""
        processor = NERArticleProcessor(**self.config)
        
        # Mock database results
        self.mock_cursor.fetchall.side_effect = [
            [('PERSON', 10, 5, 0.85, 0.7, 0.95)],  # entity_statistics
            [('Apple Inc.', 'ORGANIZATION', 3, 0.9, 2)]  # common_entities
        ]
        
        # Mock NER processor statistics
        self.mock_ner_instance.get_statistics.return_value = {
            'total_texts_processed': 5,
            'total_entities_extracted': 15
        }
        
        stats = processor.get_entity_statistics()
        
        # Verify structure
        self.assertIn('ner_processor_stats', stats)
        self.assertIn('entity_type_statistics', stats)
        self.assertIn('most_common_entities', stats)
        
        # Check entity type statistics
        entity_stats = stats['entity_type_statistics'][0]
        self.assertEqual(entity_stats['type'], 'PERSON')
        self.assertEqual(entity_stats['count'], 10)
        self.assertEqual(entity_stats['avg_confidence'], 0.85)
    
    def test_search_entities(self):
        """Test entity search functionality."""
        processor = NERArticleProcessor(**self.config)
        
        # Mock database results
        self.mock_cursor.fetchall.return_value = [
            ('Apple Inc.', 'ORGANIZATION', 0.9, 'test_1', 'Apple News', 'https://example.com', datetime.now())
        ]
        
        results = processor.search_entities(
            entity_text='Apple',
            entity_type='ORGANIZATION',
            min_confidence=0.8
        )
        
        # Verify results
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result['entity_text'], 'Apple Inc.')
        self.assertEqual(result['entity_type'], 'ORGANIZATION')
        self.assertEqual(result['confidence'], 0.9)
    
    def test_create_ner_article_processor_factory(self):
        """Test the factory function for creating NER article processors."""
        processor = create_ner_article_processor(**self.config)
        
        self.assertIsInstance(processor, NERArticleProcessor)


class TestNERIntegration(unittest.TestCase):
    """Integration tests for NER functionality."""
    
    @patch('src.nlp.ner_processor.pipeline')
    @patch('src.nlp.ner_article_processor.psycopg2')
    @patch('src.nlp.article_processor.psycopg2')
    def test_end_to_end_processing(self, mock_psycopg2_article, mock_psycopg2_ner, mock_pipeline):
        """Test end-to-end NER processing pipeline."""
        # Mock transformers pipeline
        mock_ner = Mock()
        mock_pipeline.return_value = mock_ner
        
        # Mock NER results
        mock_ner.return_value = [
            {
                'word': 'OpenAI',
                'entity_group': 'ORG',
                'score': 0.95,
                'start': 0,
                'end': 6
            },
            {
                'word': 'GPT-4',
                'entity_group': 'MISC',
                'score': 0.88,
                'start': 15,
                'end': 20
            }
        ]
        
        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_psycopg2_ner.connect.return_value.__enter__.return_value = mock_conn
        mock_psycopg2_article.connect.return_value.__enter__.return_value = mock_conn
        
        # Test article
        articles = [
            {
                'article_id': 'ai_news_1',
                'title': 'OpenAI Releases GPT-4',
                'content': 'OpenAI today released GPT-4, their most advanced language model...',
                'url': 'https://example.com/ai-news'
            }
        ]
        
        # Process with NER
        with patch('src.nlp.sentiment_analysis.create_analyzer'):
            processor = NERArticleProcessor(
                redshift_host='test-host',
                redshift_port=5439,
                redshift_database='test-db',
                redshift_user='test-user',
                redshift_password='test-password',
                sentiment_provider=None,  # Use None to get default model
                ner_enabled=True
            )
        
        # Mock parent class processing
        with patch.object(processor.__class__.__bases__[0], 'process_articles') as mock_parent:
            mock_parent.return_value = [
                {
                    'article_id': 'ai_news_1',
                    'sentiment': 'positive',
                    'confidence': 0.8
                }
            ]
            
            results = processor.process_articles(articles)
        
        # Verify results
        self.assertEqual(len(results), 1)
        result = results[0]
        
        # Check NER results
        self.assertIn('entities', result)
        entities = result['entities']
        
        # Should have 2 entities: OpenAI (TECHNOLOGY) and GPT-4 (MISCELLANEOUS)
        self.assertEqual(len(entities), 2)
        
        # Find OpenAI entity
        openai_entity = next(e for e in entities if 'OpenAI' in e['text'])
        self.assertEqual(openai_entity['type'], 'TECHNOLOGY')
        self.assertGreaterEqual(openai_entity['confidence'], 0.95)
        
        # Find GPT-4 entity (should be classified as MISCELLANEOUS)
        gpt_entity = next(e for e in entities if 'GPT-4' in e['text'])
        self.assertEqual(gpt_entity['type'], 'MISCELLANEOUS')
        self.assertGreaterEqual(gpt_entity['confidence'], 0.88)


if __name__ == '__main__':
    unittest.main()
