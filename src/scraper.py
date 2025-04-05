"""
Web scraping module for NeuroNews.

This module provides a simple interface to the Scrapy-based scraper.
It maintains backward compatibility with the original API.
"""
import json
import os
from scraper.run import run_spider


def scrape_news(output_file='data/news_articles.json', use_playwright=False):
    """
    Scrape news articles from configured sources.
    
    Args:
        output_file (str): Path to save the scraped articles.
        use_playwright (bool): Whether to use Playwright for JavaScript-heavy pages.
        
    Returns:
        list: List of scraped news articles.
    """
    print("Scraping news using Scrapy-based scraper...")
    if use_playwright:
        print("Using Playwright for JavaScript-heavy pages")
    
    # Run the spider and save results to the output file
    run_spider(output_file, use_playwright)
    
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
