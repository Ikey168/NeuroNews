#!/usr/bin/env python3
"""Fix malformed message strings in sns_alert_manager.py"""

import re

def fix_sns_messages():
    """Fix all malformed message strings."""
    
    file_path = "/workspaces/NeuroNews/src/scraper/sns_alert_manager.py"
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Fix multiline string concatenation in message format calls
    pattern = r'message="([^"]*)"[\s\n]+([^"]*)"\.format\("[\s\n]*'
    replacement = r'message="\1 \2".format('
    
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("Fixed message string concatenation")

if __name__ == "__main__":
    fix_sns_messages()
