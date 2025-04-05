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


def run_spider(output_file=None, use_playwright=False):
    """
    Run the news spider.
    
    Args:
        output_file (str, optional): Path to save the scraped data.
        use_playwright (bool, optional): Whether to use Playwright for JavaScript-heavy pages.
    """
    settings = get_project_settings()
    
    # Override the output file if specified
    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        settings.set('FEED_URI', output_file)
        settings.set('FEED_FORMAT', 'json')
    
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
    
    args = parser.parse_args()
    
    if args.list_sources:
        settings = get_project_settings()
        print("Configured news sources:")
        for source in settings.get('SCRAPING_SOURCES'):
            print(f"  - {source}")
        return
    
    print(f"Starting NeuroNews scraper...")
    if args.playwright:
        print("Using Playwright for JavaScript-heavy pages")
    print(f"Output will be saved to: {args.output}")
    
    run_spider(args.output, args.playwright)
    print("Scraping completed.")


if __name__ == "__main__":
    main()
