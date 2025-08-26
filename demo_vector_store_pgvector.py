#!/usr/bin/env python3
"""
Demo script for NeuroNews Vector Store with pgvector
Demonstrates the complete workflow for issue #227
"""

import os
import psycopg2
import numpy as np
import time
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import json


class VectorStoreDemo:
    def __init__(self):
        self.conn_params = {
            'host': 'localhost',
            'port': 5433,
            'database': 'neuronews_vector',
            'user': 'neuronews',
            'password': 'neuronews_vector_pass'
        }
        self.conn = None
        
    def connect(self):
        """Connect to the vector database."""
        try:
            self.conn = psycopg2.connect(**self.conn_params)
            print("✅ Connected to vector database")
            return True
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            return False
    
    def test_pgvector_extension(self):
        """Test that pgvector extension is properly installed."""
        print("🧪 Testing pgvector extension...")
        
        with self.conn.cursor() as cur:
            # Check extension
            cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
            result = cur.fetchone()
            
            if result:
                print(f"✅ pgvector extension installed: {result[0]} v{result[1]}")
            else:
                print("❌ pgvector extension not found")
                return False
            
            # Test vector operations
            cur.execute("SELECT '[1,2,3]'::vector(3) <-> '[4,5,6]'::vector(3) as distance;")
            distance = cur.fetchone()[0]
            print(f"✅ Vector operations working: L2 distance = {distance:.4f}")
            
            # Test cosine similarity
            cur.execute("SELECT 1 - ('[1,2,3]'::vector(3) <=> '[4,5,6]'::vector(3)) as cosine_sim;")
            cosine_sim = cur.fetchone()[0]
            print(f"✅ Cosine similarity working: {cosine_sim:.4f}")
            
        return True
    
    def verify_schema(self):
        """Verify that all tables and indexes exist."""
        print("🔍 Verifying database schema...")
        
        expected_tables = ['documents', 'chunks', 'embeddings', 'inverted_terms', 'search_logs']
        
        with self.conn.cursor() as cur:
            # Check tables
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """)
            tables = [row[0] for row in cur.fetchall()]
            
            print(f"📊 Found tables: {', '.join(tables)}")
            
            missing_tables = set(expected_tables) - set(tables)
            if missing_tables:
                print(f"❌ Missing tables: {', '.join(missing_tables)}")
                return False
            
            # Check vector indexes
            cur.execute("""
                SELECT indexname, tablename 
                FROM pg_indexes 
                WHERE indexname LIKE '%vector%'
                ORDER BY indexname;
            """)
            vector_indexes = cur.fetchall()
            
            if vector_indexes:
                print("✅ Vector indexes found:")
                for idx_name, table_name in vector_indexes:
                    print(f"   - {idx_name} on {table_name}")
            else:
                print("⚠️  No vector indexes found")
            
            # Check functions
            cur.execute("""
                SELECT proname, pronargs 
                FROM pg_proc 
                WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'vector_ops')
                ORDER BY proname;
            """)
            functions = cur.fetchall()
            
            if functions:
                print("✅ Vector functions found:")
                for func_name, arg_count in functions:
                    print(f"   - {func_name}({arg_count} args)")
            
        print("✅ Schema verification complete")
        return True
    
    def create_sample_data(self):
        """Create sample documents, chunks, and embeddings."""
        print("📝 Creating sample data...")
        
        # Sample articles data
        sample_articles = [
            {
                'article_id': 'article_1',
                'url': 'https://example.com/ai-breakthrough',
                'title': 'AI Breakthrough in Natural Language Processing',
                'content': 'Researchers at leading tech companies have achieved a significant breakthrough in natural language processing. The new model demonstrates unprecedented accuracy in understanding context and generating human-like responses. This advancement could revolutionize how we interact with AI systems.',
                'source': 'TechNews',
                'category': 'technology'
            },
            {
                'article_id': 'article_2',
                'url': 'https://example.com/climate-change',
                'title': 'Climate Change Impact on Global Agriculture',
                'content': 'A new study reveals the severe impact of climate change on global food production. Rising temperatures and changing precipitation patterns are affecting crop yields worldwide. Scientists warn that immediate action is needed to adapt agricultural practices.',
                'source': 'ScienceDaily',
                'category': 'environment'
            },
            {
                'article_id': 'article_3',
                'url': 'https://example.com/quantum-computing',
                'title': 'Quantum Computing Reaches New Milestone',
                'content': 'Scientists have achieved quantum supremacy in a new experiment, demonstrating the potential of quantum computers to solve complex problems. This milestone brings us closer to practical applications in cryptography, drug discovery, and optimization.',
                'source': 'QuantumTimes',
                'category': 'technology'
            }
        ]
        
        # Simple embedding simulation (normally you'd use a real model)
        def simulate_embedding(text: str, dim: int = 384) -> List[float]:
            """Simulate text embedding using hash-based approach."""
            import hashlib
            
            # Use hash to generate deterministic but pseudo-random embeddings
            hash_obj = hashlib.md5(text.encode())
            seed = int(hash_obj.hexdigest()[:8], 16)
            np.random.seed(seed)
            
            # Generate random vector and normalize
            embedding = np.random.normal(0, 1, dim)
            embedding = embedding / np.linalg.norm(embedding)
            
            return embedding.tolist()
        
        with self.conn.cursor() as cur:
            for article in sample_articles:
                # Insert document
                cur.execute("""
                    INSERT INTO documents (article_id, url, title, content, source, category, published_at, word_count)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                    RETURNING id
                """, (
                    article['article_id'],
                    article['url'],
                    article['title'],
                    article['content'],
                    article['source'],
                    article['category'],
                    len(article['content'].split())
                ))
                
                doc_id = cur.fetchone()[0]
                
                # Create chunks (split content into sentences)
                sentences = article['content'].split('. ')
                
                for i, sentence in enumerate(sentences):
                    if sentence.strip():
                        # Ensure sentence ends with period
                        chunk_content = sentence.strip()
                        if not chunk_content.endswith('.'):
                            chunk_content += '.'
                        
                        # Insert chunk
                        cur.execute("""
                            INSERT INTO chunks (document_id, chunk_index, content, word_count, char_count, chunk_type)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (
                            doc_id,
                            i,
                            chunk_content,
                            len(chunk_content.split()),
                            len(chunk_content),
                            'sentence'
                        ))
                        
                        chunk_id = cur.fetchone()[0]
                        
                        # Generate embedding
                        embedding = simulate_embedding(chunk_content)
                        
                        # Insert embedding
                        cur.execute("""
                            INSERT INTO embeddings (chunk_id, embedding, model_name, embedding_dimension)
                            VALUES (%s, %s, %s, %s)
                        """, (
                            chunk_id,
                            embedding,
                            'demo-hash-embedding',
                            384
                        ))
            
            self.conn.commit()
            
        print("✅ Sample data created successfully")
        return True
    
    def test_similarity_search(self):
        """Test vector similarity search functionality."""
        print("🔍 Testing similarity search...")
        
        # Generate query embedding
        query_text = "artificial intelligence and machine learning"
        query_embedding = self.simulate_embedding(query_text)
        
        with self.conn.cursor() as cur:
            # Test similarity search using cosine distance
            cur.execute("""
                SELECT 
                    d.title,
                    c.content,
                    (1 - (e.embedding <=> %s::vector(384))) as similarity_score
                FROM embeddings e
                JOIN chunks c ON e.chunk_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE (1 - (e.embedding <=> %s::vector(384))) > 0.1
                ORDER BY similarity_score DESC
                LIMIT 5
            """, (query_embedding, query_embedding))
            
            results = cur.fetchall()
            
            print(f"🎯 Query: '{query_text}'")
            print(f"📊 Found {len(results)} similar chunks:")
            
            for i, (title, content, similarity) in enumerate(results, 1):
                print(f"   {i}. {title}")
                print(f"      Similarity: {similarity:.4f}")
                print(f"      Content: {content[:100]}...")
                print()
            
            # Test using helper function
            print("🧪 Testing helper function search_similar_documents...")
            cur.execute("""
                SELECT * FROM search_similar_documents(%s::vector(384), 0.1, 3)
            """, (query_embedding,))
            
            function_results = cur.fetchall()
            print(f"📊 Helper function returned {len(function_results)} results")
            
        return True
    
    def test_performance(self):
        """Test query performance and index usage."""
        print("⚡ Testing query performance...")
        
        query_embedding = self.simulate_embedding("performance test query")
        
        with self.conn.cursor() as cur:
            # Test with EXPLAIN ANALYZE
            cur.execute("""
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT 
                    d.title,
                    (1 - (e.embedding <=> %s::vector(384))) as similarity
                FROM embeddings e
                JOIN chunks c ON e.chunk_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE (1 - (e.embedding <=> %s::vector(384))) > 0.3
                ORDER BY similarity DESC
                LIMIT 10
            """, (query_embedding, query_embedding))
            
            explain_result = cur.fetchone()[0]
            execution_time = explain_result[0]['Execution Time']
            
            print(f"✅ Query executed in {execution_time:.2f}ms")
            
            # Check if index is being used
            plan_str = json.dumps(explain_result[0], indent=2)
            if 'Index Scan' in plan_str:
                print("✅ Vector index is being used")
            else:
                print("⚠️  Vector index may not be used (check data size)")
            
        return True
    
    def demonstrate_analytics(self):
        """Demonstrate analytics and monitoring capabilities."""
        print("📈 Demonstrating analytics capabilities...")
        
        with self.conn.cursor() as cur:
            # Insert sample search logs
            sample_queries = [
                "artificial intelligence breakthrough",
                "climate change agriculture",
                "quantum computing applications"
            ]
            
            for query in sample_queries:
                query_embedding = self.simulate_embedding(query)
                cur.execute("""
                    INSERT INTO search_logs (query_text, query_embedding, query_type, results_count, processing_time_ms)
                    VALUES (%s, %s, %s, %s, %s)
                """, (query, query_embedding, 'semantic', 5, np.random.randint(10, 100)))
            
            self.conn.commit()
            
            # Query analytics
            cur.execute("SELECT * FROM search_analytics ORDER BY search_date DESC LIMIT 5;")
            analytics = cur.fetchall()
            
            if analytics:
                print("📊 Search Analytics:")
                for row in analytics:
                    print(f"   Date: {row[0]}, Type: {row[1]}, Searches: {row[2]}, Avg Time: {row[3]:.1f}ms")
            
            # Document statistics
            cur.execute("SELECT COUNT(*) as total_docs FROM documents;")
            doc_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) as total_chunks FROM chunks;")
            chunk_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) as total_embeddings FROM embeddings;")
            embedding_count = cur.fetchone()[0]
            
            print(f"📚 Database Statistics:")
            print(f"   Documents: {doc_count}")
            print(f"   Chunks: {chunk_count}")
            print(f"   Embeddings: {embedding_count}")
            
        return True
    
    def simulate_embedding(self, text: str, dim: int = 384) -> List[float]:
        """Simulate text embedding using hash-based approach."""
        import hashlib
        
        hash_obj = hashlib.md5(text.encode())
        seed = int(hash_obj.hexdigest()[:8], 16)
        np.random.seed(seed)
        
        embedding = np.random.normal(0, 1, dim)
        embedding = embedding / np.linalg.norm(embedding)
        
        return embedding.tolist()
    
    def cleanup(self):
        """Clean up database connection."""
        if self.conn:
            self.conn.close()
            print("🔌 Database connection closed")


