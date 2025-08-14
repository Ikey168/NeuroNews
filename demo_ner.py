"""
Demo script for Named Entity Recognition (NER) functionality.
Showcases entity extraction from news articles with various entity types.
"""

import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any
import json

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.nlp.ner_processor import create_ner_processor
from src.nlp.ner_article_processor import create_ner_article_processor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NERDemo:
    """
    Demonstration class for NER functionality.
    Shows entity extraction capabilities across different article types.
    """
    
    def __init__(self):
        """Initialize the NER demo."""
        logger.info("Initializing NER Demo...")
        
        # Sample articles for demonstration
        self.sample_articles = [
            {
                'article_id': 'tech_news_1',
                'title': 'Apple Unveils Revolutionary AI Chip at WWDC',
                'content': '''
                Apple Inc. CEO Tim Cook announced the company's latest breakthrough in artificial intelligence 
                during the Worldwide Developers Conference (WWDC) in Cupertino, California. The new M3 Neural 
                chip features advanced machine learning capabilities powered by a custom neural processing unit.
                
                "This represents a quantum leap in our AI capabilities," said Cook during the keynote presentation.
                The chip will power Apple's new Siri 2.0 voice assistant and enhance the company's Privacy 
                Protection Policy. Apple's Senior Vice President of Hardware Technologies, Johny Srouji, 
                demonstrated the chip's performance improvements in real-time language translation and 
                computer vision tasks.
                
                The announcement sent Apple's stock price soaring on NASDAQ, with analysts from Goldman Sachs 
                and Morgan Stanley praising the innovation. The chip will be manufactured using TSMC's 
                3-nanometer process and will debut in the upcoming iPhone 16 and MacBook Pro models.
                ''',
                'url': 'https://example.com/apple-ai-chip',
                'source': 'TechCrunch',
                'category': 'Technology'
            },
            {
                'article_id': 'policy_news_1',
                'title': 'EU Passes Landmark AI Regulation Act',
                'content': '''
                The European Union has passed the comprehensive Artificial Intelligence Act, marking the 
                world's first major regulation of AI systems. The legislation was approved by the European 
                Parliament in Brussels after months of negotiations between member states.
                
                European Commission President Ursula von der Leyen hailed the act as "a global first that 
                will set the standard for AI governance worldwide." The regulation introduces strict 
                requirements for high-risk AI applications in healthcare, finance, and law enforcement.
                
                Companies like Google, Microsoft, and Meta will need to comply with new transparency 
                requirements for their large language models. The act also establishes the European AI 
                Office in Dublin, Ireland, to oversee implementation and enforcement.
                
                Privacy advocates, including the Electronic Frontier Foundation and Privacy International, 
                welcomed the legislation's focus on protecting citizens' rights. However, some tech industry 
                groups expressed concerns about compliance costs and innovation impacts.
                
                The regulation will be phased in over the next two years, with penalties reaching up to 
                €35 million or 7% of global annual revenue for violations.
                ''',
                'url': 'https://example.com/eu-ai-regulation',
                'source': 'Reuters',
                'category': 'Policy'
            },
            {
                'article_id': 'science_news_1',
                'title': 'MIT Researchers Achieve Quantum Computing Breakthrough',
                'content': '''
                Researchers at the Massachusetts Institute of Technology (MIT) have demonstrated a new 
                quantum error correction method that could bring practical quantum computing closer to 
                reality. The team, led by Professor Peter Shor and Dr. Sarah Chen, published their 
                findings in the journal Nature Quantum Information.
                
                The breakthrough was achieved using IBM's 127-qubit quantum processor at the MIT-IBM 
                Watson AI Lab in Cambridge, Massachusetts. The research was funded by the National 
                Science Foundation (NSF) and the Defense Advanced Research Projects Agency (DARPA).
                
                "This represents a major step toward fault-tolerant quantum computing," said Shor, 
                who is also known for developing Shor's algorithm for quantum factorization. The team's 
                approach reduces quantum error rates by 90% compared to previous methods.
                
                The research has implications for cryptography, drug discovery, and climate modeling. 
                Companies like Rigetti Computing, IonQ, and Atom Computing are already exploring 
                commercial applications of the technology.
                
                The work builds on earlier research from Google's Quantum AI team and the University 
                of California, Berkeley. The next phase will involve scaling the approach to larger 
                quantum systems with support from the Department of Energy.
                ''',
                'url': 'https://example.com/quantum-breakthrough',
                'source': 'MIT Technology Review',
                'category': 'Science'
            }
        ]
        
        logger.info(f"Loaded {len(self.sample_articles)} sample articles for demonstration")
    
    def demo_basic_ner(self):
        """Demonstrate basic NER functionality."""
        logger.info("=== Basic NER Demonstration ===")
        
        try:
            # Create NER processor
            ner_processor = create_ner_processor(
                confidence_threshold=0.7
            )
            
            # Process first article
            article = self.sample_articles[0]
            full_text = f"{article['title']}. {article['content']}"
            
            logger.info(f"Processing article: {article['title']}")
            logger.info(f"Text length: {len(full_text)} characters")
            
            # Extract entities
            entities = ner_processor.extract_entities(full_text, article['article_id'])
            
            # Display results
            logger.info(f"Extracted {len(entities)} entities:")
            
            entity_types = {}
            for entity in entities:
                entity_type = entity['type']
                if entity_type not in entity_types:
                    entity_types[entity_type] = []
                entity_types[entity_type].append(entity)
                
                logger.info(f"  {entity['text']} ({entity['type']}) - Confidence: {entity['confidence']:.2f}")
            
            # Show entity type distribution
            logger.info("\nEntity Type Distribution:")
            for entity_type, type_entities in entity_types.items():
                logger.info(f"  {entity_type}: {len(type_entities)} entities")
            
            # Show statistics
            stats = ner_processor.get_statistics()
            logger.info(f"\nProcessing Statistics:")
            logger.info(f"  Total texts processed: {stats['total_texts_processed']}")
            logger.info(f"  Total entities extracted: {stats['total_entities_extracted']}")
            logger.info(f"  Average entities per text: {stats['average_entities_per_text']:.2f}")
            
            return entities
            
        except Exception as e:
            logger.error(f"Error in basic NER demo: {e}")
            return []
    
    def demo_entity_types(self):
        """Demonstrate different entity types across all articles."""
        logger.info("\n=== Entity Types Demonstration ===")
        
        try:
            ner_processor = create_ner_processor(confidence_threshold=0.6)
            
            all_entities = []
            for article in self.sample_articles:
                full_text = f"{article['title']}. {article['content']}"
                entities = ner_processor.extract_entities(full_text, article['article_id'])
                
                for entity in entities:
                    entity['article_title'] = article['title']
                    entity['article_category'] = article['category']
                
                all_entities.extend(entities)
            
            # Group entities by type
            entity_groups = {}
            for entity in all_entities:
                entity_type = entity['type']
                if entity_type not in entity_groups:
                    entity_groups[entity_type] = []
                entity_groups[entity_type].append(entity)
            
            # Display by type
            for entity_type, entities in sorted(entity_groups.items()):
                logger.info(f"\n{entity_type} Entities ({len(entities)} found):")
                
                # Show top entities by confidence
                sorted_entities = sorted(entities, key=lambda x: x['confidence'], reverse=True)
                for entity in sorted_entities[:5]:  # Top 5
                    logger.info(f"  • {entity['text']} (Confidence: {entity['confidence']:.2f}) "
                              f"from '{entity['article_title']}'")
                
                if len(entities) > 5:
                    logger.info(f"  ... and {len(entities) - 5} more")
            
            return entity_groups
            
        except Exception as e:
            logger.error(f"Error in entity types demo: {e}")
            return {}
    
    def demo_technology_detection(self):
        """Demonstrate technology-specific entity detection."""
        logger.info("\n=== Technology Entity Detection ===")
        
        try:
            ner_processor = create_ner_processor(confidence_threshold=0.5)
            
            # Focus on technology article
            tech_article = self.sample_articles[0]  # Apple AI chip article
            full_text = f"{tech_article['title']}. {tech_article['content']}"
            
            entities = ner_processor.extract_entities(full_text, tech_article['article_id'])
            
            # Filter technology-related entities
            tech_entities = [e for e in entities if 'TECHNOLOGY' in e['type']]
            org_entities = [e for e in entities if e['type'] in ['ORGANIZATION', 'TECHNOLOGY_ORGANIZATION']]
            location_entities = [e for e in entities if e['type'] == 'LOCATION']
            person_entities = [e for e in entities if e['type'] == 'PERSON']
            
            logger.info("Technology-Related Entities:")
            for entity in tech_entities:
                logger.info(f"  🔧 {entity['text']} ({entity['type']}) - {entity['confidence']:.2f}")
            
            logger.info("\nOrganizations:")
            for entity in org_entities:
                logger.info(f"  🏢 {entity['text']} ({entity['type']}) - {entity['confidence']:.2f}")
            
            logger.info("\nKey People:")
            for entity in person_entities:
                logger.info(f"  👤 {entity['text']} - {entity['confidence']:.2f}")
            
            logger.info("\nLocations:")
            for entity in location_entities:
                logger.info(f"  📍 {entity['text']} - {entity['confidence']:.2f}")
            
            return {
                'technology': tech_entities,
                'organizations': org_entities,
                'people': person_entities,
                'locations': location_entities
            }
            
        except Exception as e:
            logger.error(f"Error in technology detection demo: {e}")
            return {}
    
    def demo_policy_detection(self):
        """Demonstrate policy and regulation entity detection."""
        logger.info("\n=== Policy & Regulation Detection ===")
        
        try:
            ner_processor = create_ner_processor(confidence_threshold=0.5)
            
            # Focus on policy article
            policy_article = self.sample_articles[1]  # EU AI regulation article
            full_text = f"{policy_article['title']}. {policy_article['content']}"
            
            entities = ner_processor.extract_entities(full_text, policy_article['article_id'])
            
            # Categorize entities
            policy_entities = [e for e in entities if e['type'] == 'POLICY']
            org_entities = [e for e in entities if 'ORGANIZATION' in e['type']]
            location_entities = [e for e in entities if e['type'] == 'LOCATION']
            person_entities = [e for e in entities if e['type'] == 'PERSON']
            
            logger.info("Policy/Regulation Entities:")
            for entity in policy_entities:
                logger.info(f"  📋 {entity['text']} - {entity['confidence']:.2f}")
            
            logger.info("\nRegulatory Bodies & Organizations:")
            for entity in org_entities:
                logger.info(f"  🏛️ {entity['text']} ({entity['type']}) - {entity['confidence']:.2f}")
            
            logger.info("\nKey Officials:")
            for entity in person_entities:
                logger.info(f"  👥 {entity['text']} - {entity['confidence']:.2f}")
            
            logger.info("\nJurisdictions:")
            for entity in location_entities:
                logger.info(f"  🌍 {entity['text']} - {entity['confidence']:.2f}")
            
            return entities
            
        except Exception as e:
            logger.error(f"Error in policy detection demo: {e}")
            return []
    
    def demo_full_pipeline(self):
        """Demonstrate the full NER article processing pipeline."""
        logger.info("\n=== Full NER Pipeline Demonstration ===")
        
        # Note: This would typically connect to a real database
        # For demo purposes, we'll simulate the database operations
        logger.info("Note: Database operations are simulated for demo purposes")
        
        try:
            # Mock database configuration
            config = {
                'redshift_host': 'demo-cluster.us-west-2.redshift.amazonaws.com',
                'redshift_port': 5439,
                'redshift_database': 'newsdb',
                'redshift_user': 'demo_user',
                'redshift_password': 'demo_password',
                'sentiment_provider': 'vader',  # Use VADER for demo (no API required)
                'ner_enabled': True,
                'ner_confidence_threshold': 0.7
            }
            
            # This would normally create a real processor, but we'll demonstrate the structure
            logger.info("Creating NER Article Processor...")
            logger.info(f"Configuration: NER enabled, confidence threshold: {config['ner_confidence_threshold']}")
            
            # Simulate processing results
            results = []
            for i, article in enumerate(self.sample_articles):
                # Simulate entity extraction
                ner_processor = create_ner_processor(confidence_threshold=0.7)
                full_text = f"{article['title']}. {article['content']}"
                entities = ner_processor.extract_entities(full_text, article['article_id'])
                
                # Simulate processing result
                result = {
                    'article_id': article['article_id'],
                    'title': article['title'],
                    'url': article['url'],
                    'sentiment': 'positive' if i % 2 == 0 else 'neutral',  # Mock sentiment
                    'confidence': 0.85,
                    'entities': entities,
                    'entity_count': len(entities),
                    'entity_types': list(set(e['type'] for e in entities)),
                    'processed_at': datetime.utcnow().isoformat()
                }
                results.append(result)
                
                logger.info(f"Processed article '{article['title']}':")
                logger.info(f"  - Sentiment: {result['sentiment']} ({result['confidence']:.2f})")
                logger.info(f"  - Entities: {result['entity_count']} extracted")
                logger.info(f"  - Entity types: {', '.join(result['entity_types'])}")
            
            logger.info(f"\nPipeline completed: {len(results)} articles processed")
            
            # Simulate database storage summary
            total_entities = sum(r['entity_count'] for r in results)
            logger.info(f"Would store {total_entities} entities in database tables:")
            logger.info("  - article_sentiment: sentiment analysis results")
            logger.info("  - article_entities: detailed entity information")
            logger.info("  - news_articles: updated with entities JSON")
            
            return results
            
        except Exception as e:
            logger.error(f"Error in full pipeline demo: {e}")
            return []
    
    def demo_statistics_and_search(self):
        """Demonstrate statistics and search capabilities."""
        logger.info("\n=== Statistics & Search Demo ===")
        
        try:
            ner_processor = create_ner_processor(confidence_threshold=0.6)
            
            # Process all articles
            all_entities = []
            for article in self.sample_articles:
                full_text = f"{article['title']}. {article['content']}"
                entities = ner_processor.extract_entities(full_text, article['article_id'])
                all_entities.extend(entities)
            
            # Get statistics
            stats = ner_processor.get_statistics()
            
            logger.info("Overall NER Statistics:")
            logger.info(f"  📊 Total texts processed: {stats['total_texts_processed']}")
            logger.info(f"  🎯 Total entities extracted: {stats['total_entities_extracted']}")
            logger.info(f"  📈 Average entities per text: {stats['average_entities_per_text']:.2f}")
            logger.info(f"  ⚠️ Processing errors: {stats['processing_errors']}")
            
            logger.info("\nEntity Type Distribution:")
            for entity_type, count in sorted(stats['entity_type_distribution'].items(), 
                                           key=lambda x: x[1], reverse=True):
                percentage = (count / stats['total_entities_extracted']) * 100
                logger.info(f"  {entity_type}: {count} ({percentage:.1f}%)")
            
            # Demonstrate search functionality
            logger.info("\nEntity Search Examples:")
            
            # Search for Apple entities
            apple_entities = [e for e in all_entities if 'apple' in e['text'].lower()]
            if apple_entities:
                logger.info(f"  🔍 Found {len(apple_entities)} Apple-related entities:")
                for entity in apple_entities[:3]:
                    logger.info(f"    • {entity['text']} ({entity['type']}) - {entity['confidence']:.2f}")
            
            # Search for high-confidence entities
            high_conf_entities = [e for e in all_entities if e['confidence'] >= 0.9]
            logger.info(f"  🏆 High-confidence entities (≥0.9): {len(high_conf_entities)}")
            for entity in sorted(high_conf_entities, key=lambda x: x['confidence'], reverse=True)[:5]:
                logger.info(f"    • {entity['text']} ({entity['type']}) - {entity['confidence']:.2f}")
            
            # Search by entity type
            org_entities = [e for e in all_entities if 'ORGANIZATION' in e['type']]
            logger.info(f"  🏢 Organization entities: {len(org_entities)}")
            for entity in sorted(org_entities, key=lambda x: x['confidence'], reverse=True)[:5]:
                logger.info(f"    • {entity['text']} ({entity['type']}) - {entity['confidence']:.2f}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error in statistics demo: {e}")
            return {}
    
    def run_all_demos(self):
        """Run all demonstration scenarios."""
        logger.info("🚀 Starting NER Demo Suite")
        logger.info("=" * 50)
        
        try:
            # Run individual demos
            self.demo_basic_ner()
            self.demo_entity_types()
            self.demo_technology_detection()
            self.demo_policy_detection()
            self.demo_full_pipeline()
            self.demo_statistics_and_search()
            
            logger.info("\n" + "=" * 50)
            logger.info("🎉 NER Demo Suite Completed Successfully!")
            logger.info("\nKey Features Demonstrated:")
            logger.info("  ✅ Basic entity extraction (PERSON, ORGANIZATION, LOCATION)")
            logger.info("  ✅ Technology-specific entity detection")
            logger.info("  ✅ Policy and regulation entity detection")
            logger.info("  ✅ Enhanced entity type classification")
            logger.info("  ✅ Full processing pipeline integration")
            logger.info("  ✅ Statistics and search capabilities")
            logger.info("  ✅ Database storage simulation")
            
        except Exception as e:
            logger.error(f"Error running demo suite: {e}")
            raise


