#!/usr/bin/env python3
"""Quick coverage estimation for the NeuroNews project."""

import os
import subprocess
import sys
from pathlib import Path

def count_python_files(directory):
    """Count Python files and estimate lines of code."""
    py_files = 0
    total_lines = 0
    
    for root, dirs, files in os.walk(directory):
        # Skip test directories, __pycache__, etc.
        dirs[:] = [d for d in dirs if not d.startswith(('.', '__pycache__'))]
        
        for file in files:
            if file.endswith('.py') and not file.startswith('test_'):
                py_files += 1
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        lines = len([line for line in f if line.strip() and not line.strip().startswith('#')])
                        total_lines += lines
                except:
                    pass
    
    return py_files, total_lines

def estimate_test_coverage():
    """Estimate test coverage by running limited tests."""
    
    # Count source code
    print("=== NeuroNews Project Coverage Estimate ===\n")
    
    src_files, src_lines = count_python_files('src')
    print(f"Source Code Stats:")
    print(f"  - Python files: {src_files}")
    print(f"  - Estimated executable lines: {src_lines}")
    
    test_files, test_lines = count_python_files('tests')
    print(f"\nTest Code Stats:")
    print(f"  - Test files: {test_files}")
    print(f"  - Test lines: {test_lines}")
    
    # Estimate test-to-code ratio
    test_ratio = test_lines / src_lines if src_lines > 0 else 0
    print(f"  - Test-to-code ratio: {test_ratio:.2f}")
    
    # Run focused coverage on key modules
    print("\n=== Graph API Coverage (Our Focus) ===")
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            'tests/api/graph/test_operations_simple.py',
            'tests/api/graph/test_queries.py', 
            'tests/api/graph/test_traversal.py',
            'tests/api/graph/test_metrics.py',
            '--cov=src/api/graph',
            '--cov-report=term-missing',
            '--tb=no', '-v'
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("Graph API Coverage Results:")
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if 'src/api/graph' in line or 'TOTAL' in line or '%' in line:
                    print(f"  {line}")
        else:
            print("Graph API tests failed to run completely")
            
    except subprocess.TimeoutExpired:
        print("Graph API coverage test timed out")
    except Exception as e:
        print(f"Error running Graph API coverage: {e}")
    
    # Overall project estimate
    print("\n=== Overall Project Estimate ===")
    
    # Check different modules
    modules = ['src/api', 'src/nlp', 'src/database', 'src/scraper']
    total_estimated_coverage = 0
    module_count = 0
    
    for module in modules:
        if os.path.exists(module):
            files, lines = count_python_files(module)
            module_coverage = estimate_module_coverage(module)
            total_estimated_coverage += module_coverage
            module_count += 1
            print(f"  {module}: ~{files} files, ~{lines} lines, estimated {module_coverage:.1f}% coverage")
    
    overall_coverage = total_estimated_coverage / module_count if module_count > 0 else 0
    print(f"\nEstimated Overall Project Coverage: {overall_coverage:.1f}%")
    
    return overall_coverage

def estimate_module_coverage(module_path):
    """Estimate coverage for a module based on test file presence."""
    module_name = os.path.basename(module_path)
    test_path = f"tests/{module_name}"
    
    if not os.path.exists(test_path):
        return 10.0  # Low coverage if no test directory
    
    # Count test files vs source files
    test_files, _ = count_python_files(test_path)
    src_files, _ = count_python_files(module_path)
    
    if src_files == 0:
        return 0.0
    
    test_ratio = test_files / src_files
    
    # Rough estimation based on test file ratio
    if test_ratio >= 1.0:
        return 75.0  # High coverage
    elif test_ratio >= 0.5:
        return 50.0  # Medium coverage  
    elif test_ratio >= 0.25:
        return 30.0  # Low-medium coverage
    else:
        return 15.0  # Low coverage

if __name__ == "__main__":
    estimate_test_coverage()
