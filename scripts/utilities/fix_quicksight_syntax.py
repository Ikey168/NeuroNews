#!/usr/bin/env python3
"""Fix syntax errors in quicksight_service.py"""

import re

def fix_quicksight_syntax():
    """Fix all syntax errors in quicksight_service.py"""
    
    file_path = "/workspaces/NeuroNews/src/dashboards/quicksight_service.py"
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Fix malformed f-strings
    fixes = [
        # Fix multiline f-strings that are broken
        (r'f"Failed to create dataset \{\s+dataset_config\[\'id\'\]\}: \{e\}"', 
         r'f"Failed to create dataset {dataset_config[\'id\']}: {e}"'),
        
        (r'f"Failed to create analysis \{\s+analysis_id\}: \{e\}"', 
         r'f"Failed to create analysis {analysis_id}: {e}"'),
        
        (r'"SheetId": f"\{\s+sheet_id\}"', 
         r'"SheetId": f"{sheet_id}"'),
        
        (r'f"Validation completed: \{\s+component_results\}"', 
         r'f"Validation completed: {component_results}"'),
        
        (r'f"Overall validation: \{\s+results\}"', 
         r'f"Overall validation: {results}"'),
         
        # Fix broken multiline strings in f-strings
        (r'f"([^"]*)\{\s+([^}]+)\s*\}\s*([^"]*)"([^}]*)"', r'f"\1{\2}\3"'),
    ]
    
    for pattern, replacement in fixes:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
    
    # Remove orphaned closing braces/quotes
    content = re.sub(r'\s*\}""$', '}}"', content, flags=re.MULTILINE)
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("Fixed syntax errors in quicksight_service.py")

if __name__ == "__main__":
    fix_quicksight_syntax()
