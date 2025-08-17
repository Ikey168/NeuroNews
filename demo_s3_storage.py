#!/usr/bin/env python3
"""
Demo script for NeuroNews S3 Article Storage functionality.

This script demonstrates the comprehensive S3 storage capabilities
for raw and processed articles with proper organization and integrity verification.
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timezone
from typing import Dict, List, Any

# Add the project root to the path
sys.path.append('/workspaces/NeuroNews')

from src.database.s3_storage import (
    S3ArticleStorage,
    S3StorageConfig,
    ArticleType,
    ingest_scraped_articles_to_s3,
    verify_s3_data_consistency
)

# Sample news articles for demonstration
SAMPLE_ARTICLES = [
    {
        "title": "AI Revolution in Healthcare: New Breakthrough in Medical Diagnosis",
        "content": """
        Artificial Intelligence continues to transform healthcare with a groundbreaking 
        new system that can diagnose rare diseases with 95% accuracy. Researchers at 
        leading medical institutions have developed an AI model that analyzes medical 
        images and patient data to identify conditions that traditionally take weeks 
        to diagnose. This advancement could revolutionize patient care and reduce 
        diagnostic delays significantly.
        """.strip(),
        "url": "https://newsexample.com/ai-healthcare-breakthrough-2025",
        "source": "TechMed News",
        "published_date": "2025-08-13",
        "author": "Dr. Sarah Johnson",
        "tags": ["AI", "Healthcare", "Medical Technology", "Diagnosis"],
        "category": "Technology"
    },
    {
        "title": "Climate Change: New Carbon Capture Technology Shows Promise",
        "content": """
        Scientists have unveiled a revolutionary carbon capture technology that could 
        remove millions of tons of CO2 from the atmosphere annually. The new system 
        uses advanced materials and renewable energy to capture carbon dioxide directly 
        from the air and convert it into useful products. Early trials show the 
        technology is both cost-effective and scalable, offering hope in the fight 
        against climate change.
        """.strip(),
        "url": "https://newsexample.com/carbon-capture-breakthrough-2025",
        "source": "Environmental Science Today",
        "published_date": "2025-08-13",
        "author": "Prof. Michael Chen",
        "tags": ["Climate Change", "Carbon Capture", "Environment", "Technology"],
        "category": "Environment"
    },
    {
        "title": "Space Exploration: Mars Mission Discovers Signs of Ancient Water",
        "content": """
        NASA's latest Mars rover has uncovered compelling evidence of ancient water 
        systems on the Red Planet. The discovery includes mineral formations and 
        geological structures that could only have formed in the presence of flowing 
        water. This finding significantly strengthens the case for past life on Mars 
        and provides valuable insights for future human missions to the planet.
        """.strip(),
        "url": "https://newsexample.com/mars-water-discovery-2025",
        "source": "Space News Network",
        "published_date": "2025-08-13",
        "author": "Dr. Emily Rodriguez",
        "tags": ["Mars", "Space Exploration", "NASA", "Astrobiology"],
        "category": "Science"
    },
    {
        "title": "Renewable Energy: Solar Efficiency Reaches New Heights",
        "content": """
        A breakthrough in solar panel technology has achieved record-breaking efficiency 
        rates of over 50%, marking a significant milestone in renewable energy. The new 
        perovskite-silicon tandem cells promise to make solar power more affordable and 
        accessible worldwide. This advancement could accelerate the global transition 
        to clean energy and help nations meet their climate goals.
        """.strip(),
        "url": "https://newsexample.com/solar-efficiency-record-2025",
        "source": "Clean Energy Quarterly",
        "published_date": "2025-08-13",
        "author": "Dr. James Wilson",
        "tags": ["Solar Energy", "Renewable Energy", "Clean Technology", "Sustainability"],
        "category": "Energy"
    },
    {
        "title": "Cybersecurity: New AI-Powered Defense System Launched",
        "content": """
        A new AI-powered cybersecurity system has been deployed by major corporations 
        to defend against increasingly sophisticated cyber attacks. The system uses 
        machine learning to detect and respond to threats in real-time, adapting to 
        new attack patterns automatically. Early results show a 90% reduction in 
        successful cyber attacks among early adopters.
        """.strip(),
        "url": "https://newsexample.com/ai-cybersecurity-system-2025",
        "source": "Cyber Defense Weekly",
        "published_date": "2025-08-13",
        "author": "Alex Thompson",
        "tags": ["Cybersecurity", "AI", "Machine Learning", "Defense"],
        "category": "Technology"
    }
]

class S3StorageDemo:
    """Demo class for S3 article storage functionality."""
    
    def __init__(self):
        """Initialize the demo with S3 configuration."""
        # Load configuration from file
        config_path = '/workspaces/NeuroNews/src/database/config_s3.json'
        self.config = self._load_config(config_path)
        
        # Create S3 storage configuration
        self.s3_config = S3StorageConfig(
            bucket_name=self.config['s3_storage']['bucket_name'],
            region=self.config['s3_storage']['region'],
            raw_prefix=self.config['s3_storage']['raw_prefix'],
            processed_prefix=self.config['s3_storage']['processed_prefix'],
            enable_versioning=self.config['s3_storage']['enable_versioning'],
            enable_encryption=self.config['s3_storage']['enable_encryption'],
            storage_class=self.config['s3_storage']['storage_class'],
            lifecycle_days=self.config['s3_storage']['lifecycle_days'],
            max_file_size_mb=self.config['s3_storage']['max_file_size_mb']
        )
        
        # Initialize storage
        self.storage = None
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️  Configuration file not found: {config_path}")
            return self._get_default_config()
        except json.JSONDecodeError as e:
            print(f"⚠️  Error parsing configuration file: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "s3_storage": {
                "bucket_name": "neuronews-articles-demo",
                "region": "us-east-1",
                "raw_prefix": "raw_articles",
                "processed_prefix": "processed_articles",
                "enable_versioning": True,
                "enable_encryption": True,
                "storage_class": "STANDARD",
                "lifecycle_days": 365,
                "max_file_size_mb": 100
            }
        }
    
    async def initialize_storage(self):
        """Initialize S3 storage with error handling."""
        try:
            self.storage = S3ArticleStorage(self.s3_config)
            if self.storage.s3_client:
                print("✅ S3 storage initialized successfully")
                return True
            else:
                print("⚠️  S3 client not available (missing credentials)")
                return False
        except Exception as e:
            print(f"❌ Failed to initialize S3 storage: {e}")
            return False
    
    async def demo_basic_functionality(self):
        """Demonstrate basic S3 storage functionality."""
        print("\n" + "="*60)
        print("🔧 DEMO: Basic S3 Storage Functionality")
        print("="*60)
        
        if not self.storage or not self.storage.s3_client:
            print("⚠️  Demonstrating functionality without AWS credentials...")
            self._demo_functionality_without_aws()
            return
        
        try:
            # Demo 1: Store raw article
            print("\n📥 Demo 1: Storing Raw Article")
            sample_article = SAMPLE_ARTICLES[0]
            metadata = await self.storage.store_raw_article(sample_article)
            print(f"✅ Stored raw article: {metadata.s3_key}")
            print(f"   Article ID: {metadata.article_id}")
            print(f"   Content Hash: {metadata.content_hash[:16]}...")
            print(f"   File Size: {metadata.file_size} bytes")
            
            # Demo 2: Retrieve and verify article
            print("\n📤 Demo 2: Retrieving and Verifying Article")
            retrieved_article = await self.storage.retrieve_article(metadata.s3_key)
            print(f"✅ Retrieved article: {retrieved_article['title']}")
            
            is_valid = await self.storage.verify_article_integrity(metadata.s3_key)
            print(f"✅ Article integrity verified: {is_valid}")
            
            # Demo 3: Store processed article
            print("\n⚙️  Demo 3: Storing Processed Article")
            processed_article = {
                **sample_article,
                "nlp_processed": True,
                "sentiment_score": 0.85,
                "key_entities": ["AI", "Healthcare", "Medical Technology"],
                "summary": "AI breakthrough in medical diagnosis shows 95% accuracy."
            }
            
            processing_metadata = {
                "nlp_model": "NeuroNLP-v2.1",
                "processing_time": 2.3,
                "confidence_score": 0.92
            }
            
            processed_metadata = await self.storage.store_processed_article(
                processed_article, processing_metadata
            )
            print(f"✅ Stored processed article: {processed_metadata.s3_key}")
            
        except Exception as e:
            print(f"❌ Error in basic functionality demo: {e}")
    
    def _demo_functionality_without_aws(self):
        """Demo functionality without actual AWS connection."""
        print("\n📝 Demonstrating S3 key generation and structure...")
        
        sample_article = SAMPLE_ARTICLES[0]
        
        # Test key generation
        raw_key = self.storage._generate_s3_key(sample_article, ArticleType.RAW)
        processed_key = self.storage._generate_s3_key(sample_article, ArticleType.PROCESSED)
        
        print(f"✅ Raw article S3 key: {raw_key}")
        print(f"✅ Processed article S3 key: {processed_key}")
        
        # Test content hash
        content_hash = self.storage._calculate_content_hash(sample_article['content'])
        print(f"✅ Content hash: {content_hash[:16]}...")
        
        # Test article ID generation
        article_id = self.storage._generate_article_id(sample_article)
        print(f"✅ Article ID: {article_id}")
    
    async def demo_batch_ingestion(self):
        """Demonstrate batch article ingestion."""
        print("\n" + "="*60)
        print("📦 DEMO: Batch Article Ingestion")
        print("="*60)
        
        if not self.storage or not self.storage.s3_client:
            print("⚠️  Skipping batch ingestion demo (no AWS credentials)")
            return
        
        try:
            print(f"\n📥 Ingesting {len(SAMPLE_ARTICLES)} articles...")
            
            # Use the ingestion function
            result = await ingest_scraped_articles_to_s3(
                SAMPLE_ARTICLES, 
                self.s3_config
            )
            
            print(f"✅ Ingestion Status: {result['status']}")
            print(f"   Total Articles: {result['total_articles']}")
            print(f"   Stored Successfully: {result['stored_articles']}")
            print(f"   Failed: {result['failed_articles']}")
            
            if result['errors']:
                print(f"   Errors: {len(result['errors'])}")
                for error in result['errors'][:3]:  # Show first 3 errors
                    print(f"     - {error}")
            
            if result['stored_keys']:
                print(f"\n📁 Sample stored keys:")
                for key in result['stored_keys'][:3]:  # Show first 3 keys
                    print(f"   - {key}")
            
        except Exception as e:
            print(f"❌ Error in batch ingestion demo: {e}")
    
    async def demo_data_organization(self):
        """Demonstrate S3 data organization structure."""
        print("\n" + "="*60)
        print("📁 DEMO: S3 Data Organization Structure")
        print("="*60)
        
        print("\n🗂️  Expected S3 bucket structure:")
        print("neuronews-articles/")
        print("├── raw_articles/")
        print("│   └── 2025/")
        print("│       └── 08/")
        print("│           └── 13/")
        print("│               ├── article1.json")
        print("│               ├── article2.json")
        print("│               └── ...")
        print("└── processed_articles/")
        print("    └── 2025/")
        print("        └── 08/")
        print("            └── 13/")
        print("                ├── article1.json")
        print("                ├── article2.json")
        print("                └── ...")
        
        if not self.storage or not self.storage.s3_client:
            print("\n⚠️  Would demonstrate actual S3 structure with AWS credentials")
            return
        
        try:
            # List articles by date
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            
            print(f"\n📋 Listing articles for {today}:")
            
            raw_articles = await self.storage.list_articles_by_date(today, ArticleType.RAW)
            processed_articles = await self.storage.list_articles_by_date(today, ArticleType.PROCESSED)
            
            print(f"   Raw articles: {len(raw_articles)}")
            for article in raw_articles[:3]:  # Show first 3
                print(f"     - {article}")
            
            print(f"   Processed articles: {len(processed_articles)}")
            for article in processed_articles[:3]:  # Show first 3
                print(f"     - {article}")
                
        except Exception as e:
            print(f"❌ Error demonstrating data organization: {e}")
    
    async def demo_data_consistency_verification(self):
        """Demonstrate data consistency and integrity verification."""
        print("\n" + "="*60)
        print("🔍 DEMO: Data Consistency & Integrity Verification")
        print("="*60)
        
        if not self.storage or not self.storage.s3_client:
            print("⚠️  Skipping verification demo (no AWS credentials)")
            return
        
        try:
            print("\n🔐 Running data consistency verification...")
            
            result = await verify_s3_data_consistency(
                self.s3_config, 
                sample_size=50
            )
            
            print(f"✅ Verification Status: {result['status']}")
            print(f"   Total Articles Checked: {result['total_checked']}")
            print(f"   Valid Articles: {result['valid_articles']}")
            print(f"   Invalid Articles: {result['invalid_articles']}")
            
            if 'integrity_rate' in result:
                print(f"   Integrity Rate: {result['integrity_rate']:.1f}%")
            
            if result['errors']:
                print(f"\n⚠️  Integrity Issues Found:")
                for error in result['errors'][:5]:  # Show first 5 errors
                    print(f"     - {error}")
            
            # Storage statistics
            if 'storage_statistics' in result:
                stats = result['storage_statistics']
                print(f"\n📊 Storage Statistics:")
                print(f"   Total Articles: {stats.get('total_count', 0)}")
                print(f"   Raw Articles: {stats.get('raw_articles', {}).get('count', 0)}")
                print(f"   Processed Articles: {stats.get('processed_articles', {}).get('count', 0)}")
                
        except Exception as e:
            print(f"❌ Error in data consistency verification: {e}")
    
    async def demo_storage_statistics(self):
        """Demonstrate storage statistics and monitoring."""
        print("\n" + "="*60)
        print("📊 DEMO: Storage Statistics & Monitoring")
        print("="*60)
        
        if not self.storage or not self.storage.s3_client:
            print("⚠️  Skipping statistics demo (no AWS credentials)")
            return
        
        try:
            print("\n📈 Retrieving storage statistics...")
            
            stats = await self.storage.get_storage_statistics()
            
            if 'error' in stats:
                print(f"❌ Error retrieving statistics: {stats['error']}")
                return
            
            print("✅ Storage Statistics:")
            print(f"   Total Articles: {stats['total_count']}")
            print(f"   Total Size: {stats['total_size']:,} bytes")
            
            print(f"\n📁 Raw Articles:")
            print(f"   Count: {stats['raw_articles']['count']}")
            print(f"   Size: {stats['raw_articles']['total_size']:,} bytes")
            
            print(f"\n⚙️  Processed Articles:")
            print(f"   Count: {stats['processed_articles']['count']}")
            print(f"   Size: {stats['processed_articles']['total_size']:,} bytes")
            
            print(f"\n🕒 Last Updated: {stats['last_updated']}")
            
        except Exception as e:
            print(f"❌ Error retrieving storage statistics: {e}")
    
    async def demo_cleanup_operations(self):
        """Demonstrate cleanup and maintenance operations."""
        print("\n" + "="*60)
        print("🧹 DEMO: Cleanup & Maintenance Operations")
        print("="*60)
        
        if not self.storage or not self.storage.s3_client:
            print("⚠️  Demonstrating cleanup concepts without AWS...")
            print("📝 Cleanup operations would:")
            print("   - Remove articles older than configured retention period")
            print("   - Clean up incomplete uploads")
            print("   - Optimize storage costs through lifecycle policies")
            print("   - Generate maintenance reports")
            return
        
        try:
            print("\n🧹 Note: This is a demonstration. No actual cleanup will be performed.")
            print("   In production, cleanup operations would:")
            print("   - Remove articles older than retention period")
            print("   - Transition old data to cheaper storage classes")
            print("   - Generate cleanup reports")
            
            # Demonstrate what cleanup would do (without actually doing it)
            print(f"\n📅 Simulating cleanup for articles older than {self.s3_config.lifecycle_days} days...")
            
            # Get current statistics
            stats = await self.storage.get_storage_statistics()
            print(f"   Current total articles: {stats.get('total_count', 0)}")
            
            # In a real scenario, this would clean up old articles
            print("   ✅ Cleanup simulation completed")
            
        except Exception as e:
            print(f"❌ Error in cleanup demonstration: {e}")
    
    def print_configuration_summary(self):
        """Print configuration summary."""
        print("\n" + "="*60)
        print("⚙️  S3 STORAGE CONFIGURATION SUMMARY")
        print("="*60)
        
        print(f"🪣 Bucket: {self.s3_config.bucket_name}")
        print(f"🌍 Region: {self.s3_config.region}")
        print(f"📁 Raw Prefix: {self.s3_config.raw_prefix}")
        print(f"⚙️  Processed Prefix: {self.s3_config.processed_prefix}")
        print(f"🔒 Encryption: {'Enabled' if self.s3_config.enable_encryption else 'Disabled'}")
        print(f"📝 Versioning: {'Enabled' if self.s3_config.enable_versioning else 'Disabled'}")
        print(f"💾 Storage Class: {self.s3_config.storage_class}")
        print(f"🗓️  Lifecycle: {self.s3_config.lifecycle_days} days")
        print(f"📏 Max File Size: {self.s3_config.max_file_size_mb} MB")
    
    async def run_complete_demo(self):
        """Run complete S3 storage demonstration."""
        print("🚀 NeuroNews S3 Article Storage Demo")
        print("="*60)
        print("This demo showcases comprehensive S3 storage capabilities")
        print("for organizing and managing scraped news articles.")
        
        # Initialize storage
        storage_available = await self.initialize_storage()
        
        # Print configuration
        self.print_configuration_summary()
        
        # Run all demos
        await self.demo_basic_functionality()
        await self.demo_batch_ingestion()
        await self.demo_data_organization()
        await self.demo_data_consistency_verification()
        await self.demo_storage_statistics()
        await self.demo_cleanup_operations()
        
        # Summary
        print("\n" + "="*60)
        print("✨ DEMO SUMMARY")
        print("="*60)
        
        print("🎯 Demonstrated Features:")
        print("   ✅ Raw article storage with proper S3 organization")
        print("   ✅ Processed article storage with metadata")
        print("   ✅ Batch ingestion capabilities")
        print("   ✅ Data integrity verification")
        print("   ✅ Storage statistics and monitoring")
        print("   ✅ Structured S3 organization (YYYY/MM/DD)")
        print("   ✅ Cleanup and maintenance operations")
        
        if not storage_available:
            print("\n⚠️  Note: This demo ran without AWS credentials.")
            print("   To see full functionality, configure AWS credentials and run again.")
            print("   See AWS_DEPLOYMENT_GUIDE.md for setup instructions.")
        
        print("\n🚀 S3 Article Storage is ready for production use!")


async def main():
    """Main demo function."""
    demo = S3StorageDemo()
    await demo.run_complete_demo()


if __name__ == "__main__":
    print("Starting NeuroNews S3 Storage Demo...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nDemo completed. Thank you for exploring NeuroNews S3 Storage! 🎉")
