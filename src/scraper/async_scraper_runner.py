"""
Async News Scraper Runner
Main entry point for running the high-performance async news scraper.
"""

from src.scraper.async_scraper_engine import (
    ASYNC_NEWS_SOURCES,
    AsyncNewsScraperEngine,
    NewsSource,
)
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))


class AsyncScraperRunner:
    """Runner for the async news scraper."""

    def __init__(self, config_path: str = None):
        self.config_path = config_path
        self.config = self.load_config()
        self.setup_logging()

    def load_config(self) -> dict:
        """Load configuration from file or use defaults."""
        default_config = {
            "max_concurrent": 20,
            "max_threads": 8,
            "headless": True,
            "output_dir": "output/async_scraped",
            "sources": [],
            "timeout": 30,
            "performance_monitoring": True,
        }

        if self.config_path and Path(self.config_path).exists():
            with open(self.config_path, "r") as f:
                file_config = json.load(f)
                default_config.update(file_config)

        return default_config

    def setup_logging(self):
        """Setup logging configuration."""
        log_level = logging.DEBUG if self.config.get("debug", False) else logging.INFO

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler("async_scraper.log"),
            ],
        )

        self.logger = logging.getLogger(__name__)

    def get_sources_to_scrape(self, source_filter: str = None) -> list:
        """Get list of sources to scrape."""
        # Use configured sources if available, otherwise use defaults
        if self.config.get("sources"):
            sources = []
            for source_config in self.config["sources"]:
                source = NewsSource(**source_config)
                sources.append(source)
        else:
            sources = ASYNC_NEWS_SOURCES

        # Filter sources if specified
        if source_filter:
            source_names = [name.strip() for name in source_filter.split(",")]
            sources = [s for s in sources if s.name in source_names]

        return sources

    async def run_scraper(self, sources: list, test_mode: bool = False) -> list:
        """Run the async scraper."""
        self.logger.info("🚀 Starting Async News Scraper")
        self.logger.info(
            f"📊 Configuration: {
                self.config['max_concurrent']} concurrent, {
                self.config['max_threads']} threads"
        )
        self.logger.info("🎯 Sources: {0}".format([s.name for s in sources]]))

        start_time = time.time()

        # Limit sources in test mode
        if test_mode:
            sources = sources[:2]  # Only first 2 sources
            self.logger.info("🧪 Running in test mode - limited sources")

        # Initialize and run scraper
        async with AsyncNewsScraperEngine(
            max_concurrent=self.config["max_concurrent"],
            max_threads=self.config["max_threads"],
            headless=self.config["headless"],
        ) as scraper:

            # Start performance monitoring
            if self.config.get("performance_monitoring", True):
                monitor_task = asyncio.create_task(self.monitor_performance(scraper))

            # Scrape all sources
            articles = await scraper.scrape_sources_async(sources)

            # Stop monitoring
            if self.config.get("performance_monitoring", True):
                monitor_task.cancel()

            # Save results
            await self.save_results(scraper, articles)

            # Final statistics
            end_time = time.time()
            duration = end_time - start_time

            self.logger.info("🎉 Async scraping completed!")
            self.logger.info("⏱️  Duration: {0} seconds".format(duration))
            self.logger.info("📰 Articles: {0}".format(len(articles)))
            self.logger.info(
                "📈 Rate: {0} articles/second".format(
                    len(articles) /
                    duration)
            )

            return articles

    async def monitor_performance(self, scraper: AsyncNewsScraperEngine):
        """Monitor scraper performance in real-time."""
        try:
            while True:
                await asyncio.sleep(10)  # Update every 10 seconds

                stats = scraper.get_performance_stats()
                self.logger.info(
                    f"📊 Performance: {stats['total_articles']} articles, "
                    f"{stats['articles_per_second']:.2f}/sec, "
                    f"{stats['success_rate']:.1f}% success, "
                    f"{stats['avg_memory_mb']:.1f}MB RAM, "
                    f"{stats['avg_cpu_percent']:.1f}% CPU"
                )

        except asyncio.CancelledError:
            pass

    async def save_results(self, scraper: AsyncNewsScraperEngine, articles: list):
        """Save scraping results."""
        output_dir = Path(self.config["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save articles
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        articles_file = output_dir / "async_scraped_articles_{0}.json".format(timestamp)

        await scraper.save_articles(articles, str(articles_file))

        # Save performance stats
        stats = scraper.get_performance_stats()
        stats_file = output_dir / "performance_stats_{0}.json".format(timestamp)

        with open(stats_file, "w") as f:
            json.dump(stats, f, indent=2)

        self.logger.info("💾 Results saved to {0}".format(output_dir))

        # Print summary
        self.print_summary(articles, stats)

    def print_summary(self, articles: list, stats: dict):
        """Print scraping summary."""
        print("\n" + "=" * 60)
        print("📊 ASYNC SCRAPER PERFORMANCE SUMMARY")
        print("=" * 60)

        print(f"⏱️  Total Duration: {stats['elapsed_time']:.2f} seconds")
        print("📰 Total Articles: {0}".format(len(articles)))
        print(f"📈 Articles/Second: {stats['articles_per_second']:.2f}")
        print(f"✅ Success Rate: {stats['success_rate']:.1f}%")
        print(
            f"🔄 Total Requests: {
                stats['successful_requests'] +
                stats['failed_requests']}"
        )
        print(f"⚡ Avg Response Time: {stats['avg_response_time']:.2f}s")
        print(f"💾 Avg Memory Usage: {stats['avg_memory_mb']:.1f} MB")
        print(f"🖥️  Avg CPU Usage: {stats['avg_cpu_percent']:.1f}%")

        print("\n📋 Source Breakdown:")
        for source, source_stats in stats["source_stats"].items():
            print(
                f"  {source}: {
                    source_stats['articles']} articles, {
                    source_stats['errors']} errors"
            )

        # Quality breakdown
        quality_counts = {"high": 0, "medium": 0, "low": 0}
        for article in articles:
            quality = getattr(article, "content_quality", "unknown")
            if quality in quality_counts:
                quality_counts[quality] += 1

        print("\n🏆 Quality Distribution:")
        for quality, count in quality_counts.items():
            percentage = (count / len(articles)) * 100 if articles else 0
            print("  {0}: {1} ({2}%)".format(quality.title(), count, percentage))

        print("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="NeuroNews Async Scraper")
    parser.add_argument("--config", "-c", help="Configuration file path")
    parser.add_argument(
        "--sources", "-s", help="Comma-separated list of sources to scrape"
    )
    parser.add_argument("--test", "-t", action="store_true", help="Run in test mode")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--concurrent", type=int, help="Max concurrent connections")
    parser.add_argument("--threads", type=int, help="Max thread pool size")
    parser.add_argument(
        "--no-headless", action="store_true", help="Run browser in non-headless mode"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Create runner
    runner = AsyncScraperRunner(args.config)

    # Override config with command line arguments
    if args.output:
        runner.config["output_dir"] = args.output
    if args.concurrent:
        runner.config["max_concurrent"] = args.concurrent
    if args.threads:
        runner.config["max_threads"] = args.threads
    if args.no_headless:
        runner.config["headless"] = False
    if args.debug:
        runner.config["debug"] = True
        runner.setup_logging()  # Re-setup with debug level

    # Get sources to scrape
    sources = runner.get_sources_to_scrape(args.sources)

    if not sources:
        print("❌ No sources to scrape!")
        return 1

    # Run scraper
    try:
        articles = asyncio.run(runner.run_scraper(sources, args.test))
        print("🎉 Successfully scraped {0} articles!".format(len(articles)))
        return 0

    except KeyboardInterrupt:
        print("\n⚠️  Scraping interrupted by user")
        return 1
    except Exception as e:
        print("❌ Scraper failed: {0}".format(e))
        return 1


if __name__ == "__main__":
    exit(main())
