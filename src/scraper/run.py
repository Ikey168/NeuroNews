"""
Command-line interface for running the NeuroNews scrapers.
"""
import argparse
import os
import sys
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from .spiders.news_spider import NewsSpider


def run_spider(output_file=None):
    """Run the news spider."""
    settings = get_project_settings()
    
    # Override the output file if specified
    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        settings.set('FEED_URI', output_file)
        settings.set('FEED_FORMAT', 'json')
    
    process = CrawlerProcess(settings)
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
    
    args = parser.parse_args()
    
    if args.list_sources:
        settings = get_project_settings()
        print("Configured news sources:")
        for source in settings.get('SCRAPING_SOURCES'):
            print(f"  - {source}")
        return
    
    print(f"Starting NeuroNews scraper...")
    print(f"Output will be saved to: {args.output}")
    run_spider(args.output)
    print("Scraping completed.")


if __name__ == "__main__":
    main()
