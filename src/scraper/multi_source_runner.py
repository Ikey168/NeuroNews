"""
Multi-source spider runner for NeuroNews.
"""

import argparse
import json
import os
from datetime import datetime

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from src.scraper.spiders.arstechnica_spider import ArsTechnicaSpider
from src.scraper.spiders.bbc_spider import BBCSpider

# Import all spider classes
from src.scraper.spiders.cnn_spider import CNNSpider
from src.scraper.spiders.guardian_spider import GuardianSpider
from src.scraper.spiders.news_spider import NewsSpider
from src.scraper.spiders.npr_spider import NPRSpider
from src.scraper.spiders.reuters_spider import ReutersSpider
from src.scraper.spiders.techcrunch_spider import TechCrunchSpider
from src.scraper.spiders.theverge_spider import VergeSpider
from src.scraper.spiders.wired_spider import WiredSpider


class MultiSourceRunner:
    """Runner for executing multiple news source spiders."""

    def __init__(self):
        self.settings = get_project_settings()
        self.spiders = {
            "cnn": CNNSpider,
            "bbc": BBCSpider,
            "techcrunch": TechCrunchSpider,
            "arstechnica": ArsTechnicaSpider,
            "reuters": ReutersSpider,
            "guardian": GuardianSpider,
            "theverge": VergeSpider,
            "wired": WiredSpider,
            "npr": NPRSpider,
            "news": NewsSpider,  # Generic news spider
        }

    def run_spider(self, spider_name):
        """Run a single spider."""
        if spider_name not in self.spiders:
            raise ValueError(
                f"Spider '{spider_name}' not found. Available: {
                    list(
                        self.spiders.keys())}"
            )

        process = CrawlerProcess(self.settings)
        process.crawl(self.spiders[spider_name])
        process.start()

    def run_all_spiders(self, exclude=None, include_only=None):
        """Run all spiders or a subset."""
        exclude = exclude or []

        if include_only:
            spiders_to_run = {
                k: v for k, v in self.spiders.items() if k in include_only
            }
        else:
            spiders_to_run = {k: v for k, v in self.spiders.items() if k not in exclude}

        if not spiders_to_run:
            print("No spiders to run.")
            return

        print(f"Running spiders: {list(spiders_to_run.keys())}")

        process = CrawlerProcess(self.settings)
        for spider_class in spiders_to_run.values():
            process.crawl(spider_class)

        process.start()

    def generate_report(self):
        """Generate a report of scraped data."""
        data_dir = "data"
        sources_dir = os.path.join(data_dir, "sources")

        if not os.path.exists(sources_dir):
            print("No data found. Run spiders first.")
            return

        report = {
            "timestamp": datetime.now().isoformat(),
            "sources": {},
            "total_articles": 0,
            "quality_distribution": {"high": 0, "medium": 0, "low": 0},
        }

        # Analyze source-specific files
        for filename in os.listdir(sources_dir):
            if filename.endswith("_articles.json"):
                source_name = filename.replace("_articles.json", "")
                file_path = os.path.join(sources_dir, filename)

                try:
                    with open(file_path, "r") as f:
                        articles = json.load(f)

                    article_count = len(articles)
                    report["sources"][source_name] = {
                        "article_count": article_count,
                        "avg_content_length": sum(
                            len(a.get("content", "")) for a in articles
                        )
                        / max(1, article_count),
                        "avg_validation_score": sum(
                            a.get("validation_score", 0) for a in articles
                        )
                        / max(1, article_count),
                        "categories": list(
                            set(a.get("category", "unknown") for a in articles)
                        ),
                    }

                    report["total_articles"] += article_count

                    # Count quality distribution
                    for article in articles:
                        quality = article.get("content_quality", "unknown")
                        if quality in report["quality_distribution"]:
                            report["quality_distribution"][quality] += 1

                except Exception as e:
                    print(f"Error processing {filename}: {e}")

        # Save report
        report_path = os.path.join(data_dir, "scraping_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"Report generated: {report_path}")
        print(f"Total articles scraped: {report['total_articles']}")
        print(f"Sources processed: {len(report['sources'])}")

        return report


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Multi-source news scraper for NeuroNews"
    )
    parser.add_argument("--spider", type=str, help="Run specific spider")
    parser.add_argument("--all", action="store_true", help="Run all spiders")
    parser.add_argument("--exclude", nargs="+", help="Exclude specific spiders")
    parser.add_argument("--include", nargs="+", help="Include only specific spiders")
    parser.add_argument(
        "--report", action="store_true", help="Generate scraping report"
    )
    parser.add_argument("--list", action="store_true", help="List available spiders")

    args = parser.parse_args()

    runner = MultiSourceRunner()

    if args.list:
        print("Available spiders:")
        for spider_name in runner.spiders.keys():
            print(f"  - {spider_name}")
        return

    if args.report:
        runner.generate_report()
        return

    if args.spider:
        runner.run_spider(args.spider)
    elif args.all:
        runner.run_all_spiders(exclude=args.exclude, include_only=args.include)
    else:
        print("Use --help for usage information")


if __name__ == "__main__":
    main()
