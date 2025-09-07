#!/usr/bin/env python3
"""
Modular Test Suite Runner
Runs all modular test files organized by functional components
"""

import pytest
import os
import sys
from pathlib import Path

def main():
    """Run all modular tests"""
    
    # Get the current directory
    current_dir = Path(__file__).parent
    modules_dir = current_dir / "tests" / "modules"
    
    # Ensure modules directory exists
    if not modules_dir.exists():
        print(f"Modules directory not found: {modules_dir}")
        return 1
    
    # Test files to run in order
    test_files = [
        "test_infrastructure_module.py",  # Core infrastructure first
        "test_database_module.py",        # Database layer
        "test_api_module.py",             # API layer
        "test_nlp_module.py",             # NLP processing
        "test_scraper_module.py",         # Data collection
        "test_knowledge_graph_module.py", # Knowledge representation
        "test_ingestion_module.py",       # Data ingestion
        "test_services_module.py",        # Business services
    ]
    
    # Build full paths
    test_paths = [str(modules_dir / test_file) for test_file in test_files]
    
    # Check that all files exist
    missing_files = [path for path in test_paths if not Path(path).exists()]
    if missing_files:
        print("Missing test files:")
        for file in missing_files:
            print(f"  - {file}")
        return 1
    
    print("Running modular test suite...")
    print(f"Test modules directory: {modules_dir}")
    print(f"Running {len(test_files)} test modules")
    
    # Run pytest without coverage for now
    pytest_args = [
        *test_paths,
        "-v", 
        "--tb=short"
    ]
    
    return pytest.main(pytest_args)

if __name__ == "__main__":
    sys.exit(main())
