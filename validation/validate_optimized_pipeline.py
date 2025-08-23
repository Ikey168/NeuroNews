"""
Performance Validation Script for Optimized Data Ingestion Pipeline - Issue #26

This script validates the performance improvements of the optimized data ingestion
pipeline by running benchmarks and comparing results with baseline performance.
"""

from src.ingestion.optimized_pipeline import (
    OptimizationConfig, OptimizedIngestionPipeline, create_optimized_pipeline,
    create_performance_optimized_pipeline)
import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PerformanceValidator:
    """Validates performance improvements of the optimized pipeline."""

    def __init__(self):
        self.results = {}
        self.test_data = self._generate_test_data()

    def _generate_test_data(self, size: int = 1000) -> List[Dict[str, Any]]:
        """Generate realistic test data for benchmarking."""
        test_articles = []

        # Different article types to simulate real-world diversity
        article_templates = [
            {
                "source": "TechNews",
                "category": "Technology",
                "content_base": "Technology breakthrough in artificial intelligence and machine learning ",
                "author_base": "Tech Reporter",
            },
            {
                "source": "WorldNews",
                "category": "Politics",
                "content_base": "Political developments and international relations continue to evolve ",
                "author_base": "Political Correspondent",
            },
            {
                "source": "ScienceDaily",
                "category": "Science",
                "content_base": "Scientific research reveals new discoveries in quantum physics and biology ",
                "author_base": "Science Writer",
            },
            {
                "source": "HealthNews",
                "category": "Health",
                "content_base": "Medical advances and health research show promising results for treatment ",
                "author_base": "Health Correspondent",
            },
            {
                "source": "BusinessTimes",
                "category": "Business",
                "content_base": "Market analysis and business trends indicate significant growth opportunities ",
                "author_base": "Business Analyst",
            },
        ]

        for i in range(size):
            template = article_templates[i % len(article_templates)]

            # Vary content length to simulate real articles
            content_multiplier = 10 + (i % 40)  # 10-50 repetitions

            article = {
                "title": f"{template['category']} Update {i}: Important Developments in {template['source']}",
                "url": f"https://{template['source'].lower()}.com/article/{i}",
                "content": template["content_base"] * content_multiplier,
                "source": template["source"],
                "published_date": "2024-01-{0}T{1}:00:00Z".format((i % 28) + 1: 02d, (i % 24): 02d),
                "author": f"{template['author_base']} {i % 10}",
                "category": template["category"],
                "scraped_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "content_length": len(template["content_base"] * content_multiplier),
                "word_count": len(template["content_base"].split())
                * content_multiplier,
            }

            test_articles.append(article)

        return test_articles

    async def run_baseline_benchmark(
        self, articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Run baseline processing (simulated serial processing)."""
        logger.info(
            "Running baseline benchmark (simulated serial processing)...")

        start_time = time.time()
        processed_articles = []

        # Simulate basic processing for each article
        for article in articles:
            # Simulate basic processing time
            await asyncio.sleep(0.001)  # 1ms per article simulation

            # Basic processing
            processed_article = article.copy()
            processed_article["processing_metadata"] = {
                "baseline_processing": True,
                "processing_time": 0.001,
            }

            processed_articles.append(processed_article)

        end_time = time.time()
        processing_time = end_time - start_time

        return {
            "name": "Baseline",
            "processing_time": processing_time,
            "articles_processed": len(processed_articles),
            "throughput": len(processed_articles) / processing_time,
            "average_time_per_article": processing_time / len(processed_articles),
            "processed_articles": processed_articles,
        }

    async def run_optimized_benchmark(
        self,
        articles: List[Dict[str, Any]],
        config: OptimizationConfig,
        name: str = "Optimized",
    ) -> Dict[str, Any]:
        """Run optimized pipeline benchmark."""
        logger.info("Running {0} benchmark...".format(name))

        pipeline = OptimizedIngestionPipeline(config)

        try:
            start_time = time.time()
            results = await pipeline.process_articles_async(articles)
            end_time = time.time()

            processing_time = end_time - start_time

            return {
                "name": name,
                "processing_time": processing_time,
                "articles_processed": len(results["processed_articles"]),
                "throughput": len(results["processed_articles"]) / processing_time,
                "average_time_per_article": processing_time
                / len(results["processed_articles"]),
                "metrics": results["metrics"],
                "config": {
                    "max_concurrent_tasks": config.max_concurrent_tasks,
                    "batch_size": config.batch_size,
                    "adaptive_batching": config.adaptive_batching,
                },
            }

        finally:
            pipeline.cleanup()

    async def run_performance_comparison(
        self, dataset_sizes: List[int] = None
    ) -> Dict[str, Any]:
        """Run comprehensive performance comparison."""
        if dataset_sizes is None:
            dataset_sizes = [100, 250, 500, 1000]

        comparison_results = {}

        for size in dataset_sizes:
            logger.info(f"
{'='*50}")
            logger.info("Testing with {0} articles".format(size))
            logger.info(f"{'='*50}")

            test_articles = self.test_data[:size]
            size_results = {}

            # Baseline test
            baseline_result = await self.run_baseline_benchmark(test_articles)
            size_results["baseline"] = baseline_result

            # Standard optimized configuration
            standard_config = OptimizationConfig(
                max_concurrent_tasks=10, batch_size=25, adaptive_batching=True
            )

            standard_result = await self.run_optimized_benchmark(
                test_articles, standard_config, "Standard Optimized"
            )
            size_results["standard_optimized"] = standard_result

            # High performance configuration
            high_perf_config = OptimizationConfig(
                max_concurrent_tasks=30,
                batch_size=50,
                adaptive_batching=True,
                max_memory_usage_mb=512.0,
            )

            high_perf_result = await self.run_optimized_benchmark(
                test_articles, high_perf_config, "High Performance"
            )
            size_results["high_performance"] = high_perf_result

            # Memory optimized configuration
            memory_config = OptimizationConfig(
                max_concurrent_tasks=15,
                batch_size=20,
                adaptive_batching=True,
                max_memory_usage_mb=256.0,
            )

            memory_result = await self.run_optimized_benchmark(
                test_articles, memory_config, "Memory Optimized"
            )
            size_results["memory_optimized"] = memory_result

            comparison_results["{0}_articles".format(size)] = size_results

            # Print size comparison
            self._print_size_comparison(size, size_results)

        return comparison_results

    def _print_size_comparison(self, size: int, results: Dict[str, Any]):
        """Print comparison results for a specific dataset size."""
        print(""
Results for {0} articles:".format(size))
        print(
            f"{'Configuration':<20} {'Time (s)':<10} {'Throughput (art/s)':<18} {'Speedup':<10}""
        )
        print("-" * 70)

        baseline_time = results["baseline"]["processing_time"]

        for config_name, result in results.items():
            time_taken = result["processing_time"]
            throughput = result["throughput"]
            speedup = baseline_time / time_taken if time_taken > 0 else 0

            print(
                "{0} {1} {2} {3}x".format(config_name:<20, time_taken:<10.3f, throughput:<18.1f, speedup:<10.2f)
            )


    async def run_stress_test(self, max_articles: int = 2000) -> Dict[str, Any]:
        """Run stress test with increasing load."""
        logger.info(""
Running stress test up to {0} articles...".format(max_articles))"

        stress_results = {}
        article_counts = [100, 250, 500, 750, 1000, 1500, 2000]
        article_counts = [count for count in article_counts if count <= max_articles]

        config = OptimizationConfig(
            max_concurrent_tasks=25,
            batch_size=50,
            adaptive_batching=True,
            max_memory_usage_mb=1024.0,
        )

        for count in article_counts:
            logger.info("Stress testing with {0} articles...".format(count))

            test_articles = self.test_data[:count]

            try:
                result = await self.run_optimized_benchmark(
                    test_articles, config, "Stress Test {0}".format(count)
                )

                stress_results[count] = {
                    "processing_time": result["processing_time"],
                    "throughput": result["throughput"],
                    "memory_used": result["metrics"]["performance"].get(
                        "peak_memory_usage", 0
                    ),
                    "success": True,
                }

                logger.info(f"✓ {count} articles: {result['throughput']:.1f} art/s")

            except Exception as e:
                logger.error("✗ {0} articles failed: {1}".format(count, e))
                stress_results[count] = {"success": False, "error": str(e)}

        return stress_results

    async def validate_memory_efficiency(self) -> Dict[str, Any]:
        """Validate memory efficiency of the pipeline."""
        logger.info(""
Validating memory efficiency...")"

        # Test with different memory limits
        memory_configs = [
            (128, "Low Memory"),
            (256, "Medium Memory"),
            (512, "High Memory"),
            (1024, "Very High Memory"),
        ]

        memory_results = {}
        test_articles = self.test_data[:500]  # Fixed size for memory testing

        for memory_limit, config_name in memory_configs:
            config = OptimizationConfig(
                max_concurrent_tasks=20,
                batch_size=25,
                max_memory_usage_mb=float(memory_limit),
                adaptive_batching=True,
            )

            try:
                result = await self.run_optimized_benchmark(
                    test_articles, config, config_name
                )

                memory_results[memory_limit] = {
                    "throughput": result["throughput"],
                    "processing_time": result["processing_time"],
                    "memory_limit": memory_limit,
                    "peak_memory": result["metrics"]["performance"].get(
                        "peak_memory_usage", 0
                    ),
                    "success": True,
                }

            except Exception as e:
                memory_results[memory_limit] = {
                    "success": False,
                    "error": str(e),
                    "memory_limit": memory_limit,
                }

        return memory_results

    def save_results(self, results: Dict[str, Any], output_path: str = None):
        """Save validation results to file."""
        if output_path is None:
            timestamp = int(time.time())
            output_path = "data/performance_validation_{0}.json".format(timestamp)

        # Ensure directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Add metadata
        results["metadata"] = {
            "validation_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "test_data_size": len(self.test_data),
            "python_version": sys.version,
            "validation_script_version": "1.0",
        }

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, default=str)

            logger.info("Results saved to: {0}".format(output_path))

        except Exception as e:
            logger.error("Failed to save results: {0}".format(e))


    def generate_performance_report(self, results: Dict[str, Any]) -> str:
        """Generate a comprehensive performance report."""
        report_lines = [
            "=" * 70,
            "OPTIMIZED DATA INGESTION PIPELINE - PERFORMANCE VALIDATION REPORT",
            "=" * 70,
            f"Validation Time: {results.get('metadata', {}).get('validation_time', 'Unknown')}",
            f"Test Data Size: {results.get('metadata', {}).get('test_data_size', 'Unknown')} articles",
            "",
        ]

        # Performance comparison summary
        if "performance_comparison" in results:
            report_lines.extend(["PERFORMANCE COMPARISON SUMMARY", "-" * 35, ""])

            for size_key, size_results in results["performance_comparison"].items():
                size = size_key.replace("_articles", "")
                report_lines.append("Dataset Size: {0} articles".format(size))

                baseline_throughput = size_results["baseline"]["throughput"]

                for config_name, result in size_results.items():
                    if config_name != "baseline":
                        throughput = result["throughput"]
                        speedup = throughput / baseline_throughput
                        report_lines.append(
                            "  {0}: {1} art/s ({2}x speedup)".format(config_name:<20, throughput:>8.1f, speedup:>5.2f)
                        )

                report_lines.append("")

        # Stress test results
        if "stress_test" in results:
            report_lines.extend(["STRESS TEST RESULTS", "-" * 20, ""])

            for count, result in results["stress_test"].items():
                if result.get("success", False):
                    report_lines.append(
                        f"{count:>5} articles: {result['throughput']:>8.1f} art/s "
                        f"({result['processing_time']:>6.2f}s)"
                    )
                else:
                    report_lines.append(
                        f"{count:>5} articles: FAILED - {result.get('error', 'Unknown error')}"
                    )

            report_lines.append("")

        # Memory efficiency results
        if "memory_efficiency" in results:
            report_lines.extend(["MEMORY EFFICIENCY RESULTS", "-" * 26, ""])

            for memory_limit, result in results["memory_efficiency"].items():
                if result.get("success", False):
                    throughput = result["throughput"]
                    peak_memory = result.get("peak_memory", 0)
                    report_lines.append(
                        "{0} MB limit: {1} art/s ".format(memory_limit:>4, throughput:>8.1f)
                        "(peak: {0} MB)".format(peak_memory:>6.1f)
                    )
                else:
                    report_lines.append("{0} MB limit: FAILED".format(memory_limit:>4))

            report_lines.append("")

        # Recommendations
        report_lines.extend(["PERFORMANCE RECOMMENDATIONS", "-" * 29, ""])

        # Calculate best configuration based on results
        if "performance_comparison" in results:
            best_configs = self._analyze_best_configurations(
                results["performance_comparison"]
            )

            for size, config in best_configs.items():
                report_lines.append(
                    f"For {size} articles: Use {config['name']} configuration"
                )

        report_lines.extend(
            [
                "",
                "For high-throughput scenarios: Use High Performance configuration",
                "For memory-constrained environments: Use Memory Optimized configuration",
                "For balanced performance: Use Standard Optimized configuration",
                "",
                "=" * 70,
            ]
        )

        return ""
".join(report_lines)"

    def _analyze_best_configurations(
        self, comparison_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze results to find best configurations for different dataset sizes."""
        best_configs = {}

        for size_key, size_results in comparison_results.items():
            size = size_key.replace("_articles", "")

            best_throughput = 0
            best_config = None

            for config_name, result in size_results.items():
                if config_name != "baseline" and result["throughput"] > best_throughput:
                    best_throughput = result["throughput"]
                    best_config = {"name": config_name, "throughput": best_throughput}

            if best_config:
                best_configs[size] = best_config

        return best_configs


async def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(
        description="Validate optimized pipeline performance"
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=1000,
        help="Maximum number of articles for testing",
    )
    parser.add_argument(
        "--stress-test",
        action="store_true",
        help="Run stress test with increasing load",
    )
    parser.add_argument(
        "--memory-test", action="store_true", help="Run memory efficiency validation"
    )
    parser.add_argument("--output", type=str, help="Output file path for results")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick validation with smaller datasets",
    )

    args = parser.parse_args()

    validator = PerformanceValidator()
    all_results = {}

    try:
        # Determine dataset sizes based on mode
        if args.quick:
            dataset_sizes = [50, 100, 250]
            max_stress_articles = 500
        else:
            dataset_sizes = [100, 250, 500, min(1000, args.max_articles)]
            max_stress_articles = args.max_articles

        logger.info("Starting performance validation...")
        logger.info("Test data generated: {0} articles".format(len(validator.test_data)))

        # Run performance comparison
        logger.info(""
" + "=" * 50)
        logger.info("RUNNING PERFORMANCE COMPARISON")
        logger.info("=" * 50)"

        comparison_results = await validator.run_performance_comparison(dataset_sizes)
        all_results["performance_comparison"] = comparison_results

        # Run stress test if requested
        if args.stress_test:
            logger.info(""
" + "=" * 50)
            logger.info("RUNNING STRESS TEST")
            logger.info("=" * 50)"

            stress_results = await validator.run_stress_test(max_stress_articles)
            all_results["stress_test"] = stress_results

        # Run memory efficiency test if requested
        if args.memory_test:
            logger.info(""
" + "=" * 50)
            logger.info("RUNNING MEMORY EFFICIENCY TEST")
            logger.info("=" * 50)"

            memory_results = await validator.validate_memory_efficiency()
            all_results["memory_efficiency"] = memory_results

        # Save results
        validator.save_results(all_results, args.output)

        # Generate and print report
        report = validator.generate_performance_report(all_results)
        print(""
" + report)"

        # Save report to file
        if args.output:
            report_path = args.output.replace(".json", "_report.txt")
        else:
            timestamp = int(time.time())
            report_path = "data/performance_report_{0}.txt".format(timestamp)

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info("Performance report saved to: {0}".format(report_path))
        except Exception as e:
            logger.error("Failed to save report: {0}".format(e))

        logger.info("Performance validation completed successfully!")

    except Exception as e:
        logger.error("Validation failed: {0}".format(e))
        logger.error(traceback.format_exc())
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
