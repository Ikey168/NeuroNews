"""
Main entry point for NeuroNews application.
"""
import argparse
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
    
    args = parser.parse_args()
    
    if args.scrape:
        print(f"Running news scraper...")
        run_spider(args.output)
        print(f"Scraping completed. Data saved to {args.output}")
    else:
        print("No action specified. Use --scrape to run the news scraper.")


if __name__ == "__main__":
    main()
