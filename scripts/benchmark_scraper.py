"""
Benchmark script to compare scraper performance.
"""

import asyncio
import time
import statistics
import matplotlib.pyplot as plt
from typing import List, Dict, Any
import json
import psutil
import os
from datetime import datetime
import argparse

from src.scraper.optimized_scraper import OptimizedScraper
from src.scraper.spiders.news_spider import NewsSpider
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

def run_benchmark(
    urls: List[str],
    concurrency_levels: List[int],
    iterations: int = 3
) -> Dict[str, List[Dict[str, float]]]:
    """
    Run performance benchmark comparing scrapers.
    
    Args:
        urls: List of URLs to scrape
        concurrency_levels: List of concurrency settings to test
        iterations: Number of test iterations
        
    Returns:
        Dictionary of benchmark results
    """
    results = {
        'optimized': [],
        'original': []
    }
    
    # Test different concurrency levels
    for concurrency in concurrency_levels:
        print(f"\nTesting concurrency level: {concurrency}")
        
        # Optimized scraper metrics
        opt_times = []
        opt_memory = []
        opt_success = []
        
        # Original scraper metrics
        orig_times = []
        orig_memory = []
        orig_success = []
        
        for i in range(iterations):
            print(f"Iteration {i+1}/{iterations}")
            
            # Test optimized scraper
            process = psutil.Process()
            start_mem = process.memory_info().rss
            
            start = time.time()
            scraper = OptimizedScraper(concurrency=concurrency)
            articles = scraper.run(urls)
            duration = time.time() - start
            
            end_mem = process.memory_info().rss
            memory_used = end_mem - start_mem
            
            opt_times.append(duration)
            opt_memory.append(memory_used)
            opt_success.append(len(articles))
            
            # Test original scraper
            process = psutil.Process()
            start_mem = process.memory_info().rss
            
            start = time.time()
            settings = get_project_settings()
            settings.set('CONCURRENT_REQUESTS', concurrency)
            process = CrawlerProcess(settings)
            process.crawl(NewsSpider, start_urls=urls)
            process.start()
            duration = time.time() - start
            
            end_mem = process.memory_info().rss
            memory_used = end_mem - start_mem
            
            # Get results from spider output
            with open('articles.json') as f:
                articles = json.load(f)
            os.remove('articles.json')
            
            orig_times.append(duration)
            orig_memory.append(memory_used)
            orig_success.append(len(articles))
            
            # Clear caches between runs
            import gc
            gc.collect()
            
            # Brief pause between iterations
            time.sleep(1)
        
        # Record averaged results
        results['optimized'].append({
            'concurrency': concurrency,
            'time': statistics.mean(opt_times),
            'time_stdev': statistics.stdev(opt_times),
            'memory': statistics.mean(opt_memory),
            'success_rate': sum(opt_success) / (len(urls) * iterations)
        })
        
        results['original'].append({
            'concurrency': concurrency,
            'time': statistics.mean(orig_times),
            'time_stdev': statistics.stdev(orig_times),
            'memory': statistics.mean(orig_memory),
            'success_rate': sum(orig_success) / (len(urls) * iterations)
        })
        
    return results

def plot_results(results: Dict[str, List[Dict[str, float]]]):
    """
    Plot benchmark results.
    
    Args:
        results: Benchmark result data
    """
    # Prepare data
    concurrency = [r['concurrency'] for r in results['optimized']]
    opt_times = [r['time'] for r in results['optimized']]
    opt_mem = [r['memory'] / 1024 / 1024 for r in results['optimized']]  # Convert to MB
    orig_times = [r['time'] for r in results['original']]
    orig_mem = [r['memory'] / 1024 / 1024 for r in results['original']]
    
    # Create figure with multiple subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10))
    
    # Processing time comparison
    ax1.plot(concurrency, opt_times, 'b-o', label='Optimized')
    ax1.plot(concurrency, orig_times, 'r-o', label='Original')
    ax1.set_xlabel('Concurrency Level')
    ax1.set_ylabel('Processing Time (seconds)')
    ax1.set_title('Scraper Performance Comparison')
    ax1.legend()
    ax1.grid(True)
    
    # Memory usage comparison
    ax2.plot(concurrency, opt_mem, 'b-o', label='Optimized')
    ax2.plot(concurrency, orig_mem, 'r-o', label='Original')
    ax2.set_xlabel('Concurrency Level')
    ax2.set_ylabel('Memory Usage (MB)')
    ax2.set_title('Memory Usage Comparison')
    ax2.legend()
    ax2.grid(True)
    
    plt.tight_layout()
    
    # Save plot
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    plt.savefig(f'benchmark_results_{timestamp}.png')
    plt.close()

def main():
    """Run benchmark script."""
    parser = argparse.ArgumentParser(description='Run scraper benchmark tests')
    parser.add_argument(
        '--urls',
        type=str,
        default='benchmark_urls.txt',
        help='File containing URLs to test (one per line)'
    )
    parser.add_argument(
        '--concurrency',
        type=str,
        default='5,10,20,50',
        help='Comma-separated list of concurrency levels to test'
    )
    parser.add_argument(
        '--iterations',
        type=int,
        default=3,
        help='Number of test iterations'
    )
    
    args = parser.parse_args()
    
    # Load test URLs
    with open(args.urls) as f:
        urls = [line.strip() for line in f if line.strip()]
    
    concurrency_levels = [int(c) for c in args.concurrency.split(',')]
    
    print(f"Running benchmark with {len(urls)} URLs")
    print(f"Testing concurrency levels: {concurrency_levels}")
    print(f"Running {args.iterations} iterations per test")
    
    results = run_benchmark(urls, concurrency_levels, args.iterations)
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with open(f'benchmark_results_{timestamp}.json', 'w') as f:
        json.dump(results, f, indent=2)
        
    plot_results(results)
    
    print("\nBenchmark complete!")
    print(f"Results saved to benchmark_results_{timestamp}.json")
    print(f"Plots saved to benchmark_results_{timestamp}.png")

if __name__ == '__main__':
    main()