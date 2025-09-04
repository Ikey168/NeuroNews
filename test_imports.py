#!/usr/bin/env pytho#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from api.graph.visualization import GraphVisualizer
    print("✓ GraphVisualizer imported successfully")
    
    # Check what methods are available
    visualizer = GraphVisualizer()
    print("✓ GraphVisualizer instance created")
    
    methods = [method for method in dir(visualizer) if not method.startswith('_')]
    print(f"Available methods: {methods}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

try:
    from api.graph.export import GraphExporter
    print("✓ GraphExporter imported successfully")
    
    exporter = GraphExporter()
    print("✓ GraphExporter instance created")
    
except Exception as e:
    print(f"✗ Export Error: {e}")

try:
    from api.graph.metrics import GraphMetricsCalculator
    print("✓ GraphMetricsCalculator imported successfully")
    
    calculator = GraphMetricsCalculator()
    print("✓ GraphMetricsCalculator instance created")
    
except Exception as e:
    print(f"✗ Metrics Error: {e}")3
import sys
import os
import traceback

# Add the project root to Python path
sys.path.insert(0, '/workspaces/NeuroNews')

print("Testing imports for Issue #235 evaluation framework...")
print("=" * 60)

try:
    print("1. Testing embeddings provider import...")
    from services.embeddings.provider import EmbeddingProvider
    print("✅ EmbeddingProvider import successful")
except Exception as e:
    print(f"❌ EmbeddingProvider import failed: {e}")
    traceback.print_exc()

try:
    print("\\n2. Testing RAG answer service import...")
    from services.rag.answer import RAGAnswerService
    print("✅ RAGAnswerService import successful")
except Exception as e:
    print(f"❌ RAGAnswerService import failed: {e}")
    traceback.print_exc()

try:
    print("\\n3. Testing MLflow tracking import...")
    from services.mlops.tracking import mlrun
    print("✅ MLflow tracking import successful")
except Exception as e:
    print(f"❌ MLflow tracking import failed: {e}")
    traceback.print_exc()

try:
    print("\\n4. Testing API routes import...")
    from services.api.routes.ask import AskRequest, ask_question, get_rag_service
    print("✅ API routes import successful")
except Exception as e:
    print(f"❌ API routes import failed: {e}")
    traceback.print_exc()

print("\\n" + "=" * 60)
print("Import testing complete!")
