import os
import sys
import pytest
import boto3
from moto import mock_s3
from datetime import datetime
from botocore.exceptions import ClientError

# Add src directory to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from database.s3_storage import S3Storage

@pytest.fixture
def s3_client():
    with mock_s3():
        s3 = boto3.client('s3', region_name='us-east-1')
        yield s3

@pytest.fixture
def s3_bucket(s3_client):
    bucket_name = 'test-bucket'
    s3_client.create_bucket(Bucket=bucket_name)
    return bucket_name

@pytest.fixture
def s3_storage(s3_bucket):
    return S3Storage(bucket_name=s3_bucket)

def test_initialize_s3_storage_success(s3_bucket):
    storage = S3Storage(bucket_name=s3_bucket)
    assert storage.bucket_name == s3_bucket
    assert storage.s3_client is not None

def test_initialize_s3_storage_bucket_not_found():
    with pytest.raises(ClientError):
        S3Storage(bucket_name='non-existent-bucket')

def test_generate_s3_key():
    storage = S3Storage(bucket_name='test')
    article = {
        'source': 'test-source',
        'published_date': '2025-01-01'
    }
    key = storage._generate_s3_key(article)
    assert key.startswith('2025/01/01/test-source/')
    assert key.endswith('.json')

def test_upload_article_success(s3_storage, s3_client):
    article = {
        'id': 'test-123',
        'title': 'Test Article',
        'content': 'Test content',
        'source': 'test-source',
        'published_date': '2025-01-01'
    }
    
    key = s3_storage.upload_article(article)
    
    assert key is not None
    response = s3_client.get_object(Bucket=s3_storage.bucket_name, Key=key)
    assert response['ResponseMetadata']['HTTPStatusCode'] == 200

def test_upload_article_missing_fields(s3_storage):
    article = {
        'title': 'Test Article'
    }
    
    with pytest.raises(ValueError):
        s3_storage.upload_article(article)

def test_get_article_success(s3_storage, s3_client):
    article = {
        'id': 'test-123',
        'title': 'Test Article',
        'content': 'Test content',
        'source': 'test-source',
        'published_date': '2025-01-01'
    }
    
    key = s3_storage.upload_article(article)
    retrieved_article = s3_storage.get_article(key)
    
    assert retrieved_article['id'] == article['id']
    assert retrieved_article['title'] == article['title']

def test_list_articles_success(s3_storage):
    articles = [
        {
            'id': f'test-{i}',
            'title': f'Test Article {i}',
            'content': f'Test content {i}',
            'source': 'test-source',
            'published_date': '2025-01-01'
        }
        for i in range(3)
    ]
    
    for article in articles:
        s3_storage.upload_article(article)
    
    listed_articles = s3_storage.list_articles()
    assert len(listed_articles) == 3

def test_delete_article_success(s3_storage, s3_client):
    article = {
        'id': 'test-123',
        'title': 'Test Article',
        'content': 'Test content',
        'source': 'test-source',
        'published_date': '2025-01-01'
    }
    
    key = s3_storage.upload_article(article)
    s3_storage.delete_article(key)
    
    with pytest.raises(ClientError):
        s3_client.get_object(Bucket=s3_storage.bucket_name, Key=key)

def test_upload_file_success(s3_storage, tmpdir):
    content = "test content"
    file_path = tmpdir.join("test.txt")
    file_path.write(content)
    
    key = s3_storage.upload_file(str(file_path), 'test/test.txt')
    assert key == 'test/test.txt'

def test_download_file_success(s3_storage, s3_client, tmpdir):
    content = "test content"
    source_path = tmpdir.join("source.txt")
    source_path.write(content)
    
    key = s3_storage.upload_file(str(source_path), 'test/test.txt')
    
    download_path = tmpdir.join("downloaded.txt")
    s3_storage.download_file(key, str(download_path))
    
    assert download_path.read() == content