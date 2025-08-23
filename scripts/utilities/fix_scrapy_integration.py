#!/usr/bin/env python3
"""Fix all malformed f-strings in scrapy_integration.py"""

import re

def fix_scrapy_integration():
    """Fix all malformed f-strings."""
    
    file_path = "/workspaces/NeuroNews/src/ingestion/scrapy_integration.py"
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Fix the specific malformed f-string pattern
    content = re.sub(
        r'f"Optimized pipeline stats: \{stats\[\'metrics\'\]\[\'summary\'\]\}([^"]*\n[^"]*)',
        r'f"Optimized pipeline stats: {stats[\'metrics\'][\'summary\']}"',
        content,
        flags=re.MULTILINE
    )
    
    # Fix any stray quotes
    content = content.replace('# Save performance report"', '# Save performance report')
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("Fixed scrapy_integration.py f-strings")

if __name__ == "__main__":
    fix_scrapy_integration()
