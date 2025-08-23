from src.database.s3_storage import S3Storage
import json
import os
import sys

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

# Add src directory to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))


@pytest.fixture(autouse=True)
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def s3_client(aws_credentials):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        yield s3


@pytest.fixture
def s3_bucket(s3_client):
    bucket_name = "test-bucket"
    s3_client.create_bucket(Bucket=bucket_name)
    return bucket_name


@pytest.fixture
def s3_storage(s3_bucket):
    return S3Storage(bucket_name=s3_bucket)


@mock_aws
def test_initialize_s3_storage_success(s3_bucket):
    storage = S3Storage(bucket_name=s3_bucket)
    assert storage.bucket_name == s3_bucket
    assert storage.s3_client is not None


@mock_aws
def test_initialize_s3_storage_bucket_not_found():
    with pytest.raises(ValueError, match="Bucket non-existent-bucket does not exist"):
        S3Storage(bucket_name="non-existent-bucket")


@mock_aws
def test_generate_s3_key(s3_bucket):
    storage = S3Storage(bucket_name=s3_bucket)
    article = {"source": "test-source", "published_date": "2025-01-01"}
    key = storage._generate_s3_key(article)
    assert "news_articles/2025/01/01/test-source/" in key
    assert key.endswith(".json")


@mock_aws
def test_upload_article_success(s3_storage, s3_client):
    article = {
        "id": "test-123",
        "title": "Test Article",
        "content": "Test content",
        "source": "test-source",
        "published_date": "2025-01-01",
    }

    key = s3_storage.upload_article(article)

    assert key is not None
    response = s3_client.get_object(Bucket=s3_storage.bucket_name, Key=key)
    content = json.loads(response["Body"].read().decode())

    # Check that original article data is preserved
    for key_field, value in article.items():
        assert content[key_field] == value

    # Check that additional metadata is added
    assert "content_hash" in content
    assert "scraped_date" in content
    assert "storage_type" in content


@mock_aws
def test_upload_article_missing_fields(s3_storage):
    article = {"title": "Test Article"}

    with pytest.raises(ValueError):
        s3_storage.upload_article(article)


@mock_aws
def test_get_article_success(s3_storage, s3_client):
    article = {
        "id": "test-123",
        "title": "Test Article",
        "content": "Test content",
        "source": "test-source",
        "published_date": "2025-01-01",
    }

    # Upload article as JSON
    key = f"test/{article['id']}.json"
    s3_client.put_object(Bucket=s3_storage.bucket_name, Key=key, Body=json.dumps(article))

    # Retrieve and verify
    retrieved_article = s3_storage.get_article(key)
    assert retrieved_article["id"] == article["id"]
    assert retrieved_article["title"] == article["title"]


@mock_aws
def test_list_articles_success(s3_storage):
    articles = [
        {
            "id": "test-{0}".format(i),
            "title": "Test Article {0}".format(i),
            "content": "Test content {0}".format(i),
            "source": "test-source",
            "published_date": "2025-01-01",
        }
        for i in range(3)
    ]

    for article in articles:
        s3_storage.upload_article(article)

    listed_articles = s3_storage.list_articles()
    assert len(listed_articles) == 3


@mock_aws
def test_delete_article_success(s3_storage, s3_client):
    article = {
        "id": "test-123",
        "title": "Test Article",
        "content": "Test content",
        "source": "test-source",
        "published_date": "2025-01-01",
    }

    key = s3_storage.upload_article(article)
    s3_storage.delete_article(key)

    with pytest.raises(ClientError):
        s3_client.get_object(Bucket=s3_storage.bucket_name, Key=key)


@mock_aws
def test_upload_file_success(s3_storage, tmpdir):
    content = "test content"
    file_path = tmpdir.join("test.txt")
    file_path.write(content)

    key = s3_storage.upload_file(str(file_path), "test/test.txt")
    assert key == "test/test.txt"


@mock_aws
def test_download_file_success(s3_storage, s3_client, tmpdir):
    content = "test content"
    source_path = tmpdir.join("source.txt")
    source_path.write(content)

    key = s3_storage.upload_file(str(source_path), "test/test.txt")

    download_path = tmpdir.join("downloaded.txt")
    s3_storage.download_file(key, str(download_path))

    assert download_path.read() == content
