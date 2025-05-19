"""
Measure and compare scraper execution times for different news sources.
"""

import asyncio
import time
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List
from datetime import datetime
import json
import logging
from pathlib import Path

from src.scraper.optimized_scraper import OptimizedScraper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test news sources
NEWS_SOURCES = {
    'reuters': [
        'https://www.reuters.com/business/',
        'https://www.reuters.com/markets/',
        'https://www.reuters.com/technology/'
    ],
    'bloomberg': [
        'https://www.bloomberg.com/markets',
        'https://www.bloomberg.com/technology',
        'https://www.bloomberg.com/economics'
    ],
    'wsj': [
        'https://www.wsj.com/news/markets',
        'https://www.wsj.com/news/technology',
        'https://www.wsj.com/news/business'
    ]
}

class ScraperTimer:
    """Measure scraper performance metrics."""

    def __init__(self, concurrency: int = 10):
        """
        Initialize timer.
        
        Args:
            concurrency: Number of concurrent requests
        """
        self.scraper = OptimizedScraper(concurrency=concurrency)
        self.results: Dict[str, List[Dict]] = {}
        
    async def measure_source(self, source: str, urls: List[str], iterations: int = 3) -> None:
        """
        Measure scraping performance for a news source.
        
        Args:
            source: News source name
            urls: List of URLs to scrape
            iterations: Number of test iterations
        """
        logger.info(f"Testing source: {source}")
        self.results[source] = []
        
        for i in range(iterations):
            logger.info(f"Iteration {i+1}/{iterations}")
            
            # Measure execution time
            start_time = time.time()
            articles = await self.scraper.process_urls(urls)
            duration = time.time() - start_time
            
            # Record metrics
            self.results[source].append({
                'duration': duration,
                'articles': len(articles),
                'avg_time_per_article': duration / len(articles) if articles else 0,
                'success_rate': len(articles) / len(urls)
            })
            
            # Brief pause between iterations
            await asyncio.sleep(1)

    def analyze_results(self) -> pd.DataFrame:
        """
        Analyze timing results.
        
        Returns:
            DataFrame with analysis results
        """
        data = []
        
        for source, measurements in self.results.items():
            for m in measurements:
                data.append({
                    'source': source,
                    'duration': m['duration'],
                    'articles': m['articles'],
                    'avg_time_per_article': m['avg_time_per_article'],
                    'success_rate': m['success_rate']
                })
                
        return pd.DataFrame(data)

    def plot_results(self, save_path: Path) -> None:
        """
        Create visualizations of the results.
        
        Args:
            save_path: Directory to save plots
        """
        df = self.analyze_results()
        
        # Set style
        plt.style.use('seaborn')
        sns.set_palette("husl")
        
        # Create figure with multiple plots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        
        # 1. Total duration by source
        sns.boxplot(data=df, x='source', y='duration', ax=ax1)
        ax1.set_title('Scraping Duration by Source')
        ax1.set_ylabel('Duration (seconds)')
        
        # 2. Articles scraped by source
        sns.boxplot(data=df, x='source', y='articles', ax=ax2)
        ax2.set_title('Articles Scraped by Source')
        ax2.set_ylabel('Number of Articles')
        
        # 3. Average time per article
        sns.boxplot(data=df, x='source', y='avg_time_per_article', ax=ax3)
        ax3.set_title('Average Time per Article')
        ax3.set_ylabel('Seconds per Article')
        
        # 4. Success rate
        sns.boxplot(data=df, x='source', y='success_rate', ax=ax4)
        ax4.set_title('Scraping Success Rate')
        ax4.set_ylabel('Success Rate')
        
        plt.tight_layout()
        
        # Save plot
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        plt.savefig(save_path / f'scraper_timing_{timestamp}.png')
        plt.close()

async def main():
    """Run timing measurements."""
    # Create output directory
    output_dir = Path('scraper_metrics')
    output_dir.mkdir(exist_ok=True)
    
    # Initialize timer
    timer = ScraperTimer()
    
    # Test each source
    for source, urls in NEWS_SOURCES.items():
        await timer.measure_source(source, urls)
    
    # Analyze and visualize results
    df = timer.analyze_results()
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    df.to_csv(output_dir / f'timing_results_{timestamp}.csv')
    
    # Save summary statistics
    summary = df.groupby('source').agg({
        'duration': ['mean', 'std', 'min', 'max'],
        'articles': ['mean', 'sum'],
        'avg_time_per_article': ['mean', 'std'],
        'success_rate': 'mean'
    }).round(3)
    
    with open(output_dir / f'summary_{timestamp}.json', 'w') as f:
        json.dump(summary.to_dict(), f, indent=2)
    
    # Create visualizations
    timer.plot_results(output_dir)
    
    logger.info("Timing analysis complete!")
    logger.info(f"Results saved to {output_dir}")

if __name__ == '__main__':
    asyncio.run(main())