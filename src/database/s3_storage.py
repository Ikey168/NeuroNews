import os
import json
from typing import Dict, List, Any, Optional
import boto3
from botocore.exceptions import ClientError

class S3Storage:
    def __init__(
        self,
        bucket_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: str = "us-east-1",
        prefix: str = "news_articles"
    ):
        """
        Initialize S3 storage handler.

        Args:
            bucket_name: Name of the S3 bucket
            aws_access_key_id: AWS access key ID. If None, will use environment variables
            aws_secret_access_key: AWS secret access key. If None, will use environment variables
            aws_region: AWS region name (default: us-east-1)
            prefix: Prefix for S3 keys (default: news_articles)
        """
        self.bucket_name = bucket_name
        self.prefix = prefix

        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )

        # Verify bucket exists and is accessible
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                raise ValueError(f"Bucket {bucket_name} does not exist")
            elif error_code == 403:
                raise ValueError(f"Access denied to bucket {bucket_name}")
            raise

    def _generate_s3_key(self, article: Dict[str, Any]) -> str:
        """
        Generate S3 key for an article.

        Args:
            article: Article data dictionary containing at least source and published_date

        Returns:
            S3 key string
        """
        try:
            date_parts = article['published_date'].split('-')
            key = f"{date_parts[0]}/{date_parts[1]}/{date_parts[2]}/{article['source']}/"
            key += f"{article.get('id', self._generate_id())}.json"
            return os.path.join(self.prefix, key)
        except (KeyError, IndexError):
            raise ValueError("Article must contain 'source' and 'published_date' fields")

    def _generate_id(self) -> str:
        """Generate a unique ID for an article."""
        import uuid
        return str(uuid.uuid4())

    def upload_article(self, article: Dict[str, Any]) -> str:
        """
        Upload an article to S3.

        Args:
            article: Article data dictionary containing required fields

        Returns:
            S3 key where the article was stored

        Raises:
            ValueError: If required fields are missing
        """
        required_fields = ['title', 'content', 'source', 'published_date']
        missing_fields = [field for field in required_fields if field not in article]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        key = self._generate_s3_key(article)
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=json.dumps(article)
        )
        return key

    def get_article(self, key: str) -> Dict[str, Any]:
        """
        Get an article from S3.

        Args:
            key: S3 key for the article

        Returns:
            Article data dictionary
        """
        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
        article_json = response['Body'].read().decode('utf-8')
        return json.loads(article_json)

    def list_articles(self, prefix: Optional[str] = None) -> List[str]:
        """
        List all article keys in the bucket.

        Args:
            prefix: Optional prefix to filter keys

        Returns:
            List of S3 keys
        """
        prefix = prefix or self.prefix
        paginator = self.s3_client.get_paginator('list_objects_v2')
        keys = []
        
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            if 'Contents' in page:
                keys.extend([obj['Key'] for obj in page['Contents']])
        
        return keys

    def delete_article(self, key: str) -> None:
        """
        Delete an article from S3.

        Args:
            key: S3 key for the article
        """
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)

    def upload_file(self, local_path: str, s3_key: str) -> str:
        """
        Upload a file to S3.

        Args:
            local_path: Path to local file
            s3_key: Desired S3 key for the file

        Returns:
            S3 key where the file was stored
        """
        self.s3_client.upload_file(local_path, self.bucket_name, s3_key)
        return s3_key

    def download_file(self, s3_key: str, local_path: str) -> None:
        """
        Download a file from S3.

        Args:
            s3_key: S3 key of the file to download
            local_path: Local path where to save the file
        """
        self.s3_client.download_file(self.bucket_name, s3_key, local_path)