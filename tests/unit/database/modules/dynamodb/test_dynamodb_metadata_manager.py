"""
Comprehensive tests for DynamoDB Metadata Manager module
Tests all components: DynamoDBMetadataManager, DynamoDBMetadataConfig, ArticleMetadataIndex
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Guard optional boto3 dependency so collection never crashes.
pytest.importorskip("boto3")

# Patch targets: the manager looks up get_resource / get_client in its own
# module namespace (imported from src.utils.local_cloud), and uses Key / Attr
# imported at module scope from boto3.dynamodb.conditions.
SOURCE_MODULE = "src.database.dynamodb_metadata_manager"


def _make_manager(table_mock=None):
    """Construct a DynamoDBMetadataManager with the local-cloud factories mocked.

    Returns (manager, table_mock). The table is the object returned by
    ``dynamodb.Table(...)`` inside the manager.
    """
    from src.database.dynamodb_metadata_manager import (
        DynamoDBMetadataManager,
        DynamoDBMetadataConfig,
    )

    if table_mock is None:
        table_mock = MagicMock()

    mock_resource = Mock()
    mock_resource.Table.return_value = table_mock
    mock_client = Mock()

    with patch(SOURCE_MODULE + ".get_resource", return_value=mock_resource), \
         patch(SOURCE_MODULE + ".get_client", return_value=mock_client):
        config = DynamoDBMetadataConfig(table_name="test_articles")
        manager = DynamoDBMetadataManager(config)

    return manager, table_mock


class TestDynamoDBMetadataConfig:
    """Tests for DynamoDBMetadataConfig class"""

    def test_config_initialization(self):
        """Test DynamoDB configuration initialization"""
        from src.database.dynamodb_metadata_manager import DynamoDBMetadataConfig

        # Test with all parameters
        config = DynamoDBMetadataConfig(
            table_name='test_articles',
            region='us-east-1',
            endpoint_url='http://localhost:8000'
        )

        assert config.table_name == 'test_articles'
        assert config.region == 'us-east-1'
        assert config.endpoint_url == 'http://localhost:8000'

    def test_config_defaults(self):
        """Test default configuration values"""
        from src.database.dynamodb_metadata_manager import DynamoDBMetadataConfig

        config = DynamoDBMetadataConfig(table_name='test_table')

        assert config.table_name == 'test_table'
        assert config.region is not None
        assert hasattr(config, 'endpoint_url')


class TestArticleMetadataIndex:
    """Tests for ArticleMetadataIndex class"""

    def test_article_metadata_initialization(self):
        """Test ArticleMetadataIndex initialization"""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        # Test with all fields
        metadata = ArticleMetadataIndex(
            article_id='test_123',
            title='Test Article Title',
            source='test-source.com',
            url='https://test-source.com/article',
            published_date='2024-01-15T10:30:00Z',
            content_hash='abcdef123456',
            author='Test Author',
            tags=['test', 'article', 'news'],
            category='technology',
            language='en',
            word_count=1500,
            content_summary='Test article summary'
        )

        assert metadata.article_id == 'test_123'
        assert metadata.title == 'Test Article Title'
        assert metadata.source == 'test-source.com'
        assert metadata.url == 'https://test-source.com/article'
        assert metadata.published_date == '2024-01-15T10:30:00Z'
        assert metadata.content_hash == 'abcdef123456'
        assert metadata.author == 'Test Author'
        assert metadata.tags == ['test', 'article', 'news']
        assert metadata.category == 'technology'
        assert metadata.language == 'en'
        assert metadata.word_count == 1500
        assert metadata.content_summary == 'Test article summary'

    def test_article_metadata_minimal(self):
        """Test ArticleMetadataIndex with minimal required fields"""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        metadata = ArticleMetadataIndex(
            article_id='minimal_123',
            title='Minimal Article',
            source='minimal.com',
            url='https://minimal.com/article',
            published_date='2024-01-16',
            content_hash='minimal123'
        )

        assert metadata.article_id == 'minimal_123'
        assert metadata.title == 'Minimal Article'
        assert metadata.source == 'minimal.com'

    def test_to_dynamodb_item(self):
        """Test conversion to DynamoDB item format"""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        metadata = ArticleMetadataIndex(
            article_id='convert_123',
            title='Conversion Test Article',
            source='convert.com',
            url='https://convert.com/article',
            published_date='2024-01-17T15:45:00Z',
            content_hash='convert456',
            author='Conversion Author',
            tags=['conversion', 'test'],
            category='testing',
            language='en',
            word_count=2000,
            content_summary='Conversion test summary'
        )

        dynamodb_item = metadata.to_dynamodb_item()

        # Verify item structure
        assert isinstance(dynamodb_item, dict)
        assert dynamodb_item['article_id'] == 'convert_123'
        assert dynamodb_item['title'] == 'Conversion Test Article'
        assert dynamodb_item['source'] == 'convert.com'
        assert dynamodb_item['url'] == 'https://convert.com/article'
        assert dynamodb_item['published_date'] == '2024-01-17T15:45:00Z'
        assert dynamodb_item['content_hash'] == 'convert456'
        assert dynamodb_item['author'] == 'Conversion Author'
        assert dynamodb_item['tags'] == ['conversion', 'test']
        assert dynamodb_item['category'] == 'testing'
        assert dynamodb_item['language'] == 'en'
        assert dynamodb_item['word_count'] == 2000
        assert dynamodb_item['content_summary'] == 'Conversion test summary'

    def test_from_dynamodb_item(self):
        """Test creation from DynamoDB item format"""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        dynamodb_item = {
            'article_id': 'from_item_123',
            'title': 'From Item Test',
            'source': 'fromitem.com',
            'url': 'https://fromitem.com/test',
            'published_date': '2024-01-18T12:00:00Z',
            'content_hash': 'fromitem789',
            'author': 'From Item Author',
            'tags': ['from', 'item', 'test'],
            'category': 'testing',
            'language': 'en',
            'word_count': 1800,
            'content_summary': 'From item test summary'
        }

        metadata = ArticleMetadataIndex.from_dynamodb_item(dynamodb_item)

        assert metadata.article_id == 'from_item_123'
        assert metadata.title == 'From Item Test'
        assert metadata.source == 'fromitem.com'
        assert metadata.url == 'https://fromitem.com/test'
        assert metadata.published_date == '2024-01-18T12:00:00Z'
        assert metadata.content_hash == 'fromitem789'
        assert metadata.author == 'From Item Author'
        assert metadata.tags == ['from', 'item', 'test']
        assert metadata.category == 'testing'
        assert metadata.language == 'en'
        assert metadata.word_count == 1800
        assert metadata.content_summary == 'From item test summary'

    def test_roundtrip_conversion(self):
        """Test roundtrip conversion: metadata -> DynamoDB item -> metadata"""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        original_metadata = ArticleMetadataIndex(
            article_id='roundtrip_123',
            title='Roundtrip Test Article',
            source='roundtrip.com',
            url='https://roundtrip.com/article',
            published_date='2024-01-19T09:15:30Z',
            content_hash='roundtrip456',
            author='Roundtrip Author',
            tags=['roundtrip', 'conversion', 'test'],
            category='testing',
            language='en',
            word_count=2500,
            content_summary='Roundtrip conversion test'
        )

        # Convert to DynamoDB item and back
        dynamodb_item = original_metadata.to_dynamodb_item()
        reconstructed_metadata = ArticleMetadataIndex.from_dynamodb_item(dynamodb_item)

        # Verify all fields match
        assert reconstructed_metadata.article_id == original_metadata.article_id
        assert reconstructed_metadata.title == original_metadata.title
        assert reconstructed_metadata.source == original_metadata.source
        assert reconstructed_metadata.url == original_metadata.url
        assert reconstructed_metadata.published_date == original_metadata.published_date
        assert reconstructed_metadata.content_hash == original_metadata.content_hash
        assert reconstructed_metadata.author == original_metadata.author
        assert reconstructed_metadata.tags == original_metadata.tags
        assert reconstructed_metadata.category == original_metadata.category
        assert reconstructed_metadata.language == original_metadata.language
        assert reconstructed_metadata.word_count == original_metadata.word_count
        assert reconstructed_metadata.content_summary == original_metadata.content_summary

    def test_title_tokenization(self):
        """Test title tokenization functionality"""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        test_titles = [
            'Simple Title',
            'Technology News and Innovation Updates',
            'Breaking: Major Scientific Discovery Announced',
            'How to Build Better Software Applications',
            'COVID-19 Impact on Global Economy and Markets'
        ]

        for title in test_titles:
            metadata = ArticleMetadataIndex(
                article_id=f'token_{hash(title)}',
                title=title,
                source='token-test.com',
                url='https://token-test.com/article',
                published_date='2024-01-20T10:00:00Z',
                content_hash='token123'
            )

            # title_tokens is populated in __post_init__ for full-text search.
            assert isinstance(metadata.title_tokens, list)
            assert len(metadata.title_tokens) > 0
            assert all(isinstance(token, str) for token in metadata.title_tokens)


@pytest.mark.asyncio
class TestDynamoDBMetadataManager:
    """Tests for DynamoDBMetadataManager class"""

    @pytest.fixture(autouse=True)
    def setup_aws_mocking(self):
        """Setup AWS mocking for all tests"""
        # Set up environment variables for AWS
        os.environ['AWS_ACCESS_KEY_ID'] = 'test_key_id'
        os.environ['AWS_SECRET_ACCESS_KEY'] = 'test_secret_key'
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

        yield

        # Clean up environment variables
        for key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION']:
            if key in os.environ:
                del os.environ[key]

    async def test_manager_initialization(self):
        """Test DynamoDBMetadataManager initialization"""
        from src.database.dynamodb_metadata_manager import DynamoDBMetadataConfig

        manager, table = _make_manager()

        assert isinstance(manager.config, DynamoDBMetadataConfig)
        assert manager.config.table_name == 'test_articles'
        assert hasattr(manager, 'dynamodb')
        assert hasattr(manager, 'table')
        assert manager.table is table

    async def test_create_metadata_from_article(self):
        """Test creating metadata from article data"""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        manager, _ = _make_manager()

        article_data = {
            'id': 'article_123',
            'title': 'Test Article for Metadata Creation',
            'content': 'Comprehensive content for testing metadata creation functionality.',
            'url': 'https://test.com/article',
            'source': 'test.com',
            'published_date': '2024-01-21T14:30:00Z',
            'author': 'Test Author',
            'tags': ['test', 'metadata', 'creation'],
            'category': 'testing',
            'content_summary': 'Test article summary',
        }

        metadata = manager._create_metadata_from_article(article_data)

        assert isinstance(metadata, ArticleMetadataIndex)
        assert metadata.article_id == 'article_123'
        assert metadata.title == 'Test Article for Metadata Creation'
        assert metadata.source == 'test.com'
        assert metadata.url == 'https://test.com/article'

        # Content hash is generated from content via sha256.
        assert isinstance(metadata.content_hash, str)
        assert len(metadata.content_hash) > 0

    async def test_tokenize_search_query(self):
        """Test search query tokenization"""
        manager, _ = _make_manager()

        search_queries = [
            'machine learning artificial intelligence',
            'breaking news technology updates',
            'Python programming tutorial guide',
            'COVID-19 vaccine research results',
            'climate change environmental impact'
        ]

        for query in search_queries:
            tokens = manager._tokenize_search_query(query)
            assert isinstance(tokens, list)
            assert len(tokens) > 0
            assert all(isinstance(token, str) for token in tokens)
            assert all(len(token) > 0 for token in tokens)

    async def test_index_article_metadata(self):
        """Test indexing article metadata"""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        table = MagicMock()
        table.put_item.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        manager, table = _make_manager(table_mock=table)

        article_data = {
            'id': 'index_test_123',
            'title': 'Article for Indexing Test',
            'content': 'Content for testing article metadata indexing functionality.',
            'url': 'https://index-test.com/article',
            'source': 'index-test.com',
            'published_date': '2024-01-22T16:45:00Z',
            'author': 'Index Test Author',
            'tags': ['index', 'test', 'metadata'],
            'category': 'testing'
        }

        result = await manager.index_article_metadata(article_data)

        # Returns the indexed metadata record and writes to the table.
        assert isinstance(result, ArticleMetadataIndex)
        assert result.article_id == 'index_test_123'
        table.put_item.assert_called_once()

    async def test_get_article_by_id(self):
        """Test retrieving article by ID"""
        from src.database.dynamodb_metadata_manager import ArticleMetadataIndex

        mock_item_data = {
            'article_id': 'get_test_123',
            'title': 'Retrieved Article Test',
            'source': 'get-test.com',
            'url': 'https://get-test.com/article',
            'published_date': '2024-01-23T11:20:00Z',
            'content_hash': 'gettest456',
            'author': 'Get Test Author',
            'tags': ['get', 'test', 'retrieve'],
            'category': 'testing'
        }

        table = MagicMock()
        table.get_item.return_value = {
            'Item': mock_item_data,
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        manager, table = _make_manager(table_mock=table)

        result = await manager.get_article_by_id('get_test_123')

        assert isinstance(result, ArticleMetadataIndex)
        assert result.article_id == 'get_test_123'
        table.get_item.assert_called_once_with(Key={'article_id': 'get_test_123'})

    async def test_get_articles_by_source(self):
        """Test retrieving articles by source"""
        from src.database.dynamodb_metadata_manager import QueryResult

        mock_items = [
            {
                'article_id': f'source_test_{i}',
                'title': f'Source Test Article {i}',
                'source': 'source-test.com',
                'url': f'https://source-test.com/article-{i}',
                'published_date': f'2024-01-{24+i}T10:00:00Z',
                'content_hash': f'sourcetest{i}',
                'category': 'testing'
            }
            for i in range(5)
        ]

        table = MagicMock()
        # get_articles_by_source uses table.query against the source-date-index.
        table.query.return_value = {
            'Items': mock_items,
            'Count': len(mock_items),
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        manager, table = _make_manager(table_mock=table)

        result = await manager.get_articles_by_source('source-test.com')

        assert isinstance(result, QueryResult)
        assert result.count == 5
        table.query.assert_called_once()

    async def test_get_articles_by_date_range(self):
        """Test retrieving articles by date range"""
        from src.database.dynamodb_metadata_manager import QueryResult

        mock_items = [
            {
                'article_id': f'date_test_{i}',
                'title': f'Date Range Test Article {i}',
                'source': 'date-test.com',
                'url': f'https://date-test.com/article-{i}',
                'published_date': f'2024-01-{15+i}T{10+i}:00:00Z',
                'content_hash': f'datetest{i}',
                'category': 'testing'
            }
            for i in range(3)
        ]

        table = MagicMock()
        # get_articles_by_date_range uses table.scan with a between filter.
        table.scan.return_value = {
            'Items': mock_items,
            'Count': len(mock_items),
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        manager, table = _make_manager(table_mock=table)

        # Source signature expects ISO date strings, not datetime objects.
        result = await manager.get_articles_by_date_range('2024-01-15', '2024-01-25')

        assert isinstance(result, QueryResult)
        assert result.count == 3
        table.scan.assert_called_once()

    async def test_get_articles_by_tags(self):
        """Test retrieving articles by tags"""
        from src.database.dynamodb_metadata_manager import QueryResult

        mock_items = [
            {
                'article_id': f'tags_test_{i}',
                'title': f'Tags Test Article {i}',
                'source': 'tags-test.com',
                'url': f'https://tags-test.com/article-{i}',
                'published_date': f'2024-01-{20+i}T12:00:00Z',
                'content_hash': f'tagstest{i}',
                'tags': ['test', 'tags', f'tag{i}'],
                'category': 'testing'
            }
            for i in range(4)
        ]

        table = MagicMock()
        # get_articles_by_tags uses table.scan with a contains filter.
        table.scan.return_value = {
            'Items': mock_items,
            'Count': len(mock_items),
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        manager, table = _make_manager(table_mock=table)

        search_tags = ['test', 'tags']
        result = await manager.get_articles_by_tags(search_tags)

        assert isinstance(result, QueryResult)
        assert result.count == 4
        table.scan.assert_called_once()

    async def test_batch_index_articles(self):
        """Test batch indexing of multiple articles"""
        table = MagicMock()

        # Mock batch writer context manager.
        mock_batch_writer = MagicMock()
        table.batch_writer.return_value.__enter__ = Mock(return_value=mock_batch_writer)
        table.batch_writer.return_value.__exit__ = Mock(return_value=None)
        manager, table = _make_manager(table_mock=table)

        batch_articles = [
            {
                'id': f'batch_test_{i}',
                'title': f'Batch Test Article {i}',
                'content': f'Batch content for testing article {i}.',
                'url': f'https://batch-test.com/article-{i}',
                'source': 'batch-test.com',
                'published_date': f'2024-01-{25+i}T09:00:00Z',
                'author': f'Batch Author {i}',
                'tags': ['batch', 'test', f'article{i}'],
                'category': 'testing'
            }
            for i in range(10)
        ]

        result = await manager.batch_index_articles(batch_articles)

        # Returns a stats dict and writes via the batch writer.
        assert isinstance(result, dict)
        assert result['status'] == 'completed'
        assert result['total_articles'] == 10
        assert result['indexed_count'] == 10
        assert result['failed_count'] == 0
        table.batch_writer.assert_called()
        assert mock_batch_writer.put_item.call_count == 10
