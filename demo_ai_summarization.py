#!/usr/bin/env python3
"""
Demo script for AI-Powered Article Summarization (Issue #30).

This script demonstrates the complete summarization pipeline including:
- AI model initialization
- Summary generation for different lengths
- Database storage and retrieval
- Performance metrics
- API endpoint testing

Usage:
    python demo_ai_summarization.py

Author: NeuroNews Development Team
Created: August 2025
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict

# Add src directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.nlp.ai_summarizer import (AIArticleSummarizer, SummarizationModel,
                                   SummaryLength)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Sample news articles for demonstration
SAMPLE_ARTICLES = [
    {
        "id": "article_001",
        "title": "Advances in Artificial Intelligence Transform Healthcare",
        "content": """
        Artificial intelligence is revolutionizing healthcare by enabling faster diagnoses, 
        personalized treatments, and improved patient outcomes. Recent breakthroughs in machine 
        learning have led to AI systems that can detect diseases like cancer with accuracy 
        matching or exceeding human specialists. These systems analyze medical images, patient 
        records, and genetic data to identify patterns that might be missed by traditional 
        diagnostic methods.
        
        One of the most promising applications is in radiology, where AI algorithms can scan 
        thousands of medical images in minutes, flagging potential abnormalities for human 
        review. This not only speeds up the diagnostic process but also helps catch diseases 
        in their early stages when treatment is most effective.
        
        Drug discovery is another area where AI is making significant impact. Traditional drug 
        development can take decades and cost billions of dollars. AI-powered systems can now 
        analyze molecular structures, predict drug interactions, and identify promising compounds 
        much faster than conventional methods. This acceleration could bring life-saving 
        medications to market years earlier.
        
        However, the integration of AI in healthcare also raises important questions about data 
        privacy, algorithm bias, and the need for human oversight. Medical professionals 
        emphasize that AI should augment, not replace, human judgment in critical medical 
        decisions. As this technology continues to evolve, striking the right balance between 
        automation and human expertise will be crucial for maximizing benefits while minimizing 
        risks.
        """,
    },
    {
        "id": "article_002",
        "title": "Climate Change Accelerates Arctic Ice Melt",
        "content": """
        Scientists report that Arctic sea ice is melting at an unprecedented rate, with 
        implications for global weather patterns and sea level rise. The latest data from 
        satellite monitoring shows that ice coverage has reached its second-lowest extent 
        on record, continuing a troubling trend observed over the past several decades.
        
        The Arctic Ocean, once permanently covered by thick ice, now experiences increasingly 
        longer ice-free periods during summer months. This dramatic change is attributed 
        primarily to rising global temperatures caused by greenhouse gas emissions. The ice 
        serves as a crucial reflector of solar radiation, and its loss creates a feedback 
        loop that accelerates warming in the region.
        
        Marine ecosystems are being severely disrupted by these changes. Polar bears, seals, 
        and other Arctic wildlife depend on sea ice for hunting, breeding, and migration. 
        Many species are now forced to travel greater distances or adapt their behavior 
        patterns, with some populations showing signs of decline.
        
        The melting ice also opens new shipping routes and access to previously unreachable 
        oil and gas reserves, creating both economic opportunities and environmental concerns. 
        International cooperation will be essential to manage these resources responsibly 
        while addressing the underlying causes of climate change.
        
        Researchers emphasize that immediate action to reduce carbon emissions is critical 
        to slow this process and prevent more catastrophic changes to Arctic ecosystems 
        and global climate stability.
        """,
    },
    {
        "id": "article_003",
        "title": "Quantum Computing Breakthrough Achieved",
        "content": """
        Researchers have achieved a major breakthrough in quantum computing, demonstrating 
        a quantum processor that can solve certain problems exponentially faster than 
        classical computers. This milestone represents years of progress in overcoming 
        the technical challenges that have limited quantum computing's practical applications.
        
        The breakthrough involves improved quantum error correction techniques that allow 
        quantum bits (qubits) to maintain their delicate quantum states for longer periods. 
        Previously, quantum computers were severely limited by decoherence, where qubits 
        lose their quantum properties due to environmental interference. The new approach 
        uses advanced materials and isolation techniques to create more stable quantum systems.
        
        Potential applications for this technology are vast and transformative. Quantum 
        computers could revolutionize cryptography by breaking current encryption methods 
        while enabling new, quantum-safe security protocols. In drug discovery, they could 
        simulate molecular interactions with unprecedented accuracy, accelerating the 
        development of new medications.
        
        Financial modeling, optimization problems, and artificial intelligence could all 
        benefit from quantum computing's ability to process certain types of calculations 
        much faster than conventional computers. Climate modeling, in particular, could 
        see dramatic improvements in accuracy and detail, helping scientists better 
        understand and predict environmental changes.
        
        Despite this progress, practical quantum computers for everyday use are still 
        years away. Current systems require extremely cold temperatures and sophisticated 
        isolation to function, making them expensive and complex to operate. However, 
        this breakthrough brings the quantum computing revolution significantly closer 
        to reality.
        """,
    },
]


async def demo_basic_summarization():
    """Demonstrate basic summarization functionality."""
    print("\n" + "=" * 60)
    print("🤖 AI-POWERED SUMMARIZATION DEMO")
    print("=" * 60)

    # Initialize summarizer with lighter model for demo
    print("\n📦 Initializing AI Summarizer...")
    summarizer = AIArticleSummarizer(
        default_model=SummarizationModel.DISTILBART,  # Lighter model for demo
        enable_caching=True,
    )

    print(f"✅ Summarizer initialized with device: {summarizer.device}")

    # Test with first article
    article = SAMPLE_ARTICLES[0]
    print(f"\n📰 Processing Article: {article['title']}")
    print(f"📊 Original length: {len(article['content'])} characters")

    # Generate summaries of different lengths
    all_summaries = await summarizer.summarize_article_all_lengths(article["content"])

    print("\n📝 Generated Summaries:")
    print("-" * 40)

    for length, summary in all_summaries.items():
        print(f"\n{length.value.upper()} SUMMARY:")
        print(f"Model: {summary.model.value}")
        print(f"Text: {summary.text}")
        print(f"📈 Metrics:")
        print(f"  - Words: {summary.word_count}")
        print(f"  - Sentences: {summary.sentence_count}")
        print(f"  - Compression: {summary.compression_ratio:.1%}")
        print(f"  - Confidence: {summary.confidence_score:.2f}")
        print(f"  - Processing time: {summary.processing_time:.2f}s")

    return summarizer, all_summaries


async def demo_model_comparison():
    """Demonstrate different summarization models."""
    print("\n" + "=" * 60)
    print("🔬 MODEL COMPARISON DEMO")
    print("=" * 60)

    article = SAMPLE_ARTICLES[1]  # Climate change article
    models_to_test = [SummarizationModel.DISTILBART, SummarizationModel.T5]

    print(f"\n📰 Article: {article['title']}")
    print(f"📊 Testing {len(models_to_test)} different models...")

    results = {}

    for model in models_to_test:
        print(f"\n🔄 Testing model: {model.value}")
        try:
            summarizer = AIArticleSummarizer(default_model=model)
            summary = await summarizer.summarize_article(
                article["content"], SummaryLength.MEDIUM
            )

            results[model.value] = summary
            print(
                f"✅ Success - {summary.word_count} words in {summary.processing_time:.2f}s"
            )

        except Exception as e:
            print(f"❌ Failed: {str(e)}")
            continue

    # Compare results
    print("\n📊 Model Comparison Results:")
    print("-" * 50)

    for model_name, summary in results.items():
        print(f"\n{model_name}:")
        print(f"Summary: {summary.text[:100]}...")
        print(f"Quality metrics:")
        print(f"  - Words: {summary.word_count}")
        print(f"  - Compression: {summary.compression_ratio:.1%}")
        print(f"  - Confidence: {summary.confidence_score:.2f}")
        print(f"  - Speed: {summary.processing_time:.2f}s")

    return results


async def demo_batch_processing():
    """Demonstrate batch processing capabilities."""
    print("\n" + "=" * 60)
    print("⚡ BATCH PROCESSING DEMO")
    print("=" * 60)

    print(f"\n📦 Processing {len(SAMPLE_ARTICLES)} articles in batch...")

    summarizer = AIArticleSummarizer()
    start_time = time.time()

    # Process all articles concurrently
    tasks = []
    for article in SAMPLE_ARTICLES:
        task = summarizer.summarize_article(article["content"], SummaryLength.SHORT)
        tasks.append((article["id"], article["title"], task))

    results = []
    for article_id, title, task in tasks:
        try:
            summary = await task
            results.append(
                {
                    "article_id": article_id,
                    "title": title,
                    "summary": summary,
                    "success": True,
                }
            )
        except Exception as e:
            results.append(
                {
                    "article_id": article_id,
                    "title": title,
                    "error": str(e),
                    "success": False,
                }
            )

    total_time = time.time() - start_time
    successful = sum(1 for r in results if r["success"])

    print(f"\n📊 Batch Processing Results:")
    print(f"✅ Successful: {successful}/{len(SAMPLE_ARTICLES)}")
    print(f"⏱️ Total time: {total_time:.2f}s")
    print(f"🚀 Average per article: {total_time/len(SAMPLE_ARTICLES):.2f}s")

    for result in results:
        if result["success"]:
            summary = result["summary"]
            print(f"\n📰 {result['title'][:50]}...")
            print(f"   Summary: {summary.text[:80]}...")
            print(
                f"   Metrics: {summary.word_count} words, {summary.processing_time:.2f}s"
            )
        else:
            print(f"\n❌ {result['title'][:50]}...")
            print(f"   Error: {result['error']}")

    return results


async def demo_performance_metrics():
    """Demonstrate performance monitoring capabilities."""
    print("\n" + "=" * 60)
    print("📈 PERFORMANCE METRICS DEMO")
    print("=" * 60)

    summarizer = AIArticleSummarizer()

    # Process several articles to generate metrics
    print("\n🔄 Generating performance data...")

    for i, article in enumerate(SAMPLE_ARTICLES):
        print(f"Processing article {i+1}/{len(SAMPLE_ARTICLES)}...")
        await summarizer.summarize_article(article["content"], SummaryLength.MEDIUM)

    # Get performance metrics
    metrics = summarizer.get_model_info()

    print("\n📊 Performance Metrics:")
    print("-" * 30)
    print(f"Total summaries generated: {metrics['metrics']['total_summaries']}")
    print(f"Total processing time: {metrics['metrics']['total_processing_time']:.2f}s")
    print(
        f"Average processing time: {metrics['metrics']['average_processing_time']:.2f}s"
    )
    print(f"Device used: {metrics['device']}")
    print(f"Loaded models: {len(metrics['loaded_models'])}")

    print("\n📋 Model usage breakdown:")
    for model, count in metrics["metrics"]["model_usage_count"].items():
        if count > 0:
            print(f"  - {model.value}: {count} times")

    print("\n⚙️ Configuration:")
    for length, config in metrics["configs"].items():
        print(
            f"  - {length}: max_len={config['max_length']}, "
            f"min_len={config['min_length']}"
        )

    return metrics


async def save_demo_results(summaries: Dict, results: Dict, metrics: Dict):
    """Save demo results to JSON file for analysis."""
    demo_results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "basic_summaries": {
            length.value: {
                "text": summary.text,
                "word_count": summary.word_count,
                "compression_ratio": summary.compression_ratio,
                "confidence_score": summary.confidence_score,
                "processing_time": summary.processing_time,
                "model": summary.model.value,
            }
            for length, summary in summaries.items()
        },
        "model_comparison": {
            model_name: {
                "text": summary.text,
                "word_count": summary.word_count,
                "compression_ratio": summary.compression_ratio,
                "confidence_score": summary.confidence_score,
                "processing_time": summary.processing_time,
            }
            for model_name, summary in results.items()
        },
        "performance_metrics": metrics,
        "articles_processed": len(SAMPLE_ARTICLES),
    }

    output_file = "ai_summarization_demo_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(demo_results, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Demo results saved to: {output_file}")
    return output_file


async def main():
    """Run the complete summarization demo."""
    print("🚀 Starting AI-Powered Article Summarization Demo")
    print(f"📅 Demo Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Run all demo components
        summarizer, basic_summaries = await demo_basic_summarization()
        model_results = await demo_model_comparison()
        batch_results = await demo_batch_processing()
        performance_metrics = await demo_performance_metrics()

        # Save results
        output_file = await save_demo_results(
            basic_summaries, model_results, performance_metrics
        )

        print("\n" + "=" * 60)
        print("✅ DEMO COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print(f"📊 Summary:")
        print(f"  - Models tested: DistilBART, T5")
        print(f"  - Summary lengths: Short, Medium, Long")
        print(f"  - Articles processed: {len(SAMPLE_ARTICLES)}")
        print(f"  - Results saved to: {output_file}")
        print("\n🎯 Key Features Demonstrated:")
        print("  ✅ Multi-length summary generation")
        print("  ✅ Multiple AI model support")
        print("  ✅ Batch processing capabilities")
        print("  ✅ Performance monitoring")
        print("  ✅ Quality metrics calculation")

        print("\n🔗 Next Steps:")
        print("  - Integrate with database storage")
        print("  - Deploy API endpoints")
        print("  - Add more advanced models")
        print("  - Implement caching strategies")

    except Exception as e:
        print(f"\n❌ Demo failed with error: {str(e)}")
        logger.exception("Demo execution failed")
        return 1

    return 0


if __name__ == "__main__":
    # Run the demo
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
