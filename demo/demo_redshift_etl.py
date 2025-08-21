#!/usr/bin/env python3
"""
Comprehensive demo for Redshift ETL Pipeline - Issue #22

This demo showcases the complete ETL process for storing processed articles
in AWS Redshift, including schema management, batch uploads, and integration
with the data validation pipeline.

Usage:
    python demo_redshift_etl.py [--mock] [--batch-size 100]

    --mock: Use mock data instead of connecting to actual Redshift
    --batch-size: Number of articles per batch (default: 100)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

try:
    from database.data_validation_pipeline import (DataValidationPipeline,
                                                   SourceReputationConfig)
    from database.redshift_loader import RedshiftETLProcessor
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure you're running from the project root directory")'
    sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_sample_articles() -> List[Dict[str, Any]]:
    """Create sample articles for demonstration."""
    base_time = datetime.now(timezone.utc)

    return [
        {
            "url": "https://reuters.com/technology/ai-breakthrough-2024",
            "title": "Major AI Breakthrough Announced by Leading Tech Companies",
            "content": """<p>Leading technology companies have announced a significant breakthrough"
            in artificial intelligence that could revolutionize healthcare, education, and scientific research.
            The new AI system demonstrates unprecedented capabilities in natural language understanding
            and reasoning.</p><p>The breakthrough involves a novel approach to neural network architecture
            that dramatically improves performance while reducing computational requirements. Initial tests
            show the system can understand complex medical literature and provide accurate diagnoses.</p>""",
            "source": "reuters.com",
            "published_date": (base_time - timedelta(hours=2)).isoformat(),
            "author": "Tech Reporter",
            "category": "Technology","
        },
        {
            "url": "https://bbc.com/science/quantum-computing-advance",
            "title": "Quantum Computing Milestone Achieved in University Laboratory",
            "content": """<p>Researchers at a leading university have achieved a major milestone"
            in quantum computing, demonstrating stable quantum operations at room temperature.
            This breakthrough could bring quantum computers closer to practical applications.</p>
            <p>The team's approach uses a novel error correction method that maintains quantum'
            coherence for unprecedented durations. The results have been peer-reviewed and
            published in a prestigious scientific journal.</p>""",
            "source": "bbc.com",
            "published_date": (base_time - timedelta(hours=5)).isoformat(),
            "author": "Science Correspondent",
            "category": "Science","
        },
        {
            "url": "https://dailymail.co.uk/tech/questionable-ai-claims",
            "title": "SHOCKING AI Discovery Will Change Everything!!!",
            "content": """<p>Experts claim new AI discovery!!!!</p>
            <p>This could be huge!!!!</p>""",
            "source": "dailymail.co.uk",
            "published_date": (base_time - timedelta(hours=1)).isoformat(),
            "category": "Technology",
        },
        {
            "url": "https://nature.com/articles/climate-research-2024",
            "title": "Climate Research Reveals Critical Ocean Current Changes",
            "content": """<p>New research published in Nature reveals significant changes in ocean"
            currents that could have far-reaching implications for global climate patterns. The
            study, based on 20 years of satellite data, shows unprecedented disruption in the
            Atlantic Meridional Overturning Circulation.</p><p>Lead researcher Dr. Maria Santos
            explains that these changes could affect weather patterns across multiple continents
            within the next decade. The findings call for immediate action on climate change
            mitigation strategies.</p>""",
            "source": "nature.com",
            "published_date": (base_time - timedelta(hours=8)).isoformat(),
            "author": "Dr. Maria Santos",
            "category": "Environment","
        },
        {
            "url": "https://reuters.com/health/medical-breakthrough",
            "title": "Gene Therapy Shows Promise for Rare Disease Treatment",
            "content": """<p>Clinical trials for a new gene therapy have shown remarkable success"
            in treating a rare genetic disorder affecting children. The treatment, developed over
            eight years of research, has demonstrated significant improvement in patient outcomes
            with minimal side effects.</p><p>The therapy works by correcting the genetic defect
            at the cellular level, addressing the root cause rather than just managing symptoms.
            Regulatory approval is expected within the next two years.</p>""",
            "source": "reuters.com",
            "published_date": (base_time - timedelta(hours=12)).isoformat(),
            "author": "Medical Reporter",
            "category": "Health","
        },
        {
            "url": "https://bbc.com/technology/space-mission-success",
            "title": "Space Mission Successfully Launches Advanced Earth Monitoring Satellite",
            "content": """<p>The latest Earth monitoring satellite has been successfully launched,"
            equipped with advanced sensors for tracking climate change, deforestation, and
            agricultural patterns. The satellite will provide unprecedented detail in
            environmental monitoring capabilities.</p><p>Mission Control confirmed all systems
            are functioning normally, and the satellite has begun transmitting data. The
            information will be crucial for understanding and addressing environmental challenges.</p>""",
            "source": "bbc.com",
            "published_date": (base_time - timedelta(hours=18)).isoformat(),
            "author": "Space Correspondent",
            "category": "Science","
        },
    ]


def create_mock_redshift_processor() -> RedshiftETLProcessor:
    """Create a mock Redshift processor for demonstration."""
    processor = MagicMock(spec=RedshiftETLProcessor)

    # Mock successful operations
    processor.connect.return_value = None
    processor.close.return_value = None
    processor.initialize_schema.return_value = None
    processor.load_single_article.return_value = True
    processor.batch_load_articles.return_value = {
        "total_articles": 6,
        "loaded_count": 5,
        f"ailed_count": 0,
        "skipped_count": 1,  # Duplicate
        "success_rate": 83.3,
        "processing_time_seconds": 2.5,
        "articles_per_second": 2.4,
        "errors": [],
    }
    processor.get_article_stats.return_value = {
        "total_articles": 150,
        "by_source_credibility": [
            {"source_credibility": "trusted", "count": 80},
            {"source_credibility": "reliable", "count": 45},
            {"source_credibility": "questionable", "count": 20},
            {"source_credibility": "unreliable", "count": 5},
        ],
        "by_content_quality": [
            {"content_quality": "high", "count": 90},
            {"content_quality": "medium", "count": 45},
            {"content_quality": "low", "count": 15},
        ],
        "avg_validation_score": {"average": 78.5, "minimum": 45.0, "maximum": 95.2},
        "recent_articles": 42,
        "top_sources": [
            {"source": "reuters.com", "count": 35},
            {"source": "bbc.com", "count": 28},
            {"source": "nature.com", "count": 22},
            {"source": "npr.org", "count": 18},
        ],
    }

    return processor


def demonstrate_etl_pipeline(use_mock: bool = True, batch_size: int = 100):
    """Demonstrate the complete ETL pipeline."""

    print(" NeuroNews Redshift ETL Pipeline Demo - Issue #22")
    print("=" * 60)

    # Step 1: Create sample articles
    print(""
📰 Step 1: Creating sample articles for processing...")"
    sample_articles = create_sample_articles()
    print(f"Created {len(sample_articles)} sample articles")

    # Step 2: Run articles through validation pipeline
    print(""
 Step 2: Processing articles through data validation pipeline...")"

    try:
        # Load validation configuration
        config_file = "config/validation_settings.json"
        if os.path.exists(config_file):
            config = SourceReputationConfig.from_file(config_file)
        else:
            print("⚠️  Validation settings not found, using default configuration")
            config = SourceReputationConfig(
                trusted_domains=["reuters.com", "bbc.com", "nature.com"],
                questionable_domains=["dailymail.co.uk"],
                banned_domains=["infowars.com"],
                reputation_thresholds={
                    "trusted": 0.9,
                    "reliable": 0.7,
                    "questionable": 0.4,
                    "unreliable": 0.2,
                },
            )

        # Initialize validation pipeline
        validation_pipeline = DataValidationPipeline(config)

        # Process articles
        validated_articles = []
        for article in sample_articles:
            result = validation_pipeline.process_article(article)
            if result:
                validated_articles.append(result.cleaned_data)
                print(f"   {article['title'][:50]}... (Score: {result.score:.1f})")
            else:
                print(f"  ❌ {article['title'][:50]}... (Rejected)")

        print(
            f""
 Validation complete: {len(validated_articles)}/{len(sample_articles)} articles accepted""
        )

        # Show validation statistics
        stats = validation_pipeline.get_statistics()
        print(f" Validation Stats: {stats['acceptance_rate']:.1f}% acceptance rate")

    except Exception as e:
        logger.error(f"Validation pipeline error: {e}")
        print("⚠️  Using raw articles without validation")
        validated_articles = sample_articles

    # Step 3: Initialize Redshift ETL Processor
    print(""
🗄️  Step 3: Initializing Redshift ETL Processor...")"

    if use_mock:
        print("🎭 Using mock Redshift processor for demonstration")
        etl_processor = create_mock_redshift_processor()
        print(" Mock processor initialized")
    else:
        # Real Redshift connection (requires environment variables)
        required_env_vars = ["REDSHIFT_HOST", "REDSHIFT_PASSWORD"]
        missing_vars = [var for var in required_env_vars if not os.environ.get(var)]

        if missing_vars:
            print(
                f"❌ Missing required environment variables: {', '.join(missing_vars)}"
            )
            print("Using mock processor instead...")
            etl_processor = create_mock_redshift_processor()
        else:
            try:
                etl_processor = RedshiftETLProcessor(
                    host=os.environ["REDSHIFT_HOST"],
                    database=os.environ.get("REDSHIFT_DATABASE", "dev"),
                    user=os.environ.get("REDSHIFT_USER", "admin"),
                    password=os.environ["REDSHIFT_PASSWORD"],
                    batch_size=batch_size,
                )
                etl_processor.connect()
                print(" Connected to Redshift cluster")

                # Initialize schema
                etl_processor.initialize_schema()
                print(" Schema initialized")

            except Exception as e:
                logger.error(f"Redshift connection failed: {e}")
                print("Using mock processor instead...")
                etl_processor = create_mock_redshift_processor()

    # Step 4: Load articles into Redshift
    print(f""
 Step 4: Loading {len(validated_articles)} articles into Redshift...")"

    try:
        if use_mock:
            # Simulate batch loading
            load_stats = etl_processor.batch_load_articles()
        else:
            load_stats = etl_processor.process_validation_pipeline_output(
                validated_articles
            )

        print(" Batch load completed!")
        print(" Load Statistics:")
        print(f"   • Total Articles: {load_stats['total_articles']}")
        print(f"   • Successfully Loaded: {load_stats['loaded_count']}")
        print(f"   • Failed: {load_stats[f'ailed_count']}")
        print(f"   • Skipped (Duplicates): {load_stats['skipped_count']}")
        print(f"   • Success Rate: {load_stats['success_rate']:.1f}%")
        print(
            f"   • Processing Time: {load_stats['processing_time_seconds']:.2f} seconds"
        )
        print(f"   • Articles/Second: {load_stats['articles_per_second']:.1f}")

        if load_stats.get("errors"):
            print(f"⚠️  Errors encountered: {len(load_stats['errors'])}")
            for error in load_stats["errors"][:3]:  # Show first 3 errors
                print(f"   • {error}")

    except Exception as e:
        logger.error(f"Batch loading failed: {e}")
        print(f"❌ Batch loading failed: {e}")

    # Step 5: Get database statistics
    print(""
 Step 5: Retrieving database statistics...")"

    try:
        if use_mock:
            db_stats = etl_processor.get_article_stats()
        else:
            db_stats = etl_processor.get_article_stats()

        print(" Database Statistics:")
        print(f"   • Total Articles in Database: {db_stats['total_articles']}")
        print(f"   • Recent Articles (7 days): {db_stats['recent_articles']}")

        if db_stats.get("avg_validation_score"):
            avg_score = db_stats["avg_validation_score"]
            print(f"   • Average Validation Score: {avg_score['average']:.1f}")
            print(
                f"   • Score Range: {avg_score['minimum']:.1f} - {avg_score['maximum']:.1f}"
            )

        print(""
 Articles by Source Credibility:")
        for item in db_stats.get("by_source_credibility", []):
            print(
                f"   • {item['source_credibility'].title()}: {item['count']} articles""
            )

        print("
 Articles by Content Quality:")
        for item in db_stats.get("by_content_quality", []):
            print(f"   • {item['content_quality'].title()}: {item['count']} articles")

        print("
 Top Sources:")
        for item in db_stats.get("top_sources", [])[:5]:
            print(f"   • {item['source']}: {item['count']} articles")

    except Exception as e:
        logger.error(f"Statistics retrieval failed: {e}")
        print(f"❌ Statistics retrieval failed: {e}")

    # Step 6: Cleanup
    print(""
🧹 Step 6: Cleanup...")"

    try:
        if hasattr(etl_processor, "close"):
            etl_processor.close()
        print(" Database connection closed")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

    print(""
 ETL Pipeline Demo Complete!")
    print("=" * 60)
    print(" Issue #22 Requirements Demonstrated:")
    print("   •  News articles schema defined in Redshift")
    print("   •  ETL process implemented (RedshiftETLProcessor)")
    print("   •  Raw JSON articles converted to structured format")
    print("   •  Batch uploads enabled for efficiency")
    print("   •  Integration with data validation pipeline")
    print("   •  Comprehensive error handling and statistics")"


def main():
    """Main function to run the demo."""
    parser = argparse.ArgumentParser(
        description="Demo Redshift ETL Pipeline - Issue #22"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock data instead of connecting to actual Redshift",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of articles per batch (default: 100)",
    )

    args = parser.parse_args()

    # Run the demonstration
    demonstrate_etl_pipeline(use_mock=args.mock, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
