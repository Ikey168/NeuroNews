"""
Tests for the S3Storage module.
"""
import os
import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from src.database.s3_storage import S3Storage

# Test data
SAMPLE_ARTICLE = {
    'title': 'Test Article',
    'source': 'example.com',
    'content': 'Test content',
    'author': 'Test Author',
    'published_date': '2025-04-09'
}

@pytest.fixture
def s3_storage():
    """Create S3Storage instance with mocked S3 client."""
    with patch('boto3.client') as mock_boto3_client:
        # Mock successful bucket check
        mock_client = MagicMock()
        mock_boto3_client.return_value = mock_client
        
        storage = S3Storage(
            bucket_name='test-bucket',
            aws_access_key_id='test-key',
            aws_secret_access_key='test-secret'
        )
        storage.s3_client = mock_client
        return storage

def test_initialize_s3_storage_success(s3_storage):
    """Test successful S3Storage initialization."""
    assert s3_storage.bucket_name == 'test-bucket'
    assert s3_storage.prefix == 'news_articles'

def test_initialize_s3_storage_bucket_not_found():
    """Test S3Storage initialization with non-existent bucket."""
    with patch('boto3.client') as mock_boto3_client:
        mock_client = MagicMock()
        error_response = {
            'Error': {
                'Code': '404',
                'Message': 'Not Found'
            }
        }
        mock_client.head_bucket.side_effect = ClientError(error_response, 'HeadBucket')
        mock_boto3_client.return_value = mock_client
        
        with pytest.raises(ValueError, match='Bucket test-bucket does not exist'):
            S3Storage(bucket_name='test-bucket')

def test_generate_s3_key(s3_storage):
    """Test S3 key generation."""
    key = s3_storage.generate_s3_key('example.com', 'Test Article')
    
    # Verify key format
    assert key.startswith('news_articles/example-com/')
    assert 'test-article' in key
    assert key.endswith('.json')

def test_upload_article_success(s3_storage):
    """Test successful article upload."""
    # Setup mock
    s3_storage.s3_client.put_object.return_value = {}
    
    # Upload article
    key = s3_storage.upload_article(SAMPLE_ARTICLE)
    
    # Verify S3 client was called correctly
    s3_storage.s3_client.put_object.assert_called_once()
    call_args = s3_storage.s3_client.put_object.call_args[1]
    assert call_args['Bucket'] == 'test-bucket'
    assert 'news_articles' in call_args['Key']
    assert call_args['ContentType'] == 'application/json'
    
    # Verify metadata
    metadata = call_args['Metadata']
    assert metadata['title'] == SAMPLE_ARTICLE['title']
    assert metadata['source'] == SAMPLE_ARTICLE['source']
    assert metadata['author'] == SAMPLE_ARTICLE['author']
    assert 'scraped_at' in metadata

def test_upload_article_missing_fields(s3_storage):
    """Test article upload with missing required fields."""
    invalid_article = {
        'title': 'Test Article',
        'source': 'example.com'
        # Missing 'content' field
    }
    
    with pytest.raises(ValueError, match='Missing required article fields'):
        s3_storage.upload_article(invalid_article)

def test_get_article_success(s3_storage):
    """Test successful article retrieval."""
    # Setup mock
    mock_response = {
        'Body': MagicMock(),
        'Metadata': {'title': 'Test Article'}
    }
    mock_response['Body'].read.return_value = json.dumps(SAMPLE_ARTICLE).encode()
    s3_storage.s3_client.get_object.return_value = mock_response
    
    # Get article
    result = s3_storage.get_article('test-key')
    
    # Verify result
    assert result['data'] == SAMPLE_ARTICLE
    assert result['metadata'] == {'title': 'Test Article'}

def test_list_articles_success(s3_storage):
    """Test successful article listing."""
    # Setup mock
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{
        'Contents': [
            {
                'Key': 'test-key-1',
                'Size': 100,
                'LastModified': datetime.now()
            }
        ]
    }]
    s3_storage.s3_client.get_paginator.return_value = mock_paginator
    
    # Mock head_object response
    s3_storage.s3_client.head_object.return_value = {
        'Metadata': {'title': 'Test Article'}
    }
    
    # List articles
    articles = s3_storage.list_articles()
    
    # Verify results
    assert len(articles) == 1
    assert articles[0]['key'] == 'test-key-1'
    assert articles[0]['metadata'] == {'title': 'Test Article'}

def test_delete_article_success(s3_storage):
    """Test successful article deletion."""
    # Setup mock
    s3_storage.s3_client.delete_object.return_value = {}
    
    # Delete article
    s3_storage.delete_article('test-key')
    
    # Verify S3 client was called correctly
    s3_storage.s3_client.delete_object.assert_called_once_with(
        Bucket='test-bucket',
        Key='test-key'
    )

def test_upload_file_success(s3_storage, tmp_path):
    """Test successful file upload."""
    # Create test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    
    # Setup mock
    s3_storage.s3_client.upload_file.return_value = {}
    
    # Upload file
    key = s3_storage.upload_file(str(test_file))
    
    # Verify S3 client was called correctly
    s3_storage.s3_client.upload_file.assert_called_once()
    call_args = s3_storage.s3_client.upload_file.call_args[0]
    assert call_args[0] == str(test_file)
    assert call_args[1] == 'test-bucket'
    assert 'news_articles/files/test.txt' in call_args[2]

def test_download_file_success(s3_storage, tmp_path):
    """Test successful file download."""
    # Setup mock
    s3_storage.s3_client.download_file.return_value = {}
    
    # Download file
    destination = tmp_path / "downloaded.txt"
    s3_storage.download_file('test-key', str(destination))
    
    # Verify S3 client was called correctly
    s3_storage.s3_client.download_file.assert_called_once_with(
        'test-bucket',
        'test-key',
        str(destination)
    )