def save_demo_results(results: List[Dict], filename: str = "ner_demo_results.json"):
    """Save demo results to JSON file."""
    try:
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Demo results saved to {filename}")
    except Exception as e:
        logger.error(f"Failed to save results: {e}")


if __name__ == "__main__":
    """Run the NER demonstration."""
    
    # Check if running in an environment that supports transformers
    try:
        import torch
        import transformers
        logger.info(f"PyTorch version: {torch.__version__}")
        logger.info(f"Transformers version: {transformers.__version__}")
        
        # Run the demo
        demo = NERDemo()
        demo.run_all_demos()
        
    except ImportError as e:
        logger.error("Missing required dependencies for NER demo")
        logger.error("Please install: pip install torch transformers")
        logger.error(f"Import error: {e}")
        
        # Show what the demo would do
        logger.info("\n" + "=" * 50)
        logger.info("NER Demo Overview (Dependencies Missing)")
        logger.info("=" * 50)
        logger.info("This demo would showcase:")
        logger.info("1. Entity extraction from news articles")
        logger.info("2. Classification of PERSON, ORGANIZATION, LOCATION entities")
        logger.info("3. Technology-specific entity detection (AI, ML, companies)")
        logger.info("4. Policy and regulation entity detection")
        logger.info("5. Integration with sentiment analysis pipeline")
        logger.info("6. Database storage of extracted entities")
        logger.info("7. Statistics and search capabilities")
        
    except Exception as e:
        logger.error(f"Demo failed with error: {e}")
        raise
