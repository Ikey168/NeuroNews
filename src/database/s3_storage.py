"""
S3 storage module for NeuroNews.
Handles uploading and retrieving files from AWS S3.
"""
import os
import json
import boto3
import logging
from typing import Optional, Dict, Any, List
from botocore.exceptions import ClientError
from datetime import datetime
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

class S3Storage:
    """Handles S3 storage operations for NeuroNews."""

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
            error_code = e.response['Error']['Code']
            if error_code == '404':
                raise ValueError(f"Bucket {bucket_name} does not exist")
            elif error_code == '403':
                raise ValueError(f"Access denied to bucket {bucket_name}")
            else:
                raise

    def generate_s3_key(self, source: str, title: str) -> str:
        """
        Generate a unique S3 key for an article.
        
        Args:
            source: Source of the article (e.g., website domain)
            title: Article title
            
        Returns:
            Unique S3 key for the article
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        source_clean = source.replace('.', '-')
        title_slug = title.replace(' ', '-').lower()
        # Remove special characters
        title_slug = ''.join(c for c in title_slug if c.isalnum() or c == '-')
        return f"{self.prefix}/{source_clean}/{timestamp}_{title_slug[:50]}.json"

    def upload_article(
        self,
        article_data: Dict[str, Any],
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Upload an article to S3.
        
        Args:
            article_data: Dictionary containing article data
            metadata: Optional metadata to attach to the S3 object
            
        Returns:
            S3 key of the uploaded article
            
        Raises:
            ValueError: If required article fields are missing
            ClientError: If upload fails
        """
        required_fields = ['title', 'source', 'content']
        missing_fields = [field for field in required_fields if field not in article_data]
        if missing_fields:
            raise ValueError(f"Missing required article fields: {missing_fields}")
            
        # Generate S3 key
        s3_key = self.generate_s3_key(article_data['source'], article_data['title'])
        
        # Prepare metadata
        if metadata is None:
            metadata = {}
        metadata.update({
            'title': article_data.get('title', '')[:255],  # S3 metadata values limited to 2048 bytes
            'source': article_data.get('source', '')[:255],
            'published_date': article_data.get('published_date', '')[:255],
            'author': article_data.get('author', '')[:255],
            'scraped_at': datetime.now().isoformat()[:255]
        })
        
        try:
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(article_data, ensure_ascii=False),
                ContentType='application/json',
                Metadata=metadata
            )
            logger.info(f"Successfully uploaded article to S3: {s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"Failed to upload article to S3: {e}")
            raise

    def get_article(self, s3_key: str) -> Dict[str, Any]:
        """
        Retrieve an article from S3.
        
        Args:
            s3_key: S3 key of the article
            
        Returns:
            Dictionary containing article data and metadata
            
        Raises:
            ClientError: If retrieval fails
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            article_data = json.loads(response['Body'].read().decode('utf-8'))
            metadata = response.get('Metadata', {})
            
            return {
                'data': article_data,
                'metadata': metadata
            }
        except ClientError as e:
            logger.error(f"Failed to retrieve article from S3: {e}")
            raise

    def list_articles(
        self,
        prefix: Optional[str] = None,
        max_items: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        List articles in the S3 bucket.
        
        Args:
            prefix: Optional prefix to filter articles (e.g., specific source)
            max_items: Maximum number of items to return
            
        Returns:
            List of dictionaries containing article keys and metadata
        """
        if prefix is None:
            prefix = self.prefix
            
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            articles = []
            for page in page_iterator:
                if 'Contents' not in page:
                    continue
                    
                for obj in page['Contents']:
                    # Get object metadata
                    response = self.s3_client.head_object(
                        Bucket=self.bucket_name,
                        Key=obj['Key']
                    )
                    
                    articles.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'],
                        'metadata': response.get('Metadata', {})
                    })
                    
                    if max_items and len(articles) >= max_items:
                        return articles[:max_items]
                        
            return articles
        except ClientError as e:
            logger.error(f"Failed to list articles in S3: {e}")
            raise

    def delete_article(self, s3_key: str) -> None:
        """
        Delete an article from S3.
        
        Args:
            s3_key: S3 key of the article to delete
            
        Raises:
            ClientError: If deletion fails
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            logger.info(f"Successfully deleted article from S3: {s3_key}")
        except ClientError as e:
            logger.error(f"Failed to delete article from S3: {e}")
            raise

    def upload_file(
        self,
        file_path: str,
        s3_key: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Upload a file to S3.
        
        Args:
            file_path: Path to the file to upload
            s3_key: Optional S3 key. If None, will use file name
            metadata: Optional metadata to attach to the S3 object
            
        Returns:
            S3 key of the uploaded file
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ClientError: If upload fails
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
            
        if s3_key is None:
            s3_key = f"{self.prefix}/files/{Path(file_path).name}"
            
        try:
            extra_args = {'Metadata': metadata} if metadata else {}
            self.s3_client.upload_file(
                file_path,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )
            logger.info(f"Successfully uploaded file to S3: {s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"Failed to upload file to S3: {e}")
            raise

    def download_file(self, s3_key: str, destination_path: str) -> None:
        """
        Download a file from S3.
        
        Args:
            s3_key: S3 key of the file to download
            destination_path: Local path where to save the file
            
        Raises:
            ClientError: If download fails
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            
            self.s3_client.download_file(
                self.bucket_name,
                s3_key,
                destination_path
            )
            logger.info(f"Successfully downloaded file from S3: {s3_key}")
        except ClientError as e:
            logger.error(f"Failed to download file from S3: {e}")
            raise