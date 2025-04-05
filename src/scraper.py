"""
Web scraping module for NeuroNews.

This module provides a simple interface to the Scrapy-based scraper.
It maintains backward compatibility with the original API.
"""
import json
import os
from scraper.run import run_spider


def scrape_news(output_file='data/news_articles.json', use_playwright=False, 
                s3_storage=False, aws_access_key_id=None, aws_secret_access_key=None,
                s3_bucket=None, s3_prefix='news_articles'):
    """
    Scrape news articles from configured sources.
    
    Args:
        output_file (str): Path to save the scraped articles.
        use_playwright (bool): Whether to use Playwright for JavaScript-heavy pages.
        s3_storage (bool): Whether to store articles in S3.
        aws_access_key_id (str, optional): AWS access key ID.
        aws_secret_access_key (str, optional): AWS secret access key.
        s3_bucket (str, optional): S3 bucket name.
        s3_prefix (str, optional): S3 key prefix.
        
    Returns:
        list: List of scraped news articles.
    """
    print("Scraping news using Scrapy-based scraper...")
    if use_playwright:
        print("Using Playwright for JavaScript-heavy pages")
    if s3_storage:
        print(f"Storing articles in S3 bucket: {s3_bucket or os.environ.get('S3_BUCKET')}")
    
    # Run the spider and save results to the output file
    run_spider(
        output_file=output_file,
        use_playwright=use_playwright,
        s3_storage=s3_storage,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix
    )
    
    # Read the results from the output file
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            try:
                articles = json.load(f)
                return articles
            except json.JSONDecodeError:
                print(f"Error: Could not parse {output_file} as JSON.")
                return []
    else:
        print(f"Error: Output file {output_file} not found.")
        return []
