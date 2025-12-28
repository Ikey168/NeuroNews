import sys
from unittest.mock import MagicMock, patch

# Mock boto3 and botocore before importing modules that use them
sys.modules["boto3"] = MagicMock()
sys.modules["boto3.dynamodb.conditions"] = MagicMock()
sys.modules["botocore"] = MagicMock()
sys.modules["botocore.exceptions"] = MagicMock()

# Define ClientError mock
class ClientError(Exception):
    def __init__(self, response, operation_name):
        self.response = response
        self.operation_name = operation_name
        super().__init__(response)

sys.modules["botocore.exceptions"].ClientError = ClientError

import pytest
from datetime import datetime
from src.database.dynamodb_metadata_manager import ArticleMetadataIndex, DynamoDBMetadataManager, DynamoDBMetadataConfig

class TestArticleMetadataIndex:
    """Test ArticleMetadataIndex dataclass."""

    def test_initialization(self):
        """Test initialization and default values."""
        article = ArticleMetadataIndex(
            article_id="123",
            content_hash="abc",
            title="Test Article",
            source="Test Source",
            published_date="2023-01-01"
        )
        
        assert article.article_id == "123"
        assert article.content_hash == "abc"
        assert article.title == "Test Article"
        assert article.source == "Test Source"
        assert article.published_date == "2023-01-01"
        assert article.tags == []
        assert article.language == "en"
        assert article.processing_status == "indexed"
        assert article.indexed_date is not None
        assert article.last_updated is not None
        assert "test" in article.title_tokens
        assert "article" in article.title_tokens

    def test_to_dynamodb_item(self):
        """Test conversion to DynamoDB item."""
        article = ArticleMetadataIndex(
            article_id="123",
            content_hash="abc",
            title="Test Article",
            source="Test Source",
            published_date="2023-01-01",
            tags=["tag1", "tag2"],
            category="Tech"
        )
        
        item = article.to_dynamodb_item()
        
        assert item["article_id"] == "123"
        assert item["content_hash"] == "abc"
        assert item["title"] == "Test Article"
        assert item["source"] == "Test Source"
        assert item["published_date"] == "2023-01-01"
        assert item["tags"] == ["tag1", "tag2"]
        assert item["category"] == "Tech"
        assert item["source_date"] == "Test Source#2023-01-01"
        assert item["date_source"] == "2023-01-01#Test Source"
        assert item["category_date"] == "Tech#2023-01-01"
        assert item["year_month"] == "2023-01"
        assert item["tags_string"] == "tag1#tag2"

    def test_from_dynamodb_item(self):
        """Test creation from DynamoDB item."""
        item = {
            "article_id": "123",
            "content_hash": "abc",
            "title": "Test Article",
            "source": "Test Source",
            "published_date": "2023-01-01",
            "tags": ["tag1", "tag2"],
            "category": "Tech",
            "language": "en",
            "processing_status": "indexed"
        }
        
        article = ArticleMetadataIndex.from_dynamodb_item(item)
        
        assert article.article_id == "123"
        assert article.content_hash == "abc"
        assert article.title == "Test Article"
        assert article.source == "Test Source"
        assert article.published_date == "2023-01-01"
        assert article.tags == ["tag1", "tag2"]
        assert article.category == "Tech"
        assert article.language == "en"

class TestDynamoDBMetadataManager:
    """Test DynamoDBMetadataManager."""

    def test_initialization(self):
        """Test initialization."""
        config = DynamoDBMetadataConfig(table_name="test-table", region="us-west-2")
        
        with patch("src.database.dynamodb_metadata_manager.boto3.Session") as mock_session:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb
            
            manager = DynamoDBMetadataManager(config)
            
            assert manager.table_name == "test-table"
            mock_session.assert_called_with(region_name="us-west-2")
            mock_dynamodb.Table.assert_called_with("test-table")
            mock_table.meta.client.describe_table.assert_called_with(TableName="test-table")

    def test_create_table_if_not_exists(self):
        """Test table creation if it doesn't exist."""
        config = DynamoDBMetadataConfig(table_name="test-table")
        
        with patch("src.database.dynamodb_metadata_manager.boto3.Session") as mock_session:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            
            # Simulate ResourceNotFoundException
            error_response = {"Error": {"Code": "ResourceNotFoundException"}}
            mock_table.meta.client.describe_table.side_effect = ClientError(error_response, "DescribeTable")
            
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb
            
            # Mock create_table on the dynamodb resource
            mock_dynamodb.create_table.return_value = mock_table
            
            manager = DynamoDBMetadataManager(config)
            
            mock_dynamodb.create_table.assert_called()
            call_args = mock_dynamodb.create_table.call_args[1]
            assert call_args["TableName"] == "test-table"
