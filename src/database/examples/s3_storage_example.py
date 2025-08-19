"""
Example usage of the S3Storage class.
"""

import os

from src.database.s3_storage import S3Storage


def main():
    """Example of using S3Storage."""
    # Initialize S3Storage
    # You can provide credentials directly or use environment variables
    storage = S3Storage(
        bucket_name=os.environ.get("S3_BUCKET", "neuronews-raw-articles-dev"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
    )

    # Example article data
    article = {
        "title": "Example News Article",
        "source": "example.com",
        "content": "This is the article content...",
        "author": "John Doe",
        "published_date": "2025-04-09",
        "url": "https://example.com/news/1",
        "categories": ["technology", "ai"],
    }

    try:
        # Upload article
        s3_key = storage.upload_article(
            article_data=article,
            metadata={"categories": ",".join(article["categories"])},
        )
        print(f"Successfully uploaded article: {s3_key}")

        # Retrieve the article
        retrieved = storage.get_article(s3_key)
        print("\nRetrieved article:")
        print(f"Title: {retrieved['data']['title']}")
        print(f"Author: {retrieved['data']['author']}")
        print(f"Categories: {retrieved['metadata'].get('categories')}")

        # List recent articles from the same source
        print("\nRecent articles from example.com:")
        articles = storage.list_articles(
            prefix=f"{storage.prefix}/example-com", max_items=5
        )
        for article in articles:
            print(
                f"- {article['metadata'].get('title')} "
                f"({article['last_modified'].strftime('%Y-%m-%d')})"
            )

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
