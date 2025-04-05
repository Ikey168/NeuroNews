"""
Command-line interface for running the NeuroNews scrapers.
"""
import argparse
import os
import sys
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from .spiders.news_spider import NewsSpider
from .spiders.playwright_spider import PlaywrightNewsSpider
from .pipelines.s3_pipeline import S3StoragePipeline


def run_spider(output_file=None, use_playwright=False, s3_storage=False, 
               aws_access_key_id=None, aws_secret_access_key=None, 
               s3_bucket=None, s3_prefix=None):
    """
    Run the news spider.
    
    Args:
        output_file (str, optional): Path to save the scraped data.
        use_playwright (bool, optional): Whether to use Playwright for JavaScript-heavy pages.
        s3_storage (bool, optional): Whether to store articles in S3.
        aws_access_key_id (str, optional): AWS access key ID.
        aws_secret_access_key (str, optional): AWS secret access key.
        s3_bucket (str, optional): S3 bucket name.
        s3_prefix (str, optional): S3 key prefix.
    """
    settings = get_project_settings()
    
    # Override the output file if specified
    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        settings.set('FEED_URI', output_file)
        settings.set('FEED_FORMAT', 'json')
    
    # Configure S3 storage if enabled
    if s3_storage:
        # Add S3 pipeline to the pipeline
        pipelines = dict(settings.get('ITEM_PIPELINES'))
        pipelines['src.scraper.pipelines.s3_pipeline.S3StoragePipeline'] = settings.get('S3_PIPELINE_PRIORITY', 400)
        settings.set('ITEM_PIPELINES', pipelines)
        
        # Set AWS credentials and S3 settings
        if aws_access_key_id:
            settings.set('AWS_ACCESS_KEY_ID', aws_access_key_id)
        if aws_secret_access_key:
            settings.set('AWS_SECRET_ACCESS_KEY', aws_secret_access_key)
        if s3_bucket:
            settings.set('S3_BUCKET', s3_bucket)
        if s3_prefix:
            settings.set('S3_PREFIX', s3_prefix)
    
    process = CrawlerProcess(settings)
    
    # Choose which spider to run
    if use_playwright:
        process.crawl(PlaywrightNewsSpider)
    else:
        process.crawl(NewsSpider)
    
    process.start()


def main():
    """Main entry point for the scraper CLI."""
    parser = argparse.ArgumentParser(description='NeuroNews Scraper')
    parser.add_argument(
        '--output', '-o',
        help='Output file path (default: data/news_articles.json)',
        default='data/news_articles.json'
    )
    parser.add_argument(
        '--list-sources', '-l',
        action='store_true',
        help='List the configured news sources'
    )
    parser.add_argument(
        '--playwright', '-p',
        action='store_true',
        help='Use Playwright for JavaScript-heavy pages'
    )
    
    # S3 storage options
    s3_group = parser.add_argument_group('S3 Storage Options')
    s3_group.add_argument(
        '--s3', '-s',
        action='store_true',
        help='Store articles in Amazon S3'
    )
    s3_group.add_argument(
        '--aws-key-id',
        help='AWS access key ID'
    )
    s3_group.add_argument(
        '--aws-secret-key',
        help='AWS secret access key'
    )
    s3_group.add_argument(
        '--s3-bucket',
        help='S3 bucket name'
    )
    s3_group.add_argument(
        '--s3-prefix',
        help='S3 key prefix (default: news_articles)',
        default='news_articles'
    )
    
    args = parser.parse_args()
    
    if args.list_sources:
        settings = get_project_settings()
        print("Configured news sources:")
        for source in settings.get('SCRAPING_SOURCES'):
            print(f"  - {source}")
        return
    
    # Check if S3 storage is enabled but required parameters are missing
    if args.s3 and not (os.environ.get('AWS_ACCESS_KEY_ID') or args.aws_key_id):
        parser.error("AWS access key ID is required for S3 storage. "
                    "Provide it with --aws-key-id or set the AWS_ACCESS_KEY_ID environment variable.")
    
    if args.s3 and not (os.environ.get('AWS_SECRET_ACCESS_KEY') or args.aws_secret_key):
        parser.error("AWS secret access key is required for S3 storage. "
                    "Provide it with --aws-secret-key or set the AWS_SECRET_ACCESS_KEY environment variable.")
    
    if args.s3 and not (os.environ.get('S3_BUCKET') or args.s3_bucket):
        parser.error("S3 bucket name is required for S3 storage. "
                    "Provide it with --s3-bucket or set the S3_BUCKET environment variable.")
    
    print(f"Starting NeuroNews scraper...")
    if args.playwright:
        print("Using Playwright for JavaScript-heavy pages")
    if args.s3:
        print(f"Storing articles in S3 bucket: {args.s3_bucket or os.environ.get('S3_BUCKET')}")
        print(f"S3 prefix: {args.s3_prefix}")
    print(f"Output will be saved to: {args.output}")
    
    run_spider(
        output_file=args.output,
        use_playwright=args.playwright,
        s3_storage=args.s3,
        aws_access_key_id=args.aws_key_id,
        aws_secret_access_key=args.aws_secret_key,
        s3_bucket=args.s3_bucket,
        s3_prefix=args.s3_prefix
    )
    print("Scraping completed.")


if __name__ == "__main__":
    main()
