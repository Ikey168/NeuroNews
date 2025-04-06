"""
Command-line interface for running the NeuroNews scrapers.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from .spiders.news_spider import NewsSpider
from .spiders.playwright_spider import PlaywrightNewsSpider
from .pipelines.s3_pipeline import S3StoragePipeline


def load_aws_config(env='dev'):
    """
    Load AWS configuration from config/dev_aws.json.
    
    Args:
        env (str): Environment name (dev, staging, prod).
        
    Returns:
        dict: AWS configuration.
    """
    config_path = Path(f"config/{env}_aws.json")
    if not config_path.exists():
        return {}
    
    with open(config_path, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Could not parse {config_path} as JSON.")
            return {}


def run_spider(output_file=None, use_playwright=False, s3_storage=False, 
               aws_access_key_id=None, aws_secret_access_key=None, 
               s3_bucket=None, s3_prefix=None, cloudwatch_logging=False,
               aws_region=None, cloudwatch_log_group=None, 
               cloudwatch_log_stream_prefix=None, cloudwatch_log_level=None,
               aws_profile=None, env='dev'):
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
        cloudwatch_logging (bool, optional): Whether to log to CloudWatch.
        aws_region (str, optional): AWS region.
        cloudwatch_log_group (str, optional): CloudWatch log group name.
        cloudwatch_log_stream_prefix (str, optional): CloudWatch log stream prefix.
        cloudwatch_log_level (str, optional): CloudWatch log level.
        aws_profile (str, optional): AWS profile name.
        env (str): Environment name (dev, staging, prod).
    """
    # Load AWS configuration from file if available
    aws_config = load_aws_config(env)
    
    # Set AWS profile if provided in config or as argument
    if aws_profile is None and 'aws_profile' in aws_config:
        aws_profile = aws_config['aws_profile']
    
    if aws_profile:
        os.environ['AWS_PROFILE'] = aws_profile
        print(f"Using AWS profile: {aws_profile}")
    
    settings = get_project_settings()
    
    # Override the output file if specified
    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        settings.set('FEED_URI', output_file)
        settings.set('FEED_FORMAT', 'json')
    
    # Override S3 settings from config if not provided as arguments
    if not s3_storage and aws_config.get('s3_storage', {}).get('enabled', False):
        s3_storage = True
    
    if s3_storage and s3_bucket is None and 's3_storage' in aws_config:
        s3_bucket = aws_config['s3_storage'].get('bucket')
    
    if s3_storage and s3_prefix is None and 's3_storage' in aws_config:
        s3_prefix = aws_config['s3_storage'].get('prefix')
    
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
    
    # Override CloudWatch settings from config if not provided as arguments
    if not cloudwatch_logging and aws_config.get('cloudwatch_logging', {}).get('enabled', False):
        cloudwatch_logging = True
    
    if cloudwatch_logging and cloudwatch_log_group is None and 'cloudwatch_logging' in aws_config:
        cloudwatch_log_group = aws_config['cloudwatch_logging'].get('log_group')
    
    if cloudwatch_logging and cloudwatch_log_stream_prefix is None and 'cloudwatch_logging' in aws_config:
        cloudwatch_log_stream_prefix = aws_config['cloudwatch_logging'].get('log_stream_prefix')
    
    if cloudwatch_logging and cloudwatch_log_level is None and 'cloudwatch_logging' in aws_config:
        cloudwatch_log_level = aws_config['cloudwatch_logging'].get('log_level')
    
    # Configure CloudWatch logging if enabled
    if cloudwatch_logging:
        settings.set('CLOUDWATCH_LOGGING_ENABLED', True)
        
        # Set AWS credentials and CloudWatch settings
        if aws_access_key_id:
            settings.set('AWS_ACCESS_KEY_ID', aws_access_key_id)
        if aws_secret_access_key:
            settings.set('AWS_SECRET_ACCESS_KEY', aws_secret_access_key)
        if aws_region:
            settings.set('AWS_REGION', aws_region)
        if cloudwatch_log_group:
            settings.set('CLOUDWATCH_LOG_GROUP', cloudwatch_log_group)
        if cloudwatch_log_stream_prefix:
            settings.set('CLOUDWATCH_LOG_STREAM_PREFIX', cloudwatch_log_stream_prefix)
        if cloudwatch_log_level:
            settings.set('CLOUDWATCH_LOG_LEVEL', cloudwatch_log_level)
    
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
    parser.add_argument(
        '--env',
        help='Environment (dev, staging, prod) for loading AWS config',
        default='dev'
    )
    
    # AWS credentials
    aws_group = parser.add_argument_group('AWS Credentials')
    aws_group.add_argument(
        '--aws-profile',
        help='AWS profile name'
    )
    aws_group.add_argument(
        '--aws-key-id',
        help='AWS access key ID'
    )
    aws_group.add_argument(
        '--aws-secret-key',
        help='AWS secret access key'
    )
    aws_group.add_argument(
        '--aws-region',
        help='AWS region (default: us-east-1)',
        default='us-east-1'
    )
    
    # S3 storage options
    s3_group = parser.add_argument_group('S3 Storage Options')
    s3_group.add_argument(
        '--s3', '-s',
        action='store_true',
        help='Store articles in Amazon S3'
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
    
    # CloudWatch logging options
    cloudwatch_group = parser.add_argument_group('CloudWatch Logging Options')
    cloudwatch_group.add_argument(
        '--cloudwatch', '-c',
        action='store_true',
        help='Log to AWS CloudWatch'
    )
    cloudwatch_group.add_argument(
        '--cloudwatch-log-group',
        help='CloudWatch log group name (default: NeuroNews-Scraper)',
        default='NeuroNews-Scraper'
    )
    cloudwatch_group.add_argument(
        '--cloudwatch-log-stream-prefix',
        help='CloudWatch log stream prefix (default: scraper)',
        default='scraper'
    )
    cloudwatch_group.add_argument(
        '--cloudwatch-log-level',
        help='CloudWatch log level (default: INFO)',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO'
    )
    
    args = parser.parse_args()
    
    if args.list_sources:
        settings = get_project_settings()
        print("Configured news sources:")
        for source in settings.get('SCRAPING_SOURCES'):
            print(f"  - {source}")
        return
    
    # Load AWS configuration from file
    aws_config = load_aws_config(args.env)
    
    # Set AWS profile if provided in config or as argument
    aws_profile = args.aws_profile
    if aws_profile is None and 'aws_profile' in aws_config:
        aws_profile = aws_config['aws_profile']
    
    if aws_profile:
        os.environ['AWS_PROFILE'] = aws_profile
        print(f"Using AWS profile: {aws_profile}")
    
    # Override S3 settings from config if not provided as arguments
    s3_storage = args.s3
    if not s3_storage and aws_config.get('s3_storage', {}).get('enabled', False):
        s3_storage = True
    
    s3_bucket = args.s3_bucket
    if s3_storage and s3_bucket is None and 's3_storage' in aws_config:
        s3_bucket = aws_config['s3_storage'].get('bucket')
    
    s3_prefix = args.s3_prefix
    if s3_storage and s3_prefix == 'news_articles' and 's3_storage' in aws_config:
        s3_prefix = aws_config['s3_storage'].get('prefix', s3_prefix)
    
    # Override CloudWatch settings from config if not provided as arguments
    cloudwatch_logging = args.cloudwatch
    if not cloudwatch_logging and aws_config.get('cloudwatch_logging', {}).get('enabled', False):
        cloudwatch_logging = True
    
    cloudwatch_log_group = args.cloudwatch_log_group
    if cloudwatch_logging and cloudwatch_log_group == 'NeuroNews-Scraper' and 'cloudwatch_logging' in aws_config:
        cloudwatch_log_group = aws_config['cloudwatch_logging'].get('log_group', cloudwatch_log_group)
    
    cloudwatch_log_stream_prefix = args.cloudwatch_log_stream_prefix
    if cloudwatch_logging and cloudwatch_log_stream_prefix == 'scraper' and 'cloudwatch_logging' in aws_config:
        cloudwatch_log_stream_prefix = aws_config['cloudwatch_logging'].get('log_stream_prefix', cloudwatch_log_stream_prefix)
    
    cloudwatch_log_level = args.cloudwatch_log_level
    if cloudwatch_logging and cloudwatch_log_level == 'INFO' and 'cloudwatch_logging' in aws_config:
        cloudwatch_log_level = aws_config['cloudwatch_logging'].get('log_level', cloudwatch_log_level)
    
    # Check if AWS services are enabled but required credentials are missing
    aws_services_enabled = s3_storage or cloudwatch_logging
    aws_creds_available = (
        (os.environ.get('AWS_ACCESS_KEY_ID') or args.aws_key_id) and
        (os.environ.get('AWS_SECRET_ACCESS_KEY') or args.aws_secret_key)
    )
    aws_profile_available = aws_profile is not None
    
    if aws_services_enabled and not (aws_creds_available or aws_profile_available):
        parser.error("AWS credentials are required for S3 storage or CloudWatch logging. "
                    "Provide them with --aws-key-id and --aws-secret-key, "
                    "set the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables, "
                    "or use --aws-profile to specify an AWS profile.")
    
    # Check if S3 storage is enabled but bucket name is missing
    if s3_storage and not s3_bucket:
        parser.error("S3 bucket name is required for S3 storage. "
                    "Provide it with --s3-bucket, set the S3_BUCKET environment variable, "
                    "or specify it in the AWS configuration file.")
    
    print(f"Starting NeuroNews scraper...")
    if args.playwright:
        print("Using Playwright for JavaScript-heavy pages")
    if s3_storage:
        print(f"Storing articles in S3 bucket: {s3_bucket}")
        print(f"S3 prefix: {s3_prefix}")
    if cloudwatch_logging:
        print(f"Logging to CloudWatch: {cloudwatch_log_group}/{cloudwatch_log_stream_prefix}-*")
        print(f"Log level: {cloudwatch_log_level}")
    print(f"Output will be saved to: {args.output}")
    
    run_spider(
        output_file=args.output,
        use_playwright=args.playwright,
        s3_storage=s3_storage,
        aws_access_key_id=args.aws_key_id,
        aws_secret_access_key=args.aws_secret_key,
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix,
        cloudwatch_logging=cloudwatch_logging,
        aws_region=args.aws_region,
        cloudwatch_log_group=cloudwatch_log_group,
        cloudwatch_log_stream_prefix=cloudwatch_log_stream_prefix,
        cloudwatch_log_level=cloudwatch_log_level,
        aws_profile=aws_profile,
        env=args.env
    )
    print("Scraping completed.")


if __name__ == "__main__":
    main()
