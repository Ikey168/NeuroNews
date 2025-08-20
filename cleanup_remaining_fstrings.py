#!/usr/bin/env python3
"""
Script to clean up remaining f-strings that the initial script missed.
"""
import os
import re


def fix_complex_fstrings(content):
    """Fix complex multi-line f-strings that the initial script missed."""
    
    # Fix multiline f-strings that span multiple lines
    patterns = [
        # Pattern: f"text { \n expr \n }"
        (r'f"([^"]*)\{\s*\n\s*([^}]+)\n\s*\}([^"]*)"', r'"{0}{{{1}}}{2}".format(\2)'),
        # Pattern: f"text {expr} more text { \n expr2 \n }"  
        (r'f"([^"]*\{[^}]+\}[^"]*)\{\s*\n\s*([^}]+)\n\s*\}([^"]*)"', r'"{0}{{{1}}}{2}".format(\2)'),
        # Simple remaining f-strings
        (r'f"([^"]*)"', r'"{0}"'),
        (r"f'([^']*)'", r"'{0}'"),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
    
    return content


def process_file(file_path):
    """Process a single file to remove f-strings."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Manual fixes for specific patterns found
        manual_fixes = [
            # Fix error logging patterns
            (r'f"Error processing article \{\s*\n\s*([^}]+)\n\s*\}"', r'"Error processing article {0}".format(\1)'),
            (r'f"Failed to process article \{\s*\n\s*([^}]+)\n\s*\}"', r'"Failed to process article {0}".format(\1)'),
            (r'f"API request to populate article: \{\s*\n\s*([^}]+)\n\s*\}"', r'"API request to populate article: {0}".format(\1)'),
            (r'f"Invalid published_date format: \{\s*\n\s*([^}]+)\n\s*\}"', r'"Invalid published_date format: {0}".format(\1)'),
            (r'f"Successfully populated article \{([^}]+)\}"', r'"Successfully populated article {0}".format(\1)'),
            (r'f"Error populating article \{\s*\n\s*([^}]+)\n\s*\}"', r'"Error populating article {0}".format(\1)'),
            # Fix complex format strings
            (r'f"([^"]*)\{\s*\n\s*([^}]+)\n\s*\}([^"]*)"', r'"{0}{1}{2}".format(\2)'),
            # Simple f-strings
            (r'f"([^{}"]*)"', r'"\1"'),
            (r"f'([^{}']*)'", r"'\1'"),
        ]
        
        for pattern, replacement in manual_fixes:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
        
        # Write back if changed
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated: {file_path}")
            return True
            
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False
    
    return False


def main():
    """Process all Python files in src directory."""
    updated_count = 0
    
    for root, dirs, files in os.walk('src'):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                if process_file(file_path):
                    updated_count += 1
    
    print(f"Updated {updated_count} files")


if __name__ == '__main__':
    main()
