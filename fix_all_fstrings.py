#!/usr/bin/env python3
"""Fix all malformed f-strings in scrapy_integration.py"""

def fix_all_fstrings():
    """Fix all malformed f-strings in the file."""
    
    file_path = "/workspaces/NeuroNews/src/ingestion/scrapy_integration.py"
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Fix any line that has the malformed pattern
    for i, line in enumerate(lines):
        if "f\"Optimized pipeline stats: {stats['metrics']['summary']}" in line and not line.strip().endswith('}"'):
            # This line is missing the closing quote
            lines[i] = line.replace(
                "f\"Optimized pipeline stats: {stats['metrics']['summary']}",
                "f\"Optimized pipeline stats: {stats['metrics']['summary']}\""
            )
            print(f"Fixed line {i+1}: {line.strip()} -> {lines[i].strip()}")
    
    with open(file_path, 'w') as f:
        f.writelines(lines)
    
    print("Fixed all malformed f-strings in scrapy_integration.py")

if __name__ == "__main__":
    fix_all_fstrings()
