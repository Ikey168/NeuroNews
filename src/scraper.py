"""
Web scraping module for NeuroNews.

This module provides a simple interface to the Scrapy-based scraper.
It maintains backward compatibility with the original API.
"""
import json
import os
from scraper.run import run_spider


def scrape_news(output_file='data/news_articles.json'):
    """
    Scrape news articles from configured sources.
    
    Args:
        output_file (str): Path to save the scraped articles.
        
    Returns:
        list: List of scraped news articles.
    """
    print("Scraping news using Scrapy-based scraper...")
    
    # Run the spider and save results to the output file
    run_spider(output_file)
    
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
