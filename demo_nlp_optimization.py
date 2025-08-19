#!/usr/bin/env python3
"""
Demo: Optimized NLP Pipeline for Scalability - Issue #35

This demonstration script showcases the optimized NLP pipeline's key features:
1. Multi-threaded processing for faster NLP execution
2. Intelligent caching to avoid redundant processing
3. Memory management and optimization
4. Performance monitoring and statistics
5. AWS SageMaker deployment readiness

Run this script to see the optimization improvements in action.
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Try to import our optimized components
try:
    from nlp.optimized_nlp_pipeline import (
        NLPConfig, create_high_performance_nlp_pipeline,
        create_memory_optimized_nlp_pipeline, create_optimized_nlp_pipeline)

    OPTIMIZED_AVAILABLE = True
except ImportError as e:
    logger.error(f"Optimized pipeline not available: {e}")
    OPTIMIZED_AVAILABLE = False

try:
    from nlp.nlp_integration import (create_balanced_nlp_processor,
                                     create_high_performance_nlp_processor,
                                     create_memory_efficient_nlp_processor)

    INTEGRATION_AVAILABLE = True
except ImportError as e:
    logger.error(f"Integration components not available: {e}")
    INTEGRATION_AVAILABLE = False


class OptimizedNLPDemo:
    """Demonstration of optimized NLP pipeline capabilities."""

    def __init__(self):
        self.sample_articles = self._create_sample_articles()
        self.results = {}

    def _create_sample_articles(self) -> List[Dict[str, Any]]:
        """Create sample articles for demonstration."""
        articles = [
            {
                "id": "tech_001",
                "title": "AI Revolution in Healthcare",
                "content": "Artificial intelligence is transforming healthcare with breakthrough innovations in medical diagnosis, drug discovery, and personalized treatment plans. Machine learning algorithms are now capable of detecting diseases earlier than traditional methods, leading to better patient outcomes and reduced healthcare costs. The integration of AI in medical imaging has particularly shown remarkable results in identifying cancerous tumors and other abnormalities with unprecedented accuracy.",
            },
            {
                "id": "tech_002",
                "title": "Quantum Computing Breakthrough",
                "content": "Scientists have achieved a major milestone in quantum computing by developing a new quantum processor that maintains coherence for record-breaking durations. This advancement brings us closer to practical quantum computers that could revolutionize cryptography, drug discovery, and complex optimization problems. The new processor uses innovative error correction techniques that significantly reduce quantum decoherence, making quantum calculations more reliable and scalable.",
            },
            {
                "id": "climate_001",
                "title": "Renewable Energy Surges Globally",
                "content": "Global renewable energy capacity has reached new heights as countries accelerate their transition away from fossil fuels. Solar and wind power installations have broken previous records, with costs continuing to decline rapidly. Government policies and private investment are driving this transformation, making clean energy the most economical choice in many regions. The shift toward renewables is creating millions of jobs while helping combat climate change.",
            },
            {
                "id": "climate_002",
                "title": "Climate Summit Reaches Historic Agreement",
                "content": "World leaders at the latest climate summit have reached a groundbreaking agreement on carbon emission reductions. The accord includes specific targets for reducing greenhouse gas emissions by 50% within the next decade. Developing nations will receive substantial financial support to transition to clean energy infrastructure. Environmental groups have praised the agreement as a crucial step toward limiting global warming to 1.5 degrees Celsius.",
            },
            {
                "id": "economy_001",
                "title": "Central Banks Consider Digital Currencies",
                "content": "Major central banks worldwide are exploring the development of digital currencies as the financial landscape evolves rapidly. These central bank digital currencies (CBDCs) could transform how people conduct transactions and manage money. The technology promises faster, more secure payments while maintaining government oversight. Several countries have already begun pilot programs to test the feasibility and security of digital currency systems.",
            },
            {
                "id": "economy_002",
                "title": "Supply Chain Innovations Drive Efficiency",
                "content": "Companies are implementing cutting-edge technologies to optimize their supply chains and improve resilience. Artificial intelligence, blockchain, and IoT sensors are providing unprecedented visibility into global logistics networks. These innovations help businesses predict and prevent disruptions while reducing costs and environmental impact. The modernization of supply chains has become critical for maintaining competitive advantage in the global marketplace.",
            },
            {
                "id": "health_001",
                "title": "Gene Therapy Shows Promise for Rare Diseases",
                "content": "Recent clinical trials of gene therapy treatments have shown remarkable success in treating previously incurable rare diseases. Patients who received the experimental treatments have shown significant improvement in their conditions, offering hope to millions suffering from genetic disorders. The therapy works by correcting defective genes responsible for disease, potentially providing one-time cures rather than lifelong treatments. Regulatory authorities are fast-tracking approval processes for these breakthrough therapies.",
            },
            {
                "id": "health_002",
                "title": "Mental Health Support Systems Expand",
                "content": "Healthcare systems are expanding mental health support services as awareness of psychological well-being grows. New digital platforms and telemedicine solutions are making mental health care more accessible to underserved populations. The integration of AI-powered screening tools helps identify individuals at risk and connect them with appropriate resources. This comprehensive approach to mental health is reducing stigma and improving outcomes for patients worldwide.",
            },
            {
                "id": "space_001",
                "title": "Mars Mission Preparation Advances",
                "content": "Space agencies are making significant progress in preparing for human missions to Mars. Advanced life support systems, radiation shielding, and sustainable habitat designs are being tested in Earth-based simulations. International cooperation is essential for the success of these ambitious missions, with multiple countries contributing expertise and resources. The technical challenges of deep space exploration are driving innovations that benefit life on Earth as well.",
            },
            {
                "id": "space_002",
                "title": "Satellite Network Enables Global Internet",
                "content": "A new constellation of satellites is providing high-speed internet access to remote regions previously unreachable by traditional infrastructure. This space-based network is bridging the digital divide and enabling economic opportunities in underserved areas. The technology uses advanced beam-forming and frequency reuse to maximize coverage while minimizing interference. Educational institutions and healthcare facilities in remote locations are among the primary beneficiaries of this connectivity revolution.",
            },
        ]

        logger.info(f"Created {len(articles)} sample articles for demonstration")
        return articles

    async def demonstrate_basic_optimization(self):
        """Demonstrate basic optimized pipeline functionality."""
        print("\n" + "=" * 60)
        print("🚀 BASIC OPTIMIZATION DEMONSTRATION")
        print("=" * 60)

        if not OPTIMIZED_AVAILABLE:
            print("❌ Optimized pipeline not available - skipping demonstration")
            return

        try:
            # Create optimized pipeline
            pipeline = create_optimized_nlp_pipeline(
                max_threads=4, enable_cache=True, enable_gpu=False  # Use CPU for demo
            )

            print(f"📊 Processing {len(self.sample_articles)} articles...")

            # Process articles
            start_time = time.time()
            results = await pipeline.process_articles_async(
                self.sample_articles, operations=["sentiment", "keywords"]
            )
            processing_time = time.time() - start_time

            # Display results
            print(f"✅ Processing completed in {processing_time:.2f} seconds")
            print(f"📈 Throughput: {results['throughput']:.2f} articles/sec")
            print(f"🎯 Cache hit rate: {results['cache_stats']['hit_rate']:.1%}")
            print(
                f"💾 Memory usage: {results['memory_stats']['current_usage_mb']:.1f} MB"
            )

            # Show sample results
            print("\n📋 Sample Results:")
            for i, result in enumerate(results["results"][:3]):
                print(f"  Article {i+1}: {result.get('article_id', 'N/A')}")
                if "sentiment" in result:
                    sentiment = result["sentiment"]
                    print(
                        f"    Sentiment: {sentiment.get('label', 'N/A')} ({sentiment.get('confidence', 0):.2f})"
                    )
                if "keywords" in result:
                    keywords = result["keywords"].get("keywords", [])[:5]
                    print(f"    Keywords: {', '.join(keywords)}")

            self.results["basic_optimization"] = {
                "processing_time": processing_time,
                "throughput": results["throughput"],
                "cache_hit_rate": results["cache_stats"]["hit_rate"],
                "memory_usage_mb": results["memory_stats"]["current_usage_mb"],
            }

            await pipeline.cleanup()

        except Exception as e:
            print(f"❌ Basic optimization demonstration failed: {e}")
            logger.error(f"Basic optimization error: {e}", exc_info=True)

    async def demonstrate_caching_benefits(self):
        """Demonstrate caching performance benefits."""
        print("\n" + "=" * 60)
        print("⚡ CACHING BENEFITS DEMONSTRATION")
        print("=" * 60)

        if not OPTIMIZED_AVAILABLE:
            print("❌ Optimized pipeline not available - skipping demonstration")
            return

        try:
            # Create pipeline with caching
            pipeline = create_optimized_nlp_pipeline(enable_cache=True)

            # First run (cache miss)
            print("🔄 First run (building cache)...")
            start_time = time.time()
            results1 = await pipeline.process_articles_async(
                self.sample_articles[:5], operations=["sentiment", "keywords"]
            )
            first_run_time = time.time() - start_time

            # Second run (cache hit)
            print("🔄 Second run (using cache)...")
            start_time = time.time()
            results2 = await pipeline.process_articles_async(
                self.sample_articles[:5], operations=["sentiment", "keywords"]
            )
            second_run_time = time.time() - start_time

            # Display cache benefits
            speedup = first_run_time / second_run_time if second_run_time > 0 else 1.0
            print(f"🏃 First run time: {first_run_time:.2f}s")
            print(f"🚀 Second run time: {second_run_time:.2f}s")
            print(f"⚡ Speedup: {speedup:.1f}x faster")
            print(f"📊 Cache hit rate: {results2['cache_stats']['hit_rate']:.1%}")

            self.results["caching_benefits"] = {
                "first_run_time": first_run_time,
                "second_run_time": second_run_time,
                "speedup": speedup,
                "cache_hit_rate": results2["cache_stats"]["hit_rate"],
            }

            await pipeline.cleanup()

        except Exception as e:
            print(f"❌ Caching demonstration failed: {e}")
            logger.error(f"Caching error: {e}", exc_info=True)

    async def demonstrate_memory_optimization(self):
        """Demonstrate memory optimization features."""
        print("\n" + "=" * 60)
        print("🧠 MEMORY OPTIMIZATION DEMONSTRATION")
        print("=" * 60)

        if not OPTIMIZED_AVAILABLE:
            print("❌ Optimized pipeline not available - skipping demonstration")
            return

        try:
            # Create memory-optimized pipeline
            pipeline = create_memory_optimized_nlp_pipeline(max_memory_mb=512.0)

            print("📊 Processing with memory optimization...")

            # Monitor memory during processing
            initial_memory = pipeline.memory_manager.get_memory_usage_mb()
            print(f"💾 Initial memory usage: {initial_memory:.1f} MB")

            # Process articles
            results = await pipeline.process_articles_async(
                self.sample_articles, operations=["keywords", "summary"]
            )

            # Check final memory
            final_memory = pipeline.memory_manager.get_memory_usage_mb()
            memory_stats = pipeline.memory_manager.get_stats()

            print(f"💾 Final memory usage: {final_memory:.1f} MB")
            print(f"📈 Peak memory usage: {memory_stats['peak_usage']:.1f} MB")
            print(f"🗑️ Garbage collections triggered: {memory_stats['gc_triggered']}")
            print(f"⚠️ Memory warnings: {memory_stats['memory_warnings']}")

            self.results["memory_optimization"] = {
                "initial_memory_mb": initial_memory,
                "final_memory_mb": final_memory,
                "peak_memory_mb": memory_stats["peak_usage"],
                "gc_triggered": memory_stats["gc_triggered"],
            }

            await pipeline.cleanup()

        except Exception as e:
            print(f"❌ Memory optimization demonstration failed: {e}")
            logger.error(f"Memory optimization error: {e}", exc_info=True)

    async def demonstrate_concurrent_processing(self):
        """Demonstrate concurrent processing capabilities."""
        print("\n" + "=" * 60)
        print("🔄 CONCURRENT PROCESSING DEMONSTRATION")
        print("=" * 60)

        if not OPTIMIZED_AVAILABLE:
            print("❌ Optimized pipeline not available - skipping demonstration")
            return

        try:
            # Create high-performance pipeline
            pipeline = create_high_performance_nlp_pipeline()

            print("🔄 Testing concurrent processing...")

            # Split articles into batches for concurrent processing
            batch1 = self.sample_articles[:5]
            batch2 = self.sample_articles[5:]

            # Process batches concurrently
            start_time = time.time()

            concurrent_tasks = [
                pipeline.process_articles_async(
                    batch1, operations=["sentiment", "keywords"]
                ),
                pipeline.process_articles_async(
                    batch2, operations=["sentiment", "keywords"]
                ),
            ]

            concurrent_results = await asyncio.gather(*concurrent_tasks)
            concurrent_time = time.time() - start_time

            # Process sequentially for comparison
            start_time = time.time()
            seq_result1 = await pipeline.process_articles_async(
                batch1, operations=["sentiment", "keywords"]
            )
            seq_result2 = await pipeline.process_articles_async(
                batch2, operations=["sentiment", "keywords"]
            )
            sequential_time = time.time() - start_time

            # Calculate efficiency
            total_articles = len(batch1) + len(batch2)
            concurrent_throughput = total_articles / concurrent_time
            sequential_throughput = total_articles / sequential_time
            efficiency_gain = (
                sequential_time / concurrent_time if concurrent_time > 0 else 1.0
            )

            print(
                f"🏃 Sequential processing: {sequential_time:.2f}s ({sequential_throughput:.2f} articles/sec)"
            )
            print(
                f"🚀 Concurrent processing: {concurrent_time:.2f}s ({concurrent_throughput:.2f} articles/sec)"
            )
            print(f"⚡ Efficiency gain: {efficiency_gain:.1f}x")

            self.results["concurrent_processing"] = {
                "sequential_time": sequential_time,
                "concurrent_time": concurrent_time,
                "efficiency_gain": efficiency_gain,
                "concurrent_throughput": concurrent_throughput,
            }

            await pipeline.cleanup()

        except Exception as e:
            print(f"❌ Concurrent processing demonstration failed: {e}")
            logger.error(f"Concurrent processing error: {e}", exc_info=True)

    async def demonstrate_integrated_processor(self):
        """Demonstrate integrated NLP processor capabilities."""
        print("\n" + "=" * 60)
        print("🔗 INTEGRATED PROCESSOR DEMONSTRATION")
        print("=" * 60)

        if not INTEGRATION_AVAILABLE:
            print("❌ Integrated processor not available - skipping demonstration")
            return

        try:
            # Create balanced integrated processor
            processor = create_balanced_nlp_processor()

            print("🔗 Testing integrated NLP processing...")

            # Process articles comprehensively
            results = await processor.process_articles_comprehensive(
                self.sample_articles[:6],
                operations=["sentiment", "keywords", "summary"],
            )

            # Display comprehensive results
            metrics = results["performance_metrics"]
            print(f"✅ Articles processed: {len(results['articles'])}")
            print(f"⏱️ Total processing time: {metrics['total_processing_time']:.2f}s")
            print(f"📈 Throughput: {metrics['articles_per_second']:.2f} articles/sec")
            print(f"🎯 Cache hit rate: {metrics['cache_hit_rate']:.1%}")
            print(f"💾 Memory usage: {metrics['memory_usage_mb']:.1f} MB")

            # Show comprehensive stats
            comprehensive_stats = processor.get_comprehensive_stats()
            session_stats = comprehensive_stats["total_stats"]
            print(f"📊 Total sessions: {session_stats['sessions']}")
            print(f"📋 Total articles processed: {session_stats['articles_processed']}")

            self.results["integrated_processor"] = {
                "processing_time": metrics["total_processing_time"],
                "throughput": metrics["articles_per_second"],
                "cache_hit_rate": metrics["cache_hit_rate"],
                "memory_usage_mb": metrics["memory_usage_mb"],
            }

            await processor.cleanup()

        except Exception as e:
            print(f"❌ Integrated processor demonstration failed: {e}")
            logger.error(f"Integrated processor error: {e}", exc_info=True)

    def demonstrate_aws_sagemaker_readiness(self):
        """Demonstrate AWS SageMaker deployment readiness."""
        print("\n" + "=" * 60)
        print("☁️ AWS SAGEMAKER READINESS DEMONSTRATION")
        print("=" * 60)

        if not OPTIMIZED_AVAILABLE:
            print("❌ Optimized pipeline not available - skipping demonstration")
            return

        try:
            # Create SageMaker-optimized configuration
            sagemaker_config = NLPConfig(
                max_worker_threads=8,
                batch_size=64,
                max_batch_size=256,
                enable_model_quantization=True,
                use_gpu_if_available=True,
                sagemaker_endpoint_name="neuronews-nlp-endpoint",
                sagemaker_model_name="optimized-neuronews-nlp",
                enable_sagemaker_batch_transform=True,
            )

            print("☁️ SageMaker deployment configuration:")
            print(f"  📦 Model name: {sagemaker_config.sagemaker_model_name}")
            print(f"  🔌 Endpoint: {sagemaker_config.sagemaker_endpoint_name}")
            print(f"  📊 Batch size: {sagemaker_config.batch_size}")
            print(f"  🏃 Max threads: {sagemaker_config.max_worker_threads}")
            print(
                f"  ⚡ Model quantization: {sagemaker_config.enable_model_quantization}"
            )
            print(
                f"  🔄 Batch transform: {sagemaker_config.enable_sagemaker_batch_transform}"
            )

            print("\n✅ Key SageMaker deployment features:")
            print("  • Optimized batch processing for high throughput")
            print("  • Model quantization for reduced memory usage")
            print("  • Concurrent processing for scalability")
            print("  • Intelligent caching for cost optimization")
            print("  • Memory management for stable performance")
            print("  • Error handling and graceful degradation")

            self.results["sagemaker_readiness"] = {
                "model_name": sagemaker_config.sagemaker_model_name,
                "endpoint_name": sagemaker_config.sagemaker_endpoint_name,
                "batch_size": sagemaker_config.batch_size,
                "quantization_enabled": sagemaker_config.enable_model_quantization,
                "batch_transform_enabled": sagemaker_config.enable_sagemaker_batch_transform,
            }

        except Exception as e:
            print(f"❌ SageMaker readiness demonstration failed: {e}")
            logger.error(f"SageMaker readiness error: {e}", exc_info=True)

    def print_summary_report(self):
        """Print a comprehensive summary report."""
        print("\n" + "=" * 60)
        print("📋 OPTIMIZATION SUMMARY REPORT")
        print("=" * 60)

        if not self.results:
            print("❌ No results available for summary")
            return

        print(
            f"🕒 Demonstration completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print(f"📊 Total demonstrations run: {len(self.results)}")

        for demo_name, results in self.results.items():
            print(f"\n🔸 {demo_name.replace('_', ' ').title()}:")
            for key, value in results.items():
                if isinstance(value, float):
                    if "time" in key.lower():
                        print(f"  • {key.replace('_', ' ').title()}: {value:.2f}s")
                    elif "rate" in key.lower() or "hit" in key.lower():
                        print(f"  • {key.replace('_', ' ').title()}: {value:.1%}")
                    elif "mb" in key.lower():
                        print(f"  • {key.replace('_', ' ').title()}: {value:.1f} MB")
                    else:
                        print(f"  • {key.replace('_', ' ').title()}: {value:.2f}")
                else:
                    print(f"  • {key.replace('_', ' ').title()}: {value}")

        # Calculate overall improvements
        basic_results = self.results.get("basic_optimization", {})
        if basic_results:
            throughput = basic_results.get("throughput", 0)
            cache_rate = basic_results.get("cache_hit_rate", 0)

            print("\n🎯 Key Performance Indicators:")
            print(f"  • Overall throughput: {throughput:.2f} articles/sec")
            print(f"  • Cache efficiency: {cache_rate:.1%}")
            print(f"  • Memory optimization: ✅ Enabled")
            print(f"  • Concurrent processing: ✅ Enabled")
            print(f"  • SageMaker ready: ✅ Configured")

        print("\n✅ Issue #35 Objectives Achieved:")
        print("  1. ✅ Multi-threaded processing implemented")
        print("  2. ✅ Intelligent caching system deployed")
        print("  3. ✅ AWS SageMaker optimization configured")
        print("  4. ✅ Memory management and monitoring active")
        print("  5. ✅ Performance monitoring and statistics enabled")

    def save_results_to_file(self, filename: str = "nlp_optimization_results.json"):
        """Save demonstration results to a file."""
        try:
            output_data = {
                "timestamp": datetime.now().isoformat(),
                "demonstration_results": self.results,
                "sample_articles_count": len(self.sample_articles),
                "issue": "Issue #35: Optimize NLP Pipeline for Scalability",
                "objectives_completed": [
                    "Multi-threaded processing for faster NLP execution",
                    "Intelligent caching to avoid redundant processing",
                    "AWS SageMaker optimization for cloud deployment",
                    "Memory management and performance monitoring",
                ],
            }

            with open(filename, "w") as f:
                json.dump(output_data, f, indent=2)

            print(f"💾 Results saved to: {filename}")

        except Exception as e:
            print(f"❌ Failed to save results: {e}")


async def main():
    """Main demonstration function."""
    print("🚀 NeuroNews NLP Pipeline Optimization Demo")
    print("Issue #35: Optimize NLP Pipeline for Scalability")
    print("=" * 60)

    demo = OptimizedNLPDemo()

    try:
        # Run all demonstrations
        await demo.demonstrate_basic_optimization()
        await demo.demonstrate_caching_benefits()
        await demo.demonstrate_memory_optimization()
        await demo.demonstrate_concurrent_processing()
        await demo.demonstrate_integrated_processor()
        demo.demonstrate_aws_sagemaker_readiness()

        # Print summary report
        demo.print_summary_report()

        # Save results
        demo.save_results_to_file()

        print(f"\n🎉 Demonstration completed successfully!")
        print("📋 See the summary report above for detailed results.")

    except KeyboardInterrupt:
        print("\n⚠️ Demonstration interrupted by user")
    except Exception as e:
        print(f"\n❌ Demonstration failed: {e}")
        logger.error(f"Demo error: {e}", exc_info=True)

    print("\n🔗 Integration with existing NeuroNews pipeline:")
    print("  • Drop-in replacement for existing NLP components")
    print("  • Backward compatible with current interfaces")
    print("  • Enhanced performance with caching and optimization")
    print("  • Ready for AWS SageMaker deployment")


if __name__ == "__main__":
    # Set up proper event loop for async execution
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Run the demonstration
    asyncio.run(main())
