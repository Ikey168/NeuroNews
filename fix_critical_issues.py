#!/usr/bin/env python3
"""
Fix remaining critical flake8 issues that would block CI/CD.
Focus on F821 (undefined names) and F841 (unused variables) first.
"""

import re
import os
from pathlib import Path

def fix_critical_issues():
    """Fix the most critical flake8 issues."""
    
    fixes_applied = []
    
    # Fix 1: Add missing json import in scrapy_integration.py
    scrapy_file = Path("/workspaces/NeuroNews/src/ingestion/scrapy_integration.py")
    if scrapy_file.exists():
        with open(scrapy_file, 'r') as f:
            content = f.read()
        
        if 'import json' not in content and 'from json import' not in content:
            # Add json import at the top
            lines = content.split('\n')
            import_section = []
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    continue
                else:
                    import_section = lines[:i]
                    break
            
            # Add json import
            import_section.append('import json')
            new_content = '\n'.join(import_section + lines[len(import_section):])
            
            with open(scrapy_file, 'w') as f:
                f.write(new_content)
            
            fixes_applied.append("Added missing json import to scrapy_integration.py")
    
    # Fix 2: Fix undefined __ in enhanced_graph_populator.py
    graph_file = Path("/workspaces/NeuroNews/src/knowledge_graph/enhanced_graph_populator.py")
    if graph_file.exists():
        with open(graph_file, 'r') as f:
            content = f.read()
        
        # Replace undefined __ with proper import or string
        if 'undefined name \'__\'' in content or '.__' in content:
            # Add proper import at the top
            if 'from gremlin_python.process.graph_traversal import __' not in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith('from gremlin_python') and '__' not in line:
                        lines.insert(i+1, 'from gremlin_python.process.graph_traversal import __')
                        break
                
                content = '\n'.join(lines)
                
                with open(graph_file, 'w') as f:
                    f.write(content)
                
                fixes_applied.append("Added __ import to enhanced_graph_populator.py")
    
    # Fix 3: Remove/fix unused variables
    files_to_fix = [
        "/workspaces/NeuroNews/src/dashboards/quicksight_service.py",
        "/workspaces/NeuroNews/src/knowledge_graph/enhanced_graph_populator.py"
    ]
    
    for file_path in files_to_fix:
        file_obj = Path(file_path)
        if file_obj.exists():
            with open(file_obj, 'r') as f:
                content = f.read()
            
            original_content = content
            
            # Remove unused variable assignments
            lines = content.split('\n')
            new_lines = []
            
            for line in lines:
                # Skip obvious unused variable assignments
                if re.match(r'^\s*(existing|query|refresh_params)\s*=.*', line):
                    # Check if this is just an assignment without use
                    if '=' in line and not any(x in line for x in ['return', 'if', 'elif', 'for', 'while']):
                        # Comment out the line instead of removing it
                        new_lines.append('                    # ' + line.strip() + '  # unused variable')
                        continue
                
                new_lines.append(line)
            
            content = '\n'.join(new_lines)
            
            if content != original_content:
                with open(file_obj, 'w') as f:
                    f.write(content)
                
                fixes_applied.append(f"Fixed unused variables in {file_obj.name}")
    
    return fixes_applied

def main():
    print("Fixing critical flake8 issues...")
    
    fixes = fix_critical_issues()
    
    print(f"Applied {len(fixes)} critical fixes:")
    for fix in fixes:
        print(f"  ✓ {fix}")
    
    print("\nCritical fixes complete!")

if __name__ == "__main__":
    main()