def run_command(cmd: str, cwd: str = None) -> bool:
    """Run a shell command."""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        if result.returncode == 0:
            return True
        else:
            print(f"❌ Command failed: {cmd}")
            print(f"Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Exception running command: {e}")
        return False


def main():
    """Main demo workflow."""
    print("🎯 NeuroNews Vector Store Demo (pgvector)")
    print("=" * 60)
    
    demo = VectorStoreDemo()
    
    try:
        # Test database connection
        print("1. 🔌 Testing database connection...")
        if not demo.connect():
            print("❌ Cannot connect to database. Make sure 'make rag-up' and 'make rag-migrate' have been run.")
            return 1
        
        # Test pgvector extension
        print("\n2. 🧪 Testing pgvector extension...")
        if not demo.test_pgvector_extension():
            return 1
        
        # Verify schema
        print("\n3. 🔍 Verifying database schema...")
        if not demo.verify_schema():
            return 1
        
        # Create sample data
        print("\n4. 📝 Creating sample data...")
        if not demo.create_sample_data():
            return 1
        
        # Test similarity search
        print("\n5. 🔍 Testing similarity search...")
        if not demo.test_similarity_search():
            return 1
        
        # Test performance
        print("\n6. ⚡ Testing query performance...")
        if not demo.test_performance():
            return 1
        
        # Demonstrate analytics
        print("\n7. 📈 Demonstrating analytics...")
        if not demo.demonstrate_analytics():
            return 1
        
        # Summary
        print("\n" + "=" * 60)
        print("🎉 Demo completed successfully!")
        print()
        print("✅ Key Features Demonstrated:")
        print("   - pgvector extension properly installed and working")
        print("   - Vector similarity search with cosine distance")
        print("   - Database schema with documents, chunks, embeddings")
        print("   - Performance-optimized vector indexes (IVFFlat)")
        print("   - Helper functions for common operations")
        print("   - Search analytics and monitoring")
        print()
        print("🚀 Next Steps:")
        print("   1. Connect your embedding model (sentence-transformers, OpenAI, etc.)")
        print("   2. Implement document ingestion pipeline")
        print("   3. Build RAG question-answering system")
        print("   4. Set up monitoring and alerting")
        print()
        print("🔗 Access Points:")
        print("   - Database: postgresql://neuronews:neuronews_vector_pass@localhost:5433/neuronews_vector")
        print("   - pgAdmin: http://localhost:5050 (admin@neuronews.com/admin)")
        print("   - Documentation: docs/rag/quickstart.md")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        return 1
    finally:
        demo.cleanup()


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
