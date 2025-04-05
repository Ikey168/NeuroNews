"""
Main entry point for NeuroNews application.
"""
import argparse
import os
from scraper.run import run_spider


def main():
    """Main function."""
    print("NeuroNews application starting...")
    
    parser = argparse.ArgumentParser(description='NeuroNews Application')
    parser.add_argument(
        '--scrape', '-s',
        action='store_true',
        help='Run the news scraper'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output file path for scraped data (default: data/news_articles.json)',
        default='data/news_articles.json'
    )
    parser.add_argument(
        '--playwright', '-p',
        action='store_true',
        help='Use Playwright for JavaScript-heavy pages'
    )
    
    # S3 storage options
    s3_group = parser.add_argument_group('S3 Storage Options')
    s3_group.add_argument(
        '--s3',
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
    
    if args.scrape:
        print(f"Running news scraper...")
        
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
        
        if args.playwright:
            print("Using Playwright for JavaScript-heavy pages")
        if args.s3:
            print(f"Storing articles in S3 bucket: {args.s3_bucket or os.environ.get('S3_BUCKET')}")
            print(f"S3 prefix: {args.s3_prefix}")
        
        run_spider(
            output_file=args.output,
            use_playwright=args.playwright,
            s3_storage=args.s3,
            aws_access_key_id=args.aws_key_id,
            aws_secret_access_key=args.aws_secret_key,
            s3_bucket=args.s3_bucket,
            s3_prefix=args.s3_prefix
        )
        print(f"Scraping completed. Data saved to {args.output}")
        if args.s3:
            print(f"Articles also stored in S3 bucket: {args.s3_bucket or os.environ.get('S3_BUCKET')}")
    else:
        print("No action specified. Use --scrape to run the news scraper.")


if __name__ == "__main__":
    main()
