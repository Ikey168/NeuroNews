#!/usr/bin/env python3
"""
Demo: MLflow-instrumented Embeddings & Indexer Jobs
Issue #217: Instrument embeddings & indexer jobs with MLflow tracking

This demo showcases the complete MLflow tracking integration for embeddings
generation and RAG indexing, logging parameters, metrics, and artifacts.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from services.embeddings.provider import EmbeddingsProvider
    from jobs.rag.indexer import RAGIndexer
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure you're running from the project root directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def demo_embeddings_provider():
    """Demo the EmbeddingsProvider with MLflow tracking."""
    print("\n" + "="*80)
    print("🧠 DEMO: Embeddings Provider with MLflow Tracking")
    print("="*80)
    
    # Create provider
    provider = EmbeddingsProvider(
        model_name="all-MiniLM-L6-v2",
        batch_size=8,
        max_workers=2,
    )
    
    # Sample news articles for embedding
    sample_texts = [
        "Breaking: AI researchers achieve breakthrough in natural language understanding with new transformer architecture",
        "Scientists develop revolutionary solar panel technology that doubles energy efficiency while reducing costs by 50%",
        "Global markets surge as tech companies report record earnings driven by artificial intelligence investments",
        "Climate change summit reaches historic agreement on carbon reduction targets for next decade",
        "Space exploration takes leap forward with successful launch of Mars sample return mission",
        "Medical breakthrough: Gene therapy shows promising results in treating rare genetic disorders",
        "Quantum computing milestone achieved with error-corrected quantum processor demonstration",
        "Renewable energy adoption accelerates globally as wind and solar costs hit record lows",
        "Cybersecurity experts warn of increased AI-powered attacks targeting financial institutions",
        "Educational technology transforms learning with personalized AI tutoring systems showing remarkable results"
    ]
    
    print(f"📄 Processing {len(sample_texts)} news articles...")
    print(f"🔧 Model: {provider.model_name}")
    print(f"📐 Embedding dimension: {provider.embedding_dimension}")
    print(f"🔄 Batch size: {provider.batch_size}")
    
    # Generate embeddings with MLflow tracking
    start_time = datetime.now()
    embeddings, metrics = await provider.generate_embeddings(
        sample_texts,
        experiment_name="embeddings_demo", 
        run_name=f"news_articles_{start_time.strftime('%Y%m%d_%H%M%S')}"
    )
    
    # Display results
    print(f"\n✅ Embeddings generation completed!")
    print(f"📊 Metrics:")
    print(f"   • Documents processed: {metrics['documents_processed']}")
    print(f"   • Embeddings generated: {metrics['embeddings_generated']}")
    print(f"   • Processing speed: {metrics['embeddings_per_second']:.1f} embeddings/sec")
    print(f"   • Total time: {metrics['total_processing_time']:.2f}s")
    print(f"   • Failures: {metrics['failures']}")
    
    # Show sample embedding properties
    if embeddings:
        sample_embedding = embeddings[0]
        print(f"\n🔍 Sample embedding analysis:")
        print(f"   • Shape: {sample_embedding.shape}")
        print(f"   • Norm: {float(sum(x*x for x in sample_embedding)**0.5):.3f}")
        print(f"   • Mean: {float(sum(sample_embedding)/len(sample_embedding)):.6f}")
        print(f"   • Non-zero elements: {sum(1 for x in sample_embedding if abs(x) > 1e-6)}/{len(sample_embedding)}")
    
    print(f"\n📋 MLflow tracking logged:")
    print(f"   • Parameters: provider, model, dimension, batch_size, max_workers")
    print(f"   • Metrics: docs_processed, embeddings_per_second, failures")
    print(f"   • Artifacts: sample_embeddings.json, latency_histogram.json, model_info.json")
    
    return embeddings, metrics


async def demo_rag_indexer():
    """Demo the RAGIndexer with MLflow tracking."""
    print("\n" + "="*80)
    print("🗂️  DEMO: RAG Indexer with MLflow Tracking")
    print("="*80)
    
    # Create indexer
    indexer = RAGIndexer(
        chunk_size=128,
        chunk_overlap=25,
        batch_size=4,
        embedding_model="all-MiniLM-L6-v2",
        index_type="flat",
    )
    
    # Sample news documents for indexing
    sample_documents = [
        {
            "id": "news_001",
            "title": "Artificial Intelligence Revolution in Healthcare",
            "content": """
            Artificial intelligence is transforming healthcare at an unprecedented pace. Machine learning algorithms
            are now being used to diagnose diseases with accuracy that rivals human doctors. Deep learning models
            can analyze medical images, predict patient outcomes, and even discover new drug compounds. Hospitals
            worldwide are implementing AI-powered systems for patient monitoring, treatment planning, and resource
            optimization. The integration of AI in healthcare promises to reduce costs while improving patient care
            quality. Natural language processing is helping doctors analyze patient records more efficiently, while
            computer vision is revolutionizing radiology and pathology. As AI continues to evolve, we can expect
            even more groundbreaking applications in personalized medicine and preventive care.
            """
        },
        {
            "id": "news_002", 
            "title": "Renewable Energy Reaches Tipping Point",
            "content": """
            The renewable energy sector has reached a critical tipping point with solar and wind power becoming
            the cheapest sources of electricity in many regions worldwide. Solar panel efficiency has improved
            dramatically over the past decade, while manufacturing costs have plummeted. Wind turbines are
            growing larger and more efficient, capable of generating power even in low-wind conditions. Energy
            storage solutions are also advancing rapidly, with battery technology improvements making renewable
            energy more reliable. Countries are setting ambitious targets for carbon neutrality, driving massive
            investments in clean energy infrastructure. The transition to renewable energy is creating millions
            of jobs while reducing greenhouse gas emissions and air pollution.
            """
        },
        {
            "id": "news_003",
            "title": "Space Technology Advances Enable Mars Exploration", 
            "content": """
            Recent advances in space technology are making Mars exploration more feasible than ever before. Reusable
            rockets have dramatically reduced launch costs, making frequent missions to Mars economically viable.
            Advanced life support systems are being developed to sustain human crews during the months-long journey
            to Mars. Robotic missions continue to provide valuable data about the Martian environment, helping
            scientists understand the planet's geology, atmosphere, and potential for supporting life. In-situ
            resource utilization technologies are being developed to produce fuel, water, and oxygen from Martian
            materials. Private space companies are collaborating with government agencies to develop the technologies
            needed for human Mars missions. The dream of establishing a human presence on Mars is becoming reality.
            """
        },
        {
            "id": "news_004",
            "title": "Quantum Computing Breakthrough Promises Computational Revolution",
            "content": """
            A major breakthrough in quantum computing has brought us closer to achieving quantum supremacy in practical
            applications. Scientists have successfully demonstrated error-corrected quantum computation, a critical
            milestone for building large-scale quantum computers. These quantum systems promise to solve complex
            problems that are intractable for classical computers, including drug discovery, financial modeling,
            and cryptography. Quantum algorithms are being developed for optimization problems, machine learning,
            and simulation of quantum systems. The technology could revolutionize fields ranging from materials
            science to artificial intelligence. Major technology companies and research institutions are investing
            billions in quantum computing research, racing to build the first practical quantum computers.
            """
        }
    ]
    
    print(f"📚 Processing {len(sample_documents)} news documents...")
    print(f"🔧 Configuration:")
    print(f"   • Chunk size: {indexer.chunk_size} words")
    print(f"   • Chunk overlap: {indexer.chunk_overlap} words")
    print(f"   • Batch size: {indexer.batch_size}")
    print(f"   • Embedding model: {indexer.embedding_model}")
    print(f"   • Index type: {indexer.index_type}")
    
    # Run indexing with MLflow tracking
    start_time = datetime.now()
    results = await indexer.index_documents(
        sample_documents,
        experiment_name="rag_indexing_demo",
        run_name=f"news_indexing_{start_time.strftime('%Y%m%d_%H%M%S')}"
    )
    
    # Display results
    print(f"\n✅ Document indexing completed!")
    print(f"📊 Results:")
    print(f"   • Documents processed: {len(sample_documents)}")
    print(f"   • Chunks created: {results['chunks_created']}")
    print(f"   • Embeddings generated: {results['embeddings_generated']}")
    print(f"   • Total processing time: {results['total_time']:.2f}s")
    print(f"   • Chunks per document: {results['chunks_created'] / len(sample_documents):.1f}")
    
    metrics = results['metrics']
    print(f"\n📈 Performance metrics:")
    print(f"   • Documents processed: {metrics['docs_processed']}")
    print(f"   • Chunks written: {metrics['chunks_written']}")
    print(f"   • Embeddings per second: {metrics['embeddings_per_second']:.1f}")
    print(f"   • Index build time: {metrics['index_build_time']:.2f}s")
    print(f"   • Failures: {metrics['failures']}")
    
    print(f"\n📋 MLflow tracking logged:")
    print(f"   • Parameters: provider, model, dim, batch_size, chunk_size, overlap")
    print(f"   • Metrics: docs_processed, chunks_written, embeddings/sec, failures")
    print(f"   • Artifacts: chunks_sample.jsonl, index_latency_histogram.json, indexing_config.json")
    
    return results


async def demo_mlflow_integration():
    """Demo the complete MLflow integration."""
    print("\n" + "="*80)
    print("🔬 DEMO: Complete MLflow Integration")
    print("="*80)
    
    print("🎯 This demo showcases Issue #217 implementation:")
    print("   ✅ jobs/rag/indexer.py wrapped with mlrun")
    print("   ✅ services/embeddings/provider.py logs model/dim/batch")
    print("   ✅ Parameters logged: provider, model, dim, batch_size, chunk_size, overlap")
    print("   ✅ Metrics logged: docs_processed, chunks_written, embeddings/sec, failures")
    print("   ✅ Artifacts logged: chunks.jsonl sample, latency histogram JSON")
    
    print(f"\n🚀 Starting MLflow tracking demonstration...")
    
    # Demo 1: Embeddings Provider
    embeddings, embedding_metrics = await demo_embeddings_provider()
    
    # Demo 2: RAG Indexer
    indexing_results = await demo_rag_indexer()
    
    print(f"\n🎉 Demo completed successfully!")
    print(f"💡 To view MLflow tracking results:")
    print(f"   1. Start MLflow server: 'make mlflow-server' or 'mlflow ui'")
    print(f"   2. Open browser to: http://localhost:5000")
    print(f"   3. Check experiments: 'embeddings_demo' and 'rag_indexing_demo'")
    print(f"   4. View logged parameters, metrics, and artifacts")
    
    return {
        "embeddings_metrics": embedding_metrics,
        "indexing_results": indexing_results,
    }


async def main():
    """Main demo function."""
    print("🚀 MLflow Embeddings & Indexer Demo - Issue #217")
    print("="*80)
    
    try:
        # Run complete demo
        demo_results = await demo_mlflow_integration()
        
        print(f"\n✅ All demos completed successfully!")
        print(f"📊 Summary:")
        print(f"   • Embeddings generated: {demo_results['embeddings_metrics']['embeddings_generated']}")
        print(f"   • Documents indexed: {demo_results['indexing_results']['chunks_created']} chunks")
        print(f"   • MLflow experiments created with full tracking")
        
        return demo_results
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        print(f"❌ Demo failed: {e}")
        return None


if __name__ == "__main__":
    # Run demo
    asyncio.run(main())
