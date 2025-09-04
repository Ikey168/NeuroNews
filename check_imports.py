#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

print("Testing Graph API module imports...")

try:
    from api.graph.visualization import GraphVisualizer
    print("✓ GraphVisualizer imported successfully")
    
    visualizer = GraphVisualizer()
    print("✓ GraphVisualizer instance created")
    
    methods = [method for method in dir(visualizer) if not method.startswith('_')]
    print(f"Available methods: {methods}")
    
except Exception as e:
    print(f"✗ Visualization Error: {e}")

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
    print(f"✗ Metrics Error: {e}")

print("Import testing complete!")
