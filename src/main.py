"""
Main entry point for NeuroNews application.
"""

import argparse
import json
import os
from pathlib import Path

from scraper.run import load_aws_config, run_spider


def main():
    """Main function."""
    print("NeuroNews application starting...")

    parser = argparse.ArgumentParser(description="NeuroNews Application")
    parser.add_argument(
        "--scrape", "-s", action="store_true", help="Run the news scraper"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path for scraped data (default: data/news_articles.json)",
        default="data/news_articles.json",
    )
    parser.add_argument(
        "--playwright",
        "-p",
        action="store_true",
        help="Use Playwright for JavaScript-heavy pages",
    )
    parser.add_argument(
        "--env",
        help="Environment (dev, staging, prod) for loading AWS config",
        default="dev",
    )

    # AWS credentials
    aws_group = parser.add_argument_group("AWS Credentials")
    aws_group.add_argument("--aws-profile", help="AWS profile name")
    aws_group.add_argument("--aws-key-id", help="AWS access key ID")
    aws_group.add_argument("--aws-secret-key", help="AWS secret access key")
    aws_group.add_argument(
        "--aws-region", help="AWS region (default: us-east-1)", default="us-east-1"
    )

    # S3 storage options
    s3_group = parser.add_argument_group("S3 Storage Options")
    s3_group.add_argument(
        "--s3", action="store_true", help="Store articles in Amazon S3"
    )
    s3_group.add_argument("--s3-bucket", help="S3 bucket name")
    s3_group.add_argument(
        "--s3-prefix",
        help="S3 key prefix (default: news_articles)",
        default="news_articles",
    )

    # CloudWatch logging options
    cloudwatch_group = parser.add_argument_group("CloudWatch Logging Options")
    cloudwatch_group.add_argument(
        "--cloudwatch", "-c", action="store_true", help="Log to AWS CloudWatch"
    )
    cloudwatch_group.add_argument(
        "--cloudwatch-log-group",
        help="CloudWatch log group name (default: NeuroNews-Scraper)",
        default="NeuroNews-Scraper",
    )
    cloudwatch_group.add_argument(
        "--cloudwatch-log-stream-prefix",
        help="CloudWatch log stream prefix (default: scraper)",
        default="scraper",
    )
    cloudwatch_group.add_argument(
        "--cloudwatch-log-level",
        help="CloudWatch log level (default: INFO)",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
    )

    args = parser.parse_args()

    if args.scrape:
        print(f"Running news scraper...")

        # Load AWS configuration from file
        aws_config = load_aws_config(args.env)

        # Set AWS profile if provided in config or as argument
        aws_profile = args.aws_profile
        if aws_profile is None and "aws_profile" in aws_config:
            aws_profile = aws_config["aws_profile"]

        if aws_profile:
            os.environ["AWS_PROFILE"] = aws_profile
            print(f"Using AWS profile: {aws_profile}")

        # Override S3 settings from config if not provided as arguments
        s3_storage = args.s3
        if not s3_storage and aws_config.get("s3_storage", {}).get("enabled", False):
            s3_storage = True

        s3_bucket = args.s3_bucket
        if s3_storage and s3_bucket is None and "s3_storage" in aws_config:
            s3_bucket = aws_config["s3_storage"].get("bucket")

        s3_prefix = args.s3_prefix
        if s3_storage and s3_prefix == "news_articles" and "s3_storage" in aws_config:
            s3_prefix = aws_config["s3_storage"].get("prefix", s3_prefix)

        # Override CloudWatch settings from config if not provided as arguments
        cloudwatch_logging = args.cloudwatch
        if not cloudwatch_logging and aws_config.get("cloudwatch_logging", {}).get(
            "enabled", False
        ):
            cloudwatch_logging = True

        cloudwatch_log_group = args.cloudwatch_log_group
        if (
            cloudwatch_logging
            and cloudwatch_log_group == "NeuroNews-Scraper"
            and "cloudwatch_logging" in aws_config
        ):
            cloudwatch_log_group = aws_config["cloudwatch_logging"].get(
                "log_group", cloudwatch_log_group
            )

        cloudwatch_log_stream_prefix = args.cloudwatch_log_stream_prefix
        if (
            cloudwatch_logging
            and cloudwatch_log_stream_prefix == "scraper"
            and "cloudwatch_logging" in aws_config
        ):
            cloudwatch_log_stream_prefix = aws_config["cloudwatch_logging"].get(
                "log_stream_prefix", cloudwatch_log_stream_prefix
            )

        cloudwatch_log_level = args.cloudwatch_log_level
        if (
            cloudwatch_logging
            and cloudwatch_log_level == "INFO"
            and "cloudwatch_logging" in aws_config
        ):
            cloudwatch_log_level = aws_config["cloudwatch_logging"].get(
                "log_level", cloudwatch_log_level
            )

        # Check if AWS services are enabled but required credentials are missing
        aws_services_enabled = s3_storage or cloudwatch_logging
        aws_creds_available = (
            os.environ.get("AWS_ACCESS_KEY_ID") or args.aws_key_id
        ) and (os.environ.get("AWS_SECRET_ACCESS_KEY") or args.aws_secret_key)
        aws_profile_available = aws_profile is not None

        if aws_services_enabled and not (aws_creds_available or aws_profile_available):
            parser.error(
                "AWS credentials are required for S3 storage or CloudWatch logging. "
                "Provide them with --aws-key-id and --aws-secret-key, "
                "set the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables, "
                "or use --aws-profile to specify an AWS profile."
            )

        # Check if S3 storage is enabled but bucket name is missing
        if s3_storage and not s3_bucket:
            parser.error(
                "S3 bucket name is required for S3 storage. "
                "Provide it with --s3-bucket, set the S3_BUCKET environment variable, "
                "or specify it in the AWS configuration file."
            )

        if args.playwright:
            print("Using Playwright for JavaScript-heavy pages")
        if s3_storage:
            print(f"Storing articles in S3 bucket: {s3_bucket}")
            print(f"S3 prefix: {s3_prefix}")
        if cloudwatch_logging:
            print(
                f"Logging to CloudWatch: {cloudwatch_log_group}/{cloudwatch_log_stream_prefix}-*"
            )
            print(f"Log level: {cloudwatch_log_level}")

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
            env=args.env,
        )
        print(f"Scraping completed. Data saved to {args.output}")
        if s3_storage:
            print(f"Articles also stored in S3 bucket: {s3_bucket}")
        if cloudwatch_logging:
            print(f"Logs available in CloudWatch: {cloudwatch_log_group}")
    else:
        print("No action specified. Use --scrape to run the news scraper.")


if __name__ == "__main__":
    main()
