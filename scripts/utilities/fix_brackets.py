#!/usr/bin/env python3
"""Comprehensive bracket fixing for quicksight_service.py"""

import re

def fix_all_brackets():
    """Fix all bracket mismatches in the file."""
    
    file_path = "/workspaces/NeuroNews/src/dashboards/quicksight_service.py"
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Fix specific patterns that were causing issues
    fixes = [
        # Fix Actions list closing
        (r'"Actions": \[(.*?)\],\s*\}', r'"Actions": [\1],\n                    }', re.DOTALL),
        
        # Fix bracket mismatches in dictionary access
        (r'\["([^"]+)"\}', r'["\1"]'),
        
        # Fix mixed bracket types in data structures
        (r'\]\s*,\s*\}\s*$', r'},', re.MULTILINE),
        (r'\}\s*,\s*\]\s*$', r'},', re.MULTILINE),
        
        # Fix specific structure issues
        (r'(\s+"Actions": \[.*?)"quicksight:UpdateDataSourcePermissions",\s*\},', 
         r'\1"quicksight:UpdateDataSourcePermissions",\n                        ],', re.DOTALL),
    ]
    
    for pattern, replacement, *flags in fixes:
        flag = flags[0] if flags else 0
        content = re.sub(pattern, replacement, content, flags=flag)
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("Fixed bracket mismatches")

if __name__ == "__main__":
    fix_all_brackets()
