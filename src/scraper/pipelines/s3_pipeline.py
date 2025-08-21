"""
S3 storage pipeline for NeuroNews scrapers.
"""

import json
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from scrapy.exceptions import DropItem


class S3StoragePipeline:
    """Pipeline for storing scraped items in Amazon S3."""

    def __init__(self, aws_access_key_id, aws_secret_access_key, s3_bucket, s3_prefix):
        """Initialize the S3 storage pipeline."""
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix
        self.s3_client = None

    @classmethod
    def from_crawler(cls, crawler):
        """Create a new instance from the crawler settings."""
        return cls(
            aws_access_key_id=crawler.settings.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=crawler.settings.get("AWS_SECRET_ACCESS_KEY"),
            s3_bucket=crawler.settings.get("S3_BUCKET"),
            s3_prefix=crawler.settings.get("S3_PREFIX", "news_articles"),
        )

    def open_spider(self, spider):
        """Called when the spider is opened."""
        # Initialize S3 client
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )

        # Check if the bucket exists
        try:
            self.s3_client.head_bucket(Bucket=self.s3_bucket)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                spider.logger.error(
                    "S3 bucket {0} does not exist".format(self.s3_bucket)
                )
            elif error_code == "403":
                spider.logger.error(
                    "Access to S3 bucket {0} is forbidden".format(self.s3_bucket)
                )
            else:
                spider.logger.error(
                    "Error accessing S3 bucket {0}: {1}".format(self.s3_bucket, e)
                )
            raise DropItem("S3 bucket not accessible")

    def process_item(self, item, spider):
        """Process each scraped item."""
        if not self.s3_client:
            raise DropItem("S3 client not initialized")

        # Generate a unique key for the article
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        source_domain = item.get("source", "unknown").replace(".", "-")
        title_slug = item.get("title", "untitled")[:50].replace(" ", "-").lower()

        # Remove special characters from the title slug
        import re

        title_slug = re.sub(r"[^a-z0-9-]", "", title_slug)

        # Create the S3 key
        s3_key = "{0}/{1}/{2}_{3}.json".format(
            self.s3_prefix, source_domain, timestamp, title_slug
        )

        # Prepare metadata
        metadata = {
            "title": item.get("title", "Untitled"),
            "url": item.get("url", ""),
            "source": item.get("source", "Unknown"),
            "published_date": item.get("published_date", ""),
            "author": item.get("author", "Unknown"),
            "category": item.get("category", "General"),
            "scraped_at": datetime.now().isoformat(),
        }

        # Upload the full article to S3
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=json.dumps(dict(item), ensure_ascii=False),
                ContentType="application/json",
                Metadata={
                    "title": metadata["title"][
:255
                    ],  # S3 metadata values are limited to 2048 bytes
                    "url": metadata["url"][:255],
                    "source": metadata["source"][:255],
                    "published_date": metadata["published_date"][:255],
                    "author": metadata["author"][:255],
                    "category": metadata["category"][:255],
                    "scraped_at": metadata["scraped_at"][:255],
                },
            )
            spider.logger.info("Stored article in S3: {0}".format(s3_key))
        except ClientError as e:
            spider.logger.error("Failed to upload article to S3: {0}".format(e))
            raise DropItem("Failed to store in S3")

        return item